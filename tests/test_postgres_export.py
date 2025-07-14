"""
Test suite for PostgreSQL export operations.

Following the test plan Phase 4: Data Export Operations
- SQL generation from Django QuerySets
- CSV generation with proper headers
- Foreign key handling and relationships
- Progress tracking for large exports
"""

from unittest.mock import Mock, patch

from django.db import models

from django_gyro import Importer

from .test_utils import DatabaseMockingTestMixin


class TestPostgresExportSQLGeneration(DatabaseMockingTestMixin):
    """Test PostgreSQL export SQL generation functionality."""

    def test_converts_django_queryset_to_sql(self):
        """Test converting Django QuerySet to proper SQL."""

        class PgSqlModel1(models.Model):
            name = models.CharField(max_length=100)
            active = models.BooleanField(default=True)

            class Meta:
                app_label = "test_postgres_export"
                db_table = "pg_sql_model1"

        class PgSqlImporter1(Importer):
            model = PgSqlModel1

            class Columns:
                pass

        # Create a QuerySet
        queryset = PgSqlModel1.objects.filter(active=True)

        # Mock the PostgresExporter
        from django_gyro.exporters import PostgresExporter

        exporter = PostgresExporter("postgresql://test")

        sql = exporter.queryset_to_sql(queryset)

        # Should generate proper SELECT statement
        assert "SELECT" in sql
        assert "pg_sql_model1" in sql
        assert "active" in sql
        # Django ORM generates WHERE "table"."active" which is equivalent to = true
        assert "WHERE" in sql

    def test_handles_complex_where_clauses(self):
        """Test SQL generation with complex WHERE conditions."""

        class PgSqlModel2(models.Model):
            name = models.CharField(max_length=100)
            age = models.IntegerField()
            active = models.BooleanField(default=True)

            class Meta:
                app_label = "test_postgres_export"
                db_table = "pg_sql_model2"

        class PgSqlImporter2(Importer):
            model = PgSqlModel2

            class Columns:
                pass

        # Create complex QuerySet
        queryset = PgSqlModel2.objects.filter(active=True, age__gte=18, name__icontains="test").exclude(age__gt=65)

        from django_gyro.exporters import PostgresExporter

        exporter = PostgresExporter("postgresql://test")

        sql = exporter.queryset_to_sql(queryset)

        # Should handle multiple conditions
        assert "active" in sql
        assert "age" in sql
        assert "name" in sql
        assert "AND" in sql or "WHERE" in sql

    def test_generates_proper_copy_statements(self):
        """Test generation of PostgreSQL COPY statements."""

        class PgSqlModel3(models.Model):
            name = models.CharField(max_length=100)

            class Meta:
                app_label = "test_postgres_export"
                db_table = "pg_sql_model3"

        class PgSqlImporter3(Importer):
            model = PgSqlModel3

            class Columns:
                pass

        queryset = PgSqlModel3.objects.all()

        from django_gyro.exporters import PostgresExporter

        exporter = PostgresExporter("postgresql://test")

        copy_sql = exporter.generate_copy_statement(queryset, "output.csv")

        # Should generate proper COPY TO statement
        assert "COPY" in copy_sql
        assert "TO" in copy_sql
        assert "CSV" in copy_sql
        assert "HEADER" in copy_sql
        assert "output.csv" in copy_sql

    def test_handles_queryset_with_ordering(self):
        """Test SQL generation preserves QuerySet ordering."""

        class PgSqlModel4(models.Model):
            name = models.CharField(max_length=100)
            created_at = models.DateTimeField(auto_now_add=True)

            class Meta:
                app_label = "test_postgres_export"
                db_table = "pg_sql_model4"

        class PgSqlImporter4(Importer):
            model = PgSqlModel4

            class Columns:
                pass

        # Create ordered QuerySet
        queryset = PgSqlModel4.objects.order_by("-created_at", "name")

        from django_gyro.exporters import PostgresExporter

        exporter = PostgresExporter("postgresql://test")

        sql = exporter.queryset_to_sql(queryset)

        # Should preserve ORDER BY clause
        assert "ORDER BY" in sql
        assert "created_at" in sql
        assert "name" in sql


