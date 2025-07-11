# Django Gyro CSV Import Management Command - Technical Design

## Executive Summary

This document outlines the design for a new Django management command that efficiently loads exported CSV data into a PostgreSQL database. The solution addresses challenges including bulk data loading performance, circular relationships, dependency ordering, and primary key remapping.

## Domain Model Evolution

### Current State Analysis

The current `ImportJob` class conflates two concerns:
1. **Export concern**: Dependency analysis and ordering for data extraction
2. **Import concern**: Not yet implemented, but would handle data loading

### Proposed Domain Model Changes

#### 1. Rename and Split Responsibilities

```python
# Current: ImportJob (confusing name)
# Proposed: Split into two concepts

class ExportPlan:
    """Represents a plan for exporting data with dependency analysis"""
    model: Type[Model]
    queryset: Optional[QuerySet]
    
    def get_dependencies() -> Set[Type[Model]]
    def get_all_dependencies() -> Set[Type[Model]]

class ImportContext:
    """Manages the stateful context of an import operation"""
    source_directory: Path
    id_mapping: Dict[str, Dict[int, int]]  # model_name -> {old_id: new_id}
    batch_size: int = 10000
    use_copy: bool = True  # PostgreSQL COPY for performance
    
class ImportPlan:
    """Represents a plan for importing data with remapping capabilities"""
    model: Type[Model]
    csv_path: Path
    dependencies: List['ImportPlan']
    id_remapping_strategy: Optional[IdRemappingStrategy]
```

#### 2. Introduce Batch Concept

```python
class ImportBatch:
    """Represents a batch of import operations that should be executed together"""
    id: UUID
    created_at: datetime
    source_system: str  # e.g., "production_export_2024_01_15"
    plans: List[ImportPlan]
    context: ImportContext
    status: ImportStatus  # PENDING, IN_PROGRESS, COMPLETED, FAILED
    
    def execute(self) -> ImportResult
```

## Technical Challenges and Solutions

### 1. High-Performance Bulk Loading

**Challenge**: Django ORM's `bulk_create` is slow for large datasets.

**Solution**: Use PostgreSQL's COPY command with these optimizations:

```python
class PostgresBulkLoader:
    def load_csv_with_copy(self, model: Type[Model], csv_path: Path, 
                          id_mapping: Optional[Dict[int, int]] = None):
        """
        1. Create temporary staging table
        2. COPY data into staging table
        3. Apply ID remapping if needed
        4. INSERT from staging to final table with conflict handling
        """
        with connection.cursor() as cursor:
            # Create staging table
            staging_table = f"import_staging_{model._meta.db_table}"
            cursor.execute(f"""
                CREATE TEMP TABLE {staging_table} 
                (LIKE {model._meta.db_table} INCLUDING ALL)
            """)
            
            # Use COPY for ultra-fast loading
            with open(csv_path, 'r') as f:
                cursor.copy_expert(f"""
                    COPY {staging_table} FROM STDIN WITH CSV HEADER
                """, f)
            
            # Apply remapping and insert
            if id_mapping:
                # Update foreign keys in staging table
                for fk_field in model._meta.get_fields():
                    if isinstance(fk_field, models.ForeignKey):
                        related_model = fk_field.related_model
                        mapping = id_mapping.get(related_model._meta.label)
                        if mapping:
                            # Use CASE statement for efficient bulk update
                            self._apply_fk_remapping(cursor, staging_table, 
                                                   fk_field, mapping)
```

### 2. Circular Relationship Handling

**Challenge**: Models may have circular foreign key dependencies.

**Solution**: Multi-pass loading strategy:

```python
class CircularDependencyResolver:
    def resolve_import_order(self, models: List[Type[Model]]) -> List[List[Type[Model]]]:
        """
        Returns models grouped by import phase:
        Phase 1: Models with no dependencies or only self-references
        Phase 2: Models with dependencies only on Phase 1
        Phase 3: Circular dependencies (loaded with deferred FK constraints)
        """
        # Use existing FKDependencyValidator logic
        validator = FKDependencyValidator(models)
        
        # Identify circular dependencies
        circular_groups = validator.find_circular_dependencies()
        
        # For circular dependencies, use PostgreSQL's DEFERRABLE constraints
        return [
            non_circular_models,  # Load first
            circular_groups,      # Load with deferred constraints
        ]

class DeferredConstraintLoader:
    def load_with_deferred_constraints(self, models: List[Type[Model]], 
                                      import_context: ImportContext):
        """Load models with circular dependencies using deferred constraints"""
        with connection.cursor() as cursor:
            cursor.execute("SET CONSTRAINTS ALL DEFERRED")
            try:
                for model in models:
                    self._load_model_data(model, import_context)
                # Constraints checked here at commit
            except IntegrityError as e:
                # Handle missing FK references
                raise ImportError(f"Circular dependency resolution failed: {e}")
```

