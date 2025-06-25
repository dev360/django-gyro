"""
Test suite for Importer.Columns functionality.

Following the test plan Phase 1: Core Importer Framework
- Columns field validation and linting
- Foreign key reference validation
- Faker method object validation
"""
import pytest
import warnings
from django.db import models
from django.test import TestCase
from faker import Faker

from django_gyro import Importer


class TestImporterColumnsValidation(TestCase):
    """Test the Columns class field validation and linting."""

    def setUp(self):
        """Clear the registry before each test."""
        if hasattr(Importer, '_registry'):
            Importer._registry.clear()

    def test_columns_valid_foreign_key_reference(self):
        """Test that valid foreign key columns are accepted."""
        class Category(models.Model):
            name = models.CharField(max_length=100)
            
            class Meta:
                app_label = 'test'

        class Product(models.Model):
            name = models.CharField(max_length=100)
            category = models.ForeignKey(Category, on_delete=models.CASCADE)
            
            class Meta:
                app_label = 'test'

        # Create importers
        class CategoryImporter(Importer):
            model = Category
            
            class Columns:
                pass

        class ProductImporter(Importer):
            model = Product
            
            class Columns:
                category = Category  # Valid FK reference

        # Should not raise any warnings or errors
        # The metaclass should validate this successfully

    def test_columns_invalid_field_reference_warns(self):
        """Test that invalid field references generate warnings."""
        class Product(models.Model):
            name = models.CharField(max_length=100)
            
            class Meta:
                app_label = 'test'

        class SomeOtherModel(models.Model):
            name = models.CharField(max_length=100)
            
            class Meta:
                app_label = 'test'

        # This should generate a warning because 'category' is not a field on Product
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            
            class ProductImporter(Importer):
                model = Product
                
                class Columns:
                    category = SomeOtherModel  # Invalid - no FK field named 'category'

            # Check that a warning was issued
            assert len(w) > 0
            assert "not a field on" in str(w[0].message)

    def test_columns_non_foreign_key_field_warns(self):
        """Test that references to non-FK fields generate warnings."""
        class Product(models.Model):
            name = models.CharField(max_length=100)  # Not a FK
            price = models.DecimalField(max_digits=10, decimal_places=2)  # Not a FK
            
            class Meta:
                app_label = 'test'

        class Category(models.Model):
            name = models.CharField(max_length=100)
            
            class Meta:
                app_label = 'test'

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            
            class ProductImporter(Importer):
                model = Product
                
                class Columns:
                    name = Category  # Invalid - 'name' is CharField, not FK

            # Check that a warning was issued
            assert len(w) > 0
            assert "not a foreign key field" in str(w[0].message)

    def test_columns_missing_required_relationships_warns(self):
        """Test that missing required FK relationships generate warnings."""
        class Category(models.Model):
            name = models.CharField(max_length=100)
            
            class Meta:
                app_label = 'test'

        class Product(models.Model):
            name = models.CharField(max_length=100)
            category = models.ForeignKey(Category, on_delete=models.CASCADE)
            
            class Meta:
                app_label = 'test'

        # Create Category importer first
        class CategoryImporter(Importer):
            model = Category
            
            class Columns:
                pass

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            
            class ProductImporter(Importer):
                model = Product
                
                class Columns:
                    pass  # Missing 'category' FK reference

            # Check that a warning was issued about missing FK
            assert len(w) > 0
            assert "missing foreign key reference" in str(w[0].message).lower()

    def test_columns_valid_faker_method_reference(self):
        """Test that valid Faker method objects are accepted."""
        fake = Faker()
        
        class Product(models.Model):
            name = models.CharField(max_length=100)
            description = models.TextField()
            
            class Meta:
                app_label = 'test'

        class ProductImporter(Importer):
            model = Product
            
            class Columns:
                name = fake.word  # Valid Faker method
                description = fake.text  # Valid Faker method

        # Should not raise any warnings or errors

    def test_columns_invalid_faker_reference_warns(self):
        """Test that invalid Faker references generate warnings."""
        class Product(models.Model):
            name = models.CharField(max_length=100)
            
            class Meta:
                app_label = 'test'

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            
            class ProductImporter(Importer):
                model = Product
                
                class Columns:
                    name = "not_a_faker_method"  # Invalid - string, not Faker method

            # Check that a warning was issued
            assert len(w) > 0
            assert "must be a Django model or Faker method" in str(w[0].message)

    def test_columns_mixed_valid_references(self):
        """Test that mixed valid Django models and Faker methods work."""
        fake = Faker()
        
        class Category(models.Model):
            name = models.CharField(max_length=100)
            
            class Meta:
                app_label = 'test'

        class Product(models.Model):
            name = models.CharField(max_length=100)
            description = models.TextField()
            category = models.ForeignKey(Category, on_delete=models.CASCADE)
            
            class Meta:
                app_label = 'test'

        class CategoryImporter(Importer):
            model = Category
            
            class Columns:
                name = fake.word  # Faker method

        class ProductImporter(Importer):
            model = Product
            
            class Columns:
                category = Category  # Django model
                description = fake.text  # Faker method

        # Should not raise any warnings or errors


class TestImporterColumnsRegistryLookup(TestCase):
    """Test the Columns class registry lookup functionality."""

    def setUp(self):
        """Clear the registry before each test."""
        if hasattr(Importer, '_registry'):
            Importer._registry.clear()

    def test_columns_finds_referenced_model_importers(self):
        """Test that Columns validation finds referenced model importers."""
        class Category(models.Model):
            name = models.CharField(max_length=100)
            
            class Meta:
                app_label = 'test'

        class Product(models.Model):
            name = models.CharField(max_length=100)
            category = models.ForeignKey(Category, on_delete=models.CASCADE)
            
            class Meta:
                app_label = 'test'

        # Create Category importer first
        class CategoryImporter(Importer):
            model = Category
            
            class Columns:
                pass

        # Product importer should find the CategoryImporter
        class ProductImporter(Importer):
            model = Product
            
            class Columns:
                category = Category

        # Validation should pass since CategoryImporter exists

    def test_columns_missing_importer_definitions_warns(self):
        """Test that missing importer definitions generate warnings."""
        class Category(models.Model):
            name = models.CharField(max_length=100)
            
            class Meta:
                app_label = 'test'

        class Product(models.Model):
            name = models.CharField(max_length=100)
            category = models.ForeignKey(Category, on_delete=models.CASCADE)
            
            class Meta:
                app_label = 'test'

        # Don't create CategoryImporter

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            
            class ProductImporter(Importer):
                model = Product
                
                class Columns:
                    category = Category  # References model without importer

            # Check that a warning was issued
            assert len(w) > 0
            assert "no importer found" in str(w[0].message).lower()

    def test_columns_validates_relationship_consistency(self):
        """Test that relationship consistency is validated."""
        class Category(models.Model):
            name = models.CharField(max_length=100)
            
            class Meta:
                app_label = 'test'

        class Product(models.Model):
            name = models.CharField(max_length=100)
            category = models.ForeignKey(Category, on_delete=models.CASCADE)
            
            class Meta:
                app_label = 'test'

        class Tag(models.Model):
            name = models.CharField(max_length=100)
            
            class Meta:
                app_label = 'test'

        class CategoryImporter(Importer):
            model = Category
            
            class Columns:
                pass

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            
            class ProductImporter(Importer):
                model = Product
                
                class Columns:
                    category = Tag  # Wrong model - should be Category

            # Check that a warning was issued about model mismatch
            assert len(w) > 0
            assert "relationship mismatch" in str(w[0].message).lower() 