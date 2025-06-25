"""
Test suite for PostgreSQL import operations.

Following the test plan Phase 5: Data Import Operations
- CSV parsing and column mapping
- Data validation and type checking
- Foreign key resolution and validation
- FK dependency validation with cyclical detection
- Constraint handling and transaction management
"""
import pytest
import tempfile
import os
from unittest.mock import Mock, patch, MagicMock
from django.db import models
from django.test import TestCase
from io import StringIO

from django_gyro import Importer, DataSlicer


class TestPostgresImportCSVParsing(TestCase):
    """Test CSV parsing functionality."""

    def setUp(self):
        """Clear the registry before each test."""
        if hasattr(Importer, '_registry'):
            Importer._registry.clear()

    def tearDown(self):
        """Clean up after each test."""
        if hasattr(Importer, '_registry'):
            Importer._registry.clear()

    def test_parses_csv_headers_correctly(self):
        """Test CSV header parsing and validation."""
        class PgImportModel1(models.Model):
            name = models.CharField(max_length=100)
            email = models.EmailField()
            active = models.BooleanField(default=True)
            class Meta:
                app_label = 'test'
                db_table = 'pg_import_model1'

        class PgImportImporter1(Importer):
            model = PgImportModel1
            class Columns:
                pass

        from django_gyro.importers import PostgresImporter
        importer = PostgresImporter("postgresql://test")
        
        # Mock CSV content with headers
        csv_content = "name,email,active\nJohn Doe,john@example.com,true\n"
        
        headers = importer.parse_csv_headers(StringIO(csv_content))
        
        # Should correctly identify headers
        assert 'name' in headers
        assert 'email' in headers
        assert 'active' in headers
        assert len(headers) == 3

    def test_maps_columns_to_model_fields(self):
        """Test mapping CSV columns to Django model fields."""
        class PgImportModel2(models.Model):
            name = models.CharField(max_length=100)
            description = models.TextField()
            price = models.DecimalField(max_digits=10, decimal_places=2)
            class Meta:
                app_label = 'test'
                db_table = 'pg_import_model2'

        class PgImportImporter2(Importer):
            model = PgImportModel2
            class Columns:
                pass

        from django_gyro.importers import PostgresImporter
        importer = PostgresImporter("postgresql://test")
        
        csv_headers = ['name', 'description', 'price']
        field_mapping = importer.map_columns_to_fields(PgImportModel2, csv_headers)
        
        # Should create correct field mapping
        assert 'name' in field_mapping
        assert 'description' in field_mapping
        assert 'price' in field_mapping
        
        # Should map to correct field types
        assert field_mapping['name'].get_internal_type() == 'CharField'
        assert field_mapping['description'].get_internal_type() == 'TextField'
        assert field_mapping['price'].get_internal_type() == 'DecimalField'

    def test_handles_missing_columns(self):
        """Test handling of missing required columns."""
        class PgImportModel3(models.Model):
            name = models.CharField(max_length=100)
            required_field = models.CharField(max_length=100)
            optional_field = models.CharField(max_length=100, null=True, blank=True)
            class Meta:
                app_label = 'test'
                db_table = 'pg_import_model3'

        class PgImportImporter3(Importer):
            model = PgImportModel3
            class Columns:
                pass

        from django_gyro.importers import PostgresImporter
        importer = PostgresImporter("postgresql://test")
        
        # CSV missing required field
        csv_headers = ['name', 'optional_field']
        
        with pytest.raises(ValueError, match="Missing required column"):
            importer.validate_required_columns(PgImportModel3, csv_headers)

    def test_handles_extra_columns(self):
        """Test handling of extra CSV columns not in model."""
        class PgImportModel4(models.Model):
            name = models.CharField(max_length=100)
            email = models.EmailField()
            class Meta:
                app_label = 'test'
                db_table = 'pg_import_model4'

        class PgImportImporter4(Importer):
            model = PgImportModel4
            class Columns:
                pass

        from django_gyro.importers import PostgresImporter
        importer = PostgresImporter("postgresql://test")
        
        # CSV has extra column
        csv_headers = ['name', 'email', 'extra_column']
        
        # Should handle gracefully and warn about extra columns
        field_mapping = importer.map_columns_to_fields(PgImportModel4, csv_headers)
        
        # Should only map known fields
        assert 'name' in field_mapping
        assert 'email' in field_mapping
        assert 'extra_column' not in field_mapping


class TestPostgresImportDataValidation(TestCase):
    """Test data validation functionality."""

    def setUp(self):
        """Clear the registry before each test."""
        if hasattr(Importer, '_registry'):
            Importer._registry.clear()

    def tearDown(self):
        """Clean up after each test."""
        if hasattr(Importer, '_registry'):
            Importer._registry.clear()

    def test_validates_data_types(self):
        """Test data type validation for different field types."""
        class PgValidateModel1(models.Model):
            name = models.CharField(max_length=100)
            age = models.IntegerField()
            price = models.DecimalField(max_digits=10, decimal_places=2)
            active = models.BooleanField()
            class Meta:
                app_label = 'test'
                db_table = 'pg_validate_model1'

        class PgValidateImporter1(Importer):
            model = PgValidateModel1
            class Columns:
                pass

        from django_gyro.importers import PostgresImporter
        importer = PostgresImporter("postgresql://test")
        
        # Valid data
        valid_row = {
            'name': 'John Doe',
            'age': '25',
            'price': '99.99',
            'active': 'true'
        }
        
        validated_row = importer.validate_row_data(PgValidateModel1, valid_row)
        
        # Should convert types correctly
        assert validated_row['name'] == 'John Doe'
        assert validated_row['age'] == 25
        assert float(validated_row['price']) == 99.99
        assert validated_row['active'] is True

    def test_checks_required_fields(self):
        """Test validation of required field constraints."""
        class PgValidateModel2(models.Model):
            name = models.CharField(max_length=100)  # Required
            email = models.EmailField()  # Required
            description = models.TextField(null=True, blank=True)  # Optional
            class Meta:
                app_label = 'test'
                db_table = 'pg_validate_model2'

        class PgValidateImporter2(Importer):
            model = PgValidateModel2
            class Columns:
                pass

        from django_gyro.importers import PostgresImporter
        importer = PostgresImporter("postgresql://test")
        
        # Missing required field
        invalid_row = {
            'name': 'John Doe',
            # Missing email
            'description': 'Some description'
        }
        
        with pytest.raises(ValueError, match="Required field .* is missing"):
            importer.validate_row_data(PgValidateModel2, invalid_row)

    def test_custom_model_validation(self):
        """Test custom model validation during import."""
        class PgValidateModel3(models.Model):
            name = models.CharField(max_length=100)
            age = models.IntegerField()
            
            def clean(self):
                if self.age < 0:
                    raise ValueError("Age cannot be negative")
            
            class Meta:
                app_label = 'test'
                db_table = 'pg_validate_model3'

        class PgValidateImporter3(Importer):
            model = PgValidateModel3
            class Columns:
                pass

        from django_gyro.importers import PostgresImporter
        importer = PostgresImporter("postgresql://test")
        
        # Invalid data that fails model validation
        invalid_row = {
            'name': 'John Doe',
            'age': '-5'
        }
        
        with pytest.raises(ValueError, match="Age cannot be negative"):
            importer.validate_row_data(PgValidateModel3, invalid_row)

    def test_handles_invalid_data_types(self):
        """Test handling of invalid data type conversions."""
        class PgValidateModel4(models.Model):
            name = models.CharField(max_length=100)
            age = models.IntegerField()
            price = models.DecimalField(max_digits=10, decimal_places=2)
            class Meta:
                app_label = 'test'
                db_table = 'pg_validate_model4'

        class PgValidateImporter4(Importer):
            model = PgValidateModel4
            class Columns:
                pass

        from django_gyro.importers import PostgresImporter
        importer = PostgresImporter("postgresql://test")
        
        # Invalid data types
        invalid_row = {
            'name': 'John Doe',
            'age': 'not_a_number',
            'price': 'invalid_decimal'
        }
        
        with pytest.raises(ValueError, match="Invalid data type"):
            importer.validate_row_data(PgValidateModel4, invalid_row)


class TestPostgresImportForeignKeyResolution(TestCase):
    """Test foreign key resolution functionality."""

    def setUp(self):
        """Clear the registry before each test."""
        if hasattr(Importer, '_registry'):
            Importer._registry.clear()

    def tearDown(self):
        """Clean up after each test."""
        if hasattr(Importer, '_registry'):
            Importer._registry.clear()

    def test_resolves_foreign_key_references(self):
        """Test resolution of foreign key references."""
        class PgFkCategory4(models.Model):
            name = models.CharField(max_length=100)
            class Meta:
                app_label = 'test'
                db_table = 'pg_fk_category4'

        class PgFkProduct4(models.Model):
            name = models.CharField(max_length=100)
            category = models.ForeignKey(PgFkCategory4, on_delete=models.CASCADE)
            class Meta:
                app_label = 'test'
                db_table = 'pg_fk_product4'

        class PgFkCategoryImporter4(Importer):
            model = PgFkCategory4
            class Columns:
                pass

        class PgFkProductImporter4(Importer):
            model = PgFkProduct4
            class Columns:
                category = PgFkCategory4

        from django_gyro.importers import PostgresImporter
        importer = PostgresImporter("postgresql://test")
        
        # Mock existing category in database
        with patch('django_gyro.importers.PostgresImporter.check_fk_exists') as mock_check:
            mock_check.return_value = True
            
            row_data = {
                'name': 'Product 1',
                'category_id': '1'
            }
            
            validated_row = importer.resolve_foreign_keys(PgFkProduct4, row_data)
            
            # Should resolve FK correctly
            assert validated_row['category_id'] == 1
            mock_check.assert_called_once()

    def test_handles_missing_foreign_key_targets(self):
        """Test handling of missing FK target records."""
        class PgFkCategory5(models.Model):
            name = models.CharField(max_length=100)
            class Meta:
                app_label = 'test'
                db_table = 'pg_fk_category5'

        class PgFkProduct5(models.Model):
            name = models.CharField(max_length=100)
            category = models.ForeignKey(PgFkCategory5, on_delete=models.CASCADE)
            class Meta:
                app_label = 'test'
                db_table = 'pg_fk_product5'

        class PgFkCategoryImporter5(Importer):
            model = PgFkCategory5
            class Columns:
                pass

        class PgFkProductImporter5(Importer):
            model = PgFkProduct5
            class Columns:
                category = PgFkCategory5

        from django_gyro.importers import PostgresImporter
        importer = PostgresImporter("postgresql://test")
        
        # Mock missing category in database
        with patch('django_gyro.importers.PostgresImporter.check_fk_exists') as mock_check:
            mock_check.return_value = False
            
            row_data = {
                'name': 'Product 1',
                'category_id': '999'  # Non-existent category
            }
            
            with pytest.raises(ValueError, match="Foreign key target does not exist"):
                importer.resolve_foreign_keys(PgFkProduct5, row_data)

    def test_handles_multi_level_foreign_key_chains(self):
        """Test handling of multi-level FK chains."""
        class PgFkCountry1(models.Model):
            name = models.CharField(max_length=100)
            class Meta:
                app_label = 'test'
                db_table = 'pg_fk_country1'

        class PgFkRegion1(models.Model):
            name = models.CharField(max_length=100)
            country = models.ForeignKey(PgFkCountry1, on_delete=models.CASCADE)
            class Meta:
                app_label = 'test'
                db_table = 'pg_fk_region1'

        class PgFkCity1(models.Model):
            name = models.CharField(max_length=100)
            region = models.ForeignKey(PgFkRegion1, on_delete=models.CASCADE)
            class Meta:
                app_label = 'test'
                db_table = 'pg_fk_city1'

        class PgFkCountryImporter1(Importer):
            model = PgFkCountry1
            class Columns:
                pass

        class PgFkRegionImporter1(Importer):
            model = PgFkRegion1
            class Columns:
                country = PgFkCountry1

        class PgFkCityImporter1(Importer):
            model = PgFkCity1
            class Columns:
                region = PgFkRegion1

        from django_gyro.importers import PostgresImporter
        importer = PostgresImporter("postgresql://test")
        
        # Should validate multi-level FK chain
        fk_chain = importer.get_fk_dependency_chain(PgFkCity1)
        
        # Should identify the chain: City -> Region -> Country
        assert len(fk_chain) == 2  # Two levels of dependencies
        assert PgFkRegion1 in fk_chain
        assert PgFkCountry1 in fk_chain


class TestFKDependencyValidation(TestCase):
    """Test FK dependency validation functionality."""

    def setUp(self):
        """Clear the registry before each test."""
        if hasattr(Importer, '_registry'):
            Importer._registry.clear()

    def tearDown(self):
        """Clean up after each test."""
        if hasattr(Importer, '_registry'):
            Importer._registry.clear()

    def test_missing_fk_target_detection(self):
        """Test detection of missing FK targets before import."""
        class PgFkDep1Category(models.Model):
            name = models.CharField(max_length=100)
            class Meta:
                app_label = 'test'
                db_table = 'pg_fk_dep1_category'

        class PgFkDep1Product(models.Model):
            name = models.CharField(max_length=100)
            category = models.ForeignKey(PgFkDep1Category, on_delete=models.CASCADE)
            class Meta:
                app_label = 'test'
                db_table = 'pg_fk_dep1_product'

        class PgFkDep1CategoryImporter(Importer):
            model = PgFkDep1Category
            class Columns:
                pass

        class PgFkDep1ProductImporter(Importer):
            model = PgFkDep1Product
            class Columns:
                category = PgFkDep1Category

        from django_gyro.importers import FKDependencyValidator
        validator = FKDependencyValidator()
        
        # Mock CSV data with invalid FK references
        csv_data = [
            {'name': 'Product 1', 'category_id': '999'},  # Non-existent category
            {'name': 'Product 2', 'category_id': '888'}   # Non-existent category
        ]
        
        with patch('django_gyro.importers.FKDependencyValidator.check_fk_targets_exist') as mock_check:
            mock_check.return_value = {'missing_fks': [999, 888]}
            
            validation_result = validator.validate_fk_targets(PgFkDep1Product, csv_data)
            
            # Should detect missing FK targets
            assert not validation_result['valid']
            assert 'missing_fks' in validation_result
            assert 999 in validation_result['missing_fks']
            assert 888 in validation_result['missing_fks']

    def test_cyclical_relationship_detection(self):
        """Test detection of cyclical FK relationships."""
        class PgAsset1(models.Model):
            name = models.CharField(max_length=100)
            risk = models.ForeignKey('PgAssetRisk1', on_delete=models.CASCADE, null=True)
            class Meta:
                app_label = 'test'
                db_table = 'pg_asset1'

        class PgAssetRisk1(models.Model):
            name = models.CharField(max_length=100)
            asset = models.ForeignKey(PgAsset1, on_delete=models.CASCADE, null=True)
            class Meta:
                app_label = 'test'
                db_table = 'pg_asset_risk1'

        class PgAssetImporter1(Importer):
            model = PgAsset1
            class Columns:
                risk = PgAssetRisk1

        class PgAssetRiskImporter1(Importer):
            model = PgAssetRisk1
            class Columns:
                asset = PgAsset1

        from django_gyro.importers import FKDependencyValidator
        validator = FKDependencyValidator()
        
        importers = [PgAssetImporter1, PgAssetRiskImporter1]
        
        # Should detect cyclical dependency
        cycles = validator.detect_cyclical_dependencies(importers)
        
        assert len(cycles) > 0
        # Should detect Asset <-> AssetRisk cycle
        cycle = cycles[0]
        assert PgAsset1 in cycle
        assert PgAssetRisk1 in cycle

    def test_excluded_columns_support(self):
        """Test excluded columns functionality."""
        class PgAsset2(models.Model):
            name = models.CharField(max_length=100)
            risk = models.ForeignKey('PgAssetRisk2', on_delete=models.CASCADE, null=True)
            class Meta:
                app_label = 'test'
                db_table = 'pg_asset2'

        class PgAssetRisk2(models.Model):
            name = models.CharField(max_length=100)
            asset = models.ForeignKey(PgAsset2, on_delete=models.CASCADE, null=True)
            class Meta:
                app_label = 'test'
                db_table = 'pg_asset_risk2'

        class PgAssetImporter2(Importer):
            model = PgAsset2
            excluded = ['risk_id']  # Exclude problematic FK
            class Columns:
                risk = PgAssetRisk2

        class PgAssetRiskImporter2(Importer):
            model = PgAssetRisk2
            class Columns:
                asset = PgAsset2

        from django_gyro.importers import FKDependencyValidator
        validator = FKDependencyValidator()
        
        # Should validate excluded columns
        excluded_fields = validator.get_excluded_fields(PgAssetImporter2)
        assert 'risk_id' in excluded_fields
        
        # Should validate that excluded fields are FK fields
        validation_result = validator.validate_excluded_fields(PgAssetImporter2)
        assert validation_result['valid']

    def test_pre_import_validation(self):
        """Test comprehensive pre-import validation."""
        class PgAsset3(models.Model):
            name = models.CharField(max_length=100)
            risk = models.ForeignKey('PgAssetRisk3', on_delete=models.CASCADE, null=True)
            class Meta:
                app_label = 'test'
                db_table = 'pg_asset3'

        class PgAssetRisk3(models.Model):
            name = models.CharField(max_length=100)
            asset = models.ForeignKey(PgAsset3, on_delete=models.CASCADE, null=True)
            class Meta:
                app_label = 'test'
                db_table = 'pg_asset_risk3'

        # Without exclusions - should fail
        class PgAssetImporter3(Importer):
            model = PgAsset3
            class Columns:
                risk = PgAssetRisk3

        class PgAssetRiskImporter3(Importer):
            model = PgAssetRisk3
            class Columns:
                asset = PgAsset3

        from django_gyro.importers import FKDependencyValidator
        validator = FKDependencyValidator()
        
        importers = [PgAssetImporter3, PgAssetRiskImporter3]
        
        # Should fail validation due to cyclical dependency without exclusions
        validation_result = validator.validate_import_plan(importers)
        
        assert not validation_result['valid']
        assert 'cyclical_dependencies' in validation_result
        assert len(validation_result['cyclical_dependencies']) > 0


class TestPostgresImportConstraintHandling(TestCase):
    """Test constraint handling functionality."""

    def setUp(self):
        """Clear the registry before each test."""
        if hasattr(Importer, '_registry'):
            Importer._registry.clear()

    def tearDown(self):
        """Clean up after each test."""
        if hasattr(Importer, '_registry'):
            Importer._registry.clear()

    def test_unique_constraint_violations(self):
        """Test handling of unique constraint violations."""
        class PgConstraintModel1(models.Model):
            email = models.EmailField(unique=True)
            name = models.CharField(max_length=100)
            class Meta:
                app_label = 'test'
                db_table = 'pg_constraint_model1'

        class PgConstraintImporter1(Importer):
            model = PgConstraintModel1
            class Columns:
                pass

        from django_gyro.importers import PostgresImporter
        importer = PostgresImporter("postgresql://test")
        
        # Mock constraint violation
        with patch('django_gyro.importers.PostgresImporter.execute_import') as mock_execute:
            from django.db import IntegrityError
            mock_execute.side_effect = IntegrityError("UNIQUE constraint failed")
            
            csv_data = [
                {'email': 'test@example.com', 'name': 'John'},
                {'email': 'test@example.com', 'name': 'Jane'}  # Duplicate email
            ]
            
            with pytest.raises(ValueError, match="Unique constraint violation"):
                importer.import_data(PgConstraintModel1, csv_data)

    def test_database_constraint_errors(self):
        """Test handling of various database constraint errors."""
        class PgConstraintModel2(models.Model):
            name = models.CharField(max_length=100)
            age = models.IntegerField()
            
            class Meta:
                app_label = 'test'
                db_table = 'pg_constraint_model2'
                constraints = [
                    models.CheckConstraint(check=models.Q(age__gte=0), name='age_positive')
                ]

        class PgConstraintImporter2(Importer):
            model = PgConstraintModel2
            class Columns:
                pass

        from django_gyro.importers import PostgresImporter
        importer = PostgresImporter("postgresql://test")
        
        # Mock check constraint violation
        with patch('django_gyro.importers.PostgresImporter.execute_import') as mock_execute:
            from django.db import IntegrityError
            mock_execute.side_effect = IntegrityError("CHECK constraint failed")
            
            csv_data = [
                {'name': 'John', 'age': '-5'}  # Violates age >= 0 constraint
            ]
            
            with pytest.raises(ValueError, match="Database constraint violation"):
                importer.import_data(PgConstraintModel2, csv_data)

    def test_transaction_rollbacks(self):
        """Test transaction rollback on import failures."""
        class PgConstraintModel3(models.Model):
            name = models.CharField(max_length=100)
            email = models.EmailField(unique=True)
            class Meta:
                app_label = 'test'
                db_table = 'pg_constraint_model3'

        class PgConstraintImporter3(Importer):
            model = PgConstraintModel3
            class Columns:
                pass

        from django_gyro.importers import PostgresImporter
        importer = PostgresImporter("postgresql://test")
        
        # Mock transaction rollback
        with patch('django_gyro.importers.PostgresImporter.execute_import') as mock_execute:
            mock_execute.side_effect = Exception("Import failed")
            
            csv_data = [
                {'name': 'John', 'email': 'john@example.com'},
                {'name': 'Jane', 'email': 'jane@example.com'}
            ]
            
            with patch('django.db.transaction.rollback') as mock_rollback:
                with pytest.raises(Exception, match="Import failed"):
                    importer.import_data_with_transaction(PgConstraintModel3, csv_data)
                
                # Should have called rollback
                mock_rollback.assert_called_once() 