### 3. Sequential ID Remapping

**Challenge**: Auto-increment IDs may conflict between source and target databases.

**Solution**: Pandas-based remapping with efficient strategies:

```python
class IdRemappingStrategy(ABC):
    @abstractmethod
    def generate_mapping(self, source_ids: pd.Series, 
                        target_db: DatabaseWrapper) -> Dict[int, int]:
        pass

class SequentialRemappingStrategy(IdRemappingStrategy):
    """Assigns new sequential IDs starting from MAX(existing_id) + 1"""
    def generate_mapping(self, source_ids: pd.Series, 
                        target_db: DatabaseWrapper) -> Dict[int, int]:
        model = self.model
        with target_db.cursor() as cursor:
            cursor.execute(f"""
                SELECT COALESCE(MAX(id), 0) FROM {model._meta.db_table}
            """)
            max_id = cursor.fetchone()[0]
        
        # Create mapping: old_id -> new_id
        new_ids = range(max_id + 1, max_id + len(source_ids) + 1)
        return dict(zip(source_ids, new_ids))

class HashBasedRemappingStrategy(IdRemappingStrategy):
    """Uses deterministic hashing for stable ID generation across imports"""
    def generate_mapping(self, source_ids: pd.Series, 
                        unique_key: str) -> Dict[int, int]:
        # Generate stable IDs based on unique business key
        # Useful for idempotent imports
        pass

class PandasRemapper:
    """Efficient pandas-based data remapping before import"""
    def remap_csv(self, csv_path: Path, id_mappings: Dict[str, Dict[int, int]], 
                  model: Type[Model]) -> Path:
        # Read CSV in chunks for memory efficiency
        chunk_size = 50000
        output_path = csv_path.with_suffix('.remapped.csv')
        
        with pd.read_csv(csv_path, chunksize=chunk_size) as reader:
            for i, chunk in enumerate(reader):
                # Remap primary key
                if 'id' in chunk.columns and model._meta.label in id_mappings:
                    chunk['id'] = chunk['id'].map(
                        id_mappings[model._meta.label]
                    ).fillna(chunk['id'])
                
                # Remap foreign keys
                for fk_field in model._meta.get_fields():
                    if isinstance(fk_field, models.ForeignKey):
                        fk_column = f"{fk_field.name}_id"
                        if fk_column in chunk.columns:
                            related_mapping = id_mappings.get(
                                fk_field.related_model._meta.label
                            )
                            if related_mapping:
                                chunk[fk_column] = chunk[fk_column].map(
                                    related_mapping
                                ).fillna(chunk[fk_column])
                
                # Write remapped chunk
                chunk.to_csv(output_path, mode='a', 
                           header=(i == 0), index=False)
        
        return output_path
```

### 4. Management Command Design

```python
class Command(BaseCommand):
    """
    Usage:
    ./manage.py import_csv /path/to/export/dir --batch-name "prod_2024_01" 
                          --remap-strategy sequential --use-copy
    """
    
    def add_arguments(self, parser):
        parser.add_argument('source_directory', type=Path)
        parser.add_argument('--batch-name', required=True)
        parser.add_argument('--remap-strategy', 
                          choices=['sequential', 'hash', 'none'], 
                          default='sequential')
        parser.add_argument('--use-copy', action='store_true', default=True,
                          help='Use PostgreSQL COPY (fast) instead of ORM')
        parser.add_argument('--batch-size', type=int, default=10000)
        parser.add_argument('--dry-run', action='store_true')
    
    def handle(self, *args, **options):
        # 1. Discovery phase
        csv_files = self._discover_csv_files(options['source_directory'])
        models = self._map_csv_to_models(csv_files)
        
        # 2. Planning phase
        import_batch = ImportBatch(
            id=uuid4(),
            source_system=options['batch_name'],
            context=ImportContext(
                source_directory=options['source_directory'],
                batch_size=options['batch_size'],
                use_copy=options['use_copy']
            )
        )
        
        # 3. Dependency resolution
        resolver = CircularDependencyResolver()
        import_phases = resolver.resolve_import_order(models)
        
        # 4. ID remapping planning
        if options['remap_strategy'] != 'none':
            remapping_plan = self._plan_remapping(
                models, options['remap_strategy']
            )
        
        # 5. Execution
        if options['dry_run']:
            self._print_execution_plan(import_phases, remapping_plan)
        else:
            with transaction.atomic():
                # Disable FK checks for circular deps
                with connection.cursor() as cursor:
                    cursor.execute("SET session_replication_role = 'replica';")
                try:
                    self._execute_import(import_batch, import_phases, 
                                       remapping_plan)
                finally:
                    with connection.cursor() as cursor:
                        cursor.execute("SET session_replication_role = 'origin';")
```

