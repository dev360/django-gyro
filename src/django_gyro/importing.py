"""
Import functionality for Django Gyro.

This module contains the classes and utilities for importing CSV data
back into Django models with support for ID remapping, bulk loading,
and circular dependency resolution.
"""

from pathlib import Path
from typing import Dict, Optional, List, Any, Set, Type
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from django.db import models


@dataclass
class ImportContext:
    """
    Manages the stateful context of an import operation.
    
    This value object holds all the configuration and state needed
    during a CSV import operation, including ID mappings, target database,
    and import progress tracking.
    """
    source_directory: Path
    batch_size: int = 10000
    use_copy: bool = True
    target_database: str = 'default'
    id_remapping_strategy: Optional['IdRemappingStrategy'] = None
    
    # Internal state - not part of equality comparison
    id_mapping: Dict[str, Dict[int, int]] = field(default_factory=dict, compare=False)
    _imported_models: set = field(default_factory=set, compare=False)
    
    def __post_init__(self):
        """Validate the context after initialization."""
        if not isinstance(self.source_directory, Path):
            self.source_directory = Path(self.source_directory)
        
        if not self.source_directory.exists():
            raise ValueError(f"Source directory does not exist: {self.source_directory}")
    
    def add_id_mapping(self, model_label: str, old_id: int, new_id: int) -> None:
        """Add an ID mapping for a model."""
        if model_label not in self.id_mapping:
            self.id_mapping[model_label] = {}
        self.id_mapping[model_label][old_id] = new_id
    
    def get_id_mapping(self, model_label: str, old_id: int) -> Optional[int]:
        """Get the new ID for an old ID, or None if not mapped."""
        return self.id_mapping.get(model_label, {}).get(old_id)
    
    def mark_model_imported(self, model_label: str) -> None:
        """Mark a model as having been imported."""
        self._imported_models.add(model_label)
    
    def is_model_imported(self, model_label: str) -> bool:
        """Check if a model has been imported."""
        return model_label in self._imported_models
    
    def discover_csv_files(self) -> List[Path]:
        """Discover all CSV files in the source directory."""
        return sorted(self.source_directory.glob("*.csv"))


class IdRemappingStrategy(ABC):
    """Abstract base class for ID remapping strategies."""
    
    @abstractmethod
    def generate_mapping(self, source_ids: Any, target_db: Any) -> Dict[int, int]:
        """Generate a mapping from old IDs to new IDs."""
        pass


class SequentialRemappingStrategy(IdRemappingStrategy):
    """Assigns new sequential IDs starting from MAX(existing_id) + 1."""
    
    def __init__(self, model):
        self.model = model
    
    def generate_mapping(self, source_ids: Any, target_db: Any) -> Dict[int, int]:
        """Generate sequential ID mappings."""
        import pandas as pd
        
        # Convert to pandas Series if needed
        if not isinstance(source_ids, pd.Series):
            source_ids = pd.Series(source_ids)
        
        # Get unique source IDs to avoid duplicates
        unique_source_ids = source_ids.drop_duplicates()
        
        # Query database for current MAX(id)
        with target_db.cursor() as cursor:
            cursor.execute(f"SELECT COALESCE(MAX(id), 0) FROM {self.model._meta.db_table}")
            max_id = cursor.fetchone()[0]
        
        # Generate sequential mappings
        mapping = {}
        next_id = max_id + 1
        
        for source_id in unique_source_ids:
            mapping[source_id] = next_id
            next_id += 1
        
        return mapping


class HashBasedRemappingStrategy(IdRemappingStrategy):
    """Uses deterministic hashing for stable ID generation across imports."""
    
    def __init__(self, model, business_key: str):
        self.model = model
        self.business_key = business_key
    
    def generate_mapping(self, source_data: Any) -> Dict[int, int]:
        """Generate hash-based ID mappings using business key."""
        import pandas as pd
        import hashlib
        
        # Ensure we have a DataFrame
        if not isinstance(source_data, pd.DataFrame):
            raise ValueError("HashBasedRemappingStrategy requires DataFrame input")
        
        # Check if business key exists
        if self.business_key not in source_data.columns:
            raise ValueError(f"Business key '{self.business_key}' not found in data")
        
        mapping = {}
        
        for _, row in source_data.iterrows():
            source_id = row['id']
            business_value = row[self.business_key]
            
            # Skip empty business values
            if pd.isna(business_value) or business_value == '':
                continue
            
            # Generate deterministic hash-based ID
            hash_input = f"{self.model._meta.label}_{business_value}"
            hash_object = hashlib.md5(hash_input.encode())
            # Use first 8 bytes of hash as integer (avoid collision in most cases)
            hash_id = int(hash_object.hexdigest()[:8], 16)
            
            # Ensure positive ID
            if hash_id <= 0:
                hash_id = abs(hash_id) + 1
            
            mapping[source_id] = hash_id
        
        return mapping


class NoRemappingStrategy(IdRemappingStrategy):
    """Identity strategy that doesn't remap IDs (leaves them unchanged)."""
    
    def __init__(self, model):
        self.model = model
    
    def generate_mapping(self, source_ids: Any, target_db: Any = None) -> Dict[int, int]:
        """Generate identity mapping (no change)."""
        import pandas as pd
        
        # Convert to pandas Series if needed
        if not isinstance(source_ids, pd.Series):
            source_ids = pd.Series(source_ids)
        
        # Create identity mapping
        return {source_id: source_id for source_id in source_ids}


class PostgresBulkLoader:
    """
    Service for high-performance bulk loading of CSV data into PostgreSQL.
    
    Uses PostgreSQL's COPY command with staging tables for optimal performance
    and supports ID remapping during the load process.
    """
    
    def __init__(self):
        self.batch_size = 10000
    
    def load_csv_with_copy(self, model: Type[models.Model], csv_path: Path, 
                          connection: Any, id_mappings: Optional[Dict[str, Dict[int, int]]] = None,
                          on_conflict: str = 'raise', cleanup_staging: bool = True) -> Dict[str, Any]:
        """
        Load CSV data using PostgreSQL COPY for high performance.
        
        Args:
            model: Django model to load data into
            csv_path: Path to CSV file
            connection: Database connection
            id_mappings: Optional ID remapping dictionary
            on_conflict: How to handle conflicts ('raise', 'ignore', 'update')
            cleanup_staging: Whether to clean up staging table after load
            
        Returns:
            Dictionary with load statistics
        """
        if not csv_path.exists():
            raise FileNotFoundError(f"CSV file not found: {csv_path}")
        
        staging_table = f"import_staging_{model._meta.db_table}"
        
        with connection.cursor() as cursor:
            try:
                # Step 1: Create staging table
                self._create_staging_table(cursor, model)
                
                # Step 2: Copy CSV data to staging table
                self._copy_csv_to_staging(cursor, csv_path, model)
                
                # Step 3: Apply ID remapping if provided
                if id_mappings:
                    self._apply_id_remappings(cursor, model, staging_table, id_mappings)
                
                # Step 4: Insert from staging to target table
                rows_loaded = self._insert_from_staging(cursor, model, on_conflict)
                
                # Step 5: Clean up staging table if requested
                if cleanup_staging:
                    self._cleanup_staging_table(cursor, staging_table)
                
                return {
                    'rows_loaded': rows_loaded,
                    'staging_table': staging_table,
                    'used_copy': True
                }
            
            except Exception as e:
                # Clean up staging table on error
                try:
                    self._cleanup_staging_table(cursor, staging_table)
                except:
                    pass  # Ignore cleanup errors
                raise e
    
    def load_csv_with_insert(self, model: Type[models.Model], csv_path: Path,
                            connection: Any, batch_size: int = 1000,
                            id_mappings: Optional[Dict[str, Dict[int, int]]] = None) -> Dict[str, Any]:
        """
        Load CSV data using batched INSERT statements (fallback when COPY not available).
        
        Args:
            model: Django model to load data into
            csv_path: Path to CSV file
            connection: Database connection
            batch_size: Number of rows to insert per batch
            id_mappings: Optional ID remapping dictionary
            
        Returns:
            Dictionary with load statistics
        """
        import pandas as pd
        
        if not csv_path.exists():
            raise FileNotFoundError(f"CSV file not found: {csv_path}")
        
        # Read CSV in chunks for memory efficiency
        total_rows = 0
        
        with connection.cursor() as cursor:
            for chunk in pd.read_csv(csv_path, chunksize=batch_size):
                # Apply ID remapping if provided
                if id_mappings:
                    chunk = self._apply_pandas_remapping(chunk, model, id_mappings)
                
                # Generate INSERT statements
                rows_inserted = self._insert_dataframe_batch(cursor, chunk, model)
                total_rows += rows_inserted
        
        return {
            'rows_loaded': total_rows,
            'used_copy': False
        }
    
    def load_csv_batch(self, model: Type[models.Model], csv_paths: List[Path],
                      connection: Any, **kwargs) -> List[Dict[str, Any]]:
        """Load multiple CSV files in batch."""
        results = []
        
        for csv_path in csv_paths:
            result = self.load_csv_with_copy(model, csv_path, connection, **kwargs)
            results.append(result)
        
        return results
    
    def load_csv_with_context(self, model: Type[models.Model], csv_path: Path,
                             context: 'ImportContext', connection: Any) -> Dict[str, Any]:
        """Load CSV using ImportContext configuration."""
        if context.use_copy:
            return self.load_csv_with_copy(
                model=model,
                csv_path=csv_path,
                connection=connection,
                id_mappings=context.id_mapping
            )
        else:
            return self.load_csv_with_insert(
                model=model,
                csv_path=csv_path,
                connection=connection,
                batch_size=context.batch_size,
                id_mappings=context.id_mapping
            )
    
    def _create_staging_table(self, cursor: Any, model: Type[models.Model]) -> None:
        """Create temporary staging table with same structure as target table."""
        staging_table = f"import_staging_{model._meta.db_table}"
        
        sql = f"CREATE TEMP TABLE {staging_table} (LIKE {model._meta.db_table} INCLUDING ALL)"
        
        cursor.execute(sql)
    
    def _copy_csv_to_staging(self, cursor: Any, csv_path: Path, model: Type[models.Model]) -> None:
        """Copy CSV data to staging table using PostgreSQL COPY command."""
        staging_table = f"import_staging_{model._meta.db_table}"
        
        copy_sql = f"COPY {staging_table} FROM STDIN WITH CSV HEADER"
        
        with open(csv_path, 'r') as f:
            cursor.copy_expert(copy_sql, f)
    
    def _apply_id_remappings(self, cursor: Any, model: Type[models.Model], 
                           staging_table: str, id_mappings: Dict[str, Dict[int, int]]) -> None:
        """Apply ID remappings to staging table."""
        # Remap primary key if needed
        model_label = f"{model._meta.app_label}.{model.__name__}"
        if model_label in id_mappings:
            self._apply_fk_remapping(cursor, staging_table, "id", id_mappings[model_label])
        
        # Remap foreign keys
        for field in model._meta.get_fields():
            if isinstance(field, models.ForeignKey):
                related_model = field.related_model
                related_label = f"{related_model._meta.app_label}.{related_model.__name__}"
                
                if related_label in id_mappings:
                    fk_column = f"{field.name}_id"
                    self._apply_fk_remapping(cursor, staging_table, fk_column, id_mappings[related_label])
    
    def _apply_fk_remapping(self, cursor: Any, staging_table: str, 
                          column_name: str, mapping: Dict[int, int]) -> None:
        """Apply foreign key remapping using efficient CASE statement."""
        if not mapping:
            return
        
        # Build CASE statement for efficient bulk update
        case_clauses = []
        for old_id, new_id in mapping.items():
            case_clauses.append(f"WHEN {column_name} = {old_id} THEN {new_id}")
        
        old_ids = ', '.join(str(old_id) for old_id in mapping.keys())
        
        sql = f"UPDATE {staging_table} SET {column_name} = CASE {' '.join(case_clauses)} END WHERE {column_name} IN ({old_ids})"
        
        cursor.execute(sql)
    
    def _insert_from_staging(self, cursor: Any, model: Type[models.Model], 
                           on_conflict: str = 'raise') -> int:
        """Insert data from staging table to target table."""
        staging_table = f"import_staging_{model._meta.db_table}"
        target_table = model._meta.db_table
        
        # Build INSERT statement
        base_sql = f"INSERT INTO {target_table} SELECT * FROM {staging_table}"
        
        if on_conflict == 'ignore':
            sql = f"{base_sql} ON CONFLICT DO NOTHING"
        elif on_conflict == 'update':
            # This would need more sophisticated handling for specific conflicts
            sql = f"{base_sql} ON CONFLICT DO NOTHING"  # Simplified for now
        else:
            sql = base_sql
        
        cursor.execute(sql)
        return cursor.rowcount
    
    def _cleanup_staging_table(self, cursor: Any, staging_table: str) -> None:
        """Clean up staging table."""
        cursor.execute(f"DROP TABLE IF EXISTS {staging_table}")
    
    def _apply_pandas_remapping(self, df: Any, model: Type[models.Model], 
                              id_mappings: Dict[str, Dict[int, int]]) -> Any:
        """Apply ID remapping to pandas DataFrame."""
        # Remap primary key
        model_label = f"{model._meta.app_label}.{model.__name__}"
        if model_label in id_mappings and 'id' in df.columns:
            df['id'] = df['id'].map(id_mappings[model_label]).fillna(df['id'])
        
        # Remap foreign keys
        for field in model._meta.get_fields():
            if isinstance(field, models.ForeignKey):
                related_model = field.related_model
                related_label = f"{related_model._meta.app_label}.{related_model.__name__}"
                fk_column = f"{field.name}_id"
                
                if related_label in id_mappings and fk_column in df.columns:
                    df[fk_column] = df[fk_column].map(id_mappings[related_label]).fillna(df[fk_column])
        
        return df
    
    def _insert_dataframe_batch(self, cursor: Any, df: Any, model: Type[models.Model]) -> int:
        """Insert pandas DataFrame using batch INSERT statements."""
        if df.empty:
            return 0
        
        # Convert DataFrame to list of tuples
        values = []
        for _, row in df.iterrows():
            values.append(tuple(row.values))
        
        # Build INSERT statement
        columns = ', '.join(df.columns)
        placeholders = ', '.join(['%s'] * len(df.columns))
        
        sql = f"INSERT INTO {model._meta.db_table} ({columns}) VALUES ({placeholders})"
        
        # Execute batch insert
        cursor.executemany(sql, values)
        return len(values)


