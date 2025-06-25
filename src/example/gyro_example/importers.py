from django_gyro import Importer
from gyro_example.models import Customer, Site, Tenant


class TenantImporter(Importer):
    model = Tenant

    class Columns:
        pass


class SiteImporter(Importer):
    model = Site

    class Columns:
        tenant = Tenant


class CustomerImporter(Importer):
    model = Customer

    class Columns:
        site = Site


class OrderImporter(Importer):
    class Columns:
        tenant = Tenant
        site = Site
        customer = Customer
