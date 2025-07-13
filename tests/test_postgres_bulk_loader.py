"""
Tests for PostgresBulkLoader service.

PostgresBulkLoader handles high-performance bulk loading of CSV data
into PostgreSQL using COPY operations with staging tables.
"""

from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from django.db import models

from django_gyro.importing import ImportContext, PostgresBulkLoader

from .test_utils import clear_django_gyro_registries


class TestPostgresBulkLoader:
    """Tests for PostgresBulkLoader service behavior."""

    def setup_method(self):
        """Clear registries before each test."""
        clear_django_gyro_registries()

    def teardown_method(self):
        """Clear registries after each test."""
        clear_django_gyro_registries()

    def test_creates_staging_table_with_same_structure(self):
        """PostgresBulkLoader creates staging table matching target table."""

        # Setup
        class TestModel(models.Model):
            name = models.CharField(max_length=100)
            email = models.EmailField()

            class Meta:
                app_label = "test_postgres_bulk_loader"
                db_table = "test_model"

        loader = PostgresBulkLoader()
        mock_cursor = Mock()

        # Exercise
        loader._create_staging_table(mock_cursor, TestModel)

        # Verify
        mock_cursor.execute.assert_called_once_with(
            "CREATE TEMP TABLE import_staging_test_model (LIKE test_model INCLUDING ALL)"
        )

    def test_copies_csv_data_to_staging_table(self):
        """PostgresBulkLoader copies CSV data to staging table efficiently."""

        # Setup
        class TestModel(models.Model):
            name = models.CharField(max_length=100)
            email = models.EmailField()

            class Meta:
                app_label = "test_postgres_bulk_loader"
                db_table = "test_model"

        loader = PostgresBulkLoader()
        mock_cursor = Mock()

        import tempfile

        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            f.write("name,email\n")
            f.write("John,john@example.com\n")
            f.write("Jane,jane@example.com\n")
            csv_path = Path(f.name)

        try:
            # Exercise
            loader._copy_csv_to_staging(mock_cursor, csv_path, TestModel)

            # Verify
            mock_cursor.copy_expert.assert_called_once()
            call_args = mock_cursor.copy_expert.call_args
            assert "COPY import_staging_test_model FROM STDIN" in call_args[0][0]
            assert "WITH CSV HEADER" in call_args[0][0]
        finally:
            csv_path.unlink()

    def test_applies_foreign_key_remapping_efficiently(self):
        """PostgresBulkLoader applies FK remapping using CASE statements."""

        # Setup
        class Tenant(models.Model):
            name = models.CharField(max_length=100)

            class Meta:
                app_label = "test_postgres_bulk_loader"
                db_table = "tenant"

        class Shop(models.Model):
            tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE)
            name = models.CharField(max_length=100)

            class Meta:
                app_label = "test_postgres_bulk_loader"
                db_table = "shop"

        loader = PostgresBulkLoader()
        mock_cursor = Mock()

        # ID mapping: old_id -> new_id
        tenant_mapping = {1: 10, 2: 20, 3: 30}

        # Exercise
        loader._apply_fk_remapping(mock_cursor, "import_staging_shop", "tenant_id", tenant_mapping)

        # Verify
        mock_cursor.execute.assert_called_once()
        sql = mock_cursor.execute.call_args[0][0]
        assert "UPDATE import_staging_shop SET tenant_id = CASE" in sql
        assert "WHEN tenant_id = 1 THEN 10" in sql
        assert "WHEN tenant_id = 2 THEN 20" in sql
        assert "WHEN tenant_id = 3 THEN 30" in sql
        assert "END WHERE tenant_id IN (1, 2, 3)" in sql

    def test_handles_empty_id_mapping(self):
        """PostgresBulkLoader handles empty ID mappings gracefully."""
        # Setup
        loader = PostgresBulkLoader()
        mock_cursor = Mock()

        # Exercise
        loader._apply_fk_remapping(
            mock_cursor,
            "import_staging_shop",
            "tenant_id",
            {},  # Empty mapping
        )

        # Verify - no SQL should be executed
        mock_cursor.execute.assert_not_called()

    def test_inserts_from_staging_to_target_table(self):
        """PostgresBulkLoader inserts data from staging to target table."""

        # Setup
        class TestModel(models.Model):
            name = models.CharField(max_length=100)
            email = models.EmailField()

            class Meta:
                app_label = "test_postgres_bulk_loader"
                db_table = "test_model"

        loader = PostgresBulkLoader()
        mock_cursor = Mock()

        # Exercise
        loader._insert_from_staging(mock_cursor, TestModel)

        # Verify
        mock_cursor.execute.assert_called_once()
        sql = mock_cursor.execute.call_args[0][0]
        assert "INSERT INTO test_model" in sql
        assert "SELECT * FROM import_staging_test_model" in sql

    def test_handles_duplicate_key_conflicts(self):
        """PostgresBulkLoader handles duplicate key conflicts during insert."""

        # Setup
        class TestModel(models.Model):
            name = models.CharField(max_length=100)
            email = models.EmailField(unique=True)

            class Meta:
                app_label = "test_postgres_bulk_loader"
                db_table = "test_model"

        loader = PostgresBulkLoader()
        mock_cursor = Mock()

        # Exercise
        loader._insert_from_staging(mock_cursor, TestModel, on_conflict="ignore")

        # Verify
        mock_cursor.execute.assert_called_once()
        sql = mock_cursor.execute.call_args[0][0]
        assert "INSERT INTO test_model" in sql
        assert "ON CONFLICT DO NOTHING" in sql

    def test_loads_csv_with_complete_workflow(self):
        """PostgresBulkLoader executes complete CSV loading workflow."""

        # Setup
        class TestModel(models.Model):
            name = models.CharField(max_length=100)
            email = models.EmailField()

            class Meta:
                app_label = "test_postgres_bulk_loader"
                db_table = "test_model"

        loader = PostgresBulkLoader()

        import tempfile

        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            f.write("name,email\n")
            f.write("John,john@example.com\n")
            f.write("Jane,jane@example.com\n")
            csv_path = Path(f.name)

        # Mock database connection
        mock_connection = Mock()
        mock_cursor = Mock()
        mock_cursor.__enter__ = Mock(return_value=mock_cursor)
        mock_cursor.__exit__ = Mock(return_value=None)
        mock_cursor.rowcount = 2  # Mock the rowcount for test data
        mock_connection.cursor.return_value = mock_cursor

        try:
            # Exercise
            result = loader.load_csv_with_copy(model=TestModel, csv_path=csv_path, connection=mock_connection)

            # Verify workflow steps
            assert mock_cursor.execute.call_count >= 3  # Create, Insert, etc.
            assert mock_cursor.copy_expert.call_count == 1  # COPY operation
            assert "rows_loaded" in result
            assert "staging_table" in result
        finally:
            csv_path.unlink()

    def test_applies_id_remapping_during_load(self):
        """PostgresBulkLoader applies ID remapping during load process."""

        # Setup
        class Tenant(models.Model):
            name = models.CharField(max_length=100)

            class Meta:
                app_label = "test_postgres_bulk_loader"
                db_table = "tenant"

        class Shop(models.Model):
            tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE)
            name = models.CharField(max_length=100)

            class Meta:
                app_label = "test_postgres_bulk_loader"
                db_table = "shop"

        loader = PostgresBulkLoader()

        import tempfile

        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            f.write("id,name,tenant_id\n")
            f.write("1,Shop1,100\n")
            f.write("2,Shop2,200\n")
            csv_path = Path(f.name)

        # Mock database connection
        mock_connection = Mock()
        mock_cursor = Mock()
        mock_cursor.__enter__ = Mock(return_value=mock_cursor)
        mock_cursor.__exit__ = Mock(return_value=None)
        mock_cursor.rowcount = 2  # Mock the rowcount for test data
        mock_connection.cursor.return_value = mock_cursor

        # ID mappings
        id_mappings = {
            "test_postgres_bulk_loader.Shop": {1: 10, 2: 20},
            "test_postgres_bulk_loader.Tenant": {100: 1000, 200: 2000},
        }

        try:
            # Exercise
            loader.load_csv_with_copy(
                model=Shop, csv_path=csv_path, connection=mock_connection, id_mappings=id_mappings
            )

            # Verify remapping was applied
            executed_sql = [call[0][0] for call in mock_cursor.execute.call_args_list]
            remapping_sql = [sql for sql in executed_sql if "CASE" in sql]
            assert len(remapping_sql) >= 1  # At least one remapping operation
        finally:
            csv_path.unlink()

    def test_handles_large_csv_files_efficiently(self):
        """PostgresBulkLoader handles large CSV files without memory issues."""

        # Setup
        class TestModel(models.Model):
            name = models.CharField(max_length=100)
            value = models.IntegerField()

            class Meta:
                app_label = "test_postgres_bulk_loader"
                db_table = "test_model"

        loader = PostgresBulkLoader()

        # Create large CSV file
        import tempfile

        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            f.write("name,value\n")
            # Write 1000 rows
            for i in range(1000):
                f.write(f"Row{i},{i}\n")
            csv_path = Path(f.name)

        # Mock database connection
        mock_connection = Mock()
        mock_cursor = Mock()
        mock_cursor.__enter__ = Mock(return_value=mock_cursor)
        mock_cursor.__exit__ = Mock(return_value=None)
        mock_cursor.rowcount = 1000  # Mock the rowcount for large file
        mock_connection.cursor.return_value = mock_cursor

        try:
            # Exercise
            result = loader.load_csv_with_copy(model=TestModel, csv_path=csv_path, connection=mock_connection)

            # Verify
            assert result["rows_loaded"] > 0
            assert "staging_table" in result
        finally:
            csv_path.unlink()

    def test_provides_detailed_error_information(self):
        """PostgresBulkLoader provides detailed error information on failure."""

        # Setup
        class TestModel(models.Model):
            name = models.CharField(max_length=100)

            class Meta:
                app_label = "test_postgres_bulk_loader"
                db_table = "test_model"

        loader = PostgresBulkLoader()

        # Mock database connection that fails
        mock_connection = Mock()
        mock_cursor = Mock()
        mock_cursor.__enter__ = Mock(return_value=mock_cursor)
        mock_cursor.__exit__ = Mock(return_value=None)
        mock_cursor.execute.side_effect = Exception("Database error")
        mock_connection.cursor.return_value = mock_cursor

        import tempfile

        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            f.write("name\n")
            f.write("John\n")
            csv_path = Path(f.name)

        try:
            # Exercise & Verify
            with pytest.raises(Exception) as exc_info:
                loader.load_csv_with_copy(model=TestModel, csv_path=csv_path, connection=mock_connection)

            # Should provide context about the failure
            assert "Database error" in str(exc_info.value)
        finally:
            csv_path.unlink()

    def test_validates_csv_file_exists(self):
        """PostgresBulkLoader validates CSV file existence."""

        # Setup
        class TestModel(models.Model):
            name = models.CharField(max_length=100)

            class Meta:
                app_label = "test_postgres_bulk_loader"
                db_table = "test_model"

        loader = PostgresBulkLoader()
        non_existent_path = Path("/definitely/does/not/exist.csv")

        # Exercise & Verify
        with pytest.raises(FileNotFoundError):
            loader.load_csv_with_copy(model=TestModel, csv_path=non_existent_path, connection=Mock())

    def test_cleans_up_staging_table_on_success(self):
        """PostgresBulkLoader cleans up staging table after successful load."""

        # Setup
        class TestModel(models.Model):
            name = models.CharField(max_length=100)

            class Meta:
                app_label = "test_postgres_bulk_loader"
                db_table = "test_model"

        loader = PostgresBulkLoader()

        import tempfile

        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            f.write("name\n")
            f.write("John\n")
            csv_path = Path(f.name)

        # Mock database connection
        mock_connection = Mock()
        mock_cursor = Mock()
        mock_cursor.__enter__ = Mock(return_value=mock_cursor)
        mock_cursor.__exit__ = Mock(return_value=None)
        mock_connection.cursor.return_value = mock_cursor

        try:
            # Exercise
            loader.load_csv_with_copy(
                model=TestModel, csv_path=csv_path, connection=mock_connection, cleanup_staging=True
            )

            # Verify cleanup
            executed_sql = [call[0][0] for call in mock_cursor.execute.call_args_list]
            cleanup_sql = [sql for sql in executed_sql if "DROP TABLE" in sql]
            assert len(cleanup_sql) >= 1  # At least one DROP TABLE
        finally:
            csv_path.unlink()

    def test_supports_batch_processing(self):
        """PostgresBulkLoader supports batch processing of multiple CSV files."""

        # Setup
        class TestModel(models.Model):
            name = models.CharField(max_length=100)

            class Meta:
                app_label = "test_postgres_bulk_loader"
                db_table = "test_model"

        loader = PostgresBulkLoader()

        # Create multiple CSV files
        import tempfile

        csv_files = []
        for i in range(3):
            with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
                f.write("name\n")
                f.write(f"Name{i}\n")
                csv_files.append(Path(f.name))

        # Mock database connection
        mock_connection = Mock()
        mock_cursor = Mock()
        mock_cursor.__enter__ = Mock(return_value=mock_cursor)
        mock_cursor.__exit__ = Mock(return_value=None)
        mock_connection.cursor.return_value = mock_cursor

        try:
            # Exercise
            results = loader.load_csv_batch(model=TestModel, csv_paths=csv_files, connection=mock_connection)

            # Verify
            assert len(results) == 3
            assert all("rows_loaded" in result for result in results)
        finally:
            for csv_file in csv_files:
                csv_file.unlink()


