from django_gyro import Importer
from gyro_example.models import Customer, CustomerReferral, Order, OrderItem, Product, Shop, Tenant


class TenantImporter(Importer):
    model = Tenant

    class Columns:
        pass


class ShopImporter(Importer):
    model = Shop

    class Columns:
        tenant = Tenant


class CustomerImporter(Importer):
    model = Customer

    class Columns:
        tenant = Tenant
        shop = Shop


class ProductImporter(Importer):
    model = Product

    class Columns:
        tenant = Tenant
        shop = Shop


class OrderImporter(Importer):
    model = Order

    class Columns:
        tenant = Tenant
        shop = Shop
        customer = Customer


class OrderItemImporter(Importer):
    model = OrderItem

    class Columns:
        tenant = Tenant
        shop = Shop
        order = Order
        product = Product


class CustomerReferralImporter(Importer):
    model = CustomerReferral

    class Columns:
        tenant = Tenant
        shop = Shop
        referred_customer = Customer
        referring_customer = Customer
