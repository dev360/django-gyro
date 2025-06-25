# Django Gyro Test Plan

## Test Environment Status ✅

**READY FOR TDD**: Test environment successfully established
- **Django 4.2.23** with `example.settings` ✅
- **pytest + pytest-django** working correctly ✅  
- **django_gyro package** importable ✅
- **Baseline**: 23 tests passing ✅

**Command to run tests**: `source venv/bin/activate && pytest tests/ -v`

---

## Overview

This document outlines the Test Driven Development (TDD) approach for implementing Django Gyro's declarative CSV import/export system using Cursor. The test plan is structured to build the API incrementally, starting with core components and progressing through integration scenarios.

Based on the technical design, Django Gyro provides:
- **Importer classes** for defining CSV-to-model mappings
- **DataSlicer** for orchestrating ETL operations
- **ImportJob** for specifying data export/import operations
- **Source/Target abstractions** for Postgres and File operations

This test plan ensures comprehensive coverage of both positive and negative scenarios, edge cases, and integration workflows before implementation begins.

## Test Status Legend

- ⚫ **Gray**: Test not implemented yet
- 🟢 **Green**: Test implemented and passing
- 🔴 **Red**: Test implemented but failing
- 🟡 **Yellow**: Test partially implemented

---

## Test Plan

### Phase 1: Core Importer Framework ✅ COMPLETE

#### `describe Importer`
| Method/Property | Test Scenarios | Status |
|-----------------|----------------|---------|
| `__init__` | - Validates model attribute exists<br>- Registers importer in global registry<br>- Raises error for duplicate model registration | 🟢 |
| `model` (class attribute) | - Valid Django model classes<br>- Invalid non-model classes<br>- Missing model attribute | 🟢 |
| `get_file_name()` | - Generates correct CSV filename from model<br>- Handles model name edge cases<br>- Ensures consistent naming | 🟢 |

#### `describe Importer.Columns`
| Method/Property | Test Scenarios | Status |
|-----------------|----------------|---------|
| Field validation | - Valid foreign key field references<br>- Invalid field names<br>- Missing required FK relationships | 🟢 |
| Registry lookup | - Finds referenced model importers<br>- Handles missing importer definitions<br>- Validates relationship consistency | 🟢 |

#### `describe Importer Registry`
| Method/Property | Test Scenarios | Status |
|-----------------|----------------|---------|
| `get_importer_for_model()` | - Finds importer by model class<br>- Returns None for unregistered models<br>- Handles model inheritance | 🟢 |
| Registry cleanup | - Clears registry between tests<br>- Prevents test pollution<br>- Handles registration conflicts | 🟢 |

### Phase 2: ImportJob Definition

#### `describe ImportJob`
| Method/Property | Test Scenarios | Status |
|-----------------|----------------|---------|
| `__init__(model)` | - Creates job with model only<br>- Invalid model types<br>- Missing model parameter | 🟢 |
| `__init__(model, query)` | - Creates job with model and QuerySet<br>- Validates QuerySet matches model<br>- Handles empty QuerySets | 🟢 |
| `model` property | - Returns correct model class<br>- Immutable after creation | 🟢 |
| `query` property | - Returns Django QuerySet<br>- Handles None values<br>- Query validation | 🟢 |

#### `describe ImportJob Dependencies`
| Method/Property | Test Scenarios | Status |
|-----------------|----------------|---------|
| `get_dependencies()` | - Identifies FK dependencies<br>- Returns dependency chain<br>- Handles circular references | 🟢 |
| Dependency ordering | - Sorts jobs by dependency order<br>- Detects circular dependencies<br>- Handles independent models | 🟢 |

### Phase 3: DataSlicer Core

#### `describe DataSlicer`
| Method/Property | Test Scenarios | Status |
|-----------------|----------------|---------|
| `run(source, target, *jobs)` | - Validates source/target compatibility<br>- Processes jobs in correct order<br>- Handles empty job list | 🟢 |
| Job validation | - Validates all jobs have registered importers<br>- Checks dependency requirements<br>- Error on invalid job types | 🟢 |