class TestPostgresBulkLoaderIntegration:
    """Integration tests for PostgresBulkLoader with other components."""

    def test_integrates_with_import_context(self):
        """PostgresBulkLoader integrates with ImportContext for configuration."""

        # Setup
        class TestModel(models.Model):
            name = models.CharField(max_length=100)

            class Meta:
                app_label = "test_postgres_bulk_loader"
                db_table = "test_model"

        import tempfile

        with tempfile.TemporaryDirectory() as temp_dir:
            csv_path = Path(temp_dir) / "test.csv"
            with open(csv_path, "w") as f:
                f.write("name\n")
                f.write("John\n")

            context = ImportContext(source_directory=Path(temp_dir), use_copy=True, batch_size=1000)

            loader = PostgresBulkLoader()

            # Mock database connection
            mock_connection = Mock()
            mock_cursor = Mock()
            mock_cursor.__enter__ = Mock(return_value=mock_cursor)
            mock_cursor.__exit__ = Mock(return_value=None)
            mock_connection.cursor.return_value = mock_cursor

            # Exercise
            result = loader.load_csv_with_context(
                model=TestModel, csv_path=csv_path, context=context, connection=mock_connection
            )

            # Verify
            assert "rows_loaded" in result
            assert result["used_copy"] is True

    def test_respects_import_context_configuration(self):
        """PostgresBulkLoader respects ImportContext configuration."""

        # Setup
        class TestModel(models.Model):
            name = models.CharField(max_length=100)

            class Meta:
                app_label = "test_postgres_bulk_loader"
                db_table = "test_model"

        import tempfile

        with tempfile.TemporaryDirectory() as temp_dir:
            csv_path = Path(temp_dir) / "test.csv"
            with open(csv_path, "w") as f:
                f.write("name\n")
                f.write("John\n")

            context = ImportContext(
                source_directory=Path(temp_dir),
                use_copy=False,  # Disable COPY, use INSERT
                batch_size=10,
            )

            loader = PostgresBulkLoader()

            # Exercise
            with patch.object(loader, "load_csv_with_insert") as mock_insert:
                mock_insert.return_value = {"rows_loaded": 1, "used_copy": False}

                result = loader.load_csv_with_context(
                    model=TestModel, csv_path=csv_path, context=context, connection=Mock()
                )

                # Verify fallback to INSERT was used
                mock_insert.assert_called_once()
                assert result["used_copy"] is False
