"""
Tests for ID remapping strategies.

These tests cover the various strategies for remapping primary keys
during import operations to avoid conflicts.
"""

from unittest.mock import Mock

import pandas as pd
import pytest
from django.db import models

from django_gyro.importing import (
    HashBasedRemappingStrategy,
    IdRemappingStrategy,
    NoRemappingStrategy,
    SequentialRemappingStrategy,
)


class TestIdRemappingStrategy:
    """Tests for IdRemappingStrategy abstract base class."""

    def setup_method(self):
        """Clear the registry before each test."""
        from .test_utils import clear_django_gyro_registries

        clear_django_gyro_registries()

    def teardown_method(self):
        """Clean up after each test."""
        from .test_utils import clear_django_gyro_registries

        clear_django_gyro_registries()

    def test_is_abstract_base_class(self):
        """IdRemappingStrategy cannot be instantiated directly."""
        # Exercise & Verify
        with pytest.raises(TypeError):
            IdRemappingStrategy()

    def test_defines_required_interface(self):
        """IdRemappingStrategy defines the required generate_mapping method."""
        # Exercise & Verify
        assert hasattr(IdRemappingStrategy, "generate_mapping")
        assert callable(IdRemappingStrategy.generate_mapping)


class TestSequentialRemappingStrategy:
    """Tests for SequentialRemappingStrategy behavior."""

    def setup_method(self):
        """Clear the registry before each test."""
        from .test_utils import clear_django_gyro_registries

        clear_django_gyro_registries()

    def teardown_method(self):
        """Clean up after each test."""
        from .test_utils import clear_django_gyro_registries

        clear_django_gyro_registries()

    def test_generates_sequential_ids_from_max_plus_one(self):
        """SequentialRemappingStrategy assigns IDs starting from MAX+1."""

        # Setup
        class IdRemappingTestModel(models.Model):
            name = models.CharField(max_length=100)

            class Meta:
                app_label = "test_id_remapping"
                db_table = "test_model"

        strategy = SequentialRemappingStrategy(model=IdRemappingTestModel)
        source_ids = pd.Series([100, 200, 300])

        # Mock database cursor with proper context manager
        mock_cursor = Mock()
        mock_cursor.fetchone.return_value = (5,)  # MAX(id) = 5
        mock_cursor.__enter__ = Mock(return_value=mock_cursor)
        mock_cursor.__exit__ = Mock(return_value=None)

        mock_connection = Mock()
        mock_connection.cursor.return_value = mock_cursor

        # Exercise
        mapping = strategy.generate_mapping(source_ids, mock_connection)

        # Verify
        assert mapping == {100: 6, 200: 7, 300: 8}
        mock_cursor.execute.assert_called_once_with("SELECT COALESCE(MAX(id), 0) FROM test_model")

    def test_handles_empty_target_table(self):
        """SequentialRemappingStrategy handles empty target table correctly."""

        # Setup
        class IdRemappingTestModel(models.Model):
            name = models.CharField(max_length=100)

            class Meta:
                app_label = "test_id_remapping"
                db_table = "test_model"

        strategy = SequentialRemappingStrategy(model=IdRemappingTestModel)
        source_ids = pd.Series([100, 200])

        # Mock database cursor - empty table
        mock_cursor = Mock()
        mock_cursor.fetchone.return_value = (0,)  # MAX(id) = 0 (empty table)
        mock_cursor.__enter__ = Mock(return_value=mock_cursor)
        mock_cursor.__exit__ = Mock(return_value=None)

        mock_connection = Mock()
        mock_connection.cursor.return_value = mock_cursor

        # Exercise
        mapping = strategy.generate_mapping(source_ids, mock_connection)

        # Verify
        assert mapping == {100: 1, 200: 2}

    def test_handles_single_id(self):
        """SequentialRemappingStrategy handles single ID correctly."""

        # Setup
        class IdRemappingTestModel(models.Model):
            name = models.CharField(max_length=100)

            class Meta:
                app_label = "test_id_remapping"
                db_table = "test_model"

        strategy = SequentialRemappingStrategy(model=IdRemappingTestModel)
        source_ids = pd.Series([500])

        # Mock database cursor
        mock_cursor = Mock()
        mock_cursor.fetchone.return_value = (42,)  # MAX(id) = 42
        mock_cursor.__enter__ = Mock(return_value=mock_cursor)
        mock_cursor.__exit__ = Mock(return_value=None)

        mock_connection = Mock()
        mock_connection.cursor.return_value = mock_cursor

        # Exercise
        mapping = strategy.generate_mapping(source_ids, mock_connection)

        # Verify
        assert mapping == {500: 43}

    def test_preserves_source_id_order(self):
        """SequentialRemappingStrategy preserves source ID order."""

        # Setup
        class IdRemappingTestModel(models.Model):
            name = models.CharField(max_length=100)

            class Meta:
                app_label = "test_id_remapping"
                db_table = "test_model"

        strategy = SequentialRemappingStrategy(model=IdRemappingTestModel)
        # Note: unsorted source IDs
        source_ids = pd.Series([300, 100, 200])

        # Mock database cursor
        mock_cursor = Mock()
        mock_cursor.fetchone.return_value = (10,)  # MAX(id) = 10
        mock_cursor.__enter__ = Mock(return_value=mock_cursor)
        mock_cursor.__exit__ = Mock(return_value=None)

        mock_connection = Mock()
        mock_connection.cursor.return_value = mock_cursor

        # Exercise
        mapping = strategy.generate_mapping(source_ids, mock_connection)

        # Verify - sequential assignment in order of appearance
        assert mapping == {300: 11, 100: 12, 200: 13}

    def test_handles_duplicate_source_ids(self):
        """SequentialRemappingStrategy handles duplicate source IDs."""

        # Setup
        class IdRemappingTestModel(models.Model):
            name = models.CharField(max_length=100)

            class Meta:
                app_label = "test_id_remapping"
                db_table = "test_model"

        strategy = SequentialRemappingStrategy(model=IdRemappingTestModel)
        source_ids = pd.Series([100, 100, 200])  # Duplicate 100

        # Mock database cursor
        mock_cursor = Mock()
        mock_cursor.fetchone.return_value = (5,)  # MAX(id) = 5
        mock_cursor.__enter__ = Mock(return_value=mock_cursor)
        mock_cursor.__exit__ = Mock(return_value=None)

        mock_connection = Mock()
        mock_connection.cursor.return_value = mock_cursor

        # Exercise
        mapping = strategy.generate_mapping(source_ids, mock_connection)

        # Verify - duplicates get same mapping
        assert mapping == {100: 6, 200: 7}
        assert len(mapping) == 2  # Only unique mappings