@dataclass
class ImportPlan:
    """
    Represents a plan for importing data from a CSV file.
    
    This value object contains all the information needed to import
    data for a specific model, including dependencies and remapping strategy.
    """
    model: Type[models.Model]
    csv_path: Path
    dependencies: List['ImportPlan'] = field(default_factory=list)
    id_remapping_strategy: Optional[IdRemappingStrategy] = None
    
    def __post_init__(self):
        """Validate the plan after initialization."""
        if not isinstance(self.csv_path, Path):
            self.csv_path = Path(self.csv_path)
        
        if not self.csv_path.exists():
            raise ValueError(f"CSV file does not exist: {self.csv_path}")
    
    @property
    def model_label(self) -> str:
        """Get the model label (app_label.ModelName)."""
        return f"{self.model._meta.app_label}.{self.model.__name__}"
    
    def discover_foreign_key_dependencies(self) -> Set[Type[models.Model]]:
        """Discover models that this model depends on via foreign keys."""
        dependencies = set()
        
        for field in self.model._meta.get_fields():
            if isinstance(field, models.ForeignKey):
                dependencies.add(field.related_model)
        
        return dependencies
    
    def calculate_import_weight(self) -> int:
        """Calculate weight for dependency ordering (higher = import later)."""
        return len(self.dependencies)
    
    def estimate_row_count(self) -> int:
        """Estimate the number of rows in the CSV file."""
        try:
            with open(self.csv_path, 'r') as f:
                # Count lines and subtract 1 for header
                line_count = sum(1 for _ in f) - 1
                return max(0, line_count)
        except Exception:
            return 0
    
    def has_dependency(self, other_plan: 'ImportPlan') -> bool:
        """Check if this plan depends on another plan."""
        return other_plan in self.dependencies
    
    def __str__(self) -> str:
        """String representation of the import plan."""
        return f"ImportPlan(model={self.model_label}, csv={self.csv_path.name})"


