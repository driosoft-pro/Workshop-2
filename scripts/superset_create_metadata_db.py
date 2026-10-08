"""Create the Superset metadata database on an already-initialized PostgreSQL volume.

The docker-entrypoint-initdb.d script (sql/db_init/02_create_superset.sql) only
runs when the music-postgres volume is empty, so the superset-init compose
service calls this script to guarantee the `superset` database exists.

Usage (inside the superset-init container):
    python /app/scripts/superset_create_metadata_db.py
"""

from __future__ import annotations

import os
import sys

DEFAULT_ADMIN_URI = "postgresql+psycopg2://music:music@music-postgres:5432/music_source"
METADATA_DB = os.environ.get("SUPERSET_METADATA_DB_NAME", "superset")


def main() -> int:
    admin_uri = os.environ.get("SUPERSET_METADATA_ADMIN_URI", DEFAULT_ADMIN_URI)
    autocommit_uri = admin_uri.replace("+psycopg2", "")

    import psycopg2
    from psycopg2 import sql as pg_sql

    connection = psycopg2.connect(autocommit_uri)
    connection.set_session(autocommit=True)
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1 FROM pg_database WHERE datname = %s", (METADATA_DB,))
        if cursor.fetchone():
            print(f"[superset-init] database '{METADATA_DB}' already exists")
        else:
            cursor.execute(pg_sql.SQL("CREATE DATABASE {}").format(pg_sql.Identifier(METADATA_DB)))
            print(f"[superset-init] created database '{METADATA_DB}'")
    connection.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
