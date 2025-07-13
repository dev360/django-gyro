"""
Tests for ImportPlan value object.

ImportPlan represents a plan for importing data from a CSV file
with dependencies and remapping capabilities.
"""

from pathlib import Path
from unittest.mock import Mock

import pytest
from django.db import models

from django_gyro.importing import ImportPlan, SequentialRemappingStrategy


class TestImportPlan:
    """Tests for ImportPlan value object behavior."""

    def setup_method(self):
        """Clear the registry before each test."""
        from .test_utils import clear_django_gyro_registries

        clear_django_gyro_registries()

    def teardown_method(self):
        """Clean up after each test."""
        from .test_utils import clear_django_gyro_registries

        clear_django_gyro_registries()

    def test_creates_with_model_and_csv_path(self):
        """ImportPlan requires a model and CSV path."""

        # Setup
        class ImportPlanTestModel(models.Model):
            name = models.CharField(max_length=100)

            class Meta:
                app_label = "test_import_plan"

        import tempfile

        with tempfile.TemporaryDirectory() as temp_dir:
            csv_path = Path(temp_dir) / "test.csv"
            csv_path.touch()

            # Exercise
            plan = ImportPlan(model=ImportPlanTestModel, csv_path=csv_path)

            # Verify
            assert plan.model == ImportPlanTestModel
            assert plan.csv_path == csv_path
            assert plan.dependencies == []
            assert plan.id_remapping_strategy is None

    def test_provides_model_label(self):
        """ImportPlan provides a convenient model label."""

        # Setup
        class ImportPlanTestModel(models.Model):
            name = models.CharField(max_length=100)

            class Meta:
                app_label = "test_import_plan"

        import tempfile

        with tempfile.TemporaryDirectory() as temp_dir:
            csv_path = Path(temp_dir) / "test.csv"
            csv_path.touch()

            plan = ImportPlan(model=ImportPlanTestModel, csv_path=csv_path)

            # Exercise
            label = plan.model_label

            # Verify
            assert label == "test_import_plan.ImportPlanTestModel"

    def test_can_have_dependencies(self):
        """ImportPlan can depend on other ImportPlans."""

        # Setup
        class ImportPlanTenant(models.Model):
            name = models.CharField(max_length=100)

            class Meta:
                app_label = "test_import_plan"

        class ImportPlanShop(models.Model):
            tenant = models.ForeignKey(ImportPlanTenant, on_delete=models.CASCADE)
            name = models.CharField(max_length=100)

            class Meta:
                app_label = "test_import_plan"

        import tempfile

        with tempfile.TemporaryDirectory() as temp_dir:
            tenant_csv = Path(temp_dir) / "tenant.csv"
            shop_csv = Path(temp_dir) / "shop.csv"
            tenant_csv.touch()
            shop_csv.touch()

            tenant_plan = ImportPlan(model=ImportPlanTenant, csv_path=tenant_csv)
            shop_plan = ImportPlan(model=ImportPlanShop, csv_path=shop_csv, dependencies=[tenant_plan])

            # Exercise & Verify
            assert len(shop_plan.dependencies) == 1
            assert shop_plan.dependencies[0] == tenant_plan

    def test_can_be_configured_with_remapping_strategy(self):
        """ImportPlan can have a specific ID remapping strategy."""

        # Setup
        class ImportPlanTestModel(models.Model):
            name = models.CharField(max_length=100)

            class Meta:
                app_label = "test_import_plan"

        import tempfile

        with tempfile.TemporaryDirectory() as temp_dir:
            csv_path = Path(temp_dir) / "test.csv"
            csv_path.touch()

            strategy = Mock(spec=SequentialRemappingStrategy)
            plan = ImportPlan(model=ImportPlanTestModel, csv_path=csv_path, id_remapping_strategy=strategy)

            # Exercise & Verify
            assert plan.id_remapping_strategy is strategy

    def test_validates_csv_file_exists(self):
        """ImportPlan validates that the CSV file exists."""

        # Setup
        class ImportPlanTestModel(models.Model):
            name = models.CharField(max_length=100)

            class Meta:
                app_label = "test_import_plan"

        non_existent_csv = Path("/definitely/does/not/exist.csv")

        # Exercise & Verify
        with pytest.raises(ValueError, match="CSV file does not exist"):
            ImportPlan(model=ImportPlanTestModel, csv_path=non_existent_csv)

    def test_discovers_foreign_key_dependencies(self):
        """ImportPlan can discover dependencies from model foreign keys."""

        # Setup
        class ImportPlanTenant(models.Model):
            name = models.CharField(max_length=100)

            class Meta:
                app_label = "test_import_plan"

        class ImportPlanShop(models.Model):
            tenant = models.ForeignKey(ImportPlanTenant, on_delete=models.CASCADE)
            name = models.CharField(max_length=100)

            class Meta:
                app_label = "test_import_plan"

        import tempfile

        with tempfile.TemporaryDirectory() as temp_dir:
            csv_path = Path(temp_dir) / "shop.csv"
            csv_path.touch()

            # Exercise
            plan = ImportPlan(model=ImportPlanShop, csv_path=csv_path)
            fk_dependencies = plan.discover_foreign_key_dependencies()

            # Verify
            assert ImportPlanTenant in fk_dependencies
            assert len(fk_dependencies) == 1

    def test_calculates_import_order_weight(self):
        """ImportPlan calculates weight for dependency ordering."""

        # Setup
        class ImportPlanTenant(models.Model):
            name = models.CharField(max_length=100)

            class Meta:
                app_label = "test_import_plan"

        class ImportPlanShop(models.Model):
            tenant = models.ForeignKey(ImportPlanTenant, on_delete=models.CASCADE)
            name = models.CharField(max_length=100)

            class Meta:
                app_label = "test_import_plan"

        import tempfile

        with tempfile.TemporaryDirectory() as temp_dir:
            tenant_csv = Path(temp_dir) / "tenant.csv"
            shop_csv = Path(temp_dir) / "shop.csv"
            tenant_csv.touch()
            shop_csv.touch()

            tenant_plan = ImportPlan(model=ImportPlanTenant, csv_path=tenant_csv)
            shop_plan = ImportPlan(model=ImportPlanShop, csv_path=shop_csv, dependencies=[tenant_plan])

            # Exercise
            tenant_weight = tenant_plan.calculate_import_weight()
            shop_weight = shop_plan.calculate_import_weight()

            # Verify
            assert tenant_weight == 0  # No dependencies
            assert shop_weight == 1  # One dependency

    def test_estimates_row_count_from_csv(self):
        """ImportPlan can estimate row count from CSV file."""

        # Setup
        class ImportPlanTestModel(models.Model):
            name = models.CharField(max_length=100)

            class Meta:
                app_label = "test_import_plan"

        import tempfile

        with tempfile.TemporaryDirectory() as temp_dir:
            csv_path = Path(temp_dir) / "test.csv"
            with open(csv_path, "w") as f:
                f.write("name,email\n")
                f.write("John,john@example.com\n")
                f.write("Jane,jane@example.com\n")
                f.write("Bob,bob@example.com\n")

            plan = ImportPlan(model=ImportPlanTestModel, csv_path=csv_path)

            # Exercise
            row_count = plan.estimate_row_count()

            # Verify
            assert row_count == 3  # 3 data rows (excluding header)

    def test_equality_based_on_model_and_path(self):
        """Two ImportPlans are equal if they have same model and CSV path."""

        # Setup
        class ImportPlanTestModel(models.Model):
            name = models.CharField(max_length=100)

            class Meta:
                app_label = "test_import_plan"

        import tempfile

        with tempfile.TemporaryDirectory() as temp_dir:
            csv_path = Path(temp_dir) / "test.csv"
            csv_path.touch()

            plan1 = ImportPlan(model=ImportPlanTestModel, csv_path=csv_path)
            plan2 = ImportPlan(model=ImportPlanTestModel, csv_path=csv_path)

            # Exercise & Verify
            assert plan1 == plan2

    def test_can_be_used_as_dependency(self):
        """ImportPlan can be used as a dependency in other plans."""

        # Setup
        class ImportPlanTenant(models.Model):
            name = models.CharField(max_length=100)

            class Meta:
                app_label = "test_import_plan"

        class ImportPlanShop(models.Model):
            tenant = models.ForeignKey(ImportPlanTenant, on_delete=models.CASCADE)
            name = models.CharField(max_length=100)

            class Meta:
                app_label = "test_import_plan"

        import tempfile

        with tempfile.TemporaryDirectory() as temp_dir:
            tenant_csv = Path(temp_dir) / "tenant.csv"
            shop_csv = Path(temp_dir) / "shop.csv"
            tenant_csv.touch()
            shop_csv.touch()

            tenant_plan = ImportPlan(model=ImportPlanTenant, csv_path=tenant_csv)
            shop_plan = ImportPlan(model=ImportPlanShop, csv_path=shop_csv, dependencies=[tenant_plan])

            # Exercise & Verify
            assert tenant_plan in shop_plan.dependencies
            assert shop_plan.has_dependency(tenant_plan)

    def test_provides_string_representation(self):
        """ImportPlan provides useful string representation."""

        # Setup
        class ImportPlanTestModel(models.Model):
            name = models.CharField(max_length=100)

            class Meta:
                app_label = "test_import_plan"

        import tempfile

        with tempfile.TemporaryDirectory() as temp_dir:
            csv_path = Path(temp_dir) / "test.csv"
            csv_path.touch()

            plan = ImportPlan(model=ImportPlanTestModel, csv_path=csv_path)

            # Exercise
            string_repr = str(plan)

            # Verify
            assert "ImportPlan" in string_repr
            assert "ImportPlanTestModel" in string_repr
            assert "test.csv" in string_repr
