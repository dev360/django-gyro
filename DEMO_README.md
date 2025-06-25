# Django Gyro End-to-End Demo

This document explains how to run the complete Django Gyro end-to-end demo using the Docker development environment.

## Overview

The demo showcases the complete Django Gyro workflow as described in the technical design:

1. **Database Setup**: PostgreSQL database with sample e-commerce data
2. **Data Export**: Using `DataSlicer.run()` to export tenant data from PostgreSQL to CSV files
3. **File Verification**: Exported CSV files are saved to the host machine for easy inspection

## Prerequisites

- Docker and Docker Compose installed
- VS Code with Dev Containers extension (recommended)

## Quick Start

### Option 1: Using Dev Containers (Recommended)

1. **Open in Dev Container**:
   ```bash
   # Open the project in VS Code
   code .
   
   # Use Command Palette (Ctrl+Shift+P / Cmd+Shift+P)
   # Select: "Dev Containers: Reopen in Container"
   ```

2. **Wait for Setup**: The container will automatically:
   - Start PostgreSQL database
   - Run Django migrations
   - Load sample data using `python manage.py load_fake_data`

3. **Run the Demo**:
   ```bash
   # Inside the container terminal
   cd src/example
   python manage.py demo_end_to_end --use-host-volume
   ```

### Option 2: Manual Docker Compose

1. **Start the Environment**:
   ```bash
   cd .devcontainer
   docker-compose up --build
   ```

2. **Run the Demo** (in a new terminal):
   ```bash
   # Connect to the running container
   docker exec -it gyro_example bash
   
   # Navigate to the Django project
   cd src/example
   
   # Run the end-to-end demo
   python manage.py demo_end_to_end --use-host-volume
   ```

## Demo Command Options

The `demo_end_to_end` management command supports several options:

```bash
# Basic demo (exports to /tmp inside container)
python manage.py demo_end_to_end

# Export to host-mounted volume (recommended)
python manage.py demo_end_to_end --use-host-volume

# Specify a different tenant ID
python manage.py demo_end_to_end --tenant-id 2 --use-host-volume

# Custom output directory
python manage.py demo_end_to_end --output-dir /custom/path
```

## What the Demo Does

### 1. Database Verification
- Connects to PostgreSQL database
- Checks for sample data (tenants, shops, customers, products, orders)
- Shows data counts for each model

### 2. Query Setup
- Creates Django QuerySets for a specific tenant
- Filters related data (shops, customers, products, orders, order items)
- Shows export query summary

### 3. DataSlicer Execution
- Demonstrates the exact API from the technical design:
  ```python
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
      use_notebook_progress=False
  )
  ```

### 4. File Verification
- Shows created CSV files with sizes
- Displays sample content from each file
- Verifies all components are working

## Expected Output

When you run the demo, you should see output like:

```
Django Gyro End-to-End Demo
==================================================

1. Verifying database connection and data...
   ✅ PostgreSQL connected: PostgreSQL 15.x
   📊 Data Summary:
      - Tenants: 5
      - Shops: 15
      - Customers: 150
      - Products: 75
      - Orders: 50
      - Order Items: 125

2. Creating export queries for tenant ID 1...
   🎯 Target tenant: Acme Corp (acme-corp)
   📋 Export Query Summary:
      - Tenant: 1 record(s)
      - Shops: 3 record(s)
      - Customers: 30 record(s)
      - Products: 15 record(s)
      - Orders: 10 record(s)
      - Order Items: 25 record(s)

3. Setting up DataSlicer export...
   📁 Output directory: /app/exports
   🔗 Database URL: postgresql://gyro_user:***@gyro_db:5432/gyro_example

4. Executing DataSlicer.run() - Main ETL Workflow...
   📤 Exported 1 rows to gyro_example_tenant.csv
   📤 Exported 3 rows to gyro_example_shop.csv
   📤 Exported 30 rows to gyro_example_customer.csv
   📤 Exported 15 rows to gyro_example_product.csv
   📤 Exported 10 rows to gyro_example_order.csv
   📤 Exported 25 rows to gyro_example_orderitem.csv

   ✅ DataSlicer.run() completed successfully!

5. Export Results:
   🎯 Jobs executed: 6
   📄 Files created: 6
   📊 Total rows exported: 84
   🔗 Source type: PostgresSource
   💾 Target type: FileTarget

6. File Verification:
   ✅ gyro_example_tenant.csv (245 bytes)
      Header: id,name,subdomain,created_at,is_active
      Row 1: 1,"Acme Corp","acme-corp","2024-01-15 10:30:00",true
   ✅ gyro_example_shop.csv (892 bytes)
      Header: id,tenant_id,name,url,currency,created_at
      Row 1: 1,1,"Acme Store","https://acme-store.com","USD","2024-01-15 10:31:00"
   ... (and so on for all files)

🎉 Django Gyro End-to-End Demo Completed Successfully!
```

## Exported Files

When using `--use-host-volume`, the CSV files are saved to the `src/example/gyro_example/exports/` directory. You can inspect these files directly from your host machine:

```bash
# View the exported files
ls -la src/example/gyro_example/exports/

# Inspect a CSV file
cat src/example/gyro_example/exports/gyro_example_tenant.csv
head -5 src/example/gyro_example/exports/gyro_example_customer.csv
```

## Key Features Demonstrated

- ✅ **DataSlicer.run()** - Main ETL orchestration method
- ✅ **DataSlicer.Postgres()** - PostgreSQL source convenience method  
- ✅ **DataSlicer.File()** - File target convenience method
- ✅ **ImportJob** - Data export job definition
- ✅ **Automatic dependency sorting** - Ensures proper export order
- ✅ **PostgreSQL COPY operations** - Efficient data extraction
- ✅ **CSV file generation** - Proper headers and data formatting
- ✅ **Progress tracking** - Real-time feedback during export
- ✅ **Foreign key validation** - Ensures data integrity
- ✅ **Keyword-only API** - Explicit parameter requirements

## Troubleshooting

### Database Connection Issues
If you see database connection errors:
1. Ensure PostgreSQL container is running: `docker ps`
2. Check container logs: `docker logs gyro_db`
3. Verify environment variables in Docker compose

### No Sample Data
If the demo reports no data:
1. Run the data loader manually: `python manage.py load_fake_data`
2. Check if migrations ran: `python manage.py showmigrations`

### Permission Issues
If you see file permission errors:
1. Ensure the `exports/` directory exists and is writable
2. Check Docker volume mounts in docker-compose.yml

### Import Errors
If you see Django Gyro import errors:
1. Verify the package is installed: `pip list | grep django-gyro`
2. Check the volume mount for the source code in docker-compose.yml

## Architecture

The demo environment consists of:

- **PostgreSQL Database** (`gyro_db`): Stores the sample e-commerce data
- **Django Application** (`gyro_example`): Runs the Django Gyro demo
- **Volume Mounts**: 
  - Project root: `..` → `/app` (includes all source code and exports directory)
  - Django Gyro package: `../src/django_gyro` → `/usr/local/lib/python3.10/site-packages/django_gyro`
- **Network**: Both containers on `test-network` for communication

This setup provides a complete, isolated environment for testing Django Gyro with real PostgreSQL data and file exports that you can inspect from your host machine. 