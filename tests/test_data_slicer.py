"""
Test suite for DataSlicer functionality.

Following the test plan Phase 3: DataSlicer Operations
- DataSlicer configuration and initialization
- Job generation from importers and models
- Export operations to CSV
- Source/target validation
"""

import os
import tempfile
from unittest.mock import Mock, patch

from django.db import models
from django.db.models.query import QuerySet

from django_gyro import DataSlicer, Importer, ImportJob

from .test_utils import clear_django_gyro_registries


# Mock Django database operations for tests
def mock_db_operations():
    """Create a mock for database operations to prevent geo_db_type errors."""
    mock_ops = Mock()
    mock_ops.geo_db_type = Mock(return_value="geometry")
    mock_ops.max_name_length = Mock(return_value=63)  # Standard PostgreSQL limit
    return mock_ops


def mock_db_connection():
    """Create a mock database connection."""
    mock_conn = Mock()
    mock_conn.ops = mock_db_operations()
    return mock_conn


class MockQuerySet(QuerySet):
    """A mock QuerySet that can be used in tests without database access."""

    def __init__(self, model=None):
        # Don't call super().__init__() to avoid database dependencies
        self.model = model
        self._result_cache = []


class TestDataSlicerConfiguration:
    """Test DataSlicer instantiation and configuration."""

    def setup_method(self):
        """Clear registries before each test."""
        clear_django_gyro_registries()
        # Patch database connection to prevent geo_db_type errors
        self.db_conn_patcher = patch("django.db.connection", mock_db_connection())
        self.db_conn_patcher.start()

    def teardown_method(self):
        """Clear registries after each test."""
        clear_django_gyro_registries()
        self.db_conn_patcher.stop()

    def test_data_slicer_creation_with_importers(self):
        """Test creating DataSlicer with importer class list."""

        class TestModel1(models.Model):
            name = models.CharField(max_length=100)

            class Meta:
                app_label = "test_data_slicer"

        class TestModel2(models.Model):
            name = models.CharField(max_length=100)

            class Meta:
                app_label = "test_data_slicer"

        class TestImporter1(Importer):
            model = TestModel1

            class Columns:
                pass

        class TestImporter2(Importer):
            model = TestModel2

            class Columns:
                pass

        # Should accept list of importer classes
        slicer = DataSlicer([TestImporter1, TestImporter2])

        assert len(slicer.importers) == 2
        assert TestImporter1 in slicer.importers
        assert TestImporter2 in slicer.importers

    def test_data_slicer_creation_with_models(self):
        """Test creating DataSlicer with model class list."""

        class TestModel1(models.Model):
            name = models.CharField(max_length=100)

            class Meta:
                app_label = "test_data_slicer"

        class TestModel2(models.Model):
            name = models.CharField(max_length=100)

            class Meta:
                app_label = "test_data_slicer"

        class TestImporter1(Importer):
            model = TestModel1

            class Columns:
                pass

        class TestImporter2(Importer):
            model = TestModel2

            class Columns:
                pass

        # Should accept list of model classes and find their importers
        slicer = DataSlicer([TestModel1, TestModel2])

        assert len(slicer.importers) == 2
        assert TestImporter1 in slicer.importers
        assert TestImporter2 in slicer.importers

    def test_data_slicer_invalid_configuration_fails(self):
        """Test that invalid configurations raise errors."""
        # Test with non-list
        try:
            DataSlicer("not_a_list")
            raise AssertionError("Expected TypeError")
        except TypeError as e:
            assert "must be a list" in str(e)

        # Test with empty list
        try:
            DataSlicer([])
            raise AssertionError("Expected ValueError")
        except ValueError as e:
            assert "cannot be empty" in str(e)

        # Test with invalid types in list
        try:
            DataSlicer(["not_a_class"])
            raise AssertionError("Expected TypeError")
        except TypeError as e:
            assert "must be Django model or Importer class" in str(e)

        # Test with model that has no importer
        class UnregisteredSlicerModel(models.Model):
            name = models.CharField(max_length=100)

            class Meta:
                app_label = "test_data_slicer"

        try:
            DataSlicer([UnregisteredSlicerModel])
            raise AssertionError("Expected ValueError")
        except ValueError as e:
            assert "no importer found" in str(e)

    def test_data_slicer_mixed_configuration_works(self):
        """Test that mixed importers and models work together."""

        class TestModel1(models.Model):
            name = models.CharField(max_length=100)

            class Meta:
                app_label = "test_data_slicer"

        class TestModel2(models.Model):
            name = models.CharField(max_length=100)

            class Meta:
                app_label = "test_data_slicer"

        class TestImporter1(Importer):
            model = TestModel1

            class Columns:
                pass

        class TestImporter2(Importer):
            model = TestModel2

            class Columns:
                pass

        # Should accept mixed list of models and importers
        slicer = DataSlicer([TestImporter1, TestModel2])

        assert len(slicer.importers) == 2
        assert TestImporter1 in slicer.importers
        assert TestImporter2 in slicer.importers


