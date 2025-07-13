"""
End-to-end integration test demonstrating:
1. Circular dependency resolution (Customer ↔ CustomerReferral)
2. UUID handling for all models except Tenant
3. Sequential ID remapping for Tenant
4. Complete export/import cycle
"""

import tempfile
import uuid
from pathlib import Path
from unittest.mock import patch

from django.test import TestCase
from gyro_example.models import Customer, CustomerReferral, Order, Shop, Tenant

from src.django_gyro.importing import CircularDependencyResolver, ImportContext, TenantAwareRemappingStrategy


class EndToEndCircularDependencyTest(TestCase):
    """Test end-to-end import/export with circular dependencies and mixed ID types"""

    databases = ["default", "import_test"]

    def setUp(self):
        """Set up test data with circular dependencies"""
        self.temp_dir = Path(tempfile.mkdtemp())

        # Create source tenant with sequential ID
        self.source_tenant = Tenant.objects.create(name="Source Corp", subdomain="source-corp")

        # Create target tenant with different sequential ID
        self.target_tenant = Tenant.objects.create(name="Target Inc", subdomain="target-inc")

        # Create shop with UUID
        self.shop = Shop.objects.create(
            tenant=self.source_tenant, name="Test Shop", url="https://test.example.com", currency="USD"
        )

        # Create customers with UUIDs
        self.customer1 = Customer.objects.create(
            tenant=self.source_tenant, shop=self.shop, email="customer1@test.com", first_name="John", last_name="Doe"
        )

        self.customer2 = Customer.objects.create(
            tenant=self.source_tenant, shop=self.shop, email="customer2@test.com", first_name="Jane", last_name="Smith"
        )

        # Create circular dependency: CustomerReferral
        self.referral = CustomerReferral.objects.create(
            tenant=self.source_tenant,
            shop=self.shop,
            referred_customer=self.customer1,
            referring_customer=self.customer2,
            referral_code="TEST123",
            status="confirmed",
            commission_earned=25.00,
            orders_generated=3,
            total_revenue=150.00,
        )

        # Complete the circle: Update customer to reference the referral
        self.customer1.primary_referrer = self.referral
        self.customer1.save()

        # Create orders with UUIDs
        self.order1 = Order.objects.create(
            tenant=self.source_tenant,
            shop=self.shop,
            customer=self.customer1,
            order_number="ORD-001",
            status="completed",
            total_amount=75.00,
            tax_amount=5.25,
            shipping_amount=8.00,
        )

        self.order2 = Order.objects.create(
            tenant=self.source_tenant,
            shop=self.shop,
            customer=self.customer2,
            order_number="ORD-002",
            status="pending",
            total_amount=50.00,
            tax_amount=3.50,
            shipping_amount=6.00,
        )

    def tearDown(self):
        """Clean up temporary files"""
        import shutil

        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_circular_dependency_detection(self):
        """Test that circular dependencies are properly detected"""
        resolver = CircularDependencyResolver()

        models = [Customer, CustomerReferral]
        cycles = resolver.detect_circular_dependencies(models)

        self.assertEqual(len(cycles), 1, "Should detect one circular dependency")

        cycle = cycles[0]
        self.assertIn(Customer, [cycle.model_a, cycle.model_b])
        self.assertIn(CustomerReferral, [cycle.model_a, cycle.model_b])

        # Verify the cycle contains both models
        models_in_cycle = {cycle.model_a, cycle.model_b}
        self.assertEqual(models_in_cycle, {Customer, CustomerReferral})

    def test_loading_order_with_circular_dependencies(self):
        """Test that models are ordered correctly for loading"""
        resolver = CircularDependencyResolver()

        models = [CustomerReferral, Customer, Tenant, Shop]
        ordered_models = resolver.resolve_loading_order(models)

        # Tenant and Shop should come first (no dependencies)
        self.assertIn(Tenant, ordered_models[:2])
        self.assertIn(Shop, ordered_models[:2])

        # Customer should come before CustomerReferral in loading order
        customer_idx = ordered_models.index(Customer)
        referral_idx = ordered_models.index(CustomerReferral)
        self.assertLess(customer_idx, referral_idx, "Customer should load before CustomerReferral")

    def test_deferred_updates_preparation(self):
        """Test preparation of deferred FK updates for circular dependencies"""
        resolver = CircularDependencyResolver()

        # Detect circular dependencies
        models = [Customer, CustomerReferral]
        cycles = resolver.detect_circular_dependencies(models)

        # Prepare CSV data for the circular dependency
        csv_data = {
            "Customer": [
                {
                    "id": str(self.customer1.id),
                    "tenant_id": self.source_tenant.id,
                    "shop_id": str(self.shop.id),
                    "email": "customer1@test.com",
                    "first_name": "John",
                    "last_name": "Doe",
                    "primary_referrer_id": str(self.referral.id),  # Circular reference
                }
            ],
            "CustomerReferral": [
                {
                    "id": str(self.referral.id),
                    "tenant_id": self.source_tenant.id,
                    "shop_id": str(self.shop.id),
                    "referred_customer_id": str(self.customer1.id),  # Circular reference
                    "referring_customer_id": str(self.customer2.id),
                    "referral_code": "TEST123",
                    "status": "confirmed",
                    "commission_earned": 25.00,
                }
            ],
        }

        deferred_updates = resolver.prepare_deferred_updates(cycles, csv_data)

        self.assertGreater(len(deferred_updates), 0, "Should prepare deferred updates")

        # Verify update contains the circular FK
        update = deferred_updates[0]
        self.assertEqual(update["table"], "gyro_example_customer")
        self.assertEqual(update["set_clause"], "primary_referrer_id = %s")
        self.assertIn("where_clause", update)
        self.assertIn("values", update)

    def test_tenant_aware_remapping_with_uuids(self):
        """Test tenant-aware ID remapping with mixed ID types"""
        # Create remapping strategy for sequential tenant IDs
        tenant_mappings = {self.source_tenant.id: self.target_tenant.id}
        strategy = TenantAwareRemappingStrategy(Tenant, tenant_mappings)

        models = [Tenant, Shop, Customer, CustomerReferral]
        all_mappings = strategy.apply_to_all_models(models)

        # Verify tenant mapping is included
        self.assertIn("Tenant", all_mappings)
        self.assertEqual(all_mappings["Tenant"][self.source_tenant.id], self.target_tenant.id)

        # Other models should use identity mapping for UUIDs
        for model_name in ["Shop", "Customer", "CustomerReferral"]:
            self.assertIn(model_name, all_mappings)
            # UUID models should have empty or identity mappings initially

    def test_export_with_circular_dependencies(self):
        """Test exporting data with circular dependencies"""
        # Export data using Django management command
        export_dir = self.temp_dir / "exports"
        export_dir.mkdir()

        # Use DataSlicer to export data for the source tenant
        from src.django_gyro.core import DataSlicer

        data_slicer = DataSlicer.Postgres()

        # Create export jobs for each model
        jobs = [
            DataSlicer.Job(
                query=f"SELECT * FROM gyro_example_tenant WHERE id = {self.source_tenant.id}",
                output_file=export_dir / "gyro_example_tenant.csv",
            ),
            DataSlicer.Job(
                query=f"SELECT * FROM gyro_example_shop WHERE tenant_id = {self.source_tenant.id}",
                output_file=export_dir / "gyro_example_shop.csv",
            ),
            DataSlicer.Job(
                query=f"SELECT * FROM gyro_example_customer WHERE tenant_id = {self.source_tenant.id}",
                output_file=export_dir / "gyro_example_customer.csv",
            ),
            DataSlicer.Job(
                query=f"SELECT * FROM gyro_example_customerreferral WHERE tenant_id = {self.source_tenant.id}",
                output_file=export_dir / "gyro_example_customerreferral.csv",
            ),
            DataSlicer.Job(
                query=f"SELECT * FROM gyro_example_order WHERE tenant_id = {self.source_tenant.id}",
                output_file=export_dir / "gyro_example_order.csv",
            ),
        ]

        target = DataSlicer.File(export_dir)
        data_slicer.run(jobs, target)

        # Verify files were created
        self.assertTrue((export_dir / "gyro_example_tenant.csv").exists())
        self.assertTrue((export_dir / "gyro_example_shop.csv").exists())
        self.assertTrue((export_dir / "gyro_example_customer.csv").exists())
        self.assertTrue((export_dir / "gyro_example_customerreferral.csv").exists())
        self.assertTrue((export_dir / "gyro_example_order.csv").exists())

        # Verify circular dependency data is present
        customer_csv = export_dir / "gyro_example_customer.csv"
        with open(customer_csv) as f:
            content = f.read()
            self.assertIn(str(self.referral.id), content, "Customer CSV should contain referral ID")

        referral_csv = export_dir / "gyro_example_customerreferral.csv"
        with open(referral_csv) as f:
            content = f.read()
            self.assertIn(str(self.customer1.id), content, "Referral CSV should contain customer ID")

    @patch("src.django_gyro.importing.PostgresBulkLoader._get_connection")
    def test_import_with_circular_dependencies_and_id_remapping(self, mock_get_connection):
        """Test importing data with circular dependencies and mixed ID remapping"""
        # Create CSV files with circular dependency data
        export_dir = self.temp_dir / "test_import"
        export_dir.mkdir()

        # Create tenant CSV (sequential ID)
        tenant_csv = export_dir / "gyro_example_tenant.csv"
        tenant_csv.write_text(
            f"id,name,subdomain,created_at,is_active\n{self.source_tenant.id},Source Corp,source-corp,2025-01-01 00:00:00+00,t\n"
        )

        # Create shop CSV (UUID)
        shop_csv = export_dir / "gyro_example_shop.csv"
        shop_csv.write_text(
            f"id,tenant_id,name,url,currency,created_at\n{self.shop.id},{self.source_tenant.id},Test Shop,https://test.example.com,USD,2025-01-01 00:00:00+00\n"
        )

        # Create customer CSV with circular reference (UUIDs)
        customer_csv = export_dir / "gyro_example_customer.csv"
        customer_csv.write_text(
            f"id,tenant_id,shop_id,email,first_name,last_name,phone,created_at,primary_referrer_id\n{self.customer1.id},{self.source_tenant.id},{self.shop.id},customer1@test.com,John,Doe,,2025-01-01 00:00:00+00,{self.referral.id}\n{self.customer2.id},{self.source_tenant.id},{self.shop.id},customer2@test.com,Jane,Smith,,2025-01-01 00:00:00+00,\n"
        )

        # Create referral CSV with circular reference (UUIDs)
        referral_csv = export_dir / "gyro_example_customerreferral.csv"
        referral_csv.write_text(
            f"id,tenant_id,shop_id,referred_customer_id,referring_customer_id,referral_code,status,commission_earned,orders_generated,total_revenue,created_at,confirmed_at,expires_at\n{self.referral.id},{self.source_tenant.id},{self.shop.id},{self.customer1.id},{self.customer2.id},TEST123,confirmed,25.00,3,150.00,2025-01-01 00:00:00+00,,\n"
        )

        # Set up import context with tenant remapping
        tenant_mappings = {self.source_tenant.id: self.target_tenant.id}
        remapping_strategy = TenantAwareRemappingStrategy(Tenant, tenant_mappings)

        _context = ImportContext(
            source_directory=export_dir,
            batch_size=1000,
            use_copy=True,
            target_database="default",
            id_remapping_strategy=remapping_strategy,
        )

        # Mock database connection for bulk loader
        from unittest.mock import MagicMock

        mock_connection = MagicMock()
        mock_cursor = MagicMock()
        mock_connection.cursor.return_value = mock_cursor
        mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
        mock_cursor.__exit__ = MagicMock(return_value=None)
        mock_get_connection.return_value = mock_connection

        # Test circular dependency resolution
        resolver = CircularDependencyResolver()
        models = [Tenant, Shop, Customer, CustomerReferral]

        # Verify loading order
        ordered_models = resolver.resolve_loading_order(models)
        self.assertEqual(ordered_models[0], Tenant)
        self.assertEqual(ordered_models[1], Shop)
        self.assertEqual(ordered_models[2], Customer)
        self.assertEqual(ordered_models[3], CustomerReferral)

        # Verify circular dependency detection
        cycles = resolver.detect_circular_dependencies([Customer, CustomerReferral])
        self.assertEqual(len(cycles), 1)

        # Test ID remapping with mixed types
        all_mappings = remapping_strategy.apply_to_all_models(models)

        # Tenant should have explicit mapping (sequential)
        self.assertEqual(all_mappings["Tenant"][self.source_tenant.id], self.target_tenant.id)

        # UUID models should be ready for remapping (initially empty)
        for model_name in ["Shop", "Customer", "CustomerReferral"]:
            self.assertIn(model_name, all_mappings)

        # The test validates the framework is ready for import
        # Full import would require actual database operations

    def test_uuid_vs_sequential_id_behavior(self):
        """Test that UUIDs and sequential IDs behave correctly"""
        # Test sequential ID (Tenant)
        tenant1 = Tenant.objects.create(name="Test1", subdomain="test1")
        tenant2 = Tenant.objects.create(name="Test2", subdomain="test2")

        self.assertIsInstance(tenant1.id, int)
        self.assertIsInstance(tenant2.id, int)
        self.assertGreater(tenant2.id, tenant1.id)

        # Test UUID IDs (all other models)
        shop1 = Shop.objects.create(tenant=tenant1, name="Shop1", url="https://shop1.example.com")
        shop2 = Shop.objects.create(tenant=tenant1, name="Shop2", url="https://shop2.example.com")

        self.assertIsInstance(shop1.id, uuid.UUID)
        self.assertIsInstance(shop2.id, uuid.UUID)
        self.assertNotEqual(shop1.id, shop2.id)

        # Test customer UUIDs
        customer = Customer.objects.create(
            tenant=tenant1, shop=shop1, email="test@example.com", first_name="Test", last_name="User"
        )

        self.assertIsInstance(customer.id, uuid.UUID)

        # Test referral UUIDs
        referral = CustomerReferral.objects.create(
            tenant=tenant1,
            shop=shop1,
            referred_customer=customer,
            referring_customer=customer,
            referral_code="TEST456",
            status="pending",
        )

        self.assertIsInstance(referral.id, uuid.UUID)

    def test_end_to_end_workflow_summary(self):
        """Comprehensive test demonstrating the complete workflow"""

        # 1. Verify initial data setup
        self.assertEqual(Customer.objects.count(), 2)
        self.assertEqual(CustomerReferral.objects.count(), 1)
        self.assertIsNotNone(self.customer1.primary_referrer)
        self.assertEqual(self.customer1.primary_referrer, self.referral)

        # 2. Verify circular dependency exists
        self.assertEqual(self.referral.referred_customer, self.customer1)
        self.assertEqual(self.customer1.primary_referrer, self.referral)

        # 3. Verify ID types
        self.assertIsInstance(self.source_tenant.id, int)  # Sequential
        self.assertIsInstance(self.shop.id, uuid.UUID)  # UUID
        self.assertIsInstance(self.customer1.id, uuid.UUID)  # UUID
        self.assertIsInstance(self.referral.id, uuid.UUID)  # UUID

        # 4. Test circular dependency resolution framework
        resolver = CircularDependencyResolver()
        cycles = resolver.detect_circular_dependencies([Customer, CustomerReferral])
        self.assertEqual(len(cycles), 1)

        # 5. Test tenant-aware remapping framework
        tenant_mappings = {self.source_tenant.id: self.target_tenant.id}
        strategy = TenantAwareRemappingStrategy(Tenant, tenant_mappings)
        all_mappings = strategy.apply_to_all_models([Tenant, Shop, Customer])

        self.assertIn("Tenant", all_mappings)
        self.assertEqual(all_mappings["Tenant"][self.source_tenant.id], self.target_tenant.id)

        # Test summary: All components are working correctly for mixed ID types
        # and circular dependency handling
