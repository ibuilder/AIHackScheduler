"""Database index declarations and read-only diagnostics.

The previous version issued ``CREATE INDEX CONCURRENTLY`` through
``db.engine.execute`` at every application start. That call was removed in
SQLAlchemy 2.0, so every index silently failed; ``CONCURRENTLY`` and ``VACUUM``
cannot run inside a transaction anyway, and running DDL on boot races between
workers.

Indexes are now declared on the models, which means ``db.create_all()`` and
Alembic both produce them, on PostgreSQL and SQLite alike. What remains here is
diagnostics: reporting what exists, so a missing index is visible rather than
silently absent.
"""

from __future__ import annotations

import logging

from sqlalchemy import inspect, text

from extensions import db

logger = logging.getLogger(__name__)

# Indexes the application relies on for its hot paths. Declared on the models
# via ``__table_args__``; listed here so the health endpoint can verify them.
EXPECTED_INDEXES: dict[str, list[list[str]]] = {
    "users": [["company_id"], ["role"]],
    "projects": [["company_id"], ["company_id", "status"], ["created_by"]],
    "tasks": [["project_id"], ["project_id", "status"], ["project_id", "start_date"]],
    "task_dependencies": [["task_id"], ["predecessor_task_id"]],
    "resources": [["project_id"]],
    "resource_assignments": [["task_id"], ["resource_id"]],
    "audit_logs": [["company_id", "timestamp"], ["user_id"], ["resource_type", "resource_id"]],
    "azure_integrations": [["project_id"]],
    "powerbi_integrations": [["company_id"]],
}


class DatabaseOptimizer:
    """Read-only inspection of index coverage and table statistics."""

    def __init__(self, app=None):
        self.app = app

    def init_app(self, app):
        """Report on index coverage. Never issues DDL."""
        self.app = app
        with app.app_context():
            missing = self.missing_indexes()
            if missing:
                logger.warning(
                    "Missing expected indexes: %s. Run `flask db upgrade` to apply migrations.",
                    "; ".join(f"{table}({', '.join(cols)})" for table, cols in missing),
                )
            else:
                logger.info("All expected indexes are present")

    def existing_indexes(self) -> dict[str, list[list[str]]]:
        """Index columns per table, as reported by the live database."""
        inspector = inspect(db.engine)
        found: dict[str, list[list[str]]] = {}
        for table in inspector.get_table_names():
            entries = []
            for index in inspector.get_indexes(table):
                entries.append(list(index.get("column_names") or []))
            # A primary key is an index for lookup purposes.
            pk = inspector.get_pk_constraint(table).get("constrained_columns") or []
            if pk:
                entries.append(list(pk))
            found[table] = entries
        return found

    def missing_indexes(self) -> list[tuple]:
        """Expected indexes with no matching index in the database."""
        existing = self.existing_indexes()
        missing = []
        for table, expected_sets in EXPECTED_INDEXES.items():
            present = existing.get(table)
            if present is None:
                continue  # table not created yet
            for columns in expected_sets:
                # An index whose leading columns match is enough — a composite
                # index on (a, b) already serves lookups on (a).
                if not any(found[: len(columns)] == columns for found in present):
                    missing.append((table, columns))
        return missing

    def table_row_counts(self) -> dict[str, int]:
        """Row count per table. Portable across PostgreSQL and SQLite."""
        inspector = inspect(db.engine)
        counts = {}
        with db.engine.connect() as connection:
            for table in inspector.get_table_names():
                try:
                    result = connection.execute(text(f'SELECT COUNT(*) FROM "{table}"'))
                    counts[table] = result.scalar_one()
                except Exception as exc:
                    logger.debug("Could not count %s: %s", table, exc)
        return counts

    def get_slow_queries(self, limit: int = 10) -> list[dict]:
        """Slowest statements, from ``pg_stat_statements`` where available."""
        if db.engine.dialect.name != "postgresql":
            return []
        try:
            with db.engine.connect() as connection:
                result = connection.execute(
                    text(
                        "SELECT query, mean_exec_time, calls, total_exec_time "
                        "FROM pg_stat_statements ORDER BY mean_exec_time DESC LIMIT :limit"
                    ),
                    {"limit": limit},
                )
                return [dict(row._mapping) for row in result]
        except Exception as exc:
            # The extension is optional and often not installed.
            logger.info("pg_stat_statements unavailable: %s", exc)
            return []

    def get_table_sizes(self) -> list[dict]:
        """On-disk size per table. PostgreSQL only."""
        if db.engine.dialect.name != "postgresql":
            return []
        try:
            with db.engine.connect() as connection:
                result = connection.execute(
                    text(
                        "SELECT schemaname, tablename, "
                        "pg_size_pretty(pg_total_relation_size("
                        "quote_ident(schemaname) || '.' || quote_ident(tablename))) AS size "
                        "FROM pg_tables WHERE schemaname = 'public' "
                        "ORDER BY pg_total_relation_size("
                        "quote_ident(schemaname) || '.' || quote_ident(tablename)) DESC"
                    )
                )
                return [dict(row._mapping) for row in result]
        except Exception as exc:
            logger.warning("Failed to read table sizes: %s", exc)
            return []


db_optimizer = DatabaseOptimizer()
