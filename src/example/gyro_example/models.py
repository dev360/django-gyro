import uuid

from django.db import models

# Conditional PostGIS import
try:
    from django.contrib.gis.db import models as gis_models

    HAS_POSTGIS = True
except ImportError:
    HAS_POSTGIS = False

    # Create a dummy field for when PostGIS isn't available
    class DummyGeometryField(models.TextField):
        """Fallback field when PostGIS is not available."""

        pass

    # Create a dummy gis_models namespace for consistency
    class gis_models:
        MultiPolygonField = DummyGeometryField


class Tenant(models.Model):
    """Multi-tenant organization"""

    name = models.CharField(max_length=200)
    subdomain = models.CharField(max_length=50, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)


class Shop(models.Model):
    """Individual shop within a tenant"""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE)
    name = models.CharField(max_length=200)
    url = models.URLField()
    currency = models.CharField(max_length=3, default="USD")
    created_at = models.DateTimeField(auto_now_add=True)


class Customer(models.Model):
    """Customer of a shop"""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE)
    shop = models.ForeignKey(Shop, on_delete=models.CASCADE)
    email = models.EmailField()
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    phone = models.CharField(max_length=20, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    # Geometry field - uses PostGIS if available, otherwise falls back to text field
    if HAS_POSTGIS:
        geom = gis_models.MultiPolygonField(null=True, blank=True)
    else:
        geom = models.TextField(null=True, blank=True, help_text="PostGIS not available - geometry stored as text")

    # CIRCULAR DEPENDENCY: Customer -> CustomerReferral (nullable, loads first)
    primary_referrer = models.ForeignKey(
        "CustomerReferral",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text="The referral that brought this customer the most value",
    )

    class Meta:
        unique_together = ["shop", "email"]


class Product(models.Model):
    """Product in a shop"""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE)
    shop = models.ForeignKey(Shop, on_delete=models.CASCADE)
    sku = models.CharField(max_length=100)
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    inventory_count = models.IntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ["shop", "sku"]


class Order(models.Model):
    """Customer order"""

    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("processing", "Processing"),
        ("shipped", "Shipped"),
        ("delivered", "Delivered"),
        ("cancelled", "Cancelled"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE)
    shop = models.ForeignKey(Shop, on_delete=models.CASCADE)
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE)
    order_number = models.CharField(max_length=50)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    total_amount = models.DecimalField(max_digits=10, decimal_places=2)
    tax_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    shipping_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ["shop", "order_number"]


class OrderItem(models.Model):
    """Individual item within an order"""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE)
    shop = models.ForeignKey(Shop, on_delete=models.CASCADE)
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    quantity = models.IntegerField()
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    total_price = models.DecimalField(max_digits=10, decimal_places=2)


class CustomerReferral(models.Model):
    """Customer referral tracking - demonstrates circular dependency with Customer"""

    REFERRAL_STATUS = [
        ("pending", "Pending"),
        ("confirmed", "Confirmed"),
        ("rewarded", "Rewarded"),
        ("expired", "Expired"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE)
    shop = models.ForeignKey(Shop, on_delete=models.CASCADE)

    # CIRCULAR DEPENDENCY: CustomerReferral -> Customer (required, loads second)
    referred_customer = models.ForeignKey(
        Customer, on_delete=models.CASCADE, related_name="referrals_received", help_text="Customer who was referred"
    )
    referring_customer = models.ForeignKey(
        Customer, on_delete=models.CASCADE, related_name="referrals_made", help_text="Customer who made the referral"
    )

    referral_code = models.CharField(max_length=50, unique=True)
    status = models.CharField(max_length=20, choices=REFERRAL_STATUS, default="pending")

    # Tracking business value
    commission_earned = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    orders_generated = models.IntegerField(default=0, help_text="Number of orders from this referral")
    total_revenue = models.DecimalField(
        max_digits=10, decimal_places=2, default=0, help_text="Total revenue generated from this referral"
    )

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    confirmed_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = ["shop", "referral_code"]

    def __str__(self):
        return f"{self.referring_customer.email} → {self.referred_customer.email} ({self.status})"
