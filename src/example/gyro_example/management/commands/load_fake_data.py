import logging
import random
from decimal import Decimal

from django.core.management.base import BaseCommand
from faker import Faker

from gyro_example.models import Customer, CustomerReferral, Order, OrderItem, Product, Shop, Tenant

logger = logging.getLogger(__name__)

fake = Faker()


class Command(BaseCommand):
    help = "Loads Fake Data"

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS("Creating fake data..."))

        # Clear existing data
        self.stdout.write("Clearing existing data...")
        CustomerReferral.objects.all().delete()
        OrderItem.objects.all().delete()
        Order.objects.all().delete()
        Product.objects.all().delete()
        Customer.objects.all().delete()
        Shop.objects.all().delete()
        Tenant.objects.all().delete()

        # Create tenants (3-8 tenants)
        num_tenants = random.randint(3, 8)
        tenants = self.create_tenants(num_tenants)
        self.stdout.write(f"Created {len(tenants)} tenants")

        # Create shops (1-4 shops per tenant)
        shops = self.create_shops(tenants)
        self.stdout.write(f"Created {len(shops)} shops")

        # Create products (10-50 products per shop)
        products = self.create_products(shops)
        self.stdout.write(f"Created {len(products)} products")

        # Create customers (20-100 customers per shop)
        customers = self.create_customers(shops)
        self.stdout.write(f"Created {len(customers)} customers")

        # Create orders (0-5 orders per customer)
        orders = self.create_orders(customers)
        self.stdout.write(f"Created {len(orders)} orders")

        # Create order items
        order_items = self.create_order_items(orders)
        self.stdout.write(f"Created {len(order_items)} order items")

        # Create customer referrals (demonstrates circular dependency)
        referrals = self.create_customer_referrals(customers)
        self.stdout.write(f"Created {len(referrals)} customer referrals")

        self.stdout.write(self.style.SUCCESS("Fake data created successfully!"))

    def create_tenants(self, count):
        tenants = []
        for _ in range(count):
            company_name = fake.company()
            subdomain = company_name.lower().replace(" ", "").replace(",", "").replace(".", "")[:20]
            # Ensure unique subdomain
            counter = 1
            original_subdomain = subdomain
            while Tenant.objects.filter(subdomain=subdomain).exists():
                subdomain = f"{original_subdomain}{counter}"
                counter += 1

            tenant = Tenant.objects.create(
                name=company_name,
                subdomain=subdomain[:50],
                is_active=random.choice([True, True, True, False]),  # 75% active
            )
            tenants.append(tenant)
        return tenants

    def create_shops(self, tenants):
        shops = []
        currencies = ["USD", "EUR", "GBP", "CAD", "AUD"]

        for tenant in tenants:
            # Each tenant has 1-4 shops
            num_shops = random.randint(1, 4)
            for _ in range(num_shops):
                shop_name = f"{fake.word().title()} {random.choice(['Store', 'Shop', 'Market', 'Boutique'])}"
                shop = Shop.objects.create(
                    tenant=tenant,
                    name=shop_name,
                    url=f"https://{shop_name.lower().replace(' ', '')}.example.com",
                    currency=random.choice(currencies),
                )
                shops.append(shop)
        return shops

    def create_products(self, shops):
        products = []
        product_types = [
            "T-Shirt",
            "Jeans",
            "Sneakers",
            "Jacket",
            "Hat",
            "Backpack",
            "Phone Case",
            "Headphones",
            "Laptop",
            "Tablet",
            "Book",
            "Mug",
            "Sunglasses",
            "Watch",
            "Wallet",
            "Belt",
            "Socks",
            "Gloves",
        ]

        for shop in shops:
            # Each shop has 10-50 products
            num_products = random.randint(10, 50)
            for _ in range(num_products):
                product_name = f"{fake.color_name().title()} {random.choice(product_types)}"

                # Generate unique SKU
                sku = f"{''.join(fake.random_letters(3)).upper()}{fake.random_number(digits=4)}"
                counter = 1
                original_sku = sku
                while Product.objects.filter(shop=shop, sku=sku).exists():
                    sku = f"{original_sku}{counter}"
                    counter += 1

                product = Product.objects.create(
                    tenant=shop.tenant,
                    shop=shop,
                    sku=sku,
                    name=product_name,
                    description=fake.text(max_nb_chars=200),
                    price=Decimal(str(random.uniform(9.99, 299.99))).quantize(Decimal("0.01")),
                    inventory_count=random.randint(0, 100),
                    is_active=random.choice([True, True, True, False]),  # 75% active
                )
                products.append(product)
        return products

    def create_customers(self, shops):
        customers = []
        for shop in shops:
            # Each shop has 20-100 customers
            num_customers = random.randint(20, 100)
            for _ in range(num_customers):
                first_name = fake.first_name()
                last_name = fake.last_name()
                email = f"{first_name.lower()}.{last_name.lower()}@{fake.domain_name()}"

                # Ensure unique email per shop
                counter = 1
                while Customer.objects.filter(shop=shop, email=email).exists():
                    email = f"{first_name.lower()}.{last_name.lower()}{counter}@{fake.domain_name()}"
                    counter += 1

                phone = fake.phone_number()[:20]

                customer = Customer.objects.create(
                    tenant=shop.tenant,
                    shop=shop,
                    email=email,
                    first_name=first_name,
                    last_name=last_name,
                    phone=phone,
                )
                customers.append(customer)
        return customers

    def create_orders(self, customers):
        orders = []
        statuses = ["pending", "processing", "shipped", "delivered", "cancelled"]
        status_weights = [0.1, 0.2, 0.3, 0.35, 0.05]  # Most orders are delivered

        for customer in customers:
            # Each customer has 0-5 orders
            num_orders = random.randint(0, 5)
            for _i in range(num_orders):
                order_number = f"ORD-{fake.random_number(digits=8)}"

                # Ensure unique order number per shop
                counter = 1
                original_order_number = order_number
                while Order.objects.filter(shop=customer.shop, order_number=order_number).exists():
                    order_number = f"{original_order_number}-{counter}"
                    counter += 1

                # Calculate realistic amounts
                subtotal = Decimal(str(random.uniform(25.00, 500.00))).quantize(Decimal("0.01"))
                tax_rate = Decimal("0.08")  # 8% tax
                tax_amount = (subtotal * tax_rate).quantize(Decimal("0.01"))
                shipping_amount = Decimal(str(random.uniform(5.00, 25.00))).quantize(Decimal("0.01"))
                total_amount = subtotal + tax_amount + shipping_amount

                order = Order.objects.create(
                    tenant=customer.tenant,
                    shop=customer.shop,
                    customer=customer,
                    order_number=order_number,
                    status=random.choices(statuses, weights=status_weights)[0],
                    total_amount=total_amount,
                    tax_amount=tax_amount,
                    shipping_amount=shipping_amount,
                )
                orders.append(order)
        return orders

    def create_order_items(self, orders):
        order_items = []

        for order in orders:
            # Get active products from the same shop
            shop_products = list(Product.objects.filter(shop=order.shop, is_active=True))

            if not shop_products:
                continue

            # Each order has 1-5 items
            num_items = random.randint(1, min(5, len(shop_products)))
            selected_products = random.sample(shop_products, num_items)

            for product in selected_products:
                quantity = random.randint(1, 3)
                unit_price = product.price
                total_price = unit_price * quantity

                order_item = OrderItem.objects.create(
                    tenant=order.tenant,
                    shop=order.shop,
                    order=order,
                    product=product,
                    quantity=quantity,
                    unit_price=unit_price,
                    total_price=total_price,
                )
                order_items.append(order_item)

        return order_items

    def create_customer_referrals(self, customers):
        """Create customer referrals - demonstrates circular dependency Customer ↔ CustomerReferral"""
        referrals = []
        
        # Group customers by shop for referral generation
        customers_by_shop = {}
        for customer in customers:
            shop_key = customer.shop.id
            if shop_key not in customers_by_shop:
                customers_by_shop[shop_key] = []
            customers_by_shop[shop_key].append(customer)
        
        for shop_id, shop_customers in customers_by_shop.items():
            if len(shop_customers) < 2:
                continue  # Need at least 2 customers for referrals
            
            # Create 10-30% of customers as referred customers
            num_referrals = max(1, int(len(shop_customers) * random.uniform(0.1, 0.3)))
            
            for _ in range(num_referrals):
                # Pick a random referring customer and referred customer
                referring_customer = random.choice(shop_customers)
                referred_customer = random.choice([c for c in shop_customers if c != referring_customer])
                
                # Generate unique referral code
                letters = ''.join(fake.random_letters(4)).upper()
                referral_code = f"REF-{letters}{fake.random_number(digits=4)}"
                counter = 1
                original_code = referral_code
                while CustomerReferral.objects.filter(referral_code=referral_code).exists():
                    referral_code = f"{original_code}{counter}"
                    counter += 1
                
                # Create referral with business metrics
                commission = Decimal(str(random.uniform(5.0, 50.0))).quantize(Decimal("0.01"))
                orders_count = random.randint(0, 15)
                revenue = Decimal(str(random.uniform(50.0, 500.0))).quantize(Decimal("0.01"))
                
                referral = CustomerReferral.objects.create(
                    tenant=referring_customer.tenant,
                    shop=referring_customer.shop,
                    referred_customer=referred_customer,
                    referring_customer=referring_customer,
                    referral_code=referral_code,
                    status=random.choices(
                        ["pending", "confirmed", "rewarded", "expired"],
                        weights=[10, 50, 30, 10]  # Most are confirmed/rewarded
                    )[0],
                    commission_earned=commission,
                    orders_generated=orders_count,
                    total_revenue=revenue,
                )
                referrals.append(referral)
        
        # CIRCULAR DEPENDENCY PART: Update some customers with primary_referrer
        # This demonstrates the circular Customer -> CustomerReferral relationship
        for referral in referrals[:len(referrals)//2]:  # Update about half
            if referral.status in ['confirmed', 'rewarded']:
                # Set this as the customer's primary referral source
                referral.referred_customer.primary_referrer = referral
                referral.referred_customer.save()
        
        return referrals
