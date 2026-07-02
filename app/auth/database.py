"""Database compatibility layer for auth and subscription records."""

from app.core.config import settings
from app.storage.sqlite_store import get_connection as get_sqlite_connection


def is_postgres() -> bool:
    return settings.is_postgres


class PostgresConnection:
    """Expose the small sqlite-like interface used by the auth services."""

    def __init__(self):
        try:
            import psycopg
            from psycopg.rows import dict_row
        except ImportError as error:
            raise RuntimeError(
                "PostgreSQL requires psycopg. Install requirements-cloud.txt."
            ) from error

        self.raw = psycopg.connect(
            settings.database_url,
            row_factory=dict_row,
        )

    @staticmethod
    def _sql(statement: str) -> str:
        return statement.replace("?", "%s")

    def execute(self, statement: str, parameters=()):
        return self.raw.execute(
            self._sql(statement),
            parameters,
        )

    def commit(self) -> None:
        self.raw.commit()

    def rollback(self) -> None:
        self.raw.rollback()

    def close(self) -> None:
        self.raw.close()


def get_connection():
    """Return PostgreSQL in production and SQLite for local development."""

    if is_postgres():
        return PostgresConnection()

    return get_sqlite_connection()
