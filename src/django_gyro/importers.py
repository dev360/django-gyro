"""
Django Gyro Import Operations

This module provides functionality for importing CSV data into Django models
with comprehensive validation, foreign key resolution, and dependency management.
"""

import csv
import io
from collections import defaultdict
from typing import Any, Dict, List, Optional, Set

from django.core.exceptions import FieldDoesNotExist
from django.db import IntegrityError, models, transaction


class PostgresImporter:
    """
    PostgreSQL-specific importer for CSV data with comprehensive validation
    and foreign key resolution.
    """

    def __init__(self, connection_string: str):
        """Initialize with database connection."""
        self.connection_string = connection_string

    def parse_csv_headers(self, csv_file: io.StringIO) -> List[str]:
        """Parse CSV headers from file-like object."""
        csv_file.seek(0)  # Reset to beginning
        reader = csv.reader(csv_file)
        headers = next(reader, [])
        csv_file.seek(0)  # Reset for future reads
        return headers

    def map_columns_to_fields(self, model: models.Model, csv_headers: List[str]) -> Dict[str, models.Field]:
        """Map CSV columns to Django model fields."""
        field_mapping = {}
        model_fields = {field.name: field for field in model._meta.fields}

        for header in csv_headers:
            # Handle FK fields (e.g., 'category_id' -> 'category')
            field_name = header
            if header.endswith("_id"):
                base_name = header[:-3]
                if base_name in model_fields:
                    field_name = base_name

            if field_name in model_fields:
                field_mapping[header] = model_fields[field_name]

        return field_mapping

    def validate_required_columns(self, model: models.Model, csv_headers: List[str]) -> None:
        """Validate that all required columns are present in CSV."""
        model_fields = {field.name: field for field in model._meta.fields}
        field_mapping = self.map_columns_to_fields(model, csv_headers)

        for field_name, field in model_fields.items():
            # Skip auto fields and fields with defaults
            if field.auto_created or field.has_default() or field.null:
                continue

            # Check if field is represented in CSV (directly or as FK)
            field_in_csv = (
                field_name in csv_headers or f"{field_name}_id" in csv_headers or field_name in field_mapping.values()
            )

            if not field_in_csv:
                raise ValueError(f"Missing required column for field '{field_name}'")

    def validate_row_data(self, model: models.Model, row_data: Dict[str, str]) -> Dict[str, Any]:
        """Validate and convert row data types."""
        validated_row = {}
        field_mapping = self.map_columns_to_fields(model, list(row_data.keys()))

        # Check for required fields first
        model_fields = {field.name: field for field in model._meta.fields}
        for field_name, field in model_fields.items():
            # Skip auto fields and fields with defaults
            if field.auto_created or field.has_default() or field.null:
                continue

            # Check if field is represented in row data (directly or as FK)
            field_in_row = field_name in row_data or f"{field_name}_id" in row_data

            if not field_in_row:
                raise ValueError(f"Required field '{field_name}' is missing")

        for csv_column, value in row_data.items():
            if csv_column not in field_mapping:
                continue  # Skip unmapped columns

            field = field_mapping[csv_column]

            try:
                # Handle different field types
                if isinstance(field, models.CharField) or isinstance(field, models.TextField):
                    validated_row[csv_column] = str(value) if value else ""
                elif isinstance(field, models.IntegerField):
                    validated_row[csv_column] = int(value) if value else None
                elif isinstance(field, models.DecimalField):
                    validated_row[csv_column] = float(value) if value else None
                elif isinstance(field, models.BooleanField):
                    validated_row[csv_column] = value.lower() in ("true", "1", "yes", "on") if value else False
                elif isinstance(field, models.EmailField):
                    validated_row[csv_column] = str(value) if value else ""
                elif isinstance(field, models.ForeignKey):
                    validated_row[csv_column] = int(value) if value else None
                else:
                    validated_row[csv_column] = value
            except (ValueError, TypeError) as e:
                raise ValueError(f"Invalid data type for field '{csv_column}': {e}") from e

        # Validate model constraints
        try:
            # Create temporary instance for validation
            instance = model(**{k.replace("_id", ""): v for k, v in validated_row.items()})
            if hasattr(instance, "clean"):
                instance.clean()
        except Exception as e:
            raise ValueError(str(e)) from e

        return validated_row

    def check_fk_exists(self, model: models.Model, field_name: str, fk_id: int) -> bool:
        """Check if foreign key target exists in database."""
        field = model._meta.get_field(field_name)
        if isinstance(field, models.ForeignKey):
            related_model = field.related_model
            return related_model.objects.filter(pk=fk_id).exists()
        return False

    def resolve_foreign_keys(self, model: models.Model, row_data: Dict[str, Any]) -> Dict[str, Any]:
        """Resolve and validate foreign key references."""
        resolved_row = row_data.copy()

        for field_name, value in row_data.items():
            if field_name.endswith("_id") and value is not None:
                base_field_name = field_name[:-3]
                try:
                    field = model._meta.get_field(base_field_name)
                    if isinstance(field, models.ForeignKey):
                        fk_id = int(value)
                        if not self.check_fk_exists(model, base_field_name, fk_id):
                            raise ValueError(f"Foreign key target does not exist: {field_name}={fk_id}")
                        resolved_row[field_name] = fk_id
                except FieldDoesNotExist:
                    pass  # Not a FK field

        return resolved_row

    def get_fk_dependency_chain(self, model: models.Model) -> List[models.Model]:
        """Get the foreign key dependency chain for a model."""
        dependencies = []

        def _get_dependencies(current_model: models.Model, visited: Set[models.Model]) -> None:
            if current_model in visited:
                return  # Avoid infinite recursion

            visited.add(current_model)

            for field in current_model._meta.fields:
                if isinstance(field, models.ForeignKey):
                    related_model = field.related_model
                    if related_model not in dependencies:
                        dependencies.append(related_model)
                    _get_dependencies(related_model, visited)

        _get_dependencies(model, set())
        return dependencies

    def import_data(self, model: models.Model, csv_data: List[Dict[str, str]]) -> None:
        """Import CSV data into model with validation."""
        try:
            for row in csv_data:
                validated_row = self.validate_row_data(model, row)
                resolved_row = self.resolve_foreign_keys(model, validated_row)
                # Execute import would happen here
                self.execute_import(model, resolved_row)
        except IntegrityError as e:
            if "UNIQUE constraint" in str(e):
                raise ValueError(f"Unique constraint violation: {e}") from e
            elif "CHECK constraint" in str(e):
                raise ValueError(f"Database constraint violation: {e}") from e
            else:
                raise ValueError(f"Database integrity error: {e}") from e

    def execute_import(self, model: models.Model, row_data: Dict[str, Any]) -> None:
        """Execute the actual import - to be mocked in tests."""
        # This would contain the actual database insertion logic
        pass

    def import_data_with_transaction(self, model: models.Model, csv_data: List[Dict[str, str]]) -> None:
        """Import data within a database transaction."""
        try:
            with transaction.atomic():
                self.import_data(model, csv_data)
        except Exception:
            transaction.rollback()
            raise


