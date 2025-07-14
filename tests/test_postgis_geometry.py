"""
Tests for PostGIS geometry field handling in PostgresBulkLoader.

These tests verify that Django Gyro correctly detects PostGIS geometry fields
and applies the proper EWKB conversion during CSV import operations.
"""

from unittest.mock import Mock

from django.db import models

from django_gyro.importing import PostgresBulkLoader
from tests.test_utils import clear_django_gyro_registries


class TestPostGISGeometryDetection:
    """Tests for detecting PostGIS geometry fields in Django models."""

    def setup_method(self):
        """Clear the registry before each test."""
        clear_django_gyro_registries()

    def teardown_method(self):
        """Clean up after each test."""
        clear_django_gyro_registries()

    def test_detects_geometry_fields_by_type(self):
        """PostgresBulkLoader detects geometry fields by get_internal_type()."""
        
        class MockGeometryField:
            def __init__(self, column_name):
                self.column = column_name
            
            def get_internal_type(self):
                return 'GeometryField'
        
        class TestModel(models.Model):
            name = models.CharField(max_length=100)
            location = MockGeometryField('location')
            
            class Meta:
                app_label = "test_postgis"
                db_table = "test_model"
        
        # Mock the model's _meta.get_fields() to return our mock geometry field
        TestModel._meta.get_fields = lambda: [
            TestModel._meta.get_field('name'),
            TestModel.location
        ]
        
        loader = PostgresBulkLoader()
        geometry_columns = loader._get_geometry_columns(TestModel)
        
        assert geometry_columns == ['location']

    def test_detects_geometry_fields_by_class_name(self):
        """PostgresBulkLoader detects geometry fields by class name patterns."""
        
        class MockPointField:
            def __init__(self, column_name):
                self.column = column_name
                self.__class__.__name__ = 'PointField'
            
            def get_internal_type(self):
                return 'CharField'  # Doesn't match by type
        
        class TestModel(models.Model):
            name = models.CharField(max_length=100)
            location = MockPointField('location')
            
            class Meta:
                app_label = "test_postgis"
                db_table = "test_model"
        
        TestModel._meta.get_fields = lambda: [
            TestModel._meta.get_field('name'),
            TestModel.location
        ]
        
        loader = PostgresBulkLoader()
        geometry_columns = loader._get_geometry_columns(TestModel)
        
        assert geometry_columns == ['location']

    def test_ignores_non_geometry_fields(self):
        """PostgresBulkLoader ignores regular Django fields."""
        
        class TestModel(models.Model):
            name = models.CharField(max_length=100)
            email = models.EmailField()
            created_at = models.DateTimeField()
            
            class Meta:
                app_label = "test_postgis"
                db_table = "test_model"
        
        loader = PostgresBulkLoader()
        geometry_columns = loader._get_geometry_columns(TestModel)
        
        assert geometry_columns == []


class TestPostGISStagingTableHandling:
    """Tests for PostGIS-specific staging table modifications."""

    def setup_method(self):
        """Clear the registry before each test."""
        clear_django_gyro_registries()

    def teardown_method(self):
        """Clean up after each test."""
        clear_django_gyro_registries()

    def test_creates_staging_table_with_geometry_as_text(self):
        """_create_staging_table converts geometry columns to TEXT."""
        
        class TestModel(models.Model):
            name = models.CharField(max_length=100)
            
            class Meta:
                app_label = "test_postgis"
                db_table = "test_model"
        
        loader = PostgresBulkLoader()
        mock_cursor = Mock()
        
        # Mock geometry detection to return one geometry column
        loader._get_geometry_columns = Mock(return_value=['location'])
        
        # Exercise
        loader._create_staging_table(mock_cursor, TestModel)
        
        # Verify
        calls = mock_cursor.execute.call_args_list
        assert len(calls) == 2  # CREATE TABLE + ALTER COLUMN
        
        # Check CREATE TABLE call
        create_call = calls[0][0][0]
        assert "CREATE TEMP TABLE import_staging_test_model" in create_call
        assert "LIKE test_model" in create_call
        
        # Check ALTER COLUMN call for geometry
        alter_call = calls[1][0][0]
        assert "ALTER TABLE import_staging_test_model" in alter_call
        assert "ALTER COLUMN location TYPE TEXT" in alter_call

    def test_skips_geometry_conversion_for_regular_tables(self):
        """_create_staging_table skips ALTER for models without geometry."""
        
        class TestModel(models.Model):
            name = models.CharField(max_length=100)
            
            class Meta:
                app_label = "test_postgis"
                db_table = "test_model"
        
        loader = PostgresBulkLoader()
        mock_cursor = Mock()
        
        # Mock geometry detection to return no geometry columns
        loader._get_geometry_columns = Mock(return_value=[])
        
        # Exercise
        loader._create_staging_table(mock_cursor, TestModel)
        
        # Verify - only CREATE TABLE call, no ALTER
        calls = mock_cursor.execute.call_args_list
        assert len(calls) == 1
        
        create_call = calls[0][0][0]
        assert "CREATE TEMP TABLE import_staging_test_model" in create_call


