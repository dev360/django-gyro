"""
Test suite for ImportJob functionality.

Following the test plan Phase 2: ImportJob Definition
- ImportJob creation and validation
- Model and QuerySet validation
- Dependency graph computation and caching
"""

import time

import pytest
from django.db import models
from django.test import TestCase

from django_gyro import Importer, ImportJob

# Create unique suffix to avoid model conflicts
UNIQUE_SUFFIX = str(int(time.time() * 1000000))[-6:]


class TestImportJobCreation(TestCase):
    """Test ImportJob instantiation and basic validation."""

    def setUp(self):
        """Clear the registry before each test."""
        if hasattr(Importer, "_registry"):
            Importer._registry.clear()
        if hasattr(ImportJob, "_dependency_cache"):
            ImportJob._dependency_cache.clear()

    def tearDown(self):
        """Clean up after each test."""
        if hasattr(Importer, "_registry"):
            Importer._registry.clear()
        if hasattr(ImportJob, "_dependency_cache"):
            ImportJob._dependency_cache.clear()

    def test_import_job_creation_with_model_only(self):
        """Test creating ImportJob with model only."""

        class TestModelJobCreation1(models.Model):
            name = models.CharField(max_length=100)

            class Meta:
                app_label = "test_import_job"

        job = ImportJob(model=TestModelJobCreation1)

        assert job.model == TestModelJobCreation1
        assert job.query is None

    def test_import_job_creation_with_model_and_query(self):
        """Test creating ImportJob with model and QuerySet."""

        class TestModelJobCreation2(models.Model):
            name = models.CharField(max_length=100)

            class Meta:
                app_label = "test_import_job"

        queryset = TestModelJobCreation2.objects.filter(name="test")
        job = ImportJob(model=TestModelJobCreation2, query=queryset)

        assert job.model == TestModelJobCreation2
        assert job.query == queryset

    def test_import_job_invalid_model_types(self):
        """Test that invalid model types raise errors."""

        class NotAModel:
            pass

        with pytest.raises(TypeError, match="must be a Django model class"):
            ImportJob(model=NotAModel)

        with pytest.raises(TypeError, match="must be a Django model class"):
            ImportJob(model="not_a_class")

    def test_import_job_missing_model_parameter(self):
        """Test that missing model parameter raises error."""
        with pytest.raises(TypeError, match="missing 1 required positional argument"):
            ImportJob()

    def test_import_job_invalid_queryset_type(self):
        """Test that invalid QuerySet types raise errors."""

        class TestModelJobCreation3(models.Model):
            name = models.CharField(max_length=100)

            class Meta:
                app_label = "test_import_job"

        with pytest.raises(TypeError, match="must be a Django QuerySet or None"):
            ImportJob(model=TestModelJobCreation3, query="not_a_queryset")

        with pytest.raises(TypeError, match="must be a Django QuerySet or None"):
            ImportJob(model=TestModelJobCreation3, query=[])

    def test_import_job_queryset_model_mismatch(self):
        """Test that QuerySet must match the model."""

        class TestModelJobCreation4(models.Model):
            name = models.CharField(max_length=100)

            class Meta:
                app_label = "test_import_job"

        class TestModelJobCreation5(models.Model):
            name = models.CharField(max_length=100)

            class Meta:
                app_label = "test_import_job"

        wrong_queryset = TestModelJobCreation5.objects.all()

        with pytest.raises(ValueError, match="QuerySet model does not match ImportJob model"):
            ImportJob(model=TestModelJobCreation4, query=wrong_queryset)

    def test_import_job_empty_queryset_allowed(self):
        """Test that empty QuerySets are allowed."""

        class TestModelJobCreation6(models.Model):
            name = models.CharField(max_length=100)

            class Meta:
                app_label = "test_import_job"

        empty_queryset = TestModelJobCreation6.objects.none()
        job = ImportJob(model=TestModelJobCreation6, query=empty_queryset)

        assert job.model == TestModelJobCreation6
        assert job.query == empty_queryset


class TestImportJobProperties(TestCase):
    """Test ImportJob properties and immutability."""

    def setUp(self):
        """Clear the registry before each test."""
        if hasattr(Importer, "_registry"):
            Importer._registry.clear()
        if hasattr(ImportJob, "_dependency_cache"):
            ImportJob._dependency_cache.clear()

    def tearDown(self):
        """Clean up after each test."""
        if hasattr(Importer, "_registry"):
            Importer._registry.clear()
        if hasattr(ImportJob, "_dependency_cache"):
            ImportJob._dependency_cache.clear()

    def test_model_property_returns_correct_class(self):
        """Test that model property returns the correct model class."""

        class TestModelJobProperties1(models.Model):
            name = models.CharField(max_length=100)

            class Meta:
                app_label = "test_import_job"

        job = ImportJob(model=TestModelJobProperties1)
        assert job.model == TestModelJobProperties1

    def test_model_property_immutable_after_creation(self):
        """Test that model property cannot be changed after creation."""

        class TestModelJobProperties2(models.Model):
            name = models.CharField(max_length=100)

            class Meta:
                app_label = "test_import_job"

        job = ImportJob(model=TestModelJobProperties2)

        # Should not be able to modify model
        with pytest.raises(AttributeError):
            job.model = None

    def test_query_property_returns_queryset(self):
        """Test that query property returns the QuerySet."""

        class TestModelJobProperties3(models.Model):
            name = models.CharField(max_length=100)

            class Meta:
                app_label = "test_import_job"

        queryset = TestModelJobProperties3.objects.filter(name="test")
        job = ImportJob(model=TestModelJobProperties3, query=queryset)

        assert job.query == queryset

    def test_query_property_handles_none_values(self):
        """Test that query property handles None values."""

        class TestModelJobProperties4(models.Model):
            name = models.CharField(max_length=100)

            class Meta:
                app_label = "test_import_job"

        job = ImportJob(model=TestModelJobProperties4)
        assert job.query is None


