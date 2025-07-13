"""
Tests for ExportPlan (formerly ImportJob).

ExportPlan represents a plan for exporting data from Django models
with proper dependency analysis for ordering.
"""

from unittest.mock import Mock, patch

import pytest
from django.db import models

from django_gyro.core import Importer
from django_gyro.importing import ExportPlan


class TestExportPlan:
    """Tests for ExportPlan behavior (formerly ImportJob)."""

    def setup_method(self):
        """Clear the registry before each test."""
        from .test_utils import clear_django_gyro_registries

        clear_django_gyro_registries()

    def teardown_method(self):
        """Clean up after each test."""
        from .test_utils import clear_django_gyro_registries

        clear_django_gyro_registries()

    def test_creates_with_model_only(self):
        """ExportPlan can be created with just a model."""

        # Setup
        class ExportPlanTestModel(models.Model):
            name = models.CharField(max_length=100)

            class Meta:
                app_label = "test_export_plan"

        # Exercise
        plan = ExportPlan(model=ExportPlanTestModel)

        # Verify
        assert plan.model == ExportPlanTestModel
        assert plan.query is None

    def test_creates_with_model_and_queryset(self):
        """ExportPlan can be created with model and QuerySet."""

        # Setup
        class ExportPlanTestModel2(models.Model):
            name = models.CharField(max_length=100)
            active = models.BooleanField(default=True)

            class Meta:
                app_label = "test_export_plan"

        # Mock QuerySet that passes validation
        from django.db.models.query import QuerySet

        mock_queryset = Mock(spec=QuerySet)
        mock_queryset.model = ExportPlanTestModel2

        # Exercise
        plan = ExportPlan(model=ExportPlanTestModel2, query=mock_queryset)

        # Verify
        assert plan.model == ExportPlanTestModel2
        assert plan.query == mock_queryset

    def test_validates_model_is_django_model(self):
        """ExportPlan validates that model is a Django model."""

        # Setup
        class NotAModel:
            pass

        # Exercise & Verify
        with pytest.raises(TypeError, match="model must be a Django model class"):
            ExportPlan(model=NotAModel)

    def test_validates_query_is_queryset(self):
        """ExportPlan validates that query is a QuerySet."""

        # Setup
        class ExportPlanTestModel(models.Model):
            name = models.CharField(max_length=100)

            class Meta:
                app_label = "test_export_plan"

        # Exercise & Verify
        with pytest.raises(TypeError, match="query must be a Django QuerySet or None"):
            ExportPlan(model=ExportPlanTestModel, query="not a queryset")

    def test_validates_query_model_matches_plan_model(self):
        """ExportPlan validates that QuerySet model matches plan model."""

        # Setup
        class ExportPlanTestModel3(models.Model):
            name = models.CharField(max_length=100)

            class Meta:
                app_label = "test_export_plan"

        class ExportPlanTestModel4(models.Model):
            name = models.CharField(max_length=100)

            class Meta:
                app_label = "test_export_plan"

        # Mock QuerySet with different model
        from django.db.models.query import QuerySet

        mock_queryset = Mock(spec=QuerySet)
        mock_queryset.model = ExportPlanTestModel4

        # Exercise & Verify
        with pytest.raises(ValueError, match="QuerySet model does not match"):
            ExportPlan(model=ExportPlanTestModel3, query=mock_queryset)

    def test_identifies_direct_dependencies(self):
        """ExportPlan identifies direct model dependencies."""

        # Setup
        class Tenant(models.Model):
            name = models.CharField(max_length=100)

            class Meta:
                app_label = "test_export_plan"

        class Shop(models.Model):
            tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE)
            name = models.CharField(max_length=100)

            class Meta:
                app_label = "test_export_plan"

        # Mock importers
        class TenantImporter(Importer):
            model = Tenant

            class Columns:
                pass  # No dependencies

        class ShopImporter(Importer):
            model = Shop

            class Columns:
                tenant = Tenant

        def mock_get_importer(model):
            if model == Tenant:
                return TenantImporter
            elif model == Shop:
                return ShopImporter
            return None

        with patch.object(Importer, "get_importer_for_model", side_effect=mock_get_importer):
            plan = ExportPlan(model=Shop)

            # Exercise
            dependencies = plan.get_dependencies()

            # Verify
            assert Tenant in dependencies
            assert len(dependencies) == 1

    def test_handles_no_dependencies(self):
        """ExportPlan handles models with no dependencies."""

        # Setup
        class Tenant(models.Model):
            name = models.CharField(max_length=100)

            class Meta:
                app_label = "test_export_plan"

        # Mock importer with no dependencies
        class TenantImporter(Importer):
            model = Tenant

            class Columns:
                pass

        with patch.object(Importer, "get_importer_for_model") as mock_get_importer:
            mock_get_importer.return_value = TenantImporter

            plan = ExportPlan(model=Tenant)

            # Exercise
            dependencies = plan.get_dependencies()

            # Verify
            assert dependencies == []

    def test_caches_dependency_computation(self):
        """ExportPlan caches dependency computations for performance."""

        # Setup
        class ExportPlanTestModel(models.Model):
            name = models.CharField(max_length=100)

            class Meta:
                app_label = "test_export_plan"

        class TestImporter(Importer):
            model = ExportPlanTestModel

            class Columns:
                pass

        with patch.object(Importer, "get_importer_for_model") as mock_get_importer:
            mock_get_importer.return_value = TestImporter

            plan = ExportPlan(model=ExportPlanTestModel)

            # Exercise
            deps1 = plan.get_dependencies()
            deps2 = plan.get_dependencies()

            # Verify
            assert deps1 is deps2  # Same object reference (cached)
            mock_get_importer.assert_called_once()  # Only called once

    def test_detects_circular_dependencies(self):
        """ExportPlan detects circular dependencies."""

        # Setup
        class ModelA(models.Model):
            name = models.CharField(max_length=100)

            class Meta:
                app_label = "test_export_plan"

        class ModelB(models.Model):
            name = models.CharField(max_length=100)

            class Meta:
                app_label = "test_export_plan"

        # Mock circular dependency: A depends on B, B depends on A
        class ImporterA(Importer):
            model = ModelA

            class Columns:
                b = ModelB

        class ImporterB(Importer):
            model = ModelB

            class Columns:
                a = ModelA

        def mock_get_importer(model):
            if model == ModelA:
                return ImporterA
            elif model == ModelB:
                return ImporterB
            return None

        with patch.object(Importer, "get_importer_for_model", side_effect=mock_get_importer):
            plan = ExportPlan(model=ModelA)

            # Exercise & Verify
            with pytest.raises(ValueError, match="Circular dependency detected"):
                plan.get_dependencies()

    def test_sorts_plans_by_dependencies(self):
        """ExportPlan can sort multiple plans by dependency order."""

        # Setup
        class Tenant(models.Model):
            name = models.CharField(max_length=100)

            class Meta:
                app_label = "test_export_plan"

        class Shop(models.Model):
            tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE)
            name = models.CharField(max_length=100)

            class Meta:
                app_label = "test_export_plan"

        class Customer(models.Model):
            shop = models.ForeignKey(Shop, on_delete=models.CASCADE)
            name = models.CharField(max_length=100)

            class Meta:
                app_label = "test_export_plan"

        # Mock importers with dependencies
        class TenantImporter(Importer):
            model = Tenant

            class Columns:
                pass

        class ShopImporter(Importer):
            model = Shop

            class Columns:
                tenant = Tenant

        class CustomerImporter(Importer):
            model = Customer

            class Columns:
                shop = Shop

        def mock_get_importer(model):
            if model == Tenant:
                return TenantImporter
            elif model == Shop:
                return ShopImporter
            elif model == Customer:
                return CustomerImporter
            return None

        with patch.object(Importer, "get_importer_for_model", side_effect=mock_get_importer):
            # Create plans in wrong order
            customer_plan = ExportPlan(model=Customer)
            shop_plan = ExportPlan(model=Shop)
            tenant_plan = ExportPlan(model=Tenant)

            unsorted_plans = [customer_plan, shop_plan, tenant_plan]

            # Exercise
            sorted_plans = ExportPlan.sort_by_dependencies(unsorted_plans)

            # Verify
            assert len(sorted_plans) == 3
            assert sorted_plans[0].model == Tenant  # No dependencies
            assert sorted_plans[1].model == Shop  # Depends on Tenant
            assert sorted_plans[2].model == Customer  # Depends on Shop

    def test_handles_self_referential_models(self):
        """ExportPlan handles models that reference themselves."""

        # Setup
        class Category(models.Model):
            name = models.CharField(max_length=100)
            parent = models.ForeignKey("self", null=True, blank=True, on_delete=models.CASCADE)

            class Meta:
                app_label = "test_export_plan"

        class CategoryImporter(Importer):
            model = Category

            class Columns:
                parent = Category

        with patch.object(Importer, "get_importer_for_model") as mock_get_importer:
            mock_get_importer.return_value = CategoryImporter

            plan = ExportPlan(model=Category)

            # Exercise
            dependencies = plan.get_dependencies()

            # Verify
            assert Category in dependencies
            assert len(dependencies) == 1

    def test_provides_string_representation(self):
        """ExportPlan provides useful string representation."""

        # Setup
        class ExportPlanTestModel(models.Model):
            name = models.CharField(max_length=100)

            class Meta:
                app_label = "test_export_plan"

        # Exercise
        plan_without_query = ExportPlan(model=ExportPlanTestModel)

        from django.db.models.query import QuerySet

        mock_queryset = Mock(spec=QuerySet)
        mock_queryset.model = ExportPlanTestModel
        plan_with_query = ExportPlan(model=ExportPlanTestModel, query=mock_queryset)

        # Verify
        assert "ExportPlan" in str(plan_without_query)
        assert "ExportPlanTestModel" in str(plan_without_query)
        assert "ExportPlan" in str(plan_with_query)
        assert "ExportPlanTestModel" in str(plan_with_query)
        assert "query=" in str(plan_with_query)

    def test_equality_based_on_model_and_query(self):
        """Two ExportPlans are equal if they have same model and query."""

        # Setup
        class ExportPlanTestModel(models.Model):
            name = models.CharField(max_length=100)

            class Meta:
                app_label = "test_export_plan"

        from django.db.models.query import QuerySet

        mock_queryset = Mock(spec=QuerySet)
        mock_queryset.model = ExportPlanTestModel

        # Exercise
        plan1 = ExportPlan(model=ExportPlanTestModel, query=mock_queryset)
        plan2 = ExportPlan(model=ExportPlanTestModel, query=mock_queryset)
        plan3 = ExportPlan(model=ExportPlanTestModel)  # Different (no query)

        # Verify
        assert plan1 == plan2
        assert plan1 != plan3
