import logging

from django.apps import AppConfig

logger = logging.getLogger(__name__)


class GyroConfig(AppConfig):
    name = "django_gyro"
    label = "django_gyro"
    verbose_name = "Django Gyro"