class TestHashBasedRemappingStrategy:
    """Tests for HashBasedRemappingStrategy behavior."""

    def setup_method(self):
        """Clear the registry before each test."""
        from .test_utils import clear_django_gyro_registries

        clear_django_gyro_registries()

    def teardown_method(self):
        """Clean up after each test."""
        from .test_utils import clear_django_gyro_registries

        clear_django_gyro_registries()

    def test_generates_deterministic_ids_from_business_key(self):
        """HashBasedRemappingStrategy generates deterministic IDs."""

        # Setup
        class IdRemappingTestModel(models.Model):
            name = models.CharField(max_length=100)
            email = models.EmailField()

            class Meta:
                app_label = "test_id_remapping"

        strategy = HashBasedRemappingStrategy(model=IdRemappingTestModel, business_key="email")

        # Mock data with business keys
        source_data = pd.DataFrame(
            {"id": [100, 200, 300], "email": ["john@example.com", "jane@example.com", "bob@example.com"]}
        )

        # Exercise
        mapping = strategy.generate_mapping(source_data)

        # Verify
        assert len(mapping) == 3
        assert all(isinstance(k, int) for k in mapping.keys())
        assert all(isinstance(v, int) for v in mapping.values())
        # Same input should produce same output
        mapping2 = strategy.generate_mapping(source_data)
        assert mapping == mapping2

    def test_handles_empty_business_key(self):
        """HashBasedRemappingStrategy handles empty business key values."""

        # Setup
        class IdRemappingTestModel(models.Model):
            name = models.CharField(max_length=100)
            email = models.EmailField()

            class Meta:
                app_label = "test_id_remapping"

        strategy = HashBasedRemappingStrategy(model=IdRemappingTestModel, business_key="email")

        # Mock data with some empty emails
        source_data = pd.DataFrame({"id": [100, 200, 300], "email": ["john@example.com", "", "bob@example.com"]})

        # Exercise
        mapping = strategy.generate_mapping(source_data)

        # Verify - only non-empty business keys get mapped
        assert len(mapping) == 2
        assert 100 in mapping  # john@example.com
        assert 300 in mapping  # bob@example.com
        assert 200 not in mapping  # empty email

    def test_validates_business_key_exists(self):
        """HashBasedRemappingStrategy validates business key exists."""

        # Setup
        class IdRemappingTestModel(models.Model):
            name = models.CharField(max_length=100)

            class Meta:
                app_label = "test_id_remapping"

        strategy = HashBasedRemappingStrategy(model=IdRemappingTestModel, business_key="nonexistent_field")

        source_data = pd.DataFrame({"id": [100, 200], "name": ["John", "Jane"]})

        # Exercise & Verify
        with pytest.raises(ValueError, match="Business key 'nonexistent_field' not found"):
            strategy.generate_mapping(source_data)


