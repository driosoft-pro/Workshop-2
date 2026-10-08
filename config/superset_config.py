"""Apache Superset configuration for Workshop-2.

Mounted read-only at /app/pythonpath/superset_config.py (that directory is on
PYTHONPATH inside the apache/superset image).
"""

import os

SECRET_KEY = os.environ.get("SUPERSET_SECRET_KEY", "workshop2-dev-secret-change-me")

# Metadata database (created by scripts/superset_create_metadata_db.py).
SQLALCHEMY_DATABASE_URI = os.environ.get(
    "SUPERSET_SQLALCHEMY_DATABASE_URI",
    "postgresql+psycopg2://music:music@music-postgres:5432/superset",
)

SQLALCHEMY_TRACK_MODIFICATIONS = False
ENABLE_PROXY_FIX = True
WTF_CSRF_ENABLED = True
SESSION_COOKIE_SECURE = False

# Allows chart/dashboard SQL to use Jinja parameters ({{ ... }}).
FEATURE_FLAGS = {"ENABLE_TEMPLATE_PROCESSING": True}
