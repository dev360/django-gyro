"""
Tests for CircularDependencyResolver service.

CircularDependencyResolver handles detection and resolution of circular
FK dependencies between Django models during import operations.
"""

from unittest.mock import Mock

from django.db import models

from django_gyro.importing import CircularDependencyResolver


class TestCircularDependencyResolver:
    """Tests for CircularDependencyResolver service behavior."""

    def test_detects_simple_circular_dependency(self):
        """CircularDependencyResolver detects circular FK relationships."""

        # Setup
        class Asset(models.Model):
            risk = models.ForeignKey("AssetRisk", on_delete=models.CASCADE, null=True)
            name = models.CharField(max_length=100)

            class Meta:
                app_label = "test"

        class AssetRisk(models.Model):
            asset = models.ForeignKey(Asset, on_delete=models.CASCADE)
            risk_level = models.CharField(max_length=50)

            class Meta:
                app_label = "test"

        resolver = CircularDependencyResolver()

        # Exercise
        cycles = resolver.detect_circular_dependencies([Asset, AssetRisk])

        # Verify
        assert len(cycles) == 1
        cycle = cycles[0]
        assert cycle.model_a in [Asset, AssetRisk]
        assert cycle.model_b in [Asset, AssetRisk]
        assert cycle.field_a in ["risk", "asset"]
        assert cycle.field_b in ["risk", "asset"]
        assert cycle.nullable_field == "risk"  # Asset.risk is nullable

    def test_handles_no_circular_dependencies(self):
        """CircularDependencyResolver handles models with no cycles."""

        # Setup
        class Organization(models.Model):
            name = models.CharField(max_length=100)

            class Meta:
                app_label = "test"

        class Asset(models.Model):
            organization = models.ForeignKey(Organization, on_delete=models.CASCADE)
            name = models.CharField(max_length=100)

            class Meta:
                app_label = "test"

        resolver = CircularDependencyResolver()

        # Exercise
        cycles = resolver.detect_circular_dependencies([Organization, Asset])

        # Verify
        assert len(cycles) == 0

    def test_resolves_loading_order_with_cycles(self):
        """CircularDependencyResolver orders models to handle cycles."""

        # Setup
        class Asset(models.Model):
            risk = models.ForeignKey("AssetRisk", on_delete=models.CASCADE, null=True)
            name = models.CharField(max_length=100)

            class Meta:
                app_label = "test"

        class AssetRisk(models.Model):
            asset = models.ForeignKey(Asset, on_delete=models.CASCADE)
            risk_level = models.CharField(max_length=50)

            class Meta:
                app_label = "test"

        resolver = CircularDependencyResolver()

        # Exercise
        load_order = resolver.resolve_loading_order([Asset, AssetRisk])

        # Verify - Asset should come first since it has the nullable FK
        assert load_order[0] == Asset
        assert load_order[1] == AssetRisk

    def test_prepares_deferred_updates(self):
        """CircularDependencyResolver prepares FK updates for cycles."""

        # Setup
        class Asset(models.Model):
            risk = models.ForeignKey("AssetRisk", on_delete=models.CASCADE, null=True)
            name = models.CharField(max_length=100)

            class Meta:
                app_label = "test"

        class AssetRisk(models.Model):
            asset = models.ForeignKey(Asset, on_delete=models.CASCADE)
            risk_level = models.CharField(max_length=50)

            class Meta:
                app_label = "test"

        resolver = CircularDependencyResolver()
        cycles = resolver.detect_circular_dependencies([Asset, AssetRisk])

        # Mock CSV data
        csv_data = {"test_asset": [{"id": 1, "name": "Server", "risk": 10}, {"id": 2, "name": "Database", "risk": 20}]}

        # Exercise
        updates = resolver.prepare_deferred_updates(cycles, csv_data)

        # Verify
        assert len(updates) == 2
        assert updates[0]["model"] == Asset
        assert updates[0]["pk"] == 1
        assert updates[0]["field"] == "risk"
        assert updates[0]["value"] == 10

    def test_executes_deferred_updates_with_remapping(self):
        """CircularDependencyResolver executes deferred updates with ID remapping."""

        # Setup
        class Asset(models.Model):
            risk = models.ForeignKey("AssetRisk", on_delete=models.CASCADE, null=True)
            name = models.CharField(max_length=100)

            class Meta:
                app_label = "test"
                db_table = "test_asset"

        class AssetRisk(models.Model):
            asset = models.ForeignKey(Asset, on_delete=models.CASCADE)
            risk_level = models.CharField(max_length=50)

            class Meta:
                app_label = "test"
                db_table = "test_assetrisk"

        resolver = CircularDependencyResolver()

        # Mock connection and cursor
        mock_connection = Mock()
        mock_cursor = Mock()
        mock_cursor.__enter__ = Mock(return_value=mock_cursor)
        mock_cursor.__exit__ = Mock(return_value=None)
        mock_connection.cursor.return_value = mock_cursor

        # Mock updates and ID mappings
        updates = [{"model": Asset, "pk": 1, "field": "risk", "value": 10}]

        id_mappings = {
            "test.Asset": {1: 100},  # Asset ID 1 -> 100
            "test.AssetRisk": {10: 200},  # AssetRisk ID 10 -> 200
        }

        # Exercise
        resolver.execute_deferred_updates(updates, mock_connection, id_mappings)

        # Verify
        mock_cursor.execute.assert_called_once()
        sql, params = mock_cursor.execute.call_args[0]
        assert "UPDATE test_asset SET risk = %s WHERE id = %s" in sql
        assert params == [200, 100]  # Remapped FK and PK values

    def test_handles_cycles_without_nullable_fields(self):
        """CircularDependencyResolver handles cycles where no field is nullable."""

        # Setup
        class ModelA(models.Model):
            b_ref = models.ForeignKey("ModelB", on_delete=models.CASCADE)
            name = models.CharField(max_length=100)

            class Meta:
                app_label = "test"

        class ModelB(models.Model):
            a_ref = models.ForeignKey(ModelA, on_delete=models.CASCADE)
            name = models.CharField(max_length=100)

            class Meta:
                app_label = "test"

        resolver = CircularDependencyResolver()

        # Exercise
        cycles = resolver.detect_circular_dependencies([ModelA, ModelB])

        # Verify
        assert len(cycles) == 1
        assert cycles[0].nullable_field is None  # No nullable field

    def test_detects_multiple_circular_dependencies(self):
        """CircularDependencyResolver detects multiple independent cycles."""

        # Setup
        class Asset(models.Model):
            risk = models.ForeignKey("AssetRisk", on_delete=models.CASCADE, null=True)

            class Meta:
                app_label = "test"

        class AssetRisk(models.Model):
            asset = models.ForeignKey(Asset, on_delete=models.CASCADE)

            class Meta:
                app_label = "test"

        class User(models.Model):
            manager = models.ForeignKey("self", on_delete=models.CASCADE, null=True)

            class Meta:
                app_label = "test"

        class Group(models.Model):
            leader = models.ForeignKey("Member", on_delete=models.CASCADE, null=True)

            class Meta:
                app_label = "test"

        class Member(models.Model):
            group = models.ForeignKey(Group, on_delete=models.CASCADE)

            class Meta:
                app_label = "test"

        resolver = CircularDependencyResolver()

        # Exercise
        cycles = resolver.detect_circular_dependencies([Asset, AssetRisk, User, Group, Member])

        # Verify
        assert len(cycles) == 2  # Asset<->AssetRisk and Group<->Member

        # Verify the cycles are correctly identified
        cycle_models = set()
        for cycle in cycles:
            cycle_models.add((cycle.model_a, cycle.model_b))
            cycle_models.add((cycle.model_b, cycle.model_a))

        assert (Asset, AssetRisk) in cycle_models or (AssetRisk, Asset) in cycle_models
        assert (Group, Member) in cycle_models or (Member, Group) in cycle_models

    def test_ignores_self_referential_foreign_keys(self):
        """CircularDependencyResolver ignores self-referential FKs (not circular)."""

        # Setup
        class User(models.Model):
            manager = models.ForeignKey("self", on_delete=models.CASCADE, null=True)
            name = models.CharField(max_length=100)

            class Meta:
                app_label = "test"

        resolver = CircularDependencyResolver()

        # Exercise
        cycles = resolver.detect_circular_dependencies([User])

        # Verify - self-referential FKs are not considered circular dependencies
        assert len(cycles) == 0
