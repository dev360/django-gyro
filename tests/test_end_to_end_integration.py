"""
Test suite for end-to-end integration.

Following the test plan Phase 6: End-to-End Integration
- DataSlicer.run() method implementation
- Source/Target classes (Postgres, File)
- Database connection management
- Progress tracking with tqdm
- Complete ETL workflow
"""

import os
import tempfile
from unittest.mock import MagicMock, Mock, patch

import pytest
from django.db import models
from django.test import TestCase

from django_gyro import DataSlicer, Importer, ImportJob


class TestDataSlicerSourceTargetClasses(TestCase):
    """Test DataSlicer source and target classes."""

    def setUp(self):
        """Clear the registry before each test."""
        if hasattr(Importer, "_registry"):
            Importer._registry.clear()

    def tearDown(self):
        """Clean up after each test."""
        if hasattr(Importer, "_registry"):
            Importer._registry.clear()

    def test_postgres_source_creation(self):
        """Test creation of Postgres source."""
        from django_gyro.sources import PostgresSource

        postgres_url = "postgresql://user:pass@localhost:5432/testdb"
        source = PostgresSource(postgres_url)

        assert source.connection_string == postgres_url
        assert hasattr(source, "connect")
        assert hasattr(source, "execute_copy")

    def test_file_target_creation(self):
        """Test creation of File target."""
        from django_gyro.targets import FileTarget

        with tempfile.TemporaryDirectory() as temp_dir:
            target = FileTarget(temp_dir)

            assert target.base_path == temp_dir
            assert hasattr(target, "write_csv")
            assert hasattr(target, "ensure_directory_exists")

    def test_file_target_validates_directory(self):
        """Test File target validates directory accessibility."""
        from django_gyro.targets import FileTarget

        # Valid directory
        with tempfile.TemporaryDirectory() as temp_dir:
            target = FileTarget(temp_dir)
            assert target.base_path == temp_dir

        # Invalid directory should raise error
        with pytest.raises(ValueError, match="Directory does not exist or is not accessible"):
            FileTarget("/nonexistent/directory/path")

    def test_file_target_overwrite_protection(self):
        """Test File target overwrite protection."""
        from django_gyro.targets import FileTarget

        with tempfile.TemporaryDirectory() as temp_dir:
            # Create existing file
            test_file = os.path.join(temp_dir, "test.csv")
            with open(test_file, "w") as f:
                f.write("existing data")

            target = FileTarget(temp_dir)

            # Should detect existing files
            existing_files = target.check_existing_files(["test.csv"])
            assert "test.csv" in existing_files

            # Should prompt for overwrite without overwrite=True
            with pytest.raises(ValueError, match="Files already exist.*overwrite=True"):
                target.validate_overwrite(["test.csv"], overwrite=False)