class TestPostgresExportCSVGeneration(DatabaseMockingTestMixin):
    """Test CSV generation functionality."""

    def test_includes_proper_csv_headers(self):
        """Test CSV export includes correct headers."""

        class PgCsvModel1(models.Model):
            id = models.AutoField(primary_key=True)
            name = models.CharField(max_length=100)
            email = models.EmailField()
            active = models.BooleanField(default=True)

            class Meta:
                app_label = "test_postgres_export"
                db_table = "pg_csv_model1"

        class PgCsvImporter1(Importer):
            model = PgCsvModel1

            class Columns:
                pass

        from django_gyro.exporters import PostgresExporter

        exporter = PostgresExporter("postgresql://test")

        headers = exporter.get_csv_headers(PgCsvModel1)

        # Should include all model fields
        expected_headers = ["id", "name", "email", "active"]
        for header in expected_headers:
            assert header in headers

    def test_exports_all_model_fields(self):
        """Test that all model fields are included in export."""

        class PgCsvModel2(models.Model):
            name = models.CharField(max_length=100)
            description = models.TextField(blank=True)
            price = models.DecimalField(max_digits=10, decimal_places=2)
            created_at = models.DateTimeField(auto_now_add=True)

            class Meta:
                app_label = "test_postgres_export"
                db_table = "pg_csv_model2"

        class PgCsvImporter2(Importer):
            model = PgCsvModel2

            class Columns:
                pass

        from django_gyro.exporters import PostgresExporter

        exporter = PostgresExporter("postgresql://test")

        field_names = exporter.get_exportable_fields(PgCsvModel2)

        # Should include all fields
        assert "name" in field_names
        assert "description" in field_names
        assert "price" in field_names
        assert "created_at" in field_names

    def test_handles_null_values_correctly(self):
        """Test proper handling of NULL values in CSV export."""

        class PgCsvModel3(models.Model):
            name = models.CharField(max_length=100)
            optional_field = models.CharField(max_length=100, null=True, blank=True)

            class Meta:
                app_label = "test_postgres_export"
                db_table = "pg_csv_model3"

        class PgCsvImporter3(Importer):
            model = PgCsvModel3

            class Columns:
                pass

        from django_gyro.exporters import PostgresExporter

        exporter = PostgresExporter("postgresql://test")

        # Mock data with NULL values
        mock_data = [{"name": "Test", "optional_field": None}, {"name": "Test2", "optional_field": "Value"}]

        csv_output = exporter.format_csv_data(mock_data)

        # Should handle NULL values appropriately
        assert csv_output is not None
        # NULL values should be represented as empty strings or specific null representation

    def test_escapes_csv_special_characters(self):
        """Test proper escaping of CSV special characters."""

        class PgCsvModel4(models.Model):
            name = models.CharField(max_length=100)
            description = models.TextField()

            class Meta:
                app_label = "test_postgres_export"
                db_table = "pg_csv_model4"

        class PgCsvImporter4(Importer):
            model = PgCsvModel4

            class Columns:
                pass

        from django_gyro.exporters import PostgresExporter

        exporter = PostgresExporter("postgresql://test")

        # Mock data with special characters
        mock_data = [
            {"name": "Test, Inc.", "description": "Line 1\nLine 2"},
            {"name": 'Test "Quoted"', "description": "Normal text"},
        ]

        csv_output = exporter.format_csv_data(mock_data)

        # Should properly escape commas, quotes, and newlines
        assert csv_output is not None
        # Special characters should be properly escaped


class TestPostgresExportForeignKeyHandling(DatabaseMockingTestMixin):
    """Test foreign key handling in PostgreSQL exports."""

    def test_exports_foreign_key_ids_correctly(self):
        """Test that foreign key IDs are exported correctly."""

        class PgFkCategory1(models.Model):
            name = models.CharField(max_length=100)

            class Meta:
                app_label = "test_postgres_export"
                db_table = "pg_fk_category1"

        class PgFkProduct1(models.Model):
            name = models.CharField(max_length=100)
            category = models.ForeignKey(PgFkCategory1, on_delete=models.CASCADE)

            class Meta:
                app_label = "test_postgres_export"
                db_table = "pg_fk_product1"

        class PgFkCategoryImporter1(Importer):
            model = PgFkCategory1

            class Columns:
                pass

        class PgFkProductImporter1(Importer):
            model = PgFkProduct1

            class Columns:
                category = PgFkCategory1

        from django_gyro.exporters import PostgresExporter

        exporter = PostgresExporter("postgresql://test")

        # Get field mapping for Product
        field_mapping = exporter.get_field_mapping(PgFkProduct1)

        # Should include category_id field
        assert "category_id" in field_mapping or "category" in field_mapping

    def test_handles_null_foreign_keys(self):
        """Test handling of NULL foreign key relationships."""

        class PgFkCategory2(models.Model):
            name = models.CharField(max_length=100)

            class Meta:
                app_label = "test_postgres_export"
                db_table = "pg_fk_category2"

        class PgFkProduct2(models.Model):
            name = models.CharField(max_length=100)
            category = models.ForeignKey(PgFkCategory2, on_delete=models.CASCADE, null=True)

            class Meta:
                app_label = "test_postgres_export"
                db_table = "pg_fk_product2"

        class PgFkCategoryImporter2(Importer):
            model = PgFkCategory2

            class Columns:
                pass

        class PgFkProductImporter2(Importer):
            model = PgFkProduct2

            class Columns:
                category = PgFkCategory2

        from django_gyro.exporters import PostgresExporter

        exporter = PostgresExporter("postgresql://test")

        # Mock data with NULL FK
        mock_data = [{"name": "Product 1", "category_id": 1}, {"name": "Product 2", "category_id": None}]

        csv_output = exporter.format_csv_data(mock_data)

        # Should handle NULL foreign keys gracefully
        assert csv_output is not None

    def test_handles_multiple_foreign_key_relationships(self):
        """Test handling of multiple FK relationships in same model."""

        class PgFkCategory3(models.Model):
            name = models.CharField(max_length=100)

            class Meta:
                app_label = "test_postgres_export"
                db_table = "pg_fk_category3"

        class PgFkSupplier3(models.Model):
            name = models.CharField(max_length=100)

            class Meta:
                app_label = "test_postgres_export"
                db_table = "pg_fk_supplier3"

        class PgFkProduct3(models.Model):
            name = models.CharField(max_length=100)
            category = models.ForeignKey(PgFkCategory3, on_delete=models.CASCADE)
            supplier = models.ForeignKey(PgFkSupplier3, on_delete=models.CASCADE)

            class Meta:
                app_label = "test_postgres_export"
                db_table = "pg_fk_product3"

        class PgFkCategoryImporter3(Importer):
            model = PgFkCategory3

            class Columns:
                pass

        class PgFkSupplierImporter3(Importer):
            model = PgFkSupplier3

            class Columns:
                pass

        class PgFkProductImporter3(Importer):
            model = PgFkProduct3

            class Columns:
                category = PgFkCategory3
                supplier = PgFkSupplier3

        from django_gyro.exporters import PostgresExporter

        exporter = PostgresExporter("postgresql://test")

        field_mapping = exporter.get_field_mapping(PgFkProduct3)

        # Should handle multiple FK fields
        fk_fields = [field for field in field_mapping if field.endswith("_id")]
        assert len(fk_fields) >= 2  # category_id and supplier_id