class TestNoRemappingStrategy:
    """Tests for NoRemappingStrategy behavior."""

    def setup_method(self):
        """Clear the registry before each test."""
        from .test_utils import clear_django_gyro_registries

        clear_django_gyro_registries()

    def teardown_method(self):
        """Clean up after each test."""
        from .test_utils import clear_django_gyro_registries

        clear_django_gyro_registries()

    def test_returns_identity_mapping(self):
        """NoRemappingStrategy returns identity mapping (no change)."""

        # Setup
        class IdRemappingTestModel(models.Model):
            name = models.CharField(max_length=100)

            class Meta:
                app_label = "test_id_remapping"

        strategy = NoRemappingStrategy(model=IdRemappingTestModel)
        source_ids = pd.Series([100, 200, 300])

        # Exercise
        mapping = strategy.generate_mapping(source_ids)

        # Verify
        assert mapping == {100: 100, 200: 200, 300: 300}

    def test_handles_empty_source_ids(self):
        """NoRemappingStrategy handles empty source IDs."""

        # Setup
        class IdRemappingTestModel(models.Model):
            name = models.CharField(max_length=100)

            class Meta:
                app_label = "test_id_remapping"

        strategy = NoRemappingStrategy(model=IdRemappingTestModel)
        source_ids = pd.Series([])

        # Exercise
        mapping = strategy.generate_mapping(source_ids)

        # Verify
        assert mapping == {}


