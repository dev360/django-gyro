"""
Django Gyro Source Classes

This module provides source classes for reading data from various systems,
primarily PostgreSQL databases using COPY operations.
"""

import os
from typing import Any, Dict

import psycopg2
from django.db.models import QuerySet


class PostgresSource:
    """
    PostgreSQL source for extracting data using COPY operations.

    This class converts Django QuerySets to raw SQL and executes
    PostgreSQL COPY TO STDOUT commands for efficient data extraction.
    """

    def __init__(self, connection_string: str):
        """
        Initialize PostgreSQL source.

        Args:
            connection_string: PostgreSQL connection string
                Format: postgresql://user:password@host:port/database
        """
        self.connection_string = connection_string
        self._connection = None

    def connect(self):
        """Establish connection to PostgreSQL database."""
        if self._connection is None or self._connection.closed:
            self._connection = psycopg2.connect(self.connection_string)
        return self._connection

    def close(self):
        """Close database connection."""
        if self._connection and not self._connection.closed:
            self._connection.close()

    def generate_copy_statement(self, queryset: QuerySet, output_file: str, exclude=None) -> str:
        """
        Generate PostgreSQL COPY statement from Django QuerySet.

        Args:
            queryset: Django QuerySet to convert
            output_file: Output file path (for reference, actual output goes to STDOUT)
            exclude: Optional list of column names to exclude from export

        Returns:
            COPY statement string
        """
        # Get the raw SQL from the QuerySet
        sql, params = queryset.query.sql_with_params()

        # Exclude columns if requested
        if exclude:
            # Parse the SELECT clause and remove excluded columns
            # This is a simple string replacement; for complex queries, use a SQL parser
            select_prefix = "SELECT "
            if sql.strip().upper().startswith(select_prefix):
                select_end = sql.upper().find(" FROM ")
                if select_end > 0:
                    select_cols = sql[len(select_prefix) : select_end]
                    cols = [c.strip() for c in select_cols.split(",")]
                    cols = [c for c in cols if not any(ex in c for ex in exclude)]
                    new_select = select_prefix + ", ".join(cols)
                    sql = new_select + sql[select_end:]

        # Substitute parameters into the SQL
        if params:
            formatted_params = []
            for param in params:
                if isinstance(param, str):
                    # Use repr to escape single quotes
                    formatted_params.append(repr(param))
                elif isinstance(param, bool):
                    formatted_params.append("true" if param else "false")
                elif param is None:
                    formatted_params.append("NULL")
                else:
                    formatted_params.append(str(param))

            # Substitute parameters into SQL
            for formatted_param in formatted_params:
                sql = sql.replace("%s", formatted_param, 1)

        # Construct COPY statement
        copy_statement = f"""
        COPY ({sql}) TO STDOUT WITH (FORMAT CSV, HEADER)
        """.strip()

        return copy_statement

    def execute_copy(self, copy_statement: str, output_file: str) -> Dict[str, Any]:
        """
        Execute COPY statement and write to file.

        Args:
            copy_statement: PostgreSQL COPY statement
            output_file: Path to output CSV file

        Returns:
            Dict with execution statistics
        """
        conn = self.connect()

        try:
            with conn.cursor() as cursor:
                # Ensure output directory exists
                os.makedirs(os.path.dirname(output_file), exist_ok=True)

                # Execute COPY to file
                with open(output_file, "w", encoding="utf-8") as f:
                    cursor.copy_expert(copy_statement, f)

                # Get file statistics
                file_size = os.path.getsize(output_file) if os.path.exists(output_file) else 0

                # Count rows (approximate, subtract 1 for header)
                rows_exported = 0
                if os.path.exists(output_file):
                    with open(output_file, encoding="utf-8") as f:
                        rows_exported = max(0, sum(1 for _ in f) - 1)

                return {"rows_exported": rows_exported, "file_size": file_size, "file_path": output_file}

        except Exception as e:
            # Re-raise with context
            raise Exception(f"COPY operation failed: {e}") from e

        finally:
            # Don't close connection here - let it be reused
            pass

    def export_queryset(self, queryset: QuerySet, output_file: str, exclude=None) -> Dict[str, Any]:
        """
        Export a Django QuerySet to CSV file.

        Args:
            queryset: Django QuerySet to export
            output_file: Path to output CSV file
            exclude: Optional list of column names to exclude from export

        Returns:
            Dict with export statistics
        """
        copy_statement = self.generate_copy_statement(queryset, output_file, exclude=exclude)
        return self.execute_copy(copy_statement, output_file)

    def __enter__(self):
        """Context manager entry."""
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()
