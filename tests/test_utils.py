"""
Test utilities for Django Gyro tests.

This module provides utilities for proper test isolation, including
clearing all Django Gyro registries and Django model registries between tests.
It also provides database mocking utilities to prevent geo_db_type and other
database connectivity errors in tests.

SOLUTION TO MODEL REGISTRATION CONFLICTS:
==========================================

The main issue causing test failures was Django model registration conflicts.
Multiple test files were defining models with the same names (TestModel, Tenant, etc.),
causing Django's app registry to throw "Conflicting 'X' models" errors when tests
ran together in the same session.

The problem occurs at TWO levels:
1. Django Gyro's own registries (Importer._registry, ImportJob._dependency_cache)
2. Django's core model registry (apps.app_configs)

BEFORE (broken):
- Tests failed with: RuntimeError: Conflicting 'tenant' models in application 'test'
- Required unique model names like BulkLoaderTestModel, ImportPlanTestModel, etc.
- Manual registry clearing was inconsistent and incomplete

AFTER (fixed):
- Tests can use natural names like TestModel, Tenant, Shop
- Each test file uses a unique Django app label
- Django Gyro registries are automatically cleared between tests
- Clean, maintainable test code

SOLUTION COMPONENTS:
===================
1. **Unique app labels per test file**: Each test file uses app_label = "test_filename"
2. **Django Gyro registry clearing**: Automatic clearing of Importer and ImportJob caches
3. **Test mixins/utilities**: Easy-to-use helpers for consistent test isolation

USAGE:
======

For pytest-style tests:
----------------------
from tests.test_utils import clear_django_gyro_registries

class TestMyFeature:
    def setup_method(self):
        clear_django_gyro_registries()

    def teardown_method(self):
        clear_django_gyro_registries()

    def test_something(self):
        class TestModel(models.Model):  # Natural names work!
            name = models.CharField(max_length=100)
            class Meta:
                app_label = 'test_myfeature'  # Unique per test file

For Django TestCase:
-------------------
from tests.test_utils import DjangoGyroTestMixin

class TestMyFeature(DjangoGyroTestMixin, TestCase):
    def test_something(self):
        class TestModel(models.Model):
            name = models.CharField(max_length=100)
            class Meta:
                app_label = 'test_myfeature'  # Unique per test file
"""

from unittest.mock import Mock, patch

from django.db.models.query import QuerySet


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


def clear_django_gyro_registries():
    """
    Clear all Django Gyro registries and caches.

    This should be called in setUp/tearDown of tests to ensure proper
    test isolation and prevent model registration conflicts.

    Clears:
    - Importer._registry: Model to importer mappings
    - ImportJob._dependency_cache: Dependency computation cache
    - ExportPlan._dependency_cache: Export plan dependency cache
    """
    # Import here to avoid circular imports
    from django_gyro import Importer
    from django_gyro.core import ImportJob
    from django_gyro.importing import ExportPlan

    # Clear the main importer registry
    if hasattr(Importer, "_registry"):
        Importer._registry.clear()

    # Clear dependency caches
    if hasattr(ImportJob, "_dependency_cache"):
        ImportJob._dependency_cache.clear()

    if hasattr(ExportPlan, "_dependency_cache"):
        ExportPlan._dependency_cache.clear()


class DjangoGyroTestMixin:
    """
    Mixin class for Django Gyro tests that provides automatic registry cleanup
    and database mocking to prevent connectivity errors.

    Use this mixin in test classes to automatically clear all Django Gyro
    registries before and after each test, ensuring proper test isolation.
    Also patches database connections to prevent geo_db_type errors.

    Example:
        class TestMyFeature(DjangoGyroTestMixin, TestCase):
            def test_something(self):
                # Define models with simple names like TestModel, Tenant, etc.
                class TestModel(models.Model):
                    # ...
    """

    def setUp(self):
        """Clear Django Gyro registries and mock database before each test."""
        super().setUp()
        clear_django_gyro_registries()
        # Patch database connection to prevent geo_db_type errors
        self.db_conn_patcher = patch("django.db.connection", mock_db_connection())
        self.db_conn_patcher.start()

    def tearDown(self):
        """Clear Django Gyro registries and stop database mocking after each test."""
        clear_django_gyro_registries()
        self.db_conn_patcher.stop()
        super().tearDown()


class DatabaseMockingTestMixin:
    """
    Mixin for pytest-style tests that provides database mocking.

    Use this for test classes that don't inherit from Django TestCase.
    """

    def setup_method(self):
        """Mock database connection before each test."""
        clear_django_gyro_registries()
        self.db_conn_patcher = patch("django.db.connection", mock_db_connection())
        self.db_conn_patcher.start()

    def teardown_method(self):
        """Stop database mocking after each test."""
        clear_django_gyro_registries()
        self.db_conn_patcher.stop()
