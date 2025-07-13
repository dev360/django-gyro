"""
Test suite for Importer Columns validation functionality.

Following the test plan Phase 1: Core Importer Framework
- Columns class validation
- Foreign key reference validation
- Faker method validation
- Registry lookup integration
"""

import pytest
from django.db import models
from django.test import TestCase
from faker import Faker

from django_gyro import Importer


class TestImporterColumnsValidation(TestCase):
    """Test Columns validation within Importer classes."""

    def setUp(self):
        """Clear the registry before each test."""
        if hasattr(Importer, "_registry"):
            Importer._registry.clear()

    def tearDown(self):
        """Clean up after each test."""
        if hasattr(Importer, "_registry"):
            Importer._registry.clear()

    def test_columns_valid_foreign_key_reference(self):
        """Test that valid foreign key columns are accepted."""

        class CategoryColumns1(models.Model):
            name = models.CharField(max_length=100)

            class Meta:
                app_label = "test_importer_columns"

        class ProductColumns1(models.Model):
            name = models.CharField(max_length=100)
            category = models.ForeignKey(CategoryColumns1, on_delete=models.CASCADE)

            class Meta:
                app_label = "test_importer_columns"

        # Create category importer first
        class CategoryImporter(Importer):
            model = CategoryColumns1

            class Columns:
                pass

        # Should be able to reference Category in Product importer
        class ProductImporter(Importer):
            model = ProductColumns1

            class Columns:
                category = CategoryColumns1

        # Should register successfully without warnings
        assert ProductColumns1 in Importer._registry
        assert Importer._registry[ProductColumns1] == ProductImporter

    def test_columns_invalid_field_reference_warns(self):
        """Test that invalid field references generate warnings."""

        class ProductColumns2(models.Model):
            name = models.CharField(max_length=100)
            price = models.DecimalField(max_digits=10, decimal_places=2)

            class Meta:
                app_label = "test_importer_columns"

        # Should generate warning for non-FK field reference
        with pytest.warns(UserWarning, match="is not a foreign key field"):

            class ProductImporter(Importer):
                model = ProductColumns2

                class Columns:
                    name = ProductColumns2  # Invalid: referencing model for non-FK field

    def test_columns_non_foreign_key_field_warns(self):
        """Test that references to non-FK fields generate warnings."""

        class ProductColumns3(models.Model):
            name = models.CharField(max_length=100)
            price = models.DecimalField(max_digits=10, decimal_places=2)

            class Meta:
                app_label = "test_importer_columns"

        # Should warn about non-FK field being treated as FK
        with pytest.warns(UserWarning, match="is not a foreign key field"):

            class ProductImporter(Importer):
                model = ProductColumns3

                class Columns:
                    price = ProductColumns3  # Invalid: price is not a FK

    def test_columns_missing_required_relationships_warns(self):
        """Test that missing required FK relationships generate warnings."""

        class CategoryColumns3(models.Model):
            name = models.CharField(max_length=100)

            class Meta:
                app_label = "test_importer_columns"

        class ProductColumns4(models.Model):
            name = models.CharField(max_length=100)
            category = models.ForeignKey(CategoryColumns3, on_delete=models.CASCADE)

            class Meta:
                app_label = "test_importer_columns"

        # Create Product importer without referencing required Category FK
        with pytest.warns(UserWarning, match="missing foreign key reference"):

            class ProductImporter(Importer):
                model = ProductColumns4

                class Columns:
                    pass  # Missing category reference

    def test_columns_valid_faker_method_reference(self):
        """Test that valid Faker method objects are accepted."""
        fake = Faker()

        class ProductColumns5(models.Model):
            name = models.CharField(max_length=100)
            description = models.TextField()

            class Meta:
                app_label = "test_importer_columns"

        # Should accept Faker method objects
        class ProductImporter(Importer):
            model = ProductColumns5

            class Columns:
                name = fake.name
                description = fake.text

        # Should register without issues
        assert ProductColumns5 in Importer._registry

    def test_columns_invalid_faker_reference_warns(self):
        """Test that invalid Faker references generate warnings."""

        class ProductColumns6(models.Model):
            name = models.CharField(max_length=100)

            class Meta:
                app_label = "test_importer_columns"

        # Should warn about invalid Faker reference
        with pytest.warns(UserWarning, match="must be a Django model or Faker method"):

            class ProductImporter(Importer):
                model = ProductColumns6

                class Columns:
                    name = "not.a.faker.method"  # Invalid faker reference

    def test_columns_mixed_valid_references(self):
        """Test that mixed valid Django models and Faker methods work."""
        fake = Faker()

        class CategoryColumns4(models.Model):
            name = models.CharField(max_length=100)

            class Meta:
                app_label = "test_importer_columns"

        class ProductColumns7(models.Model):
            name = models.CharField(max_length=100)
            description = models.TextField()
            category = models.ForeignKey(CategoryColumns4, on_delete=models.CASCADE)

            class Meta:
                app_label = "test_importer_columns"

        # Create category importer
        class CategoryImporter(Importer):
            model = CategoryColumns4

            class Columns:
                name = fake.company

        # Should accept mixed references
        class ProductImporter(Importer):
            model = ProductColumns7

            class Columns:
                name = fake.word  # Use valid faker method
                description = fake.text
                category = CategoryColumns4

        # Both should register successfully
        assert CategoryColumns4 in Importer._registry
        assert ProductColumns7 in Importer._registry


class TestImporterColumnsRegistryLookup(TestCase):
    """Test Columns validation with registry lookup functionality."""

    def setUp(self):
        """Clear the registry before each test."""
        if hasattr(Importer, "_registry"):
            Importer._registry.clear()

    def tearDown(self):
        """Clean up after each test."""
        if hasattr(Importer, "_registry"):
            Importer._registry.clear()

    def test_columns_finds_referenced_model_importers(self):
        """Test that Columns validation finds referenced model importers."""

        class CategoryColumns5(models.Model):
            name = models.CharField(max_length=100)

            class Meta:
                app_label = "test_importer_columns"

        class ProductColumns8(models.Model):
            name = models.CharField(max_length=100)
            category = models.ForeignKey(CategoryColumns5, on_delete=models.CASCADE)

            class Meta:
                app_label = "test_importer_columns"

        # Create category importer first
        class CategoryImporter(Importer):
            model = CategoryColumns5

            class Columns:
                pass

        # Product importer should find CategoryImporter in registry
        class ProductImporter(Importer):
            model = ProductColumns8

            class Columns:
                category = CategoryColumns5

        # Verify both are registered and connected
        category_importer = Importer.get_importer_for_model(CategoryColumns5)
        product_importer = Importer.get_importer_for_model(ProductColumns8)

        assert category_importer == CategoryImporter
        assert product_importer == ProductImporter

    def test_columns_missing_importer_definitions_warns(self):
        """Test that missing importer definitions generate warnings."""

        class CategoryColumns6(models.Model):
            name = models.CharField(max_length=100)

            class Meta:
                app_label = "test_importer_columns"

        class ProductColumns9(models.Model):
            name = models.CharField(max_length=100)
            category = models.ForeignKey(CategoryColumns6, on_delete=models.CASCADE)

            class Meta:
                app_label = "test_importer_columns"

        # Create Product importer without CategoryImporter
        with pytest.warns(UserWarning, match="no importer found"):

            class ProductImporter(Importer):
                model = ProductColumns9

                class Columns:
                    category = CategoryColumns6  # CategoryImporter doesn't exist

    def test_columns_validates_relationship_consistency(self):
        """Test that relationship consistency is validated."""

        class CategoryColumns7(models.Model):
            name = models.CharField(max_length=100)

            class Meta:
                app_label = "test_importer_columns"

        class ProductColumns10(models.Model):
            name = models.CharField(max_length=100)
            category = models.ForeignKey(CategoryColumns7, on_delete=models.CASCADE)

            class Meta:
                app_label = "test_importer_columns"

        class WrongModel(models.Model):
            name = models.CharField(max_length=100)

            class Meta:
                app_label = "test_importer_columns"

        # Create category importer
        class CategoryImporter(Importer):
            model = CategoryColumns7

            class Columns:
                pass

        # Should warn about relationship mismatch
        with pytest.warns(UserWarning, match="relationship mismatch"):

            class ProductImporter(Importer):
                model = ProductColumns10

                class Columns:
                    category = WrongModel  # Wrong model for category FK