class TestDataSlicerRunMethod(TestCase):
    """Test DataSlicer.run() method implementation."""

    def setUp(self):
        """Clear the registry before each test."""
        if hasattr(Importer, "_registry"):
            Importer._registry.clear()

    def tearDown(self):
        """Clean up after each test."""
        if hasattr(Importer, "_registry"):
            Importer._registry.clear()

    def test_dataslicer_run_basic_usage(self):
        """Test basic DataSlicer.run() usage."""

        class E2ETenant1(models.Model):
            name = models.CharField(max_length=100)

            class Meta:
                app_label = "test"
                db_table = "e2e_tenant1"

        class E2EShop1(models.Model):
            name = models.CharField(max_length=100)
            tenant = models.ForeignKey(E2ETenant1, on_delete=models.CASCADE)

            class Meta:
                app_label = "test"
                db_table = "e2e_shop1"

        class E2ETenantImporter1(Importer):
            model = E2ETenant1

            class Columns:
                pass

        class E2EShopImporter1(Importer):
            model = E2EShop1

            class Columns:
                tenant = E2ETenant1

        from django_gyro.sources import PostgresSource
        from django_gyro.targets import FileTarget

        with tempfile.TemporaryDirectory() as temp_dir:
            postgres_url = "postgresql://test:test@localhost:5432/testdb"

            # Mock the actual database operations
            with patch("django_gyro.sources.PostgresSource.connect") as mock_connect, patch(
                "django_gyro.sources.PostgresSource.export_queryset"
            ) as mock_export, patch("django_gyro.targets.FileTarget.copy_file_from_source") as mock_copy:
                mock_connect.return_value = MagicMock()
                mock_export.return_value = {"rows_exported": 100, "file_size": 5000}
                mock_copy.return_value = {"target_path": "/tmp/file.csv"}

                result = DataSlicer.run(
                    source=PostgresSource(postgres_url),
                    target=FileTarget(temp_dir),
                    jobs=[
                        ImportJob(model=E2ETenant1, query=E2ETenant1.objects.all()),
                        ImportJob(model=E2EShop1, query=E2EShop1.objects.all()),
                    ],
                )

                # Should return execution results
                assert "jobs_executed" in result
                assert "files_created" in result
                assert result["jobs_executed"] == 2

    def test_dataslicer_run_validates_job_order(self):
        """Test DataSlicer.run() validates and sorts job dependencies."""

        class E2ETenant2(models.Model):
            name = models.CharField(max_length=100)

            class Meta:
                app_label = "test"
                db_table = "e2e_tenant2"

        class E2EShop2(models.Model):
            name = models.CharField(max_length=100)
            tenant = models.ForeignKey(E2ETenant2, on_delete=models.CASCADE)

            class Meta:
                app_label = "test"
                db_table = "e2e_shop2"

        class E2ETenantImporter2(Importer):
            model = E2ETenant2

            class Columns:
                pass

        class E2EShopImporter2(Importer):
            model = E2EShop2

            class Columns:
                tenant = E2ETenant2

        from django_gyro.sources import PostgresSource
        from django_gyro.targets import FileTarget

        with tempfile.TemporaryDirectory() as temp_dir:
            postgres_url = "postgresql://test:test@localhost:5432/testdb"

            with patch("django_gyro.sources.PostgresSource.connect") as mock_connect, patch(
                "django_gyro.sources.PostgresSource.export_queryset"
            ) as mock_export, patch("django_gyro.targets.FileTarget.copy_file_from_source") as mock_copy:
                mock_connect.return_value = MagicMock()
                mock_export.return_value = {"rows_exported": 100, "file_size": 5000}
                mock_copy.return_value = {"target_path": "/tmp/file.csv"}

                # Pass jobs in wrong order (Shop before Tenant)
                result = DataSlicer.run(
                    source=PostgresSource(postgres_url),
                    target=FileTarget(temp_dir),
                    jobs=[
                        ImportJob(model=E2EShop2, query=E2EShop2.objects.all()),  # Wrong order
                        ImportJob(model=E2ETenant2, query=E2ETenant2.objects.all()),
                    ],
                )

                # Should still succeed by reordering internally
                assert result["jobs_executed"] == 2

    def test_dataslicer_run_with_progress_tracking(self):
        """Test DataSlicer.run() with progress tracking."""

        class E2ETenant3(models.Model):
            name = models.CharField(max_length=100)

            class Meta:
                app_label = "test"
                db_table = "e2e_tenant3"

        class E2ETenantImporter3(Importer):
            model = E2ETenant3

            class Columns:
                pass

        from django_gyro.sources import PostgresSource
        from django_gyro.targets import FileTarget

        with tempfile.TemporaryDirectory() as temp_dir:
            postgres_url = "postgresql://test:test@localhost:5432/testdb"

            progress_callback = Mock()

            with patch("django_gyro.sources.PostgresSource.connect") as mock_connect, patch(
                "django_gyro.sources.PostgresSource.export_queryset"
            ) as mock_export, patch("django_gyro.targets.FileTarget.copy_file_from_source") as mock_copy, patch(
                "tqdm.tqdm"
            ) as mock_tqdm:
                mock_connect.return_value = MagicMock()
                mock_export.return_value = {"rows_exported": 100, "file_size": 5000}
                mock_copy.return_value = {"target_path": "/tmp/file.csv"}
                mock_progress_bar = MagicMock()
                mock_tqdm.return_value = mock_progress_bar

                DataSlicer.run(
                    source=PostgresSource(postgres_url),
                    target=FileTarget(temp_dir),
                    jobs=[ImportJob(model=E2ETenant3, query=E2ETenant3.objects.all())],
                    progress_callback=progress_callback,
                )

                # Should create progress bar
                mock_tqdm.assert_called()
                # Should call progress callback
                progress_callback.assert_called()


class TestPostgresSourceImplementation(TestCase):
    """Test PostgresSource implementation details."""

    def setUp(self):
        """Clear the registry before each test."""
        if hasattr(Importer, "_registry"):
            Importer._registry.clear()

    def tearDown(self):
        """Clean up after each test."""
        if hasattr(Importer, "_registry"):
            Importer._registry.clear()

    def test_postgres_source_converts_queryset_to_copy_statement(self):
        """Test PostgresSource converts Django QuerySet to COPY statement."""

        class E2EModel1(models.Model):
            name = models.CharField(max_length=100)
            active = models.BooleanField(default=True)

            class Meta:
                app_label = "test"
                db_table = "e2e_model1"

        from django_gyro.sources import PostgresSource

        source = PostgresSource("postgresql://test:test@localhost/testdb")
        queryset = E2EModel1.objects.filter(active=True)

        copy_statement = source.generate_copy_statement(queryset, "output.csv")

        # Should generate proper COPY statement
        assert "COPY (" in copy_statement
        assert "SELECT" in copy_statement
        assert "e2e_model1" in copy_statement  # Table name might be quoted
        assert "WHERE" in copy_statement
        assert "active" in copy_statement.lower()
        assert "TO STDOUT" in copy_statement
        assert "FORMAT CSV" in copy_statement
        assert "HEADER" in copy_statement


