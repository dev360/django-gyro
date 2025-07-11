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
        # Implementation will be added when we implement this class
        pass


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