## Alternative Approaches Considered

### 1. Graph Database for Dependency Management
- **Pros**: Natural fit for circular dependencies
- **Cons**: Additional infrastructure complexity

### 2. Django Fixtures
- **Pros**: Built-in Django feature
- **Cons**: Poor performance for large datasets, limited customization

### 3. Event Sourcing Pattern
- **Pros**: Complete audit trail, replay capability
- **Cons**: Significant architectural change

## Implementation Phases

### Phase 1: Basic Import with ORM (MVP)
1. Management command skeleton
2. Simple CSV reading with pandas
3. Model discovery from CSV files
4. Basic bulk_create implementation
5. Simple sequential ID remapping

### Phase 2: Performance Optimization
1. PostgreSQL COPY implementation
2. Chunked processing for large files
3. Parallel loading for independent models
4. Progress tracking and resumability

### Phase 3: Advanced Features
1. Circular dependency resolution
2. Multiple remapping strategies
3. Validation and error recovery
4. Import history tracking
5. Rollback capability

## Testing Strategy (TDD Approach)

### Core Principle: Object-Oriented Test Organization

Following Gary Bernhardt's approach, tests are organized around objects and their behaviors, not features. Each core object gets its own test module with focused unit tests.

### Test Coverage Requirements

- **Target**: Maintain >95% test coverage across all new code
- **Measurement**: Use `coverage.py` with branch coverage enabled
- **Focus Areas**:
  - Every public method on every object must have tests
  - Edge cases and error conditions must be tested
  - Integration points between objects must be tested
  - Performance-critical paths must have benchmarks

### Test Philosophy (Channeling the Masters)

- **Kent Beck**: "Test everything that could possibly break"
- **Martin Fowler**: "Whenever you are tempted to type something into a print statement or a debugger expression, write it as a test instead"
- **Gary Bernhardt**: "Test behavior, not implementation"
- **Joshua Kerievsky**: "Tests are the first users of your code"

### Test Structure

```
tests/
├── test_export_plan.py          # ExportPlan object tests
├── test_import_plan.py          # ImportPlan object tests
├── test_import_batch.py         # ImportBatch object tests
├── test_import_context.py       # ImportContext object tests
├── test_id_remapping.py         # IdRemappingStrategy tests
├── test_postgres_bulk_loader.py # PostgresBulkLoader tests
├── test_pandas_remapper.py      # PandasRemapper tests
├── test_circular_resolver.py    # CircularDependencyResolver tests
└── test_import_command_e2e.py   # End-to-end integration test
```

### Unit Test Examples (Following Four-Phase Test Pattern)

