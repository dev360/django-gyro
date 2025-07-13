"""
Test suite for Importer core functionality.

Following the test plan Phase 1: Core Importer Framework
- Metaclass registration system
- Model validation and registration
- File naming conventions
- Registry lookup functionality
"""

import pytest
from django.db import models
from django.test import TestCase

from django_gyro import Importer


class TestImporterMetaclassRegistry(TestCase):
    """Test the ImporterMeta metaclass and registry functionality."""

    def setUp(self):
        """Clear the registry before each test."""
        if hasattr(Importer, "_registry"):
            Importer._registry.clear()

    def tearDown(self):
        """Clean up after each test."""
        if hasattr(Importer, "_registry"):
            Importer._registry.clear()

    def test_importer_model_registration_valid(self):
        """Test that Importer classes register their models correctly."""

        # Create a test model
        class TestModelCore1(models.Model):
            name = models.CharField(max_length=100)

            class Meta:
                app_label = "test_importer_core"

        # Create an importer
        class TestImporter(Importer):
            model = TestModelCore1

            class Columns:
                pass

        # Check that the model is registered
        assert TestModelCore1 in Importer._registry
        assert Importer._registry[TestModelCore1] == TestImporter

    def test_importer_model_registration_duplicate_fails(self):
        """Test that duplicate model registration raises an error."""

        class TestModelCore2(models.Model):
            name = models.CharField(max_length=100)

            class Meta:
                app_label = "test_importer_core"

        # Create first importer
        class TestImporter1(Importer):
            model = TestModelCore2

            class Columns:
                pass

        # Attempt to create second importer with same model should fail
        with pytest.raises(ValueError, match="is already registered with importer"):

            class TestImporter2(Importer):
                model = TestModelCore2

                class Columns:
                    pass

    def test_importer_missing_model_attribute_fails(self):
        """Test that Importer without model attribute raises an error."""
        with pytest.raises(AttributeError, match="must define a 'model' attribute"):

            class TestImporter(Importer):
                class Columns:
                    pass

    def test_importer_invalid_model_type_fails(self):
        """Test that invalid model types raise appropriate errors."""

        # Test with non-model class
        class NotAModel:
            pass

        with pytest.raises(TypeError, match="must be a Django model class"):

            class TestImporter1(Importer):
                model = NotAModel

                class Columns:
                    pass

        # Test with string
        with pytest.raises(TypeError, match="must be a Django model class"):

            class TestImporter2(Importer):
                model = "not_a_model"

                class Columns:
                    pass


class TestImporterFileNaming(TestCase):
    """Test file naming functionality for Importer classes."""

    def setUp(self):
        """Clear the registry before each test."""
        if hasattr(Importer, "_registry"):
            Importer._registry.clear()

    def tearDown(self):
        """Clean up after each test."""
        if hasattr(Importer, "_registry"):
            Importer._registry.clear()

    def test_get_file_name_generates_table_name(self):
        """Test that get_file_name returns the correct table name."""

        class TestModelCore3(models.Model):
            name = models.CharField(max_length=100)

            class Meta:
                app_label = "test_importer_core"

        class TestImporter(Importer):
            model = TestModelCore3

            class Columns:
                pass

        # Should generate filename based on model's table name
        expected_filename = f"{TestModelCore3._meta.db_table}.csv"
        assert TestImporter.get_file_name() == expected_filename

    def test_get_file_name_with_custom_table_name(self):
        """Test get_file_name with custom db_table."""

        class TestModelCore4(models.Model):
            name = models.CharField(max_length=100)

            class Meta:
                app_label = "test_importer_core"
                db_table = "custom_table_name"

        class TestImporter(Importer):
            model = TestModelCore4

            class Columns:
                pass

        # Should use custom table name
        assert TestImporter.get_file_name() == "custom_table_name.csv"

    def test_get_file_name_handles_edge_cases(self):
        """Test get_file_name with various edge cases."""

        class TestModelCore5(models.Model):
            name = models.CharField(max_length=100)

            class Meta:
                app_label = "test_importer_core"

        class TestImporter(Importer):
            model = TestModelCore5

            class Columns:
                pass

        filename = TestImporter.get_file_name()

        # Should be a valid filename
        assert filename.endswith(".csv")
        assert len(filename) > 4  # More than just '.csv'
        assert not filename.startswith(".")


class TestImporterRegistryLookup(TestCase):
    """Test registry lookup functionality."""

    def setUp(self):
        """Clear the registry before each test."""
        if hasattr(Importer, "_registry"):
            Importer._registry.clear()

    def tearDown(self):
        """Clean up after each test."""
        if hasattr(Importer, "_registry"):
            Importer._registry.clear()

    def test_registry_cleanup_between_tests(self):
        """Test that registry is properly cleared between tests."""
        # Registry should be empty at start of test
        assert len(Importer._registry) == 0

    def test_get_importer_for_model_found(self):
        """Test finding importer by model class."""

        class TestModelCore6(models.Model):
            name = models.CharField(max_length=100)

            class Meta:
                app_label = "test_importer_core"

        class TestImporter(Importer):
            model = TestModelCore6

            class Columns:
                pass

        # Should find the importer
        found_importer = Importer.get_importer_for_model(TestModelCore6)
        assert found_importer == TestImporter

    def test_get_importer_for_model_not_found(self):
        """Test lookup for non-registered model."""

        class UnregisteredModel(models.Model):
            name = models.CharField(max_length=100)

            class Meta:
                app_label = "test_importer_core"

        # Should return None for unregistered model
        found_importer = Importer.get_importer_for_model(UnregisteredModel)
        assert found_importer is None

    def test_get_importer_for_model_with_inheritance(self):
        """Test importer lookup with model inheritance."""

        class BaseModel(models.Model):
            name = models.CharField(max_length=100)

            class Meta:
                app_label = "test_importer_core"

        class ChildModel(BaseModel):
            age = models.IntegerField()

            class Meta:
                app_label = "test_importer_core"

        # Create importer for child model
        class ChildModelImporter(Importer):
            model = ChildModel

            class Columns:
                pass

        # Should find importer for child model
        found_importer = Importer.get_importer_for_model(ChildModel)
        assert found_importer == ChildModelImporter

        # Should not find importer for base model
        base_importer = Importer.get_importer_for_model(BaseModel)
        assert base_importer is None