class TestImportJobDependencies(TestCase):
    """Test ImportJob dependency analysis and graph computation."""

    def setUp(self):
        """Clear the registry before each test."""
        if hasattr(Importer, "_registry"):
            Importer._registry.clear()
        if hasattr(ImportJob, "_dependency_cache"):
            ImportJob._dependency_cache.clear()

    def tearDown(self):
        """Clean up after each test."""
        if hasattr(Importer, "_registry"):
            Importer._registry.clear()
        if hasattr(ImportJob, "_dependency_cache"):
            ImportJob._dependency_cache.clear()

    def test_get_dependencies_identifies_foreign_key_dependencies(self):
        """Test that get_dependencies identifies FK dependencies."""

        class CategoryJobDeps1(models.Model):
            name = models.CharField(max_length=100)

            class Meta:
                app_label = "test_import_job"

        class ProductJobDeps1(models.Model):
            name = models.CharField(max_length=100)
            category = models.ForeignKey(CategoryJobDeps1, on_delete=models.CASCADE)

            class Meta:
                app_label = "test_import_job"

        # Create importers
        class CategoryImporter(Importer):
            model = CategoryJobDeps1

            class Columns:
                pass

        class ProductImporter(Importer):
            model = ProductJobDeps1

            class Columns:
                category = CategoryJobDeps1

        job = ImportJob(model=ProductJobDeps1)
        dependencies = job.get_dependencies()

        # Product should depend on Category
        assert CategoryJobDeps1 in dependencies

    def test_get_dependencies_returns_dependency_chain(self):
        """Test that get_dependencies returns the full dependency chain."""

        class TenantJobDeps2(models.Model):
            name = models.CharField(max_length=100)

            class Meta:
                app_label = "test_import_job"

        class ShopJobDeps2(models.Model):
            name = models.CharField(max_length=100)
            tenant = models.ForeignKey(TenantJobDeps2, on_delete=models.CASCADE)

            class Meta:
                app_label = "test_import_job"

        class ProductJobDeps2(models.Model):
            name = models.CharField(max_length=100)
            shop = models.ForeignKey(ShopJobDeps2, on_delete=models.CASCADE)

            class Meta:
                app_label = "test_import_job"

        # Create importers
        class TenantImporter(Importer):
            model = TenantJobDeps2

            class Columns:
                pass

        class ShopImporter(Importer):
            model = ShopJobDeps2

            class Columns:
                tenant = TenantJobDeps2

        class ProductImporter(Importer):
            model = ProductJobDeps2

            class Columns:
                shop = ShopJobDeps2

        job = ImportJob(model=ProductJobDeps2)
        dependencies = job.get_dependencies()

        # Product should depend on both Shop and Tenant
        assert ShopJobDeps2 in dependencies
        assert TenantJobDeps2 in dependencies

    def test_get_dependencies_handles_circular_references(self):
        """Test that circular dependencies are detected."""

        class ModelAJobDeps3(models.Model):
            name = models.CharField(max_length=100)
            b_ref = models.ForeignKey("ModelBJobDeps3", on_delete=models.CASCADE, null=True)

            class Meta:
                app_label = "test_import_job"

        class ModelBJobDeps3(models.Model):
            name = models.CharField(max_length=100)
            a_ref = models.ForeignKey(ModelAJobDeps3, on_delete=models.CASCADE, null=True)

            class Meta:
                app_label = "test_import_job"

        # Create importers
        class ModelAImporter(Importer):
            model = ModelAJobDeps3

            class Columns:
                b_ref = ModelBJobDeps3

        class ModelBImporter(Importer):
            model = ModelBJobDeps3

            class Columns:
                a_ref = ModelAJobDeps3

        job = ImportJob(model=ModelAJobDeps3)

        # Should detect circular dependency
        with pytest.raises(ValueError, match="Circular dependency detected"):
            job.get_dependencies()

    def test_get_dependencies_caches_computation(self):
        """Test that dependency computation is cached for performance."""

        class CategoryJobDeps4(models.Model):
            name = models.CharField(max_length=100)

            class Meta:
                app_label = "test_import_job"

        class ProductJobDeps4(models.Model):
            name = models.CharField(max_length=100)
            category = models.ForeignKey(CategoryJobDeps4, on_delete=models.CASCADE)

            class Meta:
                app_label = "test_import_job"

        # Create importers
        class CategoryImporter(Importer):
            model = CategoryJobDeps4

            class Columns:
                pass

        class ProductImporter(Importer):
            model = ProductJobDeps4

            class Columns:
                category = CategoryJobDeps4

        job = ImportJob(model=ProductJobDeps4)

        # First call should compute and cache
        deps1 = job.get_dependencies()

        # Second call should use cache (same result, faster)
        deps2 = job.get_dependencies()

        assert deps1 == deps2
        # Verify cache exists
        assert hasattr(ImportJob, "_dependency_cache")


class TestImportJobDependencyOrdering(TestCase):
    """Test dependency ordering functionality for ImportJobs."""

    def setUp(self):
        """Clear the registry before each test."""
        if hasattr(Importer, "_registry"):
            Importer._registry.clear()
        if hasattr(ImportJob, "_dependency_cache"):
            ImportJob._dependency_cache.clear()

    def tearDown(self):
        """Clean up after each test."""
        if hasattr(Importer, "_registry"):
            Importer._registry.clear()
        if hasattr(ImportJob, "_dependency_cache"):
            ImportJob._dependency_cache.clear()

    def test_sort_jobs_by_dependency_order(self):
        """Test sorting jobs by dependency order."""

        class TenantJobOrder1(models.Model):
            name = models.CharField(max_length=100)

            class Meta:
                app_label = "test_import_job"

        class ShopJobOrder1(models.Model):
            name = models.CharField(max_length=100)
            tenant = models.ForeignKey(TenantJobOrder1, on_delete=models.CASCADE)

            class Meta:
                app_label = "test_import_job"

        class ProductJobOrder1(models.Model):
            name = models.CharField(max_length=100)
            shop = models.ForeignKey(ShopJobOrder1, on_delete=models.CASCADE)

            class Meta:
                app_label = "test_import_job"

        # Create importers
        class TenantImporter(Importer):
            model = TenantJobOrder1

            class Columns:
                pass

        class ShopImporter(Importer):
            model = ShopJobOrder1

            class Columns:
                tenant = TenantJobOrder1

        class ProductImporter(Importer):
            model = ProductJobOrder1

            class Columns:
                shop = ShopJobOrder1

        # Create jobs in wrong order
        jobs = [
            ImportJob(model=ProductJobOrder1),
            ImportJob(model=TenantJobOrder1),
            ImportJob(model=ShopJobOrder1),
        ]

        sorted_jobs = ImportJob.sort_by_dependencies(jobs)

        # Should be ordered: Tenant, Shop, Product
        assert sorted_jobs[0].model == TenantJobOrder1
        assert sorted_jobs[1].model == ShopJobOrder1
        assert sorted_jobs[2].model == ProductJobOrder1

    def test_detect_circular_dependencies_in_job_list(self):
        """Test detection of circular dependencies in job list."""

        class ModelAJobOrder2(models.Model):
            name = models.CharField(max_length=100)
            b_ref = models.ForeignKey("ModelBJobOrder2", on_delete=models.CASCADE, null=True)

            class Meta:
                app_label = "test_import_job"

        class ModelBJobOrder2(models.Model):
            name = models.CharField(max_length=100)
            a_ref = models.ForeignKey(ModelAJobOrder2, on_delete=models.CASCADE, null=True)

            class Meta:
                app_label = "test_import_job"

        # Create importers with circular dependency
        class ModelAImporter(Importer):
            model = ModelAJobOrder2

            class Columns:
                b_ref = ModelBJobOrder2

        class ModelBImporter(Importer):
            model = ModelBJobOrder2

            class Columns:
                a_ref = ModelAJobOrder2

        jobs = [
            ImportJob(model=ModelAJobOrder2),
            ImportJob(model=ModelBJobOrder2),
        ]

        with pytest.raises(ValueError, match="Circular dependency detected"):
            ImportJob.sort_by_dependencies(jobs)

    def test_handle_independent_models_ordering(self):
        """Test that independent models can be in any order."""

        class IndependentAJobOrder3(models.Model):
            name = models.CharField(max_length=100)

            class Meta:
                app_label = "test_import_job"

        class IndependentBJobOrder3(models.Model):
            name = models.CharField(max_length=100)

            class Meta:
                app_label = "test_import_job"

        # Create importers
        class IndependentAImporter(Importer):
            model = IndependentAJobOrder3

            class Columns:
                pass

        class IndependentBImporter(Importer):
            model = IndependentBJobOrder3

            class Columns:
                pass

        jobs = [
            ImportJob(model=IndependentBJobOrder3),
            ImportJob(model=IndependentAJobOrder3),
        ]

        # Should not raise any errors
        sorted_jobs = ImportJob.sort_by_dependencies(jobs)

        # Both orders should be valid since they're independent
        assert len(sorted_jobs) == 2
        models_in_result = {job.model for job in sorted_jobs}
        assert models_in_result == {IndependentAJobOrder3, IndependentBJobOrder3}