```python
# test_export_plan.py
class TestExportPlan:
    """Tests for ExportPlan object behavior."""
    
    def test_identifies_direct_dependencies(self):
        # Setup
        tenant_plan = ExportPlan(model=Tenant)
        shop_plan = ExportPlan(model=Shop)  # Shop has FK to Tenant
        
        # Exercise
        dependencies = shop_plan.get_dependencies()
        
        # Verify
        assert Tenant in dependencies
        assert len(dependencies) == 1
        
        # Teardown (handled by test framework)
    
    def test_caches_dependency_computation(self):
        # Setup
        plan = ExportPlan(model=Order)
        
        # Exercise
        deps1 = plan.get_dependencies()
        deps2 = plan.get_dependencies()
        
        # Verify
        assert deps1 is deps2  # Same object reference
    
    def test_handles_self_referential_models(self):
        # Setup
        class Category(models.Model):
            parent = models.ForeignKey('self', null=True)
        
        plan = ExportPlan(model=Category)
        
        # Exercise & Verify
        assert plan.has_self_reference() is True

# test_id_remapping.py
class TestSequentialRemappingStrategy:
    """Tests for SequentialRemappingStrategy behavior."""
    
    def test_generates_sequential_ids_from_max_plus_one(self):
        # Setup
        strategy = SequentialRemappingStrategy(model=Tenant)
        source_ids = pd.Series([100, 200, 300])
        mock_db = Mock()
        mock_db.cursor().fetchone.return_value = (5,)  # MAX(id) = 5
        
        # Exercise
        mapping = strategy.generate_mapping(source_ids, mock_db)
        
        # Verify
        assert mapping == {100: 6, 200: 7, 300: 8}
    
    def test_handles_empty_target_table(self):
        # Setup
        strategy = SequentialRemappingStrategy(model=Tenant)
        source_ids = pd.Series([100])
        mock_db = Mock()
        mock_db.cursor().fetchone.return_value = (0,)  # No existing records
        
        # Exercise
        mapping = strategy.generate_mapping(source_ids, mock_db)
        
        # Verify
        assert mapping == {100: 1}

# test_postgres_bulk_loader.py
class TestPostgresBulkLoader:
    """Tests for PostgresBulkLoader behavior."""
    
    def test_creates_staging_table_with_same_structure(self):
        # Setup
        loader = PostgresBulkLoader()
        mock_cursor = Mock()
        
        # Exercise
        loader._create_staging_table(mock_cursor, Tenant)
        
        # Verify
        mock_cursor.execute.assert_called_with(
            "CREATE TEMP TABLE import_staging_gyro_example_tenant "
            "(LIKE gyro_example_tenant INCLUDING ALL)"
        )
    
    def test_applies_foreign_key_remapping_efficiently(self):
        # Setup
        loader = PostgresBulkLoader()
        mock_cursor = Mock()
        mapping = {1: 10, 2: 20, 3: 30}
        
        # Exercise
        loader._apply_fk_remapping(
            mock_cursor, 
            "staging_table",
            field_name="tenant_id",
            mapping=mapping
        )
        
        # Verify
        # Should use CASE statement for bulk update
        call_args = mock_cursor.execute.call_args[0][0]
        assert "UPDATE staging_table SET tenant_id = CASE" in call_args
        assert "WHEN tenant_id = 1 THEN 10" in call_args

# test_circular_resolver.py  
class TestCircularDependencyResolver:
    """Tests for CircularDependencyResolver behavior."""
    
    def test_identifies_simple_circular_dependency(self):
        # Setup
        class ModelA(models.Model):
            b = models.ForeignKey('ModelB')
        
        class ModelB(models.Model):
            a = models.ForeignKey('ModelA')
        
        resolver = CircularDependencyResolver()
        
        # Exercise
        phases = resolver.resolve_import_order([ModelA, ModelB])
        
        # Verify
        assert len(phases) == 2
        assert phases[0] == []  # No non-circular models
        assert set(phases[1]) == {ModelA, ModelB}
    
    def test_separates_circular_from_non_circular(self):
        # Setup
        resolver = CircularDependencyResolver()
        
        # Exercise
        phases = resolver.resolve_import_order([
            Tenant,      # No dependencies
            Shop,        # Depends on Tenant
            Customer,    # Depends on Tenant, Shop
            CircularA,   # Circular with CircularB
            CircularB    # Circular with CircularA
        ])
        
        # Verify
        assert Tenant in phases[0]
        assert Shop in phases[0] 
        assert CircularA in phases[1]
        assert CircularB in phases[1]
```

### End-to-End Integration Test with Multi-Database Setup

