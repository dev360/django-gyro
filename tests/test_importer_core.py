"""
Test suite for core Importer functionality.

Following the test plan Phase 1: Core Importer Framework
- Importer class with metaclass registry
- Model registration and validation
- get_file_name() method
"""
import pytest
from django.db import models
from django.test import TestCase

from django_gyro import Importer


class TestImporterMetaclassRegistry(TestCase):
    """Test the metaclass registry system for Importer classes."""

    def setUp(self):
        """Clear the registry before each test."""
        # We'll need to implement registry clearing
        if hasattr(Importer, '_registry'):
            Importer._registry.clear()

    def test_importer_model_registration_valid(self):
        """Test that Importer classes register their models correctly."""
        # Create a test model
        class TestModel(models.Model):
            name = models.CharField(max_length=100)
            
            class Meta:
                app_label = 'test'

        # Create an importer
        class TestModelImporter(Importer):
            model = TestModel
            
            class Columns:
                pass

        # Test that the importer was registered
        assert TestModelImporter.model == TestModel
        # Test that we can look up the importer by model
        found_importer = Importer.get_importer_for_model(TestModel)
        assert found_importer == TestModelImporter

    def test_importer_model_registration_duplicate_fails(self):
        """Test that duplicate model registration raises an error."""
        class TestModel(models.Model):
            name = models.CharField(max_length=100)
            
            class Meta:
                app_label = 'test'

        # Create first importer
        class TestModelImporter1(Importer):
            model = TestModel
            
            class Columns:
                pass

        # Creating second importer for same model should fail
        with pytest.raises(ValueError, match="already registered"):
            class TestModelImporter2(Importer):
                model = TestModel
                
                class Columns:
                    pass

    def test_importer_missing_model_attribute_fails(self):
        """Test that missing model attribute raises an error."""
        with pytest.raises(AttributeError, match="must define a 'model' attribute"):
            class InvalidImporter(Importer):
                class Columns:
                    pass

    def test_importer_invalid_model_type_fails(self):
        """Test that invalid model types raise an error."""
        class NotAModel:
            pass

        with pytest.raises(TypeError, match="must be a Django model class"):
            class InvalidImporter(Importer):
                model = NotAModel
                
                class Columns:
                    pass


class TestImporterFileNaming(TestCase):
    """Test the get_file_name() method for CSV file naming."""

    def test_get_file_name_generates_table_name(self):
        """Test that get_file_name() returns the correct table name."""
        class Product(models.Model):
            name = models.CharField(max_length=100)
            
            class Meta:
                app_label = 'products'

        class ProductImporter(Importer):
            model = Product
            
            class Columns:
                pass

        importer = ProductImporter()
        # Should generate: products_product.csv
        assert importer.get_file_name() == "products_product.csv"

    def test_get_file_name_with_custom_table_name(self):
        """Test get_file_name() with custom db_table."""
        class CustomProduct(models.Model):
            name = models.CharField(max_length=100)
            
            class Meta:
                app_label = 'products'
                db_table = 'custom_products'

        class CustomProductImporter(Importer):
            model = CustomProduct
            
            class Columns:
                pass

        importer = CustomProductImporter()
        # Should use the custom table name
        assert importer.get_file_name() == "custom_products.csv"

    def test_get_file_name_handles_edge_cases(self):
        """Test get_file_name() with edge cases in model names."""
        class VeryLongModelNameForTesting(models.Model):
            name = models.CharField(max_length=100)
            
            class Meta:
                app_label = 'test_app'

        class VeryLongModelNameForTestingImporter(Importer):
            model = VeryLongModelNameForTesting
            
            class Columns:
                pass

        importer = VeryLongModelNameForTestingImporter()
        # Should handle long names correctly
        expected = "test_app_verylongmodelnamefortesting.csv"
        assert importer.get_file_name() == expected


class TestImporterRegistryLookup(TestCase):
    """Test the importer registry lookup functionality."""

    def setUp(self):
        """Clear the registry before each test."""
        if hasattr(Importer, '_registry'):
            Importer._registry.clear()

    def test_get_importer_for_model_found(self):
        """Test finding importer by model class."""
        class TestModel(models.Model):
            name = models.CharField(max_length=100)
            
            class Meta:
                app_label = 'test'

        class TestModelImporter(Importer):
            model = TestModel
            
            class Columns:
                pass

        found = Importer.get_importer_for_model(TestModel)
        assert found == TestModelImporter

    def test_get_importer_for_model_not_found(self):
        """Test handling of unregistered models."""
        class UnregisteredModel(models.Model):
            name = models.CharField(max_length=100)
            
            class Meta:
                app_label = 'test'

        found = Importer.get_importer_for_model(UnregisteredModel)
        assert found is None

    def test_get_importer_for_model_with_inheritance(self):
        """Test model inheritance handling."""
        class BaseModel(models.Model):
            name = models.CharField(max_length=100)
            
            class Meta:
                app_label = 'test'

        class ChildModel(BaseModel):
            description = models.TextField()
            
            class Meta:
                app_label = 'test'

        class ChildModelImporter(Importer):
            model = ChildModel
            
            class Columns:
                pass

        # Should find the child model importer
        found = Importer.get_importer_for_model(ChildModel)
        assert found == ChildModelImporter
        
        # Should not find importer for base model
        found_base = Importer.get_importer_for_model(BaseModel)
        assert found_base is None

    def test_registry_cleanup_between_tests(self):
        """Test that registry is properly cleaned between tests."""
        # Registry should be empty at start of test
        assert len(getattr(Importer, '_registry', {})) == 0 