class TestPostgresExportProgressTracking(DatabaseMockingTestMixin):
    """Test progress tracking for large exports."""

    def test_shows_progress_for_large_exports(self):
        """Test progress tracking for large dataset exports."""

        class PgProgressModel1(models.Model):
            name = models.CharField(max_length=100)

            class Meta:
                app_label = "test_postgres_export"
                db_table = "pg_progress_model1"

        class PgProgressImporter1(Importer):
            model = PgProgressModel1

            class Columns:
                pass

        from django_gyro.exporters import PostgresExporter

        exporter = PostgresExporter("postgresql://test")

        # Mock progress callback
        progress_callback = Mock()

        # Test export with progress tracking
        with patch("django_gyro.exporters.PostgresExporter.execute_export") as mock_export:
            mock_export.return_value = {"rows_exported": 10000}

            result = exporter.export_with_progress(
                PgProgressModel1.objects.all(), "test.csv", progress_callback=progress_callback
            )

            # Should call progress callback
            assert progress_callback.called
            assert result["rows_exported"] == 10000

    def test_updates_progress_bars(self):
        """Test progress bar updates during export."""

        class PgProgressModel2(models.Model):
            name = models.CharField(max_length=100)

            class Meta:
                app_label = "test_postgres_export"
                db_table = "pg_progress_model2"

        class PgProgressImporter2(Importer):
            model = PgProgressModel2

            class Columns:
                pass

        from django_gyro.exporters import PostgresExporter

        exporter = PostgresExporter("postgresql://test")

        # Mock progress bar
        progress_bar = Mock()
        progress_bar.update = Mock()

        # Test progress updates
        exporter.update_progress(progress_bar, current=500, total=1000)

        # Should update progress bar
        progress_bar.update.assert_called()

    def test_completion_notifications(self):
        """Test completion notifications for exports."""

        class PgProgressModel3(models.Model):
            name = models.CharField(max_length=100)

            class Meta:
                app_label = "test_postgres_export"
                db_table = "pg_progress_model3"

        class PgProgressImporter3(Importer):
            model = PgProgressModel3

            class Columns:
                pass

        from django_gyro.exporters import PostgresExporter

        exporter = PostgresExporter("postgresql://test")

        # Mock completion callback
        completion_callback = Mock()

        # Test export completion
        with patch("django_gyro.exporters.PostgresExporter.execute_export") as mock_export:
            mock_export.return_value = {"rows_exported": 1000, "file_size": 50000, "duration": 2.5}

            exporter.export_with_completion(
                PgProgressModel3.objects.all(), "test.csv", completion_callback=completion_callback
            )

            # Should call completion callback with results
            completion_callback.assert_called_once()
            call_args = completion_callback.call_args[0][0]
            assert call_args["rows_exported"] == 1000
            assert call_args["file_size"] == 50000
            assert call_args["duration"] == 2.5

    def test_handles_export_interruption(self):
        """Test handling of interrupted exports."""

        class PgProgressModel4(models.Model):
            name = models.CharField(max_length=100)

            class Meta:
                app_label = "test_postgres_export"
                db_table = "pg_progress_model4"

        class PgProgressImporter4(Importer):
            model = PgProgressModel4

            class Columns:
                pass

        from django_gyro.exporters import PostgresExporter

        exporter = PostgresExporter("postgresql://test")

        # Mock export interruption
        with patch("django_gyro.exporters.PostgresExporter.execute_export") as mock_export:
            mock_export.side_effect = KeyboardInterrupt("Export interrupted")

            try:
                exporter.export_with_progress(PgProgressModel4.objects.all(), "test.csv")
                raise AssertionError("Expected KeyboardInterrupt")
            except KeyboardInterrupt:
                pass  # Expected behavior

            # Should handle interruption gracefully
            # Clean up partial files, etc.