class TestPostGISEWKBConversion:
    """Tests for EWKB conversion during INSERT from staging table."""

    def setup_method(self):
        """Clear the registry before each test."""
        clear_django_gyro_registries()

    def teardown_method(self):
        """Clean up after each test."""
        clear_django_gyro_registries()

    def test_generates_ewkb_conversion_sql_for_geometry_columns(self):
        """_insert_from_staging generates ST_GeomFromEWKB conversion for geometry columns."""
        
        class TestModel(models.Model):
            name = models.CharField(max_length=100)
            
            class Meta:
                app_label = "test_postgis"
                db_table = "test_model"
        
        loader = PostgresBulkLoader()
        mock_cursor = Mock()
        
        # Mock geometry detection
        loader._get_geometry_columns = Mock(return_value=['location'])
        
        # Mock information_schema query to return column names
        mock_cursor.fetchall.return_value = [('name',), ('location',)]
        
        # Exercise
        loader._insert_from_staging(mock_cursor, TestModel)
        
        # Verify
        calls = mock_cursor.execute.call_args_list
        assert len(calls) == 2  # information_schema query + INSERT
        
        # Check the INSERT statement contains EWKB conversion
        insert_call = calls[1][0][0]
        assert "INSERT INTO test_model" in insert_call
        assert "ST_GeomFromEWKB" in insert_call
        assert "CASE" in insert_call
        assert "\\x%" in insert_call  # Handles \x prefixed hex
        assert "decode(" in insert_call  # Handles plain hex
        assert "::bytea" in insert_call

    def test_uses_simple_select_for_non_geometry_tables(self):
        """_insert_from_staging uses simple SELECT * for models without geometry."""
        
        class TestModel(models.Model):
            name = models.CharField(max_length=100)
            
            class Meta:
                app_label = "test_postgis"
                db_table = "test_model"
        
        loader = PostgresBulkLoader()
        mock_cursor = Mock()
        
        # Mock geometry detection to return no geometry columns
        loader._get_geometry_columns = Mock(return_value=[])
        
        # Exercise
        loader._insert_from_staging(mock_cursor, TestModel)
        
        # Verify - simple SELECT * without EWKB conversion
        calls = mock_cursor.execute.call_args_list
        assert len(calls) == 1
        
        insert_call = calls[0][0][0]
        assert "INSERT INTO test_model SELECT * FROM import_staging_test_model" in insert_call
        assert "ST_GeomFromEWKB" not in insert_call
        assert "CASE" not in insert_call

    def test_handles_on_conflict_with_geometry_conversion(self):
        """_insert_from_staging handles ON CONFLICT with geometry conversion."""
        
        class TestModel(models.Model):
            name = models.CharField(max_length=100)
            
            class Meta:
                app_label = "test_postgis"
                db_table = "test_model"
        
        loader = PostgresBulkLoader()
        mock_cursor = Mock()
        
        # Mock geometry detection
        loader._get_geometry_columns = Mock(return_value=['location'])
        mock_cursor.fetchall.return_value = [('name',), ('location',)]
        
        # Exercise with ON CONFLICT
        loader._insert_from_staging(mock_cursor, TestModel, on_conflict="ignore")
        
        # Verify
        insert_call = mock_cursor.execute.call_args_list[1][0][0]
        assert "ON CONFLICT DO NOTHING" in insert_call
        assert "ST_GeomFromEWKB" in insert_call  # Still has geometry conversion