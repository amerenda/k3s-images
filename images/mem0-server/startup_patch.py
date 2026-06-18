"""
Monkey-patches mem0's SQLiteManager with a PostgreSQL replacement before
the server starts. Import this before uvicorn loads the app.
"""
import os
import sys

sys.path.insert(0, "/app")

from history_pg import PostgresHistoryManager

_pg_url = (
    f"postgresql://{os.environ['POSTGRES_USER']}:{os.environ['POSTGRES_PASSWORD']}"
    f"@{os.environ['POSTGRES_HOST']}:{os.environ['POSTGRES_PORT']}/{os.environ['POSTGRES_DB']}"
)


class _PGFactory:
    """Drop-in for SQLiteManager; ignores db_path and uses the PG URL from env."""
    def __new__(cls, db_path=None):
        return PostgresHistoryManager(_pg_url)


import mem0.memory.storage as _storage
import mem0.memory.main as _mem0_main

_storage.SQLiteManager = _PGFactory
_mem0_main.SQLiteManager = _PGFactory
