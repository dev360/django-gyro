"""Test settings for django-gyro.

This ensures tests always use PostgreSQL/PostGIS and never fall back to SQLite.
"""

from os import environ

from .settings import INSTALLED_APPS

# Force PostgreSQL for tests - no SQLite fallback
DATABASES = {
    "default": {
        "ENGINE": "django.contrib.gis.db.backends.postgis",
        "NAME": environ.get("POSTGRES_DB", "gyro_example") + "_test",
        "USER": environ.get("POSTGRES_USER", "gyro_user"),
        "PASSWORD": environ.get("POSTGRES_PASSWORD", "gyro_password"),
        "HOST": environ.get("POSTGRES_HOST", "gyro_db"),
        "PORT": environ.get("POSTGRES_PORT", "5432"),
        "TEST": {
            "NAME": environ.get("POSTGRES_DB", "gyro_example") + "_test",
        },
    },
    "other": {
        "ENGINE": "django.contrib.gis.db.backends.postgis",
        "NAME": environ.get("POSTGRES_DB_OTHER", "gyro_example_other") + "_test",
        "USER": environ.get("POSTGRES_USER", "gyro_user"),
        "PASSWORD": environ.get("POSTGRES_PASSWORD", "gyro_password"),
        "HOST": environ.get("POSTGRES_HOST", "gyro_db"),
        "PORT": environ.get("POSTGRES_PORT", "5432"),
        "TEST": {
            "NAME": environ.get("POSTGRES_DB_OTHER", "gyro_example_other") + "_test",
        },
    },
}

# Ensure PostGIS extension is available
INSTALLED_APPS = list(INSTALLED_APPS)
if "django.contrib.gis" not in INSTALLED_APPS:
    INSTALLED_APPS.insert(0, "django.contrib.gis")