class TestFileTargetImplementation(TestCase):
    """Test FileTarget implementation details."""

    def test_file_target_writes_csv_data(self):
        """Test FileTarget writes CSV data to files."""
        from django_gyro.targets import FileTarget

        with tempfile.TemporaryDirectory() as temp_dir:
            target = FileTarget(temp_dir)

            csv_data = "name,email\nJohn Doe,john@example.com\nJane Smith,jane@example.com"

            result = target.write_csv("users.csv", csv_data)

            # Should write file
            output_file = os.path.join(temp_dir, "users.csv")
            assert os.path.exists(output_file)

            # Should contain correct data
            with open(output_file) as f:
                content = f.read()
                assert "John Doe" in content
                assert "jane@example.com" in content

            # Should return write results
            assert "file_path" in result
            assert "bytes_written" in result


class TestEndToEndWorkflow(TestCase):
    """Test complete end-to-end workflow."""

    def setUp(self):
        """Clear the registry before each test."""
        if hasattr(Importer, "_registry"):
            Importer._registry.clear()

    def tearDown(self):
        """Clean up after each test."""
        if hasattr(Importer, "_registry"):
            Importer._registry.clear()

    def test_complete_etl_workflow(self):
        """Test complete ETL workflow as described in technical design."""

        # Define models matching technical design
        class E2ETenant5(models.Model):
            name = models.CharField(max_length=200)
            subdomain = models.CharField(max_length=50, unique=True)
            is_active = models.BooleanField(default=True)

            class Meta:
                app_label = "test"
                db_table = "e2e_tenant5"

        class E2EShop5(models.Model):
            tenant = models.ForeignKey(E2ETenant5, on_delete=models.CASCADE)
            name = models.CharField(max_length=200)
            url = models.URLField()
            currency = models.CharField(max_length=3, default="USD")

            class Meta:
                app_label = "test"
                db_table = "e2e_shop5"

        class E2ECustomer5(models.Model):
            tenant = models.ForeignKey(E2ETenant5, on_delete=models.CASCADE)
            shop = models.ForeignKey(E2EShop5, on_delete=models.CASCADE)
            email = models.EmailField()
            first_name = models.CharField(max_length=100)
            last_name = models.CharField(max_length=100)

            class Meta:
                app_label = "test"
                db_table = "e2e_customer5"

        # Define importers
        class E2ETenantImporter5(Importer):
            model = E2ETenant5

            class Columns:
                pass

        class E2EShopImporter5(Importer):
            model = E2EShop5

            class Columns:
                tenant = E2ETenant5

        class E2ECustomerImporter5(Importer):
            model = E2ECustomer5

            class Columns:
                tenant = E2ETenant5
                shop = E2EShop5

        from django_gyro.sources import PostgresSource
        from django_gyro.targets import FileTarget

        with tempfile.TemporaryDirectory() as temp_dir:
            postgres_url = "postgresql://user:pass@localhost:5432/proddb"

            # Mock database operations
            with patch("django_gyro.sources.PostgresSource.connect") as mock_connect, patch(
                "django_gyro.sources.PostgresSource.export_queryset"
            ) as mock_export, patch("django_gyro.targets.FileTarget.copy_file_from_source") as mock_copy, patch(
                "tqdm.tqdm"
            ) as mock_tqdm:
                mock_connect.return_value = MagicMock()
                mock_export.return_value = {"rows_exported": 100, "file_size": 5000}
                mock_copy.return_value = {"target_path": "/tmp/file.csv"}
                mock_tqdm.return_value = MagicMock()

                # Execute the workflow from technical design
                tenant = E2ETenant5.objects.filter(id=1)
                shops = E2EShop5.objects.filter(tenant__id=1, id__in=[10, 11, 12])
                customers = E2ECustomer5.objects.filter(shop__in=shops)

                result = DataSlicer.run(
                    source=PostgresSource(postgres_url),
                    target=FileTarget(temp_dir),
                    jobs=[
                        ImportJob(model=E2ETenant5, query=tenant),
                        ImportJob(model=E2EShop5, query=shops),
                        ImportJob(model=E2ECustomer5, query=customers),
                    ],
                )

                # Should execute all jobs
                assert result["jobs_executed"] == 3
                assert len(result["files_created"]) == 3

                # Should have created files (exact names depend on mock setup)
                assert result["files_created"] is not None
                assert len(result["files_created"]) > 0

    def test_dataslicer_convenience_methods(self):
        """Test DataSlicer.Postgres() and DataSlicer.File() convenience methods."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Test convenience methods match technical design API
            postgres_source = DataSlicer.Postgres("postgresql://user:pass@localhost:5432/db")
            file_target = DataSlicer.File(temp_dir)

            assert postgres_source.connection_string == "postgresql://user:pass@localhost:5432/db"
            assert file_target.base_path == temp_dir