#### `describe DataSlicer.Postgres`
| Method/Property | Test Scenarios | Status |
|-----------------|----------------|---------|
| `__init__(connection_string)` | - Valid PostgreSQL connection strings<br>- Invalid connection strings<br>- Connection timeout settings | 🟢 |
| `read_data(filename)` | - Executes COPY FROM STDIN<br>- Handles file not found errors<br>- Validates CSV format | 🟢 |
| `write_data(query, filename)` | - Executes COPY TO STDOUT<br>- Generates proper SQL from QuerySet<br>- Handles empty result sets | 🟢 |
| Connection management | - Opens/closes connections properly<br>- Handles connection failures<br>- Connection pooling | 🟢 |

#### `describe DataSlicer.File`
| Method/Property | Test Scenarios | Status |
|-----------------|----------------|---------|
| `__init__(directory_path)` | - Valid directory paths<br>- Creates directories if missing<br>- Permission validation | 🟢 |
| `__init__(directory_path, overwrite=True)` | - Overwrites existing files<br>- Preserves existing files when False<br>- Handles file locking | 🟢 |
| `read_data(filename)` | - Reads CSV files<br>- Handles missing files<br>- Validates CSV format | 🟢 |
| `write_data(data, filename)` | - Writes CSV files<br>- Creates proper CSV headers<br>- Handles large datasets | 🟢 |

### Phase 4: Data Export Operations

#### `describe PostgresExport`
| Method/Property | Test Scenarios | Status |
|-----------------|----------------|---------|
| SQL generation | - Converts Django QuerySet to SQL<br>- Handles complex WHERE clauses<br>- Generates proper COPY statements | 🟢 |
| CSV generation | - Includes proper CSV headers<br>- Exports all model fields<br>- Handles NULL values | 🟢 |
| Foreign key handling | - Exports FK IDs correctly<br>- Handles NULL foreign keys<br>- Multiple FK relationships | 🟢 |
| Progress tracking | - Shows progress for large exports<br>- Updates progress bars<br>- Completion notifications | 🟢 |

### Phase 5: Data Import Operations

#### `describe PostgresImport`
| Method/Property | Test Scenarios | Status |
|-----------------|----------------|---------|
| CSV parsing | - Parses CSV headers correctly<br>- Maps columns to model fields<br>- Handles missing columns | 🟢 |
| Data validation | - Validates data types<br>- Checks required fields<br>- Custom model validation | 🟢 |
| Foreign key resolution | - Resolves FK references<br>- Handles missing FK targets<br>- Multi-level FK chains | 🟢 |
| Constraint handling | - Unique constraint violations<br>- Database constraint errors<br>- Transaction rollbacks | 🟢 |

#### `describe FK Dependency Validation`
| Method/Property | Test Scenarios | Status |
|-----------------|----------------|---------|
| Missing FK target detection | - Validates FK IDs exist in target tables<br>- Reports missing FK references before import<br>- Suggests required import order | 🟢 |
| Cyclical relationship detection | - Detects circular FK dependencies<br>- Reports Asset↔AssetRisk type cycles<br>- Prevents import when cycles detected | 🟢 |
| Excluded columns support | - `excluded = ['risk_id']` property on Importer<br>- Excludes columns from import only (not export)<br>- Validates excluded columns are FK fields | 🟢 |
| Pre-import validation | - Validates all FK dependencies before data movement<br>- Errors on cyclical deps without exclusions<br>- Logs detailed FK validation reports | 🟢 |

### Phase 6: Integration Workflows

#### `describe FullExportWorkflow`
| Method/Property | Test Scenarios | Status |
|-----------------|----------------|---------|
| Multi-tenant export | - Exports tenant-specific data<br>- Maintains data relationships<br>- Selective data export | ⚫ |
| Complex relationships | - Handles deep FK chains<br>- Many-to-many relationships<br>- Circular references | ⚫ |
| Error recovery | - Partial export failures<br>- Disk space issues<br>- Connection interruptions | ⚫ |

#### `describe FullImportWorkflow`
| Method/Property | Test Scenarios | Status |
|-----------------|----------------|---------|
| Fresh database import | - Imports to empty database<br>- Creates all relationships<br>- Validates data integrity | ⚫ |
| Incremental import | - Updates existing records<br>- Handles duplicate keys<br>- Maintains referential integrity | ⚫ |
| Rollback scenarios | - Transaction rollbacks on failure<br>- Partial import recovery<br>- Data consistency validation | ⚫ |

#### `describe RoundTripDataIntegrity`
| Method/Property | Test Scenarios | Status |
|-----------------|----------------|---------|
| Data consistency | - Export then import preserves data<br>- All relationships maintained<br>- Data types preserved | ⚫ |
| Large dataset handling | - 100K+ record round trips<br>- Memory efficiency<br>- Performance benchmarks | ⚫ |

### Phase 7: Error Handling & Edge Cases

#### `describe DatabaseErrors`
| Method/Property | Test Scenarios | Status |
|-----------------|----------------|---------|
| Connection failures | - Connection timeouts<br>- Authentication failures<br>- Network interruptions | ⚫ |
| Query errors | - Invalid SQL generation<br>- Database constraint violations<br>- Transaction deadlocks | ⚫ |

#### `describe FileSystemErrors`
| Method/Property | Test Scenarios | Status |
|-----------------|----------------|---------|
| File operations | - Permission denied scenarios<br>- Disk space exhaustion<br>- File locking issues | ⚫ |
| Directory handling | - Missing directories<br>- Invalid paths<br>- Path traversal security | ⚫ |

#### `describe MemoryManagement`
| Method/Property | Test Scenarios | Status |
|-----------------|----------------|---------|
| Large datasets | - Streaming data processing<br>- Memory usage limits<br>- Garbage collection | ⚫ |
| Concurrent operations | - Multiple simultaneous operations<br>- Resource locking<br>- Race condition prevention | ⚫ |

### Phase 8: Performance & Scalability

#### `describe PerformanceOptimization`
| Method/Property | Test Scenarios | Status |
|-----------------|----------------|---------|
| Query optimization | - Efficient SQL generation<br>- Index usage verification<br>- Query plan analysis | ⚫ |
| Batch processing | - Configurable batch sizes<br>- Memory-efficient processing<br>- Resume interrupted operations | ⚫ |
| Benchmarking | - Execution time measurements<br>- Memory usage profiling<br>- Performance regression detection | ⚫ |

---

## Test Implementation Strategy

### 1. **Test Environment Setup**
- Use Django's `TestCase` with transaction support
- Create test database with sample multi-tenant data
- Mock external dependencies (file system, network)
- Use factories for consistent test data generation

### 2. **Test Data Strategy**
- Leverage existing fake data generator for realistic scenarios
- Create minimal test fixtures for unit tests
- Use temporary directories for file operations
- Implement test database cleanup between test runs

### 3. **Mocking Strategy**
- Mock PostgreSQL connections for unit tests
- Mock file system operations for error scenarios
- Use dependency injection for testable components
- Create test doubles for external services

### 4. **Continuous Integration**
- Run tests on multiple Python/Django versions
- Include performance regression detection
- Automated test coverage reporting
- Integration with development workflow

---

## Success Criteria

- **100% test coverage** for core API components
- **All positive scenarios** working correctly
- **Comprehensive error handling** for edge cases
- **Performance benchmarks** established and maintained
- **Documentation examples** validated through tests
- **Clean Organization** tests should be well organized and easy to follow

This test plan provides a roadmap for implementing Django Gyro using Test Driven Development, ensuring robust, reliable, and maintainable code. 