"""
Django Gyro: A Django data slicer utility for CSV import/export.

This package provides a framework for importing and exporting Django model data
with proper dependency handling and flexible configuration.
"""

from .core import Importer, ImportJob

__version__ = "0.1.0"
__all__ = ["Importer", "ImportJob"]
