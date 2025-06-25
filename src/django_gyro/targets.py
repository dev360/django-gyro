"""
Django Gyro Target Classes

This module provides target classes for writing data to various destinations,
primarily file systems with CSV format support.
"""

import os
from typing import Any, Dict, List, Optional


class FileTarget:
    """
    File system target for writing CSV data.

    This class handles writing CSV data to files with directory management,
    overwrite protection, and file validation.
    """

    def __init__(self, base_path: str, overwrite: bool = False):
        """
        Initialize File target.

        Args:
            base_path: Base directory path for writing files
            overwrite: Whether to overwrite existing files

        Raises:
            ValueError: If directory doesn't exist or isn't accessible
        """
        self.base_path = os.path.abspath(base_path)
        self.overwrite = overwrite

        # Validate directory exists and is accessible
        if not os.path.exists(self.base_path):
            raise ValueError(f"Directory does not exist or is not accessible: {self.base_path}")

        if not os.path.isdir(self.base_path):
            raise ValueError(f"Path is not a directory: {self.base_path}")

        if not os.access(self.base_path, os.W_OK):
            raise ValueError(f"Directory is not writable: {self.base_path}")

    def ensure_directory_exists(self, file_path: str) -> None:
        """
        Ensure the directory for a file path exists.

        Args:
            file_path: File path (can include subdirectories)
        """
        full_path = os.path.join(self.base_path, file_path)
        directory = os.path.dirname(full_path)

        if directory and not os.path.exists(directory):
            os.makedirs(directory, exist_ok=True)

    def check_existing_files(self, file_paths: List[str]) -> List[str]:
        """
        Check which files already exist.

        Args:
            file_paths: List of relative file paths to check

        Returns:
            List of existing file paths
        """
        existing_files = []

        for file_path in file_paths:
            full_path = os.path.join(self.base_path, file_path)
            if os.path.exists(full_path):
                existing_files.append(file_path)

        return existing_files

    def validate_overwrite(self, file_paths: List[str], overwrite: Optional[bool] = None) -> None:
        """
        Validate overwrite settings for files.

        Args:
            file_paths: List of file paths to validate
            overwrite: Override instance overwrite setting

        Raises:
            ValueError: If files exist and overwrite is not allowed
        """
        use_overwrite = overwrite if overwrite is not None else self.overwrite

        if not use_overwrite:
            existing_files = self.check_existing_files(file_paths)
            if existing_files:
                raise ValueError(
                    f"Files already exist: {existing_files}. Use overwrite=True to overwrite existing files."
                )

    def write_csv(self, file_path: str, csv_data: str) -> Dict[str, Any]:
        """
        Write CSV data to file.

        Args:
            file_path: Relative file path within base directory
            csv_data: CSV data as string

        Returns:
            Dict with write statistics
        """
        # Ensure directory exists
        self.ensure_directory_exists(file_path)

        # Validate overwrite if needed
        self.validate_overwrite([file_path])

        # Write file
        full_path = os.path.join(self.base_path, file_path)

        with open(full_path, "w", encoding="utf-8", newline="") as f:
            f.write(csv_data)

        # Get file statistics
        file_size = os.path.getsize(full_path)

        # Count rows (approximate)
        rows_written = csv_data.count("\n")
        if csv_data and not csv_data.endswith("\n"):
            rows_written += 1

        return {"file_path": full_path, "bytes_written": file_size, "rows_written": rows_written}

    def copy_file_from_source(self, source_path: str, target_path: str) -> Dict[str, Any]:
        """
        Copy a file from source to target location.

        Args:
            source_path: Source file path
            target_path: Target file path (relative to base_path)

        Returns:
            Dict with copy statistics
        """
        # Ensure directory exists
        self.ensure_directory_exists(target_path)

        # Validate overwrite if needed
        self.validate_overwrite([target_path])

        # Copy file
        full_target_path = os.path.join(self.base_path, target_path)

        import shutil

        shutil.copy2(source_path, full_target_path)

        # Get file statistics
        file_size = os.path.getsize(full_target_path)

        return {"source_path": source_path, "target_path": full_target_path, "bytes_copied": file_size}

    def list_files(self, pattern: Optional[str] = None) -> List[str]:
        """
        List files in the target directory.

        Args:
            pattern: Optional glob pattern to filter files

        Returns:
            List of file paths relative to base_path
        """
        import glob

        if pattern:
            search_pattern = os.path.join(self.base_path, pattern)
            files = glob.glob(search_pattern)
            # Convert to relative paths
            return [os.path.relpath(f, self.base_path) for f in files]
        else:
            files = []
            for root, _dirs, filenames in os.walk(self.base_path):
                for filename in filenames:
                    full_path = os.path.join(root, filename)
                    rel_path = os.path.relpath(full_path, self.base_path)
                    files.append(rel_path)
            return files

    def get_file_info(self, file_path: str) -> Dict[str, Any]:
        """
        Get information about a file.

        Args:
            file_path: File path relative to base_path

        Returns:
            Dict with file information
        """
        full_path = os.path.join(self.base_path, file_path)

        if not os.path.exists(full_path):
            raise FileNotFoundError(f"File not found: {file_path}")

        stat = os.stat(full_path)

        return {
            "file_path": file_path,
            "full_path": full_path,
            "size_bytes": stat.st_size,
            "modified_time": stat.st_mtime,
            "created_time": stat.st_ctime,
        }