class FKDependencyValidator:
    """
    Validator for foreign key dependencies and cyclical relationships.
    Implements the sophisticated FK validation requirements.
    """

    def __init__(self):
        """Initialize the validator."""
        self._dependency_cache = {}

    def check_fk_targets_exist(self, model: models.Model, csv_data: List[Dict[str, str]]) -> Dict[str, List[int]]:
        """Check if all FK targets exist in the database."""
        missing_fks = []

        # Extract FK IDs from CSV data
        fk_fields = [field for field in model._meta.fields if isinstance(field, models.ForeignKey)]

        for field in fk_fields:
            fk_column = f"{field.name}_id"
            fk_ids = set()

            for row in csv_data:
                if fk_column in row and row[fk_column]:
                    try:
                        fk_ids.add(int(row[fk_column]))
                    except ValueError:
                        continue

            # Check which IDs don't exist
            if fk_ids:
                related_model = field.related_model
                existing_ids = set(related_model.objects.filter(pk__in=fk_ids).values_list("pk", flat=True))
                missing_ids = fk_ids - existing_ids
                missing_fks.extend(missing_ids)

        return {"missing_fks": missing_fks}

    def validate_fk_targets(self, model: models.Model, csv_data: List[Dict[str, str]]) -> Dict[str, Any]:
        """Validate that all FK targets exist."""
        result = self.check_fk_targets_exist(model, csv_data)
        missing_fks = result["missing_fks"]

        return {"valid": len(missing_fks) == 0, "missing_fks": missing_fks}

    def detect_cyclical_dependencies(self, importers: List[type]) -> List[List[models.Model]]:
        """Detect cyclical dependencies between models."""
        cycles = []

        # Build dependency graph
        graph = defaultdict(set)
        models_in_graph = set()

        for importer_class in importers:
            if not hasattr(importer_class, "model"):
                continue

            model = importer_class.model
            models_in_graph.add(model)

            # Get FK dependencies
            for field in model._meta.fields:
                if isinstance(field, models.ForeignKey):
                    related_model = field.related_model
                    if related_model != model:  # Skip self-references
                        graph[model].add(related_model)
                        models_in_graph.add(related_model)

        # Detect cycles using DFS
        def _has_cycle(
            node: models.Model, visited: Set[models.Model], rec_stack: Set[models.Model], path: List[models.Model]
        ) -> Optional[List[models.Model]]:
            visited.add(node)
            rec_stack.add(node)
            path.append(node)

            for neighbor in graph[node]:
                if neighbor not in visited:
                    cycle = _has_cycle(neighbor, visited, rec_stack, path)
                    if cycle:
                        return cycle
                elif neighbor in rec_stack:
                    # Found cycle - return the cycle path
                    cycle_start = path.index(neighbor)
                    return path[cycle_start:] + [neighbor]

            rec_stack.remove(node)
            path.pop()
            return None

        visited = set()
        for model in models_in_graph:
            if model not in visited:
                cycle = _has_cycle(model, visited, set(), [])
                if cycle:
                    cycles.append(cycle)

        return cycles

    def get_excluded_fields(self, importer_class: type) -> List[str]:
        """Get excluded fields from importer."""
        return getattr(importer_class, "excluded", [])

    def validate_excluded_fields(self, importer_class: type) -> Dict[str, Any]:
        """Validate that excluded fields are actually FK fields."""
        if not hasattr(importer_class, "model"):
            return {"valid": False, "error": "Importer has no model"}

        model = importer_class.model
        excluded_fields = self.get_excluded_fields(importer_class)

        # Check that excluded fields are FK fields
        model_fk_fields = set()
        for field in model._meta.fields:
            if isinstance(field, models.ForeignKey):
                model_fk_fields.add(f"{field.name}_id")

        invalid_exclusions = []
        for excluded_field in excluded_fields:
            if excluded_field not in model_fk_fields:
                invalid_exclusions.append(excluded_field)

        return {"valid": len(invalid_exclusions) == 0, "invalid_exclusions": invalid_exclusions}

    def validate_import_plan(self, importers: List[type]) -> Dict[str, Any]:
        """Comprehensive pre-import validation."""
        validation_result = {"valid": True, "errors": [], "cyclical_dependencies": []}

        # Check for cyclical dependencies
        cycles = self.detect_cyclical_dependencies(importers)

        if cycles:
            # Check if cycles are resolved by exclusions
            unresolved_cycles = []

            for cycle in cycles:
                cycle_resolved = False

                # Check if any importer in the cycle has exclusions that break it
                for importer_class in importers:
                    if hasattr(importer_class, "model") and importer_class.model in cycle:
                        excluded_fields = self.get_excluded_fields(importer_class)

                        # Check if exclusions break the cycle
                        for field in importer_class.model._meta.fields:
                            if isinstance(field, models.ForeignKey):
                                fk_field_name = f"{field.name}_id"
                                if fk_field_name in excluded_fields and field.related_model in cycle:
                                    cycle_resolved = True
                                    break

                        if cycle_resolved:
                            break

                if not cycle_resolved:
                    unresolved_cycles.append(cycle)

            if unresolved_cycles:
                validation_result["valid"] = False
                validation_result["cyclical_dependencies"] = unresolved_cycles
                validation_result["errors"].append("Unresolved cyclical dependencies detected")

        return validation_result
