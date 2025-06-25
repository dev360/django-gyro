"""
Core Importer functionality for Django Gyro.
"""
import warnings
from typing import Dict, Type, Optional, Any, Union
from django.db import models
from faker import Faker


class ImporterMeta(type):
    """
    Metaclass for Importer classes that provides automatic registration
    and validation of model and column definitions.
    """
    
    def __new__(
        mcs, 
        name: str, 
        bases: tuple, 
        attrs: Dict[str, Any], 
        **kwargs: Any
    ) -> 'ImporterMeta':
        # Create the class first
        cls = super().__new__(mcs, name, bases, attrs, **kwargs)
        
        # Skip registration for the base Importer class
        if name == 'Importer' and not bases:
            cls._registry = {}
            return cls
        
        # Validate and register the importer if it has a model
        if hasattr(cls, 'model'):
            mcs._validate_and_register_importer(cls, name)
        else:
            raise AttributeError(f"Importer class '{name}' must define a 'model' attribute")
        
        return cls
    
    @classmethod
    def _validate_and_register_importer(
        mcs, 
        cls: 'Importer', 
        name: str
    ) -> None:
        """Validate and register an importer class."""
        model = cls.model
        
        # Validate model is actually a Django model
        if not (isinstance(model, type) and issubclass(model, models.Model)):
            raise TypeError(f"Importer '{name}' model must be a Django model class")
        
        # Check for duplicate registration
        if model in cls._registry:
            existing_importer = cls._registry[model]
            raise ValueError(
                f"Model {model.__name__} is already registered with importer "
                f"{existing_importer.__name__}"
            )
        
        # Register the importer
        cls._registry[model] = cls
        
        # Validate columns if they exist
        if hasattr(cls, 'Columns'):
            mcs._validate_columns(cls, model)
    
    @classmethod
    def _validate_columns(
        mcs, 
        cls: 'Importer', 
        model: Type[models.Model]
    ) -> None:
        """Validate the Columns class definitions."""
        columns_attrs = {
            key: value for key, value in cls.Columns.__dict__.items()
            if not key.startswith('_')
        }
        
        # Get model fields for validation
        model_fields = {field.name: field for field in model._meta.get_fields()}
        foreign_key_fields = {
            field.name: field for field in model._meta.get_fields()
            if isinstance(field, models.ForeignKey)
        }
        
        # Track missing FK references
        missing_fks = set(foreign_key_fields.keys())
        
        for column_name, column_value in columns_attrs.items():
            # Remove from missing FK list if referenced
            if column_name in missing_fks:
                missing_fks.remove(column_name)
            
            # Validate the column reference
            mcs._validate_column_reference(
                cls, model, column_name, column_value, model_fields, foreign_key_fields
            )
        
        # Warn about missing FK references
        if missing_fks:
            warnings.warn(
                f"Importer {cls.__name__} is missing foreign key reference(s): {', '.join(missing_fks)}",
                UserWarning,
                stacklevel=3
            )
    
    @classmethod
    def _validate_column_reference(
        mcs,
        cls: 'Importer',
        model: Type[models.Model],
        column_name: str,
        column_value: Any,
        model_fields: Dict[str, models.Field],
        foreign_key_fields: Dict[str, models.ForeignKey]
    ) -> None:
        """Validate a single column reference."""
        # Check if it's a Django model
        if isinstance(column_value, type) and issubclass(column_value, models.Model):
            mcs._validate_model_reference(
                cls, model, column_name, column_value, model_fields, foreign_key_fields
            )
        # Check if it's a Faker method (bound method from Faker provider)
        elif (hasattr(column_value, '__self__') and 
              hasattr(column_value.__self__, '__module__') and 
              column_value.__self__.__module__ and
              'faker.providers' in column_value.__self__.__module__):
            # Valid Faker method - no further validation needed
            pass
        else:
            warnings.warn(
                f"Importer {cls.__name__} column '{column_name}' must be a Django model or Faker method, "
                f"got {type(column_value).__name__}",
                UserWarning,
                stacklevel=4
            )
    
    @classmethod
    def _validate_model_reference(
        mcs,
        cls: 'Importer',
        model: Type[models.Model],
        column_name: str,
        referenced_model: Type[models.Model],
        model_fields: Dict[str, models.Field],
        foreign_key_fields: Dict[str, models.ForeignKey]
    ) -> None:
        """Validate a Django model reference in columns."""
        # Check if column exists as a field
        if column_name not in model_fields:
            warnings.warn(
                f"Importer {cls.__name__} references column '{column_name}' which is not a field on {model.__name__}",
                UserWarning,
                stacklevel=5
            )
            return
        
        # Check if it's a foreign key field
        if column_name not in foreign_key_fields:
            warnings.warn(
                f"Importer {cls.__name__} column '{column_name}' is not a foreign key field on {model.__name__}",
                UserWarning,
                stacklevel=5
            )
            return
        
        # Check if the referenced model matches the FK target
        fk_field = foreign_key_fields[column_name]
        if fk_field.related_model != referenced_model:
            warnings.warn(
                f"Importer {cls.__name__} column '{column_name}' relationship mismatch: "
                f"expected {fk_field.related_model.__name__}, got {referenced_model.__name__}",
                UserWarning,
                stacklevel=5
            )
            return
        
        # Check if the referenced model has an importer
        if referenced_model not in cls._registry:
            warnings.warn(
                f"Importer {cls.__name__} references {referenced_model.__name__} but no importer found for that model",
                UserWarning,
                stacklevel=5
            )


class Importer(metaclass=ImporterMeta):
    """
    Base class for defining CSV import/export mappings for Django models.
    
    Each Importer class should define:
    - model: The Django model class this importer handles
    - Columns: Optional class defining column mappings to foreign keys or Faker methods
    """
    
    model: Type[models.Model]
    _registry: Dict[Type[models.Model], Type['Importer']] = {}
    
    def get_file_name(self) -> str:
        """
        Generate the CSV filename based on the model's database table name.
        
        Returns:
            The filename with .csv extension (e.g., "products_product.csv")
        """
        table_name = self.model._meta.db_table
        return f"{table_name}.csv"
    
    @classmethod
    def get_importer_for_model(
        cls, 
        model: Type[models.Model]
    ) -> Optional[Type['Importer']]:
        """
        Look up an importer class by model.
        
        Args:
            model: The Django model class to find an importer for
            
        Returns:
            The importer class if found, None otherwise
        """
        return cls._registry.get(model) 