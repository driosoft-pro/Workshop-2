"""Apache Superset configuration for Workshop-2.

Mounted read-only at /app/pythonpath/superset_config.py (that directory is on
PYTHONPATH inside the apache/superset image).
"""

import os

SECRET_KEY = os.environ.get("SUPERSET_SECRET_KEY", "workshop2-dev-secret-change-me")

def _resolve_sqlalchemy_uri() -> str:
    uri = os.environ.get("SUPERSET_SQLALCHEMY_DATABASE_URI")
    if uri:
        return uri
    user = os.environ.get("POSTGRES_USER")
    password = os.environ.get("POSTGRES_PASSWORD")
    host = os.environ.get("POSTGRES_HOST", "music-postgres")
    port = os.environ.get("MUSIC_POSTGRES_PORT", "5432")
    db = os.environ.get("SUPERSET_METADATA_DB_NAME", "superset")
    if user and password:
        return f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{db}"
    return f"postgresql+psycopg2://{host}:{port}/{db}"


# Metadata database (created by scripts/superset_create_metadata_db.py).
SQLALCHEMY_DATABASE_URI = _resolve_sqlalchemy_uri()

SQLALCHEMY_TRACK_MODIFICATIONS = False
ENABLE_PROXY_FIX = True
WTF_CSRF_ENABLED = True
SESSION_COOKIE_SECURE = False

# Allows chart/dashboard SQL to use Jinja parameters ({{ ... }}).
FEATURE_FLAGS = {"ENABLE_TEMPLATE_PROCESSING": True}