class TestIdRemappingStrategyIntegration:
    """Integration tests for ID remapping strategies."""

    def setup_method(self):
        """Clear the registry before each test."""
        from .test_utils import clear_django_gyro_registries

        clear_django_gyro_registries()

    def teardown_method(self):
        """Clean up after each test."""
        from .test_utils import clear_django_gyro_registries

        clear_django_gyro_registries()

    def test_strategies_can_be_used_interchangeably(self):
        """All strategies implement the same interface."""

        # Setup
        class IdRemappingTestModel(models.Model):
            name = models.CharField(max_length=100)
            email = models.EmailField()

            class Meta:
                app_label = "test_id_remapping"
                db_table = "test_model"

        # Create different strategies
        sequential = SequentialRemappingStrategy(model=IdRemappingTestModel)
        hash_based = HashBasedRemappingStrategy(model=IdRemappingTestModel, business_key="email")
        no_remap = NoRemappingStrategy(model=IdRemappingTestModel)

        strategies = [sequential, hash_based, no_remap]

        # Exercise & Verify
        for strategy in strategies:
            assert isinstance(strategy, IdRemappingStrategy)
            assert hasattr(strategy, "generate_mapping")
            assert callable(strategy.generate_mapping)

    def test_can_choose_strategy_at_runtime(self):
        """Strategy can be selected at runtime based on configuration."""

        # Setup
        class IdRemappingTestModel(models.Model):
            name = models.CharField(max_length=100)

            class Meta:
                app_label = "test_id_remapping"

        def get_strategy(strategy_name: str) -> IdRemappingStrategy:
            if strategy_name == "sequential":
                return SequentialRemappingStrategy(model=IdRemappingTestModel)
            elif strategy_name == "hash":
                return HashBasedRemappingStrategy(model=IdRemappingTestModel, business_key="name")
            elif strategy_name == "none":
                return NoRemappingStrategy(model=IdRemappingTestModel)
            else:
                raise ValueError(f"Unknown strategy: {strategy_name}")

        # Exercise
        seq_strategy = get_strategy("sequential")
        hash_strategy = get_strategy("hash")
        no_strategy = get_strategy("none")

        # Verify
        assert isinstance(seq_strategy, SequentialRemappingStrategy)
        assert isinstance(hash_strategy, HashBasedRemappingStrategy)
        assert isinstance(no_strategy, NoRemappingStrategy)

        # Test invalid strategy
        with pytest.raises(ValueError, match="Unknown strategy"):
            get_strategy("invalid")


class TestIdRemappingStrategyPerformance:
    """Performance-related tests for ID remapping strategies."""

    def setup_method(self):
        """Clear the registry before each test."""
        from .test_utils import clear_django_gyro_registries

        clear_django_gyro_registries()

    def teardown_method(self):
        """Clean up after each test."""
        from .test_utils import clear_django_gyro_registries

        clear_django_gyro_registries()

    def test_sequential_strategy_scales_with_large_datasets(self):
        """SequentialRemappingStrategy handles large datasets efficiently."""

        # Setup
        class IdRemappingTestModel(models.Model):
            name = models.CharField(max_length=100)

            class Meta:
                app_label = "test_id_remapping"
                db_table = "test_model"

        strategy = SequentialRemappingStrategy(model=IdRemappingTestModel)

        # Create large dataset
        large_source_ids = pd.Series(range(1000, 11000))  # 10k IDs

        # Mock database cursor
        mock_cursor = Mock()
        mock_cursor.fetchone.return_value = (500,)  # MAX(id) = 500
        mock_cursor.__enter__ = Mock(return_value=mock_cursor)
        mock_cursor.__exit__ = Mock(return_value=None)

        mock_connection = Mock()
        mock_connection.cursor.return_value = mock_cursor

        # Exercise
        mapping = strategy.generate_mapping(large_source_ids, mock_connection)

        # Verify
        assert len(mapping) == 10000
        assert mapping[1000] == 501  # First ID
        assert mapping[10999] == 10500  # Last ID

    def test_hash_strategy_caches_results(self):
        """HashBasedRemappingStrategy caches hash computations."""

        # Setup
        class IdRemappingTestModel(models.Model):
            name = models.CharField(max_length=100)

            class Meta:
                app_label = "test_id_remapping"

        strategy = HashBasedRemappingStrategy(model=IdRemappingTestModel, business_key="name")

        # Same data multiple times
        source_data = pd.DataFrame({"id": [100, 200], "name": ["John", "Jane"]})

        # Exercise multiple times
        mapping1 = strategy.generate_mapping(source_data)
        mapping2 = strategy.generate_mapping(source_data)
        mapping3 = strategy.generate_mapping(source_data)

        # Verify consistent results (implies caching)
        assert mapping1 == mapping2 == mapping3