class ExportPlan:
    """
    Represents a data export plan for a specific Django model.
    
    ExportPlan defines what data should be exported (model + optional QuerySet)
    and provides dependency analysis to ensure proper export ordering.
    This class was formerly called ImportJob but renamed to better reflect its purpose.
    """

    # Class-level cache for dependency computations
    _dependency_cache = {}

    def __init__(self, model, query=None):
        """
        Initialize an ExportPlan.

        Args:
            model: Django model class to export
            query: Optional QuerySet to filter data (must match model)

        Raises:
            TypeError: If model is not a Django model or query is not a QuerySet
            ValueError: If query model doesn't match the specified model
        """
        # Validate model
        if not self._is_django_model(model):
            raise TypeError("model must be a Django model class")

        # Validate query
        if query is not None:
            if not self._is_django_queryset(query):
                raise TypeError("query must be a Django QuerySet or None")

            # Check that query model matches our model
            if query.model != model:
                raise ValueError("QuerySet model does not match ExportPlan model")

        # Set properties (make them private to prevent modification)
        self._model = model
        self._query = query

    @property
    def model(self):
        """Get the Django model class for this export plan."""
        return self._model

    @property
    def query(self):
        """Get the QuerySet for this export plan (or None for all records)."""
        return self._query

    def get_dependencies(self):
        """
        Get the list of Django models that this plan depends on.

        Dependencies are determined by analyzing foreign key relationships
        in the Importer's Columns configuration. The result is cached for
        performance since model relationships are static.

        Returns:
            list: List of Django model classes that must be exported first

        Raises:
            ValueError: If circular dependencies are detected
        """
        # Check cache first
        cache_key = id(self.model)
        if cache_key in self._dependency_cache:
            return self._dependency_cache[cache_key]

        # Compute dependencies
        dependencies = []
        visited = set()
        visiting = set()

        def _get_model_dependencies(model):
            """Recursively get dependencies for a model."""
            if model in visiting:
                raise ValueError(f"Circular dependency detected involving {model.__name__}")

            if model in visited:
                return []

            visiting.add(model)
            model_deps = []

            # Get the importer for this model
            from django_gyro.core import Importer
            importer_class = Importer.get_importer_for_model(model)
            if importer_class and hasattr(importer_class, "Columns"):
                # Analyze the Columns configuration
                columns_class = importer_class.Columns

                for attr_name in dir(columns_class):
                    if not attr_name.startswith("_"):
                        attr_value = getattr(columns_class, attr_name)

                        # If it's a Django model, it's a dependency
                        if self._is_django_model(attr_value):
                            if attr_value == model:
                                # Self-reference: add to dependencies but don't recurse
                                model_deps.append(attr_value)
                            else:
                                # Regular dependency: add and recurse
                                model_deps.append(attr_value)
                                nested_deps = _get_model_dependencies(attr_value)
                                model_deps.extend(nested_deps)

            visiting.remove(model)
            visited.add(model)
            return model_deps

        # Get all dependencies
        all_deps = _get_model_dependencies(self.model)

        # Remove duplicates while preserving order
        seen = set()
        for dep in all_deps:
            if dep not in seen:
                dependencies.append(dep)
                seen.add(dep)

        # Cache the result
        self._dependency_cache[cache_key] = dependencies

        return dependencies

    @classmethod
    def sort_by_dependencies(cls, plans):
        """
        Sort a list of ExportPlans by their dependency order.

        Plans with no dependencies come first, followed by plans that depend
        on them, and so on. This ensures that data is exported in the
        correct order to satisfy foreign key constraints.

        Args:
            plans: List of ExportPlan instances to sort

        Returns:
            list: Sorted list of ExportPlan instances

        Raises:
            ValueError: If circular dependencies are detected
        """
        # Build dependency graph
        dependencies = {}

        for plan in plans:
            try:
                dependencies[plan.model] = plan.get_dependencies()
            except ValueError as e:
                # Re-raise with context about which models are involved
                models_in_cycle = [p.model.__name__ for p in plans]
                raise ValueError(f"Circular dependency detected among models: {models_in_cycle}") from e

        # Topological sort
        sorted_plans = []
        remaining_plans = list(plans)

        while remaining_plans:
            # Find plans with no unsatisfied dependencies
            ready_plans = []
            for plan in remaining_plans:
                plan_deps = dependencies[plan.model]
                unsatisfied_deps = [dep for dep in plan_deps if dep in [p.model for p in remaining_plans]]

                if not unsatisfied_deps:
                    ready_plans.append(plan)

            if not ready_plans:
                # If no plans are ready, we have a circular dependency
                remaining_models = [plan.model.__name__ for plan in remaining_plans]
                raise ValueError(f"Circular dependency detected among models: {remaining_models}")

            # Add ready plans to sorted list and remove from remaining
            sorted_plans.extend(ready_plans)
            for plan in ready_plans:
                remaining_plans.remove(plan)

        return sorted_plans

    def _is_django_model(self, obj):
        """Check if an object is a Django model class."""
        try:
            return isinstance(obj, type) and issubclass(obj, models.Model) and obj != models.Model
        except ImportError:
            return False

    def _is_django_queryset(self, obj):
        """Check if an object is a Django QuerySet."""
        try:
            from django.db.models.query import QuerySet
            return isinstance(obj, QuerySet)
        except ImportError:
            return False

    def __str__(self):
        """String representation of the ExportPlan."""
        if self.query is None:
            return f"ExportPlan(model={self.model.__name__})"
        else:
            return f"ExportPlan(model={self.model.__name__}, query={self.query})"

    def __repr__(self):
        """Detailed string representation of the ExportPlan."""
        return self.__str__()
    
    def __eq__(self, other):
        """Check equality based on model and query."""
        if not isinstance(other, ExportPlan):
            return False
        return self.model == other.model and self.query == other.query
    
    def __hash__(self):
        """Hash based on model and query."""
        return hash((self.model, id(self.query)))