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