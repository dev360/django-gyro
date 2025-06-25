import json
import logging

from django.core.management.base import BaseCommand

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Loads Fake Data"

    def handle(self, *args, **options):
        pass
