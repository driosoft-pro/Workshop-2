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

def _load_env() -> None:
    """Best-effort loader for .env when executing on the host without compose."""
    env_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".env"))
    if not os.path.exists(env_path):
        return
    try:
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, val = line.split("=", 1)
                key = key.strip()
                val = val.strip().strip("\"'")
                if key and key not in os.environ:
                    os.environ[key] = val
    except Exception:
        pass


_load_env()

DEFAULT_ADMIN_URI = os.environ.get("DEFAULT_ADMIN_URI") or os.environ.get("SUPERSET_METADATA_ADMIN_URI")
METADATA_DB = os.environ.get("SUPERSET_METADATA_DB_NAME", "superset")


def _resolve_admin_uri() -> str:
    uri = (
        os.environ.get("SUPERSET_METADATA_ADMIN_URI")
        or os.environ.get("DEFAULT_ADMIN_URI")
        or DEFAULT_ADMIN_URI
        or os.environ.get("MUSIC_SOURCE_DB_URL")
    )
    if uri:
        return uri

    user = os.environ.get("POSTGRES_USER")
    password = os.environ.get("POSTGRES_PASSWORD")
    host = os.environ.get("POSTGRES_HOST", "music-postgres")
    port = os.environ.get("MUSIC_POSTGRES_PORT", "5432")
    db = os.environ.get("POSTGRES_DB", "music_source")
    if user and password:
        return f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{db}"

    raise RuntimeError(
        "Admin URI is not configured. Please define DEFAULT_ADMIN_URI or "
        "SUPERSET_METADATA_ADMIN_URI in your .env file."
    )


def main() -> int:
    try:
        admin_uri = _resolve_admin_uri()
    except Exception as exc:
        print(f"[superset-init] error: {exc}", file=sys.stderr)
        return 1

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