class TestDataSlicerJobGeneration:
    """Test DataSlicer job generation functionality."""

    def setup_method(self):
        """Clear registries before each test."""
        clear_django_gyro_registries()
        # Patch database connection to prevent geo_db_type errors
        self.db_conn_patcher = patch("django.db.connection", mock_db_connection())
        self.db_conn_patcher.start()

    def teardown_method(self):
        """Clear registries after each test."""
        clear_django_gyro_registries()
        self.db_conn_patcher.stop()

    def test_generate_import_jobs_from_importers(self):
        """Test generating ImportJobs from registered importers."""

        class TestModel1(models.Model):
            name = models.CharField(max_length=100)

            class Meta:
                app_label = "test_data_slicer"

        class TestModel2(models.Model):
            name = models.CharField(max_length=100)

            class Meta:
                app_label = "test_data_slicer"

        class TestImporter1(Importer):
            model = TestModel1

            class Columns:
                pass

        class TestImporter2(Importer):
            model = TestModel2

            class Columns:
                pass

        slicer = DataSlicer([TestImporter1, TestImporter2])
        jobs = slicer.generate_import_jobs()

        assert len(jobs) == 2
        assert all(isinstance(job, ImportJob) for job in jobs)

        job_models = {job.model for job in jobs}
        assert TestModel1 in job_models
        assert TestModel2 in job_models

    def test_generate_import_jobs_with_querysets(self):
        """Test generating ImportJobs with custom QuerySets."""

        class TestModel1(models.Model):
            name = models.CharField(max_length=100)
            active = models.BooleanField(default=True)

            class Meta:
                app_label = "test_data_slicer"

        class TestImporter1(Importer):
            model = TestModel1

            class Columns:
                pass

        slicer = DataSlicer([TestImporter1])

        # Create mock QuerySet that will pass isinstance check
        mock_queryset = MockQuerySet(model=TestModel1)

        # Test with custom querysets dict
        custom_querysets = {TestModel1: mock_queryset}
        jobs = slicer.generate_import_jobs(querysets=custom_querysets)

        assert len(jobs) == 1
        assert jobs[0].model == TestModel1
        assert jobs[0].query is not None

    def test_generate_import_jobs_dependency_sorting(self):
        """Test that jobs are auto-sorted by dependencies."""

        class Tenant(models.Model):
            name = models.CharField(max_length=100)

            class Meta:
                app_label = "test_data_slicer"

        class Shop(models.Model):
            name = models.CharField(max_length=100)
            tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE)

            class Meta:
                app_label = "test_data_slicer"

        class Product(models.Model):
            name = models.CharField(max_length=100)
            shop = models.ForeignKey(Shop, on_delete=models.CASCADE)

            class Meta:
                app_label = "test_data_slicer"

        class TenantImporter(Importer):
            model = Tenant

            class Columns:
                pass

        class ShopImporter(Importer):
            model = Shop

            class Columns:
                tenant = Tenant

        class ProductImporter(Importer):
            model = Product

            class Columns:
                shop = Shop

        # Create slicer with importers in wrong order
        slicer = DataSlicer([ProductImporter, TenantImporter, ShopImporter])
        jobs = slicer.generate_import_jobs()

        # Should be sorted: Tenant, Shop, Product
        assert jobs[0].model == Tenant
        assert jobs[1].model == Shop
        assert jobs[2].model == Product

    def test_generate_import_jobs_handles_circular_deps(self):
        """Test that circular dependencies are detected in job generation."""

        class ModelA(models.Model):
            name = models.CharField(max_length=100)
            b_ref = models.ForeignKey("ModelB", on_delete=models.CASCADE, null=True)

            class Meta:
                app_label = "test_data_slicer"

        class ModelB(models.Model):
            name = models.CharField(max_length=100)
            a_ref = models.ForeignKey(ModelA, on_delete=models.CASCADE, null=True)

            class Meta:
                app_label = "test_data_slicer"

        class ModelAImporter(Importer):
            model = ModelA

            class Columns:
                b_ref = ModelB

        class ModelBImporter(Importer):
            model = ModelB

            class Columns:
                a_ref = ModelA

        slicer = DataSlicer([ModelAImporter, ModelBImporter])

        try:
            slicer.generate_import_jobs()
            raise AssertionError("Expected ValueError")
        except ValueError as e:
            assert "Circular dependency detected" in str(e)