```python
# test_import_command_e2e.py
class TestCSVImportEndToEnd(TransactionTestCase):
    """
    End-to-end test that exports from one database and imports to another.
    Uses Django's multi-database support for isolation.
    """
    
    databases = {'default', 'import_target'}
    
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Add second database to settings dynamically
        from django.conf import settings
        settings.DATABASES['import_target'] = {
            **settings.DATABASES['default'],
            'NAME': 'test_import_target',
        }
    
    def test_export_from_source_import_to_target(self):
        # Setup - Create data in source database
        source_tenant = Tenant.objects.create(
            id=1000, 
            name="Source Tenant",
            subdomain="source"
        )
        source_shop = Shop.objects.create(
            id=2000,
            tenant=source_tenant,
            name="Source Shop"
        )
        
        with tempfile.TemporaryDirectory() as export_dir:
            # Exercise - Export from source
            export_result = DataSlicer.run(
                source=DataSlicer.Postgres(self._get_db_url('default')),
                target=DataSlicer.File(export_dir),
                jobs=[
                    ImportJob(model=Tenant),
                    ImportJob(model=Shop)
                ]
            )
            
            # Exercise - Import to target with remapping
            import_context = ImportContext(
                source_directory=export_dir,
                target_database='import_target',
                id_remapping_strategy=SequentialRemappingStrategy()
            )
            
            importer = BulkCSVImporter(context=import_context)
            import_result = importer.execute()
            
            # Verify - Check data in target database
            target_tenants = Tenant.objects.using('import_target').all()
            assert target_tenants.count() == 1
            
            target_tenant = target_tenants.first()
            assert target_tenant.name == "Source Tenant"
            assert target_tenant.id != 1000  # ID was remapped
            
            target_shops = Shop.objects.using('import_target').all()
            assert target_shops.count() == 1
            
            target_shop = target_shops.first()
            assert target_shop.tenant_id == target_tenant.id  # FK remapped
            assert target_shop.id != 2000  # ID was remapped
    
    def test_handles_circular_dependencies_with_deferred_constraints(self):
        # Setup - Create circular dependency data
        class Author(models.Model):
            favorite_book = models.ForeignKey('Book', null=True)
        
        class Book(models.Model):
            author = models.ForeignKey(Author)
        
        # Create data with circular reference
        with transaction.atomic():
            author = Author.objects.create(id=1)
            book = Book.objects.create(id=1, author=author)
            author.favorite_book = book
            author.save()
        
        with tempfile.TemporaryDirectory() as export_dir:
            # Export
            DataSlicer.run(
                source=DataSlicer.Postgres(self._get_db_url('default')),
                target=DataSlicer.File(export_dir),
                jobs=[ImportJob(model=Author), ImportJob(model=Book)]
            )
            
            # Import with circular dependency handling
            import_context = ImportContext(
                source_directory=export_dir,
                target_database='import_target',
                handle_circular=True
            )
            
            importer = BulkCSVImporter(context=import_context)
            result = importer.execute()
            
            # Verify both imported successfully
            assert Author.objects.using('import_target').count() == 1
            assert Book.objects.using('import_target').count() == 1
            
            # Verify circular reference maintained
            imported_author = Author.objects.using('import_target').first()
            imported_book = Book.objects.using('import_target').first()
            assert imported_author.favorite_book == imported_book
            assert imported_book.author == imported_author
    
    def test_performance_with_large_dataset(self):
        # Setup - Generate large dataset
        self._generate_test_data(tenant_count=10, customers_per_tenant=10000)
        
        with tempfile.TemporaryDirectory() as export_dir:
            # Export
            start_time = time.time()
            DataSlicer.run(
                source=DataSlicer.Postgres(self._get_db_url('default')),
                target=DataSlicer.File(export_dir),
                jobs=[ImportJob(model=Tenant), ImportJob(model=Customer)]
            )
            export_time = time.time() - start_time
            
            # Import with COPY
            import_context = ImportContext(
                source_directory=export_dir,
                target_database='import_target',
                use_copy=True,
                batch_size=50000
            )
            
            start_time = time.time()
            importer = BulkCSVImporter(context=import_context)
            importer.execute()
            import_time = time.time() - start_time
            
            # Verify performance
            assert import_time < 30  # Should complete in < 30 seconds
            
            # Verify data integrity
            assert Customer.objects.using('import_target').count() == 100000
```

### Test Helpers and Fixtures

```python
# tests/fixtures.py
class DatabaseFixture:
    """Manages test database setup and teardown."""
    
    @staticmethod
    def create_import_target_db():
        """Creates a separate database for import testing."""
        from django.db import connection
        with connection.cursor() as cursor:
            cursor.execute("CREATE DATABASE test_import_target")
    
    @staticmethod
    def cleanup_import_target_db():
        """Removes test import database."""
        from django.db import connection
        with connection.cursor() as cursor:
            cursor.execute("DROP DATABASE IF EXISTS test_import_target")

# tests/factories.py
class TenantFactory:
    """Factory for creating test Tenant instances."""
    
    @staticmethod
    def create_batch(count, **kwargs):
        return [
            Tenant(
                name=f"Tenant {i}",
                subdomain=f"tenant{i}",
                **kwargs
            )
            for i in range(count)
        ]
```

### Test Execution Script Enhancement

```python
# src/example/gyro_example/management/commands/test_import_export.py
class Command(BaseCommand):
    """
    Enhanced end-to-end test that exports from one DB and imports to another.
    
    Usage:
        python manage.py test_import_export --source-db default --target-db import_test
    """
    
    def add_arguments(self, parser):
        parser.add_argument('--source-db', default='default')
        parser.add_argument('--target-db', default='import_test')
        parser.add_argument('--use-copy', action='store_true', default=True)
        parser.add_argument('--verify', action='store_true', default=True)
    
    def handle(self, *args, **options):
        # Step 1: Export from source database
        export_dir = self._export_data(options['source_db'])
        
        # Step 2: Import to target database with remapping
        import_result = self._import_data(
            export_dir, 
            options['target_db'],
            use_copy=options['use_copy']
        )
        
        # Step 3: Verify data integrity if requested
        if options['verify']:
            self._verify_import(options['source_db'], options['target_db'])
    
    def _import_data(self, source_dir, target_db, use_copy=True):
        """Directly call the import logic without management command."""
        context = ImportContext(
            source_directory=source_dir,
            target_database=target_db,
            id_remapping_strategy=SequentialRemappingStrategy(),
            use_copy=use_copy
        )
        
        importer = BulkCSVImporter(context=context)
        return importer.execute()
    
    def _verify_import(self, source_db, target_db):
        """Verify data was imported correctly using .using() syntax."""
        # Count comparisons
        for model in [Tenant, Shop, Customer, Product, Order, OrderItem]:
            source_count = model.objects.using(source_db).count()
            target_count = model.objects.using(target_db).count()
            assert source_count == target_count, f"{model} count mismatch"
        
        # Verify FK relationships maintained
        source_shop = Shop.objects.using(source_db).first()
        target_shop = Shop.objects.using(target_db).filter(
            name=source_shop.name
        ).first()
        
        assert target_shop.tenant.name == source_shop.tenant.name
```

## Performance Benchmarks

Target performance for 1M rows:
- ORM bulk_create: ~300 seconds
- PostgreSQL COPY: ~10 seconds
- With ID remapping: ~15 seconds

## Security Considerations

1. **SQL Injection**: Use parameterized queries only
2. **File Access**: Validate source directory access
3. **Memory**: Stream large files, don't load entirely
4. **Permissions**: Require specific Django permission for import

## Next Steps

1. **Immediate**: Create proof-of-concept for COPY-based loading
2. **Week 1**: Implement basic management command with ORM
3. **Week 2**: Add PostgreSQL COPY optimization
4. **Week 3**: Implement ID remapping with pandas
5. **Week 4**: Handle circular dependencies
6. **Week 5**: Testing, documentation, and error handling

## Development Workflow (TDD Approach)

### Red-Green-Refactor Cycle

For each new object or feature:

1. **Red**: Write failing tests first
   - Start with the simplest test case
   - Add edge cases and error conditions
   - Run tests to ensure they fail properly

2. **Green**: Write minimal code to pass
   - Implement just enough to make tests pass
   - Don't worry about elegance yet
   - Commit when tests pass

3. **Refactor**: Improve the design
   - Extract methods/classes as needed
   - Remove duplication
   - Ensure tests still pass

### Continuous Testing During Development

```bash
# Run tests continuously with pytest-watch
pytest-watch --runner "pytest -xvs"

# Run with coverage
pytest --cov=django_gyro --cov-branch --cov-report=html

# Run specific test module as you work on an object
pytest tests/test_import_plan.py -xvs

# Run integration tests separately (slower)
pytest tests/test_import_command_e2e.py -xvs --database=all
```

### Test-First Implementation Order

1. Start with value objects (ImportContext, ImportPlan)
2. Move to strategies (IdRemappingStrategy)
3. Implement services (PostgresBulkLoader, PandasRemapper)
4. Build coordinators (CircularDependencyResolver)
5. Finish with the command (pulls everything together)

## Open Questions

1. Should we support incremental imports (upsert)?
2. How to handle M2M relationships?
3. Should we track import lineage for auditing?
4. Do we need a UI for import management?
5. How to handle custom model validation during import?