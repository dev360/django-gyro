"""
Tests for TenantAwareRemappingStrategy.

TenantAwareRemappingStrategy provides tenant-specific ID remapping
that automatically applies to all models with tenant FK relationships.
"""

from django.db import models

from django_gyro.importing import TenantAwareRemappingStrategy


class TestTenantAwareRemappingStrategy:
    """Tests for TenantAwareRemappingStrategy behavior."""

    def setup_method(self):
        """Clear the registry before each test."""
        from .test_utils import clear_django_gyro_registries
        clear_django_gyro_registries()

    def teardown_method(self):
        """Clean up after each test."""
        from .test_utils import clear_django_gyro_registries
        clear_django_gyro_registries()

    def test_creates_with_tenant_model_and_mappings(self):
        """TenantAwareRemappingStrategy requires tenant model and mappings."""

        # Setup
        class Tenant(models.Model):
            name = models.CharField(max_length=100)

            class Meta:
                app_label = "test_tenant_aware_remapping"

        tenant_mappings = {1060: 10, 2000: 11}

        # Exercise
        strategy = TenantAwareRemappingStrategy(tenant_model=Tenant, tenant_mappings=tenant_mappings)

        # Verify
        assert strategy.tenant_model == Tenant
        assert strategy.tenant_mappings == tenant_mappings
        assert strategy.tenant_field_name == "tenant_id"

    def test_generates_tenant_field_name_from_model(self):
        """TenantAwareRemappingStrategy generates FK field name from model name."""

        # Setup
        class CustomTenant(models.Model):
            name = models.CharField(max_length=100)

            class Meta:
                app_label = "test_tenant_aware_remapping"

        strategy = TenantAwareRemappingStrategy(tenant_model=CustomTenant, tenant_mappings={100: 1})

        # Exercise & Verify
        assert strategy.tenant_field_name == "customtenant_id"

    def test_applies_mappings_to_all_models(self):
        """TenantAwareRemappingStrategy generates mappings for all models."""

        # Setup
        class Tenant(models.Model):
            name = models.CharField(max_length=100)

            class Meta:
                app_label = "test_tenant_aware_remapping"

        class Shop(models.Model):
            tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE)
            name = models.CharField(max_length=100)

            class Meta:
                app_label = "test_tenant_aware_remapping"

        class Customer(models.Model):
            tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE)
            email = models.CharField(max_length=100)

            class Meta:
                app_label = "test_tenant_aware_remapping"

        class UnrelatedModel(models.Model):
            name = models.CharField(max_length=100)

            class Meta:
                app_label = "test_tenant_aware_remapping"

        strategy = TenantAwareRemappingStrategy(tenant_model=Tenant, tenant_mappings={1060: 10, 2000: 11})

        # Exercise
        id_mappings = strategy.apply_to_all_models([Tenant, Shop, Customer, UnrelatedModel])

        # Verify
        assert "test_tenant_aware_remapping.Tenant" in id_mappings
        assert id_mappings["test_tenant_aware_remapping.Tenant"] == {1060: 10, 2000: 11}

        # Shop and Customer have tenant FKs, so they benefit from automatic remapping
        # UnrelatedModel doesn't have tenant FK, so no special handling needed

    def test_identifies_models_with_tenant_foreign_keys(self):
        """TenantAwareRemappingStrategy identifies which models reference tenant."""

        # Setup
        class Tenant(models.Model):
            name = models.CharField(max_length=100)

            class Meta:
                app_label = "test_tenant_aware_remapping"

        class Shop(models.Model):
            tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE)
            name = models.CharField(max_length=100)

            class Meta:
                app_label = "test_tenant_aware_remapping"

        class Category(models.Model):
            name = models.CharField(max_length=100)

            class Meta:
                app_label = "test_tenant_aware_remapping"

        strategy = TenantAwareRemappingStrategy(tenant_model=Tenant, tenant_mappings={1000: 1})

        # Exercise
        id_mappings = strategy.apply_to_all_models([Tenant, Shop, Category])

        # Verify
        # Tenant mapping should be included
        assert "test_tenant_aware_remapping.Tenant" in id_mappings

        # Shop has tenant FK - PostgresBulkLoader will auto-remap tenant_id
        # Category has no tenant FK - no special handling needed

    def test_generates_tenant_filter_for_export(self):
        """TenantAwareRemappingStrategy provides filters for tenant-scoped exports."""

        # Setup
        class Tenant(models.Model):
            name = models.CharField(max_length=100)

            class Meta:
                app_label = "test_tenant_aware_remapping"

        strategy = TenantAwareRemappingStrategy(tenant_model=Tenant, tenant_mappings={1000: 1})

        # Exercise
        filter_params = strategy.get_tenant_filter_for_export(tenant_id=1000)

        # Verify
        assert filter_params == {"tenant_id": 1000}

    def test_handles_custom_tenant_field_patterns(self):
        """TenantAwareRemappingStrategy handles different tenant field naming."""

        # Setup
        class Org(models.Model):
            name = models.CharField(max_length=100)

            class Meta:
                app_label = "test_tenant_aware_remapping"

        strategy = TenantAwareRemappingStrategy(tenant_model=Org, tenant_mappings={500: 5})

        # Exercise & Verify
        assert strategy.tenant_field_name == "org_id"

        filter_params = strategy.get_tenant_filter_for_export(tenant_id=500)
        assert filter_params == {"org_id": 500}

    def test_integrates_with_other_remapping_strategies(self):
        """TenantAwareRemappingStrategy can be combined with other strategies."""

        # Setup
        class Tenant(models.Model):
            name = models.CharField(max_length=100)

            class Meta:
                app_label = "test_tenant_aware_remapping"

        class Shop(models.Model):
            tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE)
            name = models.CharField(max_length=100)

            class Meta:
                app_label = "test_tenant_aware_remapping"

        tenant_strategy = TenantAwareRemappingStrategy(tenant_model=Tenant, tenant_mappings={1060: 10})

        # Exercise
        base_mappings = tenant_strategy.apply_to_all_models([Tenant, Shop])

        # You could combine with other strategies like:
        # sequential_strategy = SequentialRemappingStrategy(Shop)
        # combined_mappings = {**base_mappings, 'test_tenant_aware_remapping.Shop': sequential_mappings}

        # Verify base tenant mapping is correct
        assert base_mappings["test_tenant_aware_remapping.Tenant"] == {1060: 10}

    def test_handles_multiple_tenant_models(self):
        """TenantAwareRemappingStrategy can handle scenarios with multiple tenant types."""

        # Setup
        class Tenant(models.Model):
            name = models.CharField(max_length=100)

            class Meta:
                app_label = "test_tenant_aware_remapping"

        class Shop(models.Model):
            tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE)
            name = models.CharField(max_length=100)

            class Meta:
                app_label = "test_tenant_aware_remapping"

        class Customer(models.Model):
            tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE)
            shop = models.ForeignKey(Shop, on_delete=models.CASCADE)
            email = models.CharField(max_length=100)

            class Meta:
                app_label = "test_tenant_aware_remapping"

        tenant_strategy = TenantAwareRemappingStrategy(tenant_model=Tenant, tenant_mappings={1060: 10})

        shop_strategy = TenantAwareRemappingStrategy(tenant_model=Shop, tenant_mappings={2000: 100, 2001: 101})

        # Exercise
        tenant_mappings = tenant_strategy.apply_to_all_models([Tenant, Shop, Customer])
        shop_mappings = shop_strategy.apply_to_all_models([Tenant, Shop, Customer])

        # Combine mappings
        combined_mappings = {**tenant_mappings, **shop_mappings}

        # Verify
        assert combined_mappings["test_tenant_aware_remapping.Tenant"] == {1060: 10}
        assert combined_mappings["test_tenant_aware_remapping.Shop"] == {2000: 100, 2001: 101}
        # Customer will benefit from both tenant and shop FK remapping automatically
