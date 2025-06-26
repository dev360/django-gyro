# Django Gyro

A declarative system for importing and exporting CSV data with Django models. Django Gyro provides a clean, validation-rich way to map CSV columns to Django model fields with automatic foreign key resolution and intelligent data slicing capabilities.

## Features

- **Declarative Import System**: Define how CSV data maps to your Django models using simple class-based importers
- **Automatic Foreign Key Resolution**: Intelligently resolves relationships between models during import
- **Data Slicing & Export**: Export subsets of your data with complex relationships intact
- **Multi-tenant Support**: Built-in support for multi-tenant architectures
- **Validation-Rich**: Comprehensive validation during import/export operations
- **Progress Tracking**: Built-in progress bars for long-running operations

## Quick Start

### Installation

```bash
pip install django-gyro
```

### Basic Usage

#### 1. Define Your Importers

```python
# myapp/importers.py
from django_gyro import Importer
from myapp.models import Tenant, Shop, Customer, Product, Order

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
        shop = Shop
        tenant = Tenant
```

#### 2. Export Data

```python
from django_gyro import DataSlicer, ImportJob

# Define what data to export
tenant = Tenant.objects.filter(id=1)
shops = Shop.objects.filter(tenant=tenant)
customers = Customer.objects.filter(shop__in=shops)

# Export to CSV files
DataSlicer.run(
    source=DataSlicer.Postgres(database_url),
    target=DataSlicer.File('/path/to/export/'),
    jobs=[
      ImportJob(model=Tenant, query=tenant),
      ImportJob(model=Shop, query=shops),
      ImportJob(model=Customer, query=customers),
   ],
)
```

#### 3. Import Data

```python
# Import from CSV files
DataSlicer.run(
    source=DataSlicer.File('/path/to/import/'),
    target=DataSlicer.Postgres(database_url),
    jobs=[
      ImportJob(model=Tenant),
      ImportJob(model=Shop),
      ImportJob(model=Customer),
    ],
)
```

## Use Cases

- **Data Migration**: Move data between environments while preserving relationships
- **Selective Exports**: Export specific subsets of data for development or testing
- **Multi-tenant Data Management**: Handle complex tenant-based data relationships
- **CSV Import/Export**: Robust CSV handling with validation and error reporting

## Documentation

For detailed documentation, examples, and advanced usage, see [TECHNICAL_DESIGN.md](docs/TECHNICAL_DESIGN.md).

## Requirements

- Python 3.8+
- Django 3.2+
- PostgreSQL (for DataSlicer operations)

## Contributing

We welcome contributions! Please see our [Contributing Guidelines](CONTRIBUTING.md) for details.

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Support

- 📖 [Documentation](docs/TECHNICAL_DESIGN.md)
- 🐛 [Issue Tracker](https://github.com/dev360/django-gyro/issues)
- 💬 [Discussions](https://github.com/dev360/django-gyro/discussions)
