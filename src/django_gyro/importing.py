"""
Import functionality for Django Gyro.

This module contains the classes and utilities for importing CSV data
back into Django models with support for ID remapping, bulk loading,
and circular dependency resolution.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Type

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
    target_database: str = "default"
    id_remapping_strategy: Optional["IdRemappingStrategy"] = None

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
        # Convert to list and get unique values
        if hasattr(source_ids, "__iter__") and not isinstance(source_ids, (str, bytes)):
            # Preserve order while removing duplicates
            seen = set()
            unique_source_ids = []
            for sid in source_ids:
                if sid not in seen:
                    seen.add(sid)
                    unique_source_ids.append(sid)
        else:
            unique_source_ids = [source_ids]

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
        import hashlib

        mapping = {}

        # Ensure we have a dictionary or list of dictionaries
        if isinstance(source_data, dict):
            # Single record format
            if "id" not in source_data:
                raise ValueError("HashBasedRemappingStrategy requires 'id' field in data")
            if self.business_key not in source_data:
                raise ValueError(f"Business key '{self.business_key}' not found in data")

            source_data = [source_data]  # Convert to list for uniform processing

        elif isinstance(source_data, list):
            # List of records format
            if not source_data:
                return mapping
            if "id" not in source_data[0]:
                raise ValueError("HashBasedRemappingStrategy requires 'id' field in data")
            if self.business_key not in source_data[0]:
                raise ValueError(f"Business key '{self.business_key}' not found in data")

        else:
            raise ValueError("HashBasedRemappingStrategy requires dict or list of dicts input")

        for row in source_data:
            source_id = row["id"]
            business_value = row[self.business_key]

            # Skip empty business values
            if business_value is None or business_value == "":
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
        # Convert to iterable and create identity mapping
        if hasattr(source_ids, "__iter__") and not isinstance(source_ids, (str, bytes)):
            return {source_id: source_id for source_id in source_ids}
        else:
            return {source_ids: source_ids}


class PostgresBulkLoader:
    """
    Service for high-performance bulk loading of CSV data into PostgreSQL.

    Uses PostgreSQL's COPY command with staging tables for optimal performance
    and supports ID remapping during the load process.
    """

    def __init__(self):
        self.batch_size = 10000

    def load_csv_with_copy(
        self,
        model: Type[models.Model],
        csv_path: Path,
        connection: Any,
        id_mappings: Optional[Dict[str, Dict[int, int]]] = None,
        on_conflict: str = "raise",
        cleanup_staging: bool = True,
    ) -> Dict[str, Any]:
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

                return {"rows_loaded": rows_loaded, "staging_table": staging_table, "used_copy": True}

            except Exception as e:
                # Clean up staging table on error
                try:
                    self._cleanup_staging_table(cursor, staging_table)
                except Exception:
                    pass  # Ignore cleanup errors
                raise e

    def load_csv_with_insert(
        self,
        model: Type[models.Model],
        csv_path: Path,
        connection: Any,
        batch_size: int = 1000,
        id_mappings: Optional[Dict[str, Dict[int, int]]] = None,
    ) -> Dict[str, Any]:
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
        import csv

        if not csv_path.exists():
            raise FileNotFoundError(f"CSV file not found: {csv_path}")

        # Read CSV in chunks for memory efficiency
        total_rows = 0

        with connection.cursor() as cursor:
            with open(csv_path, newline="", encoding="utf-8") as csvfile:
                reader = csv.DictReader(csvfile)
                batch = []

                for row in reader:
                    # Apply ID remapping if provided
                    if id_mappings:
                        row = self._apply_dict_remapping(row, model, id_mappings)

                    batch.append(row)

                    # Process batch when it reaches batch_size
                    if len(batch) >= batch_size:
                        rows_inserted = self._insert_dict_batch(cursor, batch, model)
                        total_rows += rows_inserted
                        batch = []

                # Process remaining rows in final batch
                if batch:
                    rows_inserted = self._insert_dict_batch(cursor, batch, model)
                    total_rows += rows_inserted

        return {"rows_loaded": total_rows, "used_copy": False}

    def load_csv_batch(
        self, model: Type[models.Model], csv_paths: List[Path], connection: Any, **kwargs
    ) -> List[Dict[str, Any]]:
        """Load multiple CSV files in batch."""
        results = []

        for csv_path in csv_paths:
            result = self.load_csv_with_copy(model, csv_path, connection, **kwargs)
            results.append(result)

        return results

    def load_csv_with_context(
        self, model: Type[models.Model], csv_path: Path, context: "ImportContext", connection: Any
    ) -> Dict[str, Any]:
        """Load CSV using ImportContext configuration."""
        if context.use_copy:
            return self.load_csv_with_copy(
                model=model, csv_path=csv_path, connection=connection, id_mappings=context.id_mapping
            )
        else:
            return self.load_csv_with_insert(
                model=model,
                csv_path=csv_path,
                connection=connection,
                batch_size=context.batch_size,
                id_mappings=context.id_mapping,
            )

    def _create_staging_table(self, cursor: Any, model: Type[models.Model]) -> None:
        """Create temporary staging table with same structure as target table."""
        staging_table = f"import_staging_{model._meta.db_table}"

        # Use INCLUDING DEFAULTS to avoid copying incompatible spatial indexes
        sql = f'CREATE TEMP TABLE "{staging_table}" (LIKE "{model._meta.db_table}" INCLUDING DEFAULTS)'
        cursor.execute(sql)

        # Handle PostGIS geometry columns - convert to TEXT for COPY compatibility
        geometry_columns = self._get_geometry_columns(model)
        for geom_column in geometry_columns:
            alter_sql = f'ALTER TABLE "{staging_table}" ALTER COLUMN "{geom_column}" TYPE TEXT'
            cursor.execute(alter_sql)

    def _copy_csv_to_staging(self, cursor: Any, csv_path: Path, model: Type[models.Model]) -> None:
        """Copy CSV data to staging table using PostgreSQL COPY command."""
        import csv

        staging_table = f"import_staging_{model._meta.db_table}"

        # Read CSV headers to determine column mapping
        with open(csv_path, newline="", encoding="utf-8") as csvfile:
            reader = csv.reader(csvfile)
            csv_headers = next(reader)

        # Get database table column names
        db_columns = [field.column for field in model._meta.get_fields() if hasattr(field, "column")]

        # Map CSV headers to database columns (exact match for now)
        mapped_columns = []
        for header in csv_headers:
            if header in db_columns:
                mapped_columns.append(header)
            else:
                # Log warning about unmapped column but continue
                print(f"Warning: CSV column '{header}' not found in model {model.__name__}")

        if not mapped_columns:
            raise ValueError(f"No CSV columns could be mapped to database columns for model {model.__name__}")

        # Construct COPY statement with explicit column list - quote identifiers for PostgreSQL
        quoted_columns = [f'"{column}"' for column in mapped_columns]
        columns_sql = "(" + ", ".join(quoted_columns) + ")"
        copy_sql = f'COPY "{staging_table}" {columns_sql} FROM STDIN WITH CSV HEADER'

        with open(csv_path, newline="", encoding="utf-8") as f:
            cursor.copy_expert(copy_sql, f)

    def _apply_id_remappings(
        self, cursor: Any, model: Type[models.Model], staging_table: str, id_mappings: Dict[str, Dict[int, int]]
    ) -> None:
        """Apply ID remappings to staging table."""
        # Remap primary key if needed
        model_label = f"{model._meta.app_label}.{model.__name__}"
        if model_label in id_mappings:
            self._apply_fk_remapping(cursor, staging_table, "id", id_mappings[model_label])

        # Remap foreign keys
        for model_field in model._meta.get_fields():
            if isinstance(model_field, models.ForeignKey):
                related_model = model_field.related_model
                related_label = f"{related_model._meta.app_label}.{related_model.__name__}"

                if related_label in id_mappings:
                    fk_column = f"{model_field.name}_id"
                    self._apply_fk_remapping(cursor, staging_table, fk_column, id_mappings[related_label])

    def _apply_fk_remapping(self, cursor: Any, staging_table: str, column_name: str, mapping: Dict[int, int]) -> None:
        """Apply foreign key remapping using efficient CASE statement."""
        if not mapping:
            return

        # Build CASE statement for efficient bulk update
        case_clauses = []
        for old_id, new_id in mapping.items():
            case_clauses.append(f'WHEN "{column_name}" = {old_id} THEN {new_id}')

        old_ids = ", ".join(str(old_id) for old_id in mapping.keys())

        sql = f'UPDATE "{staging_table}" SET "{column_name}" = CASE {" ".join(case_clauses)} END WHERE "{column_name}" IN ({old_ids})'

        cursor.execute(sql)

    def _insert_from_staging(self, cursor: Any, model: Type[models.Model], on_conflict: str = "raise") -> int:
        """Insert data from staging table to target table."""
        staging_table = f"import_staging_{model._meta.db_table}"
        target_table = model._meta.db_table

        # Handle PostGIS geometry columns with EWKB conversion
        geometry_columns = self._get_geometry_columns(model)

        if geometry_columns:
            # Get all column names from the staging table
            cursor.execute(
                f"SELECT column_name FROM information_schema.columns WHERE table_name = '{staging_table}' ORDER BY ordinal_position"
            )
            all_columns = [row[0] for row in cursor.fetchall()]

            # Build SELECT clause with geometry conversion
            select_columns = []
            for column in all_columns:
                if column in geometry_columns:
                    # Convert EWKB hex to geometry using ST_GeomFromEWKB
                    select_columns.append(f"""
                        CASE
                            WHEN "{column}" IS NULL OR "{column}" = '' THEN NULL
                            WHEN "{column}" LIKE '\\\\x%' THEN ST_GeomFromEWKB(decode(substring("{column}" from 3), 'hex'))
                            WHEN "{column}" LIKE '\\x%' THEN ST_GeomFromEWKB("{column}"::bytea)
                            ELSE ST_GeomFromEWKB(decode("{column}", 'hex'))
                        END AS "{column}"
                    """)
                else:
                    select_columns.append(f'"{column}"')

            select_clause = ",\n".join(select_columns)
            base_sql = f'INSERT INTO "{target_table}" SELECT {select_clause} FROM "{staging_table}"'
        else:
            # Regular table without geometry columns
            base_sql = f'INSERT INTO "{target_table}" SELECT * FROM "{staging_table}"'

        if on_conflict == "ignore":
            sql = f"{base_sql} ON CONFLICT DO NOTHING"
        elif on_conflict == "update":
            # This would need more sophisticated handling for specific conflicts
            sql = f"{base_sql} ON CONFLICT DO NOTHING"  # Simplified for now
        else:
            sql = base_sql

        cursor.execute(sql)
        return cursor.rowcount

    def _cleanup_staging_table(self, cursor: Any, staging_table: str) -> None:
        """Clean up staging table."""
        cursor.execute(f'DROP TABLE IF EXISTS "{staging_table}"')

    def _apply_dict_remapping(
        self, row: Dict[str, Any], model: Type[models.Model], id_mappings: Dict[str, Dict[int, int]]
    ) -> Dict[str, Any]:
        """Apply ID remapping to a single row dictionary."""
        # Create a copy to avoid modifying the original
        remapped_row = row.copy()

        # Remap primary key
        model_label = f"{model._meta.app_label}.{model.__name__}"
        if model_label in id_mappings and "id" in remapped_row:
            old_id = int(remapped_row["id"])
            new_id = id_mappings[model_label].get(old_id, old_id)
            remapped_row["id"] = str(new_id)

        # Remap foreign keys
        for model_field in model._meta.get_fields():
            if isinstance(model_field, models.ForeignKey):
                related_model = model_field.related_model
                related_label = f"{related_model._meta.app_label}.{related_model.__name__}"
                fk_column = f"{model_field.name}_id"

                if related_label in id_mappings and fk_column in remapped_row and remapped_row[fk_column]:
                    old_fk_id = int(remapped_row[fk_column])
                    new_fk_id = id_mappings[related_label].get(old_fk_id, old_fk_id)
                    remapped_row[fk_column] = str(new_fk_id)

        return remapped_row

    def _insert_dict_batch(self, cursor: Any, batch: List[Dict[str, Any]], model: Type[models.Model]) -> int:
        """Insert a batch of dictionary rows using INSERT statements."""
        if not batch:
            return 0

        # Get field names from the first row
        field_names = list(batch[0].keys())
        table_name = model._meta.db_table

        # Build INSERT statement
        placeholders = ", ".join(["%s"] * len(field_names))
        quoted_columns = ", ".join([f'"{field}"' for field in field_names])
        sql = f'INSERT INTO "{table_name}" ({quoted_columns}) VALUES ({placeholders})'

        # Prepare data for executemany
        values = []
        for row in batch:
            row_values = [row.get(field, None) for field in field_names]
            values.append(row_values)

        # Execute batch insert
        cursor.executemany(sql, values)
        return len(batch)

    def _get_geometry_columns(self, model: Type[models.Model]) -> List[str]:
        """Get list of geometry column names for a model."""
        geometry_columns = []

        # List of geometry type keywords to check
        geometry_keywords = [
            "geometry",
            "geography",
            "point",
            "linestring",
            "polygon",
            "multipolygon",
            "multilinestring",
            "multipoint",
        ]

        for model_field in model._meta.get_fields():
            if hasattr(model_field, "column"):
                field_type = getattr(model_field, "get_internal_type", lambda: "")().lower()
                class_name = model_field.__class__.__name__.lower()
                if any(keyword in field_type or keyword in class_name for keyword in geometry_keywords):
                    geometry_columns.append(model_field.column)

        return geometry_columns


@dataclass
class CircularDependency:
    """Represents a circular dependency between two models."""

    model_a: Type[models.Model]
    model_b: Type[models.Model]
    field_a: str  # Field in model_a that references model_b
    field_b: str  # Field in model_b that references model_a
    nullable_field: Optional[str] = None  # Which field can be loaded as NULL initially


class CircularDependencyResolver:
    """
    Resolves circular dependencies during import by using deferred updates.

    Strategy:
    1. Detect circular dependencies between models
    2. For each circular pair, identify nullable FK field
    3. Load first model with nullable FK set to NULL
    4. Load second model with proper FK references
    5. Update first model's nullable FK with correct values
    """

    def __init__(self):
        self.detected_cycles = []
        self.deferred_updates = []

    def detect_circular_dependencies(self, models: List[Type[models.Model]]) -> List[CircularDependency]:
        """
        Detect circular dependencies between the given models.

        Args:
            models: List of Django model classes to analyze

        Returns:
            List of CircularDependency objects
        """
        cycles = []

        for i, model_a in enumerate(models):
            for _j, model_b in enumerate(models[i + 1 :], i + 1):
                cycle = self._find_cycle_between_models(model_a, model_b)
                if cycle:
                    cycles.append(cycle)

        self.detected_cycles = cycles
        return cycles

    def _find_cycle_between_models(
        self, model_a: Type[models.Model], model_b: Type[models.Model]
    ) -> Optional[CircularDependency]:
        """Check if there's a circular dependency between two specific models."""

        # Find FK from model_a to model_b
        field_a_to_b = None
        for model_field in model_a._meta.get_fields():
            if isinstance(model_field, models.ForeignKey):
                # Handle both class references and string references
                related_model = model_field.related_model
                if hasattr(related_model, "_meta"):
                    # Direct class reference
                    if related_model == model_b:
                        field_a_to_b = model_field.name
                        break
                else:
                    # String reference - compare by name
                    if (
                        related_model == model_b.__name__
                        or related_model == f"{model_b._meta.app_label}.{model_b.__name__}"
                    ):
                        field_a_to_b = model_field.name
                        break

        # Find FK from model_b to model_a
        field_b_to_a = None
        for model_field in model_b._meta.get_fields():
            if isinstance(model_field, models.ForeignKey):
                # Handle both class references and string references
                related_model = model_field.related_model
                if hasattr(related_model, "_meta"):
                    # Direct class reference
                    if related_model == model_a:
                        field_b_to_a = model_field.name
                        break
                else:
                    # String reference - compare by name
                    if (
                        related_model == model_a.__name__
                        or related_model == f"{model_a._meta.app_label}.{model_a.__name__}"
                    ):
                        field_b_to_a = model_field.name
                        break

        # If both FKs exist, we have a circular dependency
        if field_a_to_b and field_b_to_a:
            # Determine which field is nullable
            field_a_nullable = model_a._meta.get_field(field_a_to_b).null
            field_b_nullable = model_b._meta.get_field(field_b_to_a).null

            nullable_field = None
            if field_a_nullable:
                nullable_field = field_a_to_b
            elif field_b_nullable:
                nullable_field = field_b_to_a

            return CircularDependency(
                model_a=model_a,
                model_b=model_b,
                field_a=field_a_to_b,
                field_b=field_b_to_a,
                nullable_field=nullable_field,
            )

        return None

    def resolve_loading_order(self, models: List[Type[models.Model]]) -> List[Type[models.Model]]:
        """
        Determine the optimal loading order considering circular dependencies.

        For circular dependencies, we load the model with nullable FK first.
        """
        cycles = self.detect_circular_dependencies(models)

        if not cycles:
            # No cycles, return topological sort
            return self._topological_sort(models)

        # Handle cycles by modifying the dependency graph
        modified_order = []
        processed = set()

        for cycle in cycles:
            if cycle.nullable_field:
                # Load the model with nullable FK first (without FK values)
                if cycle.nullable_field in [f.name for f in cycle.model_a._meta.get_fields()]:
                    # model_a has the nullable field
                    if cycle.model_a not in processed:
                        modified_order.append(cycle.model_a)
                        processed.add(cycle.model_a)
                    if cycle.model_b not in processed:
                        modified_order.append(cycle.model_b)
                        processed.add(cycle.model_b)
                else:
                    # model_b has the nullable field
                    if cycle.model_b not in processed:
                        modified_order.append(cycle.model_b)
                        processed.add(cycle.model_b)
                    if cycle.model_a not in processed:
                        modified_order.append(cycle.model_a)
                        processed.add(cycle.model_a)

        # Add remaining models
        for model in models:
            if model not in processed:
                modified_order.append(model)

        return modified_order

    def _topological_sort(self, models: List[Type[models.Model]]) -> List[Type[models.Model]]:
        """Simple topological sort for models without cycles."""
        # This is a simplified version - in practice you'd want proper topological sorting
        return models

    def prepare_deferred_updates(
        self, cycles: List[CircularDependency], csv_data: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        Prepare deferred update operations for circular dependencies.

        Args:
            cycles: List of detected circular dependencies
            csv_data: Dictionary of CSV data keyed by model name

        Returns:
            List of update operations to execute after initial load
        """
        updates = []

        for cycle in cycles:
            if not cycle.nullable_field:
                continue

            # Determine which model has the nullable field
            if cycle.nullable_field in [f.name for f in cycle.model_a._meta.get_fields()]:
                source_model = cycle.model_a
                nullable_field = cycle.nullable_field
            else:
                source_model = cycle.model_b
                nullable_field = cycle.field_b

            # Read original CSV data to get the FK mappings
            # Try multiple possible key formats
            source_csv_key = f"{source_model._meta.app_label}_{source_model._meta.model_name}"
            if source_csv_key not in csv_data:
                # Try without app label prefix
                source_csv_key = source_model._meta.model_name

            if source_csv_key in csv_data:
                source_data = csv_data[source_csv_key]

                # Extract ID mappings for deferred update
                for row in source_data:
                    if row.get(nullable_field):  # If the FK was supposed to be set
                        updates.append(
                            {
                                "model": source_model,
                                "pk": row["id"],
                                "field": nullable_field,
                                "value": row[nullable_field],
                            }
                        )

        self.deferred_updates = updates
        return updates

    def execute_deferred_updates(
        self, updates: List[Dict[str, Any]], connection: Any, id_mappings: Dict[str, Dict[int, int]]
    ):
        """
        Execute the deferred FK updates after initial loading.

        Args:
            updates: List of update operations
            connection: Database connection
            id_mappings: ID remapping dictionary for FK resolution
        """
        with connection.cursor() as cursor:
            for update in updates:
                model = update["model"]
                pk = update["pk"]
                field = update["field"]
                original_fk_value = update["value"]

                # Apply ID remapping to both PK and FK
                model_key = f"{model._meta.app_label}.{model.__name__}"

                # Remap the record's PK
                new_pk = id_mappings.get(model_key, {}).get(pk, pk)

                # Remap the FK value
                fk_field = model._meta.get_field(field)
                related_model = fk_field.related_model
                related_key = f"{related_model._meta.app_label}.{related_model.__name__}"
                new_fk_value = id_mappings.get(related_key, {}).get(original_fk_value, original_fk_value)

                # Execute the update
                sql = f'UPDATE "{model._meta.db_table}" SET "{field}" = %s WHERE "id" = %s'
                cursor.execute(sql, [new_fk_value, new_pk])


class TenantAwareRemappingStrategy:
    """
    Tenant-aware ID remapping that automatically applies tenant mappings to all related models.

    Usage:
        strategy = TenantAwareRemappingStrategy(
            tenant_model=Organization,
            tenant_mappings={1060: 10}  # staging org_id 1060 -> local org_id 10
        )
    """

    def __init__(self, tenant_model: Type[models.Model], tenant_mappings: Dict[int, int]):
        self.tenant_model = tenant_model
        self.tenant_mappings = tenant_mappings
        self.tenant_field_name = self._get_tenant_field_name()

    def _get_tenant_field_name(self) -> str:
        """Get the common field name used for tenant FKs (e.g., 'organization_id', 'org_id')."""
        # This could be made configurable, but we'll use a common pattern
        model_name = self.tenant_model._meta.model_name.lower()
        return f"{model_name}_id"

    def apply_to_all_models(self, models: List[Type[models.Model]]) -> Dict[str, Dict[int, int]]:
        """
        Generate ID mappings for all models, automatically applying tenant remapping.

        Args:
            models: List of Django models to generate mappings for

        Returns:
            Complete ID mapping dictionary ready for PostgresBulkLoader
        """
        id_mappings = {}

        # Add tenant model mapping
        tenant_key = f"{self.tenant_model._meta.app_label}.{self.tenant_model.__name__}"
        id_mappings[tenant_key] = self.tenant_mappings

        # For each model, check if it has a tenant FK and apply mappings
        for model in models:
            if model == self.tenant_model:
                continue  # Already handled above

            # Check if this model has a tenant FK
            from django.db import models as django_models

            has_tenant_fk = any(
                isinstance(field, django_models.ForeignKey) and field.related_model == self.tenant_model
                for field in model._meta.get_fields()
            )

            if has_tenant_fk:
                # This model references tenant, so tenant FK remapping will be auto-applied
                # by PostgresBulkLoader._apply_id_remappings()
                pass

            # Generate sequential mappings for this model's own IDs if needed
            # (This would typically be done by SequentialRemappingStrategy)
            # For now, we'll leave this empty and let the user specify if needed

        return id_mappings

    def get_tenant_filter_for_export(self, tenant_id: int) -> Dict[str, Any]:
        """
        Get filter parameters for exporting only data for a specific tenant.

        Args:
            tenant_id: The tenant ID to export data for

        Returns:
            Dictionary of filter parameters for QuerySet.filter()
        """
        return {self.tenant_field_name: tenant_id}


@dataclass
class ImportPlan:
    """
    Represents a plan for importing data from a CSV file.

    This value object contains all the information needed to import
    data for a specific model, including dependencies and remapping strategy.
    """

    model: Type[models.Model]
    csv_path: Path
    dependencies: List["ImportPlan"] = field(default_factory=list)
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

        for model_field in self.model._meta.get_fields():
            if isinstance(model_field, models.ForeignKey):
                dependencies.add(model_field.related_model)

        return dependencies

    def calculate_import_weight(self) -> int:
        """Calculate weight for dependency ordering (higher = import later)."""
        return len(self.dependencies)

    def estimate_row_count(self) -> int:
        """Estimate the number of rows in the CSV file."""
        try:
            with open(self.csv_path) as f:
                # Count lines and subtract 1 for header
                line_count = sum(1 for _ in f) - 1
                return max(0, line_count)
        except Exception:
            return 0

    def has_dependency(self, other_plan: "ImportPlan") -> bool:
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