class TestDataSlicerExportOperations:
    """Test DataSlicer export operations."""

    def setup_method(self):
        """Clear registries before each test."""
        clear_django_gyro_registries()
        # Patch database connection to prevent geo_db_type errors
        self.db_conn_patcher = patch("django.db.connection", mock_db_connection())
        self.db_conn_patcher.start()

    def teardown_method(self):
        """Clear registries after each test."""
        clear_django_gyro_registries()
        self.db_conn_patcher.stop()

    def test_export_to_csv_single_model(self):
        """Test exporting single model to CSV."""

        class TestModel(models.Model):
            name = models.CharField(max_length=100)

            class Meta:
                app_label = "test_data_slicer"

        class TestImporter(Importer):
            model = TestModel

            class Columns:
                pass

        slicer = DataSlicer([TestImporter])

        with tempfile.TemporaryDirectory() as temp_dir:
            result = slicer.export_to_csv(temp_dir)

            assert result is not None
            assert "files_created" in result
            assert len(result["files_created"]) == 1

            # Check file was created
            expected_file = os.path.join(temp_dir, TestImporter.get_file_name())
            assert os.path.exists(expected_file)

    def test_export_to_csv_multiple_models(self):
        """Test exporting multiple models with dependencies."""

        class Category(models.Model):
            name = models.CharField(max_length=100)

            class Meta:
                app_label = "test_data_slicer"

        class Product(models.Model):
            name = models.CharField(max_length=100)
            category = models.ForeignKey(Category, on_delete=models.CASCADE)

            class Meta:
                app_label = "test_data_slicer"

        class CategoryImporter(Importer):
            model = Category

            class Columns:
                pass

        class ProductImporter(Importer):
            model = Product

            class Columns:
                category = Category

        slicer = DataSlicer([ProductImporter, CategoryImporter])

        with tempfile.TemporaryDirectory() as temp_dir:
            result = slicer.export_to_csv(temp_dir)

            assert len(result["files_created"]) == 2

            # Check both files were created
            cat_file = os.path.join(temp_dir, CategoryImporter.get_file_name())
            prod_file = os.path.join(temp_dir, ProductImporter.get_file_name())
            assert os.path.exists(cat_file)
            assert os.path.exists(prod_file)

    def test_export_to_csv_with_querysets(self):
        """Test exporting with custom QuerySet filtering."""

        class TestModel(models.Model):
            name = models.CharField(max_length=100)
            active = models.BooleanField(default=True)

            class Meta:
                app_label = "test_data_slicer"

        class TestImporter(Importer):
            model = TestModel

            class Columns:
                pass

        slicer = DataSlicer([TestImporter])

        # Create mock QuerySet that will pass isinstance check
        mock_queryset = MockQuerySet(model=TestModel)
        querysets = {TestModel: mock_queryset}

        with tempfile.TemporaryDirectory() as temp_dir:
            result = slicer.export_to_csv(temp_dir, querysets=querysets)

            assert "files_created" in result
            assert len(result["files_created"]) == 1

    def test_export_to_csv_custom_directory(self):
        """Test exporting to custom directory path."""

        class TestModel(models.Model):
            name = models.CharField(max_length=100)

            class Meta:
                app_label = "test_data_slicer"

        class TestImporter(Importer):
            model = TestModel

            class Columns:
                pass

        slicer = DataSlicer([TestImporter])

        with tempfile.TemporaryDirectory() as temp_dir:
            custom_subdir = os.path.join(temp_dir, "exports", "data")

            slicer.export_to_csv(custom_subdir)

            # Should create directory if it doesn't exist
            assert os.path.exists(custom_subdir)

            # Should create file in custom directory
            expected_file = os.path.join(custom_subdir, TestImporter.get_file_name())
            assert os.path.exists(expected_file)
