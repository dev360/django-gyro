"""
Tests for ImportContext value object.

Following TDD principles - tests are written first, focusing on behavior.
"""

from pathlib import Path
import pytest
from unittest.mock import Mock

from django_gyro.importing import ImportContext, SequentialRemappingStrategy


class TestImportContext:
    """Tests for ImportContext value object behavior."""
    
    def test_creates_with_required_source_directory(self):
        """ImportContext requires a source directory."""
        # Setup
        import tempfile
        with tempfile.TemporaryDirectory() as temp_dir:
            source_dir = Path(temp_dir)
            
            # Exercise
            context = ImportContext(source_directory=source_dir)
            
            # Verify
            assert context.source_directory == source_dir
            assert isinstance(context.source_directory, Path)
    
    def test_has_sensible_defaults(self):
        """ImportContext provides sensible defaults for optional parameters."""
        # Setup
        import tempfile
        with tempfile.TemporaryDirectory() as temp_dir:
            source_dir = Path(temp_dir)
            
            # Exercise
            context = ImportContext(source_directory=source_dir)
            
            # Verify
            assert context.batch_size == 10000
            assert context.use_copy is True
            assert context.target_database == 'default'
            assert context.id_mapping == {}
    
    def test_accepts_custom_batch_size(self):
        """Batch size can be customized for memory management."""
        # Setup
        import tempfile
        with tempfile.TemporaryDirectory() as temp_dir:
            source_dir = Path(temp_dir)
            
            # Exercise
            context = ImportContext(
                source_directory=source_dir,
                batch_size=50000
            )
            
            # Verify
            assert context.batch_size == 50000
    
    def test_validates_source_directory_exists(self):
        """ImportContext validates that source directory exists."""
        # Setup
        non_existent = Path("/definitely/does/not/exist")
        
        # Exercise & Verify
        with pytest.raises(ValueError, match="Source directory does not exist"):
            ImportContext(source_directory=non_existent)
    
    def test_stores_target_database_name(self):
        """ImportContext can target a specific database."""
        # Setup
        import tempfile
        with tempfile.TemporaryDirectory() as temp_dir:
            source_dir = Path(temp_dir)
            
            # Exercise
            context = ImportContext(
                source_directory=source_dir,
                target_database='import_target'
            )
            
            # Verify
            assert context.target_database == 'import_target'
    
    def test_tracks_id_mappings_across_models(self):
        """ImportContext maintains ID mappings for all models."""
        # Setup
        import tempfile
        with tempfile.TemporaryDirectory() as temp_dir:
            source_dir = Path(temp_dir)
            context = ImportContext(source_directory=source_dir)
            
            # Exercise
            context.add_id_mapping('myapp.Tenant', old_id=1000, new_id=1)
            context.add_id_mapping('myapp.Tenant', old_id=1001, new_id=2)
            context.add_id_mapping('myapp.Shop', old_id=2000, new_id=10)
            
            # Verify
            assert context.get_id_mapping('myapp.Tenant', 1000) == 1
            assert context.get_id_mapping('myapp.Tenant', 1001) == 2
            assert context.get_id_mapping('myapp.Shop', 2000) == 10
            assert context.get_id_mapping('myapp.Shop', 9999) is None
    
    def test_provides_remapping_strategy(self):
        """ImportContext can be configured with a remapping strategy."""
        # Setup
        import tempfile
        with tempfile.TemporaryDirectory() as temp_dir:
            source_dir = Path(temp_dir)
            strategy = Mock(spec=SequentialRemappingStrategy)
            
            # Exercise
            context = ImportContext(
                source_directory=source_dir,
                id_remapping_strategy=strategy
            )
            
            # Verify
            assert context.id_remapping_strategy is strategy
    
    def test_tracks_import_progress(self):
        """ImportContext tracks which models have been imported."""
        # Setup
        import tempfile
        with tempfile.TemporaryDirectory() as temp_dir:
            source_dir = Path(temp_dir)
            context = ImportContext(source_directory=source_dir)
            
            # Exercise
            context.mark_model_imported('myapp.Tenant')
            context.mark_model_imported('myapp.Shop')
            
            # Verify
            assert context.is_model_imported('myapp.Tenant') is True
            assert context.is_model_imported('myapp.Shop') is True
            assert context.is_model_imported('myapp.Customer') is False
    
    def test_finds_csv_files_in_source_directory(self):
        """ImportContext can discover CSV files in the source directory."""
        # Setup
        import tempfile
        import os
        
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create some CSV files
            Path(temp_dir, "tenant.csv").touch()
            Path(temp_dir, "shop.csv").touch()
            Path(temp_dir, "not_csv.txt").touch()
            
            context = ImportContext(source_directory=Path(temp_dir))
            
            # Exercise
            csv_files = context.discover_csv_files()
            
            # Verify
            assert len(csv_files) == 2
            assert any(f.name == "tenant.csv" for f in csv_files)
            assert any(f.name == "shop.csv" for f in csv_files)
            assert not any(f.name == "not_csv.txt" for f in csv_files)
    
    def test_equality_based_on_configuration(self):
        """Two ImportContexts with same config are equal."""
        # Setup
        import tempfile
        with tempfile.TemporaryDirectory() as temp_dir:
            source_dir = Path(temp_dir)
            
            # Exercise
            context1 = ImportContext(
                source_directory=source_dir,
                batch_size=5000,
                target_database='other'
            )
            context2 = ImportContext(
                source_directory=source_dir,
                batch_size=5000,
                target_database='other'
            )
            context3 = ImportContext(
                source_directory=source_dir,
                batch_size=10000,  # Different
                target_database='other'
            )
            
            # Verify
            assert context1 == context2
            assert context1 != context3