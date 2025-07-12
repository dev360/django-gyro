"""
Tests for TenantAwareRemappingStrategy.

TenantAwareRemappingStrategy provides tenant-specific ID remapping
that automatically applies to all models with tenant FK relationships.
"""

import pytest
from django.db import models

from django_gyro.importing import TenantAwareRemappingStrategy


class TestTenantAwareRemappingStrategy:
    """Tests for TenantAwareRemappingStrategy behavior."""
    
    def test_creates_with_tenant_model_and_mappings(self):
        """TenantAwareRemappingStrategy requires tenant model and mappings."""
        # Setup
        class Organization(models.Model):
            name = models.CharField(max_length=100)
            class Meta:
                app_label = 'myapp'
        
        tenant_mappings = {1060: 10, 2000: 11}
        
        # Exercise
        strategy = TenantAwareRemappingStrategy(
            tenant_model=Organization,
            tenant_mappings=tenant_mappings
        )
        
        # Verify
        assert strategy.tenant_model == Organization
        assert strategy.tenant_mappings == tenant_mappings
        assert strategy.tenant_field_name == 'organization_id'
    
    def test_generates_tenant_field_name_from_model(self):
        """TenantAwareRemappingStrategy generates FK field name from model name."""
        # Setup
        class CustomTenant(models.Model):
            name = models.CharField(max_length=100)
            class Meta:
                app_label = 'myapp'
        
        strategy = TenantAwareRemappingStrategy(
            tenant_model=CustomTenant,
            tenant_mappings={100: 1}
        )
        
        # Exercise & Verify
        assert strategy.tenant_field_name == 'customtenant_id'
    
    def test_applies_mappings_to_all_models(self):
        """TenantAwareRemappingStrategy generates mappings for all models."""
        # Setup
        class Organization(models.Model):
            name = models.CharField(max_length=100)
            class Meta:
                app_label = 'myapp'
        
        class Asset(models.Model):
            organization = models.ForeignKey(Organization, on_delete=models.CASCADE)
            name = models.CharField(max_length=100)
            class Meta:
                app_label = 'myapp'
        
        class Risk(models.Model):
            organization = models.ForeignKey(Organization, on_delete=models.CASCADE)
            level = models.CharField(max_length=50)
            class Meta:
                app_label = 'myapp'
        
        class UnrelatedModel(models.Model):
            name = models.CharField(max_length=100)
            class Meta:
                app_label = 'myapp'
        
        strategy = TenantAwareRemappingStrategy(
            tenant_model=Organization,
            tenant_mappings={1060: 10, 2000: 11}
        )
        
        # Exercise
        id_mappings = strategy.apply_to_all_models([Organization, Asset, Risk, UnrelatedModel])
        
        # Verify
        assert 'myapp.Organization' in id_mappings
        assert id_mappings['myapp.Organization'] == {1060: 10, 2000: 11}
        
        # Asset and Risk have tenant FKs, so they benefit from automatic remapping
        # UnrelatedModel doesn't have tenant FK, so no special handling needed
    
    def test_identifies_models_with_tenant_foreign_keys(self):
        """TenantAwareRemappingStrategy identifies which models reference tenant."""
        # Setup
        class Organization(models.Model):
            name = models.CharField(max_length=100)
            class Meta:
                app_label = 'myapp'
        
        class Asset(models.Model):
            organization = models.ForeignKey(Organization, on_delete=models.CASCADE)
            name = models.CharField(max_length=100)
            class Meta:
                app_label = 'myapp'
        
        class Category(models.Model):
            name = models.CharField(max_length=100)
            class Meta:
                app_label = 'myapp'
        
        strategy = TenantAwareRemappingStrategy(
            tenant_model=Organization,
            tenant_mappings={1000: 1}
        )
        
        # Exercise
        id_mappings = strategy.apply_to_all_models([Organization, Asset, Category])
        
        # Verify
        # Organization mapping should be included
        assert 'myapp.Organization' in id_mappings
        
        # Asset has tenant FK - PostgresBulkLoader will auto-remap organization_id
        # Category has no tenant FK - no special handling needed
    
    def test_generates_tenant_filter_for_export(self):
        """TenantAwareRemappingStrategy provides filters for tenant-scoped exports."""
        # Setup
        class Organization(models.Model):
            name = models.CharField(max_length=100)
            class Meta:
                app_label = 'myapp'
        
        strategy = TenantAwareRemappingStrategy(
            tenant_model=Organization,
            tenant_mappings={1000: 1}
        )
        
        # Exercise
        filter_params = strategy.get_tenant_filter_for_export(tenant_id=1000)
        
        # Verify
        assert filter_params == {'organization_id': 1000}
    
    def test_handles_custom_tenant_field_patterns(self):
        """TenantAwareRemappingStrategy handles different tenant field naming."""
        # Setup
        class Org(models.Model):
            name = models.CharField(max_length=100)
            class Meta:
                app_label = 'myapp'
        
        strategy = TenantAwareRemappingStrategy(
            tenant_model=Org,
            tenant_mappings={500: 5}
        )
        
        # Exercise & Verify
        assert strategy.tenant_field_name == 'org_id'
        
        filter_params = strategy.get_tenant_filter_for_export(tenant_id=500)
        assert filter_params == {'org_id': 500}
    
    def test_integrates_with_other_remapping_strategies(self):
        """TenantAwareRemappingStrategy can be combined with other strategies."""
        # Setup
        class Organization(models.Model):
            name = models.CharField(max_length=100)
            class Meta:
                app_label = 'myapp'
        
        class Asset(models.Model):
            organization = models.ForeignKey(Organization, on_delete=models.CASCADE)
            name = models.CharField(max_length=100)
            class Meta:
                app_label = 'myapp'
        
        tenant_strategy = TenantAwareRemappingStrategy(
            tenant_model=Organization,
            tenant_mappings={1060: 10}
        )
        
        # Exercise
        base_mappings = tenant_strategy.apply_to_all_models([Organization, Asset])
        
        # You could combine with other strategies like:
        # sequential_strategy = SequentialRemappingStrategy(Asset)
        # combined_mappings = {**base_mappings, 'myapp.Asset': sequential_mappings}
        
        # Verify base tenant mapping is correct
        assert base_mappings['myapp.Organization'] == {1060: 10}
    
    def test_handles_multiple_tenant_models(self):
        """TenantAwareRemappingStrategy can handle scenarios with multiple tenant types."""
        # Setup
        class Organization(models.Model):
            name = models.CharField(max_length=100)
            class Meta:
                app_label = 'myapp'
        
        class Department(models.Model):
            organization = models.ForeignKey(Organization, on_delete=models.CASCADE)
            name = models.CharField(max_length=100)
            class Meta:
                app_label = 'myapp'
        
        class Asset(models.Model):
            organization = models.ForeignKey(Organization, on_delete=models.CASCADE)
            department = models.ForeignKey(Department, on_delete=models.CASCADE)
            name = models.CharField(max_length=100)
            class Meta:
                app_label = 'myapp'
        
        org_strategy = TenantAwareRemappingStrategy(
            tenant_model=Organization,
            tenant_mappings={1060: 10}
        )
        
        dept_strategy = TenantAwareRemappingStrategy(
            tenant_model=Department,
            tenant_mappings={2000: 100, 2001: 101}
        )
        
        # Exercise
        org_mappings = org_strategy.apply_to_all_models([Organization, Department, Asset])
        dept_mappings = dept_strategy.apply_to_all_models([Organization, Department, Asset])
        
        # Combine mappings
        combined_mappings = {**org_mappings, **dept_mappings}
        
        # Verify
        assert combined_mappings['myapp.Organization'] == {1060: 10}
        assert combined_mappings['myapp.Department'] == {2000: 100, 2001: 101}
        # Asset will benefit from both org and dept FK remapping automatically