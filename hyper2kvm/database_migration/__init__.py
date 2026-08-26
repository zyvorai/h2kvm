# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# hyper2kvm/database_migration/__init__.py
"""
Database-aware migration for VM database workloads.

Provides database-specific optimizations and validations for:
- PostgreSQL
- MySQL/MariaDB
- MongoDB
- Redis
- Oracle Database
- Microsoft SQL Server (complements Windows support)
- Cassandra
- Elasticsearch

Features:
- Database detection and version identification
- Pre-migration health checks
- Database quiescing for consistent snapshots
- Transaction log preservation
- Post-migration validation
- Performance tuning for KVM
- Configuration migration
- Connection string updates
- Replication re-establishment
"""

from .base import (
    DatabaseEngine,
    DatabaseInfo,
    DatabaseMigrationHandler,
    DatabaseMigrationResult,
)
from .detector import DatabaseDetector
from .generic import GenericDatabaseHandler
from .mongodb import MongoDBHandler
from .mysql import MySQLHandler
from .orchestrator import DatabaseMigrationOrchestrator
from .postgresql import PostgreSQLHandler
from .redis import RedisHandler

__all__ = [
    "DatabaseDetector",
    "DatabaseEngine",
    "DatabaseInfo",
    "DatabaseMigrationHandler",
    "DatabaseMigrationOrchestrator",
    "DatabaseMigrationResult",
    "GenericDatabaseHandler",
    "MongoDBHandler",
    "MySQLHandler",
    "PostgreSQLHandler",
    "RedisHandler",
]
