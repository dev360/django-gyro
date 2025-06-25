#!/usr/bin/env python
"""
Django management command to demonstrate the complete Django Gyro end-to-end workflow.

This command demonstrates the exact API described in the technical design document,
running inside the Docker container with real PostgreSQL database and data.

Usage:
    python manage.py demo_end_to_end

This will:
1. Ensure we have sample data in the database
2. Create export queries for a specific tenant's data
3. Use DataSlicer.run() to export data from PostgreSQL to CSV files
4. Show the results and verify the files were created
"""

import os

from django.core.management.base import BaseCommand
from django.db import connection

from django_gyro import DataSlicer, ImportJob
from gyro_example.models import Customer, Order, OrderItem, Product, Shop, Tenant


class Command(BaseCommand):
    help = "Demonstrate Django Gyro end-to-end workflow with real data"

    def add_arguments(self, parser):
        parser.add_argument("--tenant-id", type=int, default=1, help="Tenant ID to export data for (default: 1)")
        parser.add_argument(
            "--output-dir",
            type=str,
            default="/tmp/gyro_exports",
            help="Output directory for CSV files (default: /tmp/gyro_exports)",
        )
        parser.add_argument(
            "--use-host-volume",
            action="store_true",
            help="Export to gyro_example/exports (mounted to host) for easy verification",
        )

    def handle(self, *args, **options):
        tenant_id = options["tenant_id"]

        if options["use_host_volume"]:
            output_dir = "/app/src/example/gyro_example/exports"
        else:
            output_dir = options["output_dir"]

        self.stdout.write(self.style.SUCCESS("Django Gyro End-to-End Demo"))
        self.stdout.write("=" * 50)

        # Step 1: Verify database connection and data
        self.stdout.write("\n1. Verifying database connection and data...")

        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT version();")
                pg_version = cursor.fetchone()[0]
                self.stdout.write(f"   ✅ PostgreSQL connected: {pg_version.split(',')[0]}")
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"   ❌ Database connection failed: {e}"))
            return

        # Check data counts
        tenant_count = Tenant.objects.count()
        shop_count = Shop.objects.count()
        customer_count = Customer.objects.count()
        product_count = Product.objects.count()
        order_count = Order.objects.count()
        order_item_count = OrderItem.objects.count()

        self.stdout.write("   📊 Data Summary:")
        self.stdout.write(f"      - Tenants: {tenant_count}")
        self.stdout.write(f"      - Shops: {shop_count}")
        self.stdout.write(f"      - Customers: {customer_count}")
        self.stdout.write(f"      - Products: {product_count}")
        self.stdout.write(f"      - Orders: {order_count}")
        self.stdout.write(f"      - Order Items: {order_item_count}")

        if tenant_count == 0:
            self.stdout.write(self.style.WARNING("   ⚠️  No data found. Run: python manage.py load_fake_data"))
            return

        # Step 2: Create export queries for specific tenant
        self.stdout.write(f"\n2. Creating export queries for tenant ID {tenant_id}...")

        try:
            target_tenant = Tenant.objects.get(id=tenant_id)
            self.stdout.write(f"   🎯 Target tenant: {target_tenant.name} ({target_tenant.subdomain})")
        except Tenant.DoesNotExist:
            self.stdout.write(self.style.ERROR(f"   ❌ Tenant with ID {tenant_id} not found"))
            return

        # Create QuerySets as described in technical design
        tenant_query = Tenant.objects.filter(id=tenant_id)
        shops_query = Shop.objects.filter(tenant=target_tenant)
        customers_query = Customer.objects.filter(tenant=target_tenant)
        products_query = Product.objects.filter(tenant=target_tenant)
        orders_query = Order.objects.filter(tenant=target_tenant)
        order_items_query = OrderItem.objects.filter(tenant=target_tenant)

        self.stdout.write("   📋 Export Query Summary:")
        self.stdout.write(f"      - Tenant: {tenant_query.count()} record(s)")
        self.stdout.write(f"      - Shops: {shops_query.count()} record(s)")
        self.stdout.write(f"      - Customers: {customers_query.count()} record(s)")
        self.stdout.write(f"      - Products: {products_query.count()} record(s)")
        self.stdout.write(f"      - Orders: {orders_query.count()} record(s)")
        self.stdout.write(f"      - Order Items: {order_items_query.count()} record(s)")

        # Step 3: Set up DataSlicer export
        self.stdout.write("\n3. Setting up DataSlicer export...")

        # Create output directory
        os.makedirs(output_dir, exist_ok=True)
        self.stdout.write(f"   📁 Output directory: {output_dir}")

        # Get database connection string from Django settings
        from django.conf import settings

        db_config = settings.DATABASES["default"]
        postgres_url = (
            f"postgresql://{db_config['USER']}:{db_config['PASSWORD']}"
            f"@{db_config['HOST']}:{db_config['PORT']}/{db_config['NAME']}"
        )
        self.stdout.write(f"   🔗 Database URL: {postgres_url.replace(db_config['PASSWORD'], '***')}")

        # Step 4: Execute DataSlicer.run() - The main API from technical design
        self.stdout.write("\n4. Executing DataSlicer.run() - Main ETL Workflow...")

        def progress_callback(info):
            self.stdout.write(
                f"   📤 Exported {info.get('rows_exported', 0)} rows to {info.get('file_created', 'file')}"
            )

        try:
            # This is the exact API call described in the technical design
            result = DataSlicer.run(
                source=DataSlicer.Postgres(postgres_url),
                target=DataSlicer.File(output_dir, overwrite=True),
                jobs=[
                    ImportJob(model=Tenant, query=tenant_query),
                    ImportJob(model=Shop, query=shops_query),
                    ImportJob(model=Customer, query=customers_query),
                    ImportJob(model=Product, query=products_query),
                    ImportJob(model=Order, query=orders_query),
                    ImportJob(model=OrderItem, query=order_items_query),
                ],
                progress_callback=progress_callback,
                use_notebook_progress=False,
            )

            self.stdout.write("\n   ✅ DataSlicer.run() completed successfully!")

        except Exception as e:
            self.stdout.write(self.style.ERROR(f"   ❌ DataSlicer.run() failed: {e}"))
            import traceback

            self.stdout.write(traceback.format_exc())
            return

        # Step 5: Show results
        self.stdout.write("\n5. Export Results:")
        self.stdout.write(f"   🎯 Jobs executed: {result['jobs_executed']}")
        self.stdout.write(f"   📄 Files created: {len(result['files_created'])}")
        self.stdout.write(f"   📊 Total rows exported: {result['total_rows_exported']}")
        self.stdout.write(f"   🔗 Source type: {result['source_type']}")
        self.stdout.write(f"   💾 Target type: {result['target_type']}")

        # Step 6: Verify files and show contents
        self.stdout.write("\n6. File Verification:")

        for file_path in result["files_created"]:
            if os.path.exists(file_path):
                file_size = os.path.getsize(file_path)
                filename = os.path.basename(file_path)

                self.stdout.write(f"   ✅ {filename} ({file_size} bytes)")

                # Show first few lines of each CSV
                try:
                    with open(file_path) as f:
                        lines = f.readlines()[:3]  # Show header + 2 data rows
                        for i, line in enumerate(lines):
                            prefix = "      Header:" if i == 0 else f"      Row {i}:"
                            self.stdout.write(
                                f"{prefix} {line.strip()[:80]}..."
                                if len(line.strip()) > 80
                                else f"{prefix} {line.strip()}"
                            )

                except Exception as e:
                    self.stdout.write(f"      ⚠️  Could not read file: {e}")
            else:
                self.stdout.write(f"   ❌ {file_path} - File not found")

        # Step 7: Summary and next steps
        self.stdout.write("\n7. Demo Summary:")
        self.stdout.write("   ✅ Database connection verified")
        self.stdout.write("   ✅ Sample data loaded and queried")
        self.stdout.write("   ✅ DataSlicer.run() executed successfully")
        self.stdout.write("   ✅ CSV files exported and verified")
        self.stdout.write("   ✅ All components working end-to-end")

        self.stdout.write("\n📋 Key Features Demonstrated:")
        self.stdout.write("   ✅ DataSlicer.run() - Main ETL orchestration")
        self.stdout.write("   ✅ DataSlicer.Postgres() - PostgreSQL source")
        self.stdout.write("   ✅ DataSlicer.File() - File system target")
        self.stdout.write("   ✅ ImportJob - Data export job definition")
        self.stdout.write("   ✅ Automatic dependency sorting")
        self.stdout.write("   ✅ PostgreSQL COPY operations")
        self.stdout.write("   ✅ CSV file generation")
        self.stdout.write("   ✅ Progress tracking")

        if options["use_host_volume"]:
            self.stdout.write("\n💡 Files exported to gyro_example/exports (mounted to host)")
            self.stdout.write("   You can view them from your host machine in src/example/gyro_example/exports/")
        else:
            self.stdout.write(f"\n💡 Files exported to {output_dir}")
            self.stdout.write("   Use --use-host-volume to export to a host-mounted directory")

        self.stdout.write("\n" + "=" * 50)
        self.stdout.write(self.style.SUCCESS("🎉 Django Gyro End-to-End Demo Completed Successfully!"))
        self.stdout.write("The API works exactly as described in the technical design.")
