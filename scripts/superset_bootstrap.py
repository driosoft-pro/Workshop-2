"""Bootstrap the Apache Superset BI layer for Workshop-2 (two dashboards).

Creates (idempotently) on top of the analytical Data Warehouse ``music_dw``:

* database connection ``music_dw``
* virtual datasets    ``kpi_*`` (sql/kpi_queries.sql) + inline ``gran_*`` datasets
* charts              one or more per analytical requirement R1-R4 + granularity
* TWO dashboards, each a single page (no inner tabs), responsive 12-column grid,
  explicit layout (``position_json``), native filters scoped per chart, cross-filtering:

  1. "Workshop-2 - Granularity & Data Quality"  (/superset/dashboard/w2-granularity/)
  2. "Workshop-2 - KPIs (R1-R4)"                (/superset/dashboard/w2-requirements/)

Light / dark: handled natively by Superset (>= 6.0; this repo: 6.1.0) from
config/superset_config.py (THEME_DEFAULT / THEME_DARK). This script neither
registers themes via API nor injects CSS into dashboards.

Every chart query is executed through the Superset API as a smoke test, so a
failing KPI query fails this script (exit code 1).

Usage (inside the compose network):
    python /app/scripts/superset_bootstrap.py
On the host, with the UI published on :8088:
    SUPERSET_URL=http://localhost:8088 python -m scripts.superset_bootstrap
"""

from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
import urllib.request
from http.cookiejar import CookieJar

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

BASE_URL = os.environ.get("SUPERSET_URL", "http://localhost:8088").rstrip("/")
ADMIN_USER = os.environ.get("SUPERSET_ADMIN_USER", "admin")
ADMIN_PASSWORD = os.environ.get("SUPERSET_ADMIN_PASSWORD", "admin")


def _resolve_dw_uri() -> str:
    uri = os.environ.get("SUPERSET_DW_SQLALCHEMY_URI") or os.environ.get("MUSIC_DW_DB_URL")
    if uri:
        return uri
    user = os.environ.get("POSTGRES_USER")
    password = os.environ.get("POSTGRES_PASSWORD")
    host = os.environ.get("POSTGRES_HOST", "music-postgres")
    port = os.environ.get("MUSIC_POSTGRES_PORT", "5432")
    if user and password:
        return f"postgresql+psycopg2://{user}:{password}@{host}:{port}/music_dw"
    return f"postgresql+psycopg2://{host}:{port}/music_dw"


DW_URI = _resolve_dw_uri()
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
KPI_SQL_PATH = os.path.join(PROJECT_ROOT, "sql", "kpi_queries.sql")

# Kept for backwards compatibility (validate_report / tests): the R1-R4 dashboard.
DASHBOARD_TITLE = "Workshop-2 - KPIs (R1-R4)"
GRANULARITY_TITLE = "Workshop-2 - Granularity & Data Quality"
WORKSHOP_TITLE = "Dashboard Spotify & Grammy (R1–R4)"

WORKSHOP_CSS = """
/* ====================================================================
   DASHBOARD SPOTIFY & GRAMMY (R1-R4) - ESTILOS PREMIUM
   ==================================================================== */

/* --- Banner intro compacto (una sola línea, sin scroll) --- */
#MARKDOWN-r0c0 {
    margin-bottom: 2px !important;
}
#MARKDOWN-r0c0 .dashboard-markdown {
    padding: 6px 12px !important;
    background: #f8fafc !important;
    border: 1px solid #e2e8f0 !important;
    border-left: 4px solid #1DB954 !important;
    border-radius: 6px !important;
}
#MARKDOWN-r0c0 p {
    margin: 0 !important;
    font-size: 13.5px !important;
    line-height: 1.4 !important;
    color: #334155 !important;
}
#MARKDOWN-r0c0 a {
    color: #1DB954 !important;
    font-weight: 600 !important;
    text-decoration: none !important;
}
#MARKDOWN-r0c0 a:hover {
    text-decoration: underline !important;
}

/* ====================================================================
   TARJETAS KPI / HEADERS (4 COLORES VIBRANTES)
   ==================================================================== */

/* Contenedores base de tarjeta */
#CHART-r1c0, #CHART-r1c1, #CHART-r1c2, #CHART-r1c3,
.dashboard-chart-id-34, .dashboard-chart-id-35, .dashboard-chart-id-36, .dashboard-chart-id-37 {
    border-radius: 10px !important;
    transition: transform 0.2s ease, box-shadow 0.2s ease !important;
}
#CHART-r1c0:hover, #CHART-r1c1:hover, #CHART-r1c2:hover, #CHART-r1c3:hover,
.dashboard-chart-id-34:hover, .dashboard-chart-id-35:hover, .dashboard-chart-id-36:hover, .dashboard-chart-id-37:hover {
    transform: translateY(-2px) !important;
}

/* Asegurar que el fondo del slice sea transparente para ver el gradiente */
#CHART-r1c0 .chart-slice, #CHART-r1c0 .dashboard-chart, #CHART-r1c0 .slice_container,
#CHART-r1c1 .chart-slice, #CHART-r1c1 .dashboard-chart, #CHART-r1c1 .slice_container,
#CHART-r1c2 .chart-slice, #CHART-r1c2 .dashboard-chart, #CHART-r1c2 .slice_container,
#CHART-r1c3 .chart-slice, #CHART-r1c3 .dashboard-chart, #CHART-r1c3 .slice_container {
    background: transparent !important;
}

/* --- TARJETA 1: Premios Evaluados (Dorado Grammy) --- */
#CHART-r1c0, .dashboard-chart-id-34, div[data-test-chart-name="Premios Evaluados"] {
    border-top: 4px solid #D4AF37 !important;
    border-left: 1px solid rgba(212, 175, 55, 0.25) !important;
    border-right: 1px solid rgba(212, 175, 55, 0.25) !important;
    border-bottom: 1px solid rgba(212, 175, 55, 0.25) !important;
    background: linear-gradient(180deg, rgba(212, 175, 55, 0.12) 0%, rgba(255, 255, 255, 0.98) 100%) !important;
    box-shadow: 0 4px 12px rgba(212, 175, 55, 0.15) !important;
}
#CHART-r1c0:hover, .dashboard-chart-id-34:hover {
    box-shadow: 0 6px 18px rgba(212, 175, 55, 0.25) !important;
}
#CHART-r1c0 .header-title, #CHART-r1c0 [data-test="slice-header-text"],
.dashboard-chart-id-34 [data-test="slice-header-text"] {
    color: #997A15 !important;
    font-weight: 700 !important;
    font-size: 14px !important;
}
#CHART-r1c0 .header-line, #CHART-r1c0 .header-line *,
.dashboard-chart-id-34 .header-line, .dashboard-chart-id-34 .header-line *,
#CHART-r1c0 .superset-legacy-chart-big-number .header-line {
    color: #C9A227 !important;
    font-weight: 800 !important;
}
#CHART-r1c0 .subheader-line, .dashboard-chart-id-34 .subheader-line {
    color: #64748B !important;
    font-weight: 600 !important;
    font-size: 12.5px !important;
    margin-top: 2px !important;
}

/* --- TARJETA 2: Cobertura Integración % (Verde Spotify) --- */
#CHART-r1c1, .dashboard-chart-id-35, div[data-test-chart-name="Cobertura Integración %"] {
    border-top: 4px solid #1DB954 !important;
    border-left: 1px solid rgba(30, 215, 96, 0.25) !important;
    border-right: 1px solid rgba(30, 215, 96, 0.25) !important;
    border-bottom: 1px solid rgba(30, 215, 96, 0.25) !important;
    background: linear-gradient(180deg, rgba(30, 215, 96, 0.12) 0%, rgba(255, 255, 255, 0.98) 100%) !important;
    box-shadow: 0 4px 12px rgba(30, 215, 96, 0.15) !important;
}
#CHART-r1c1:hover, .dashboard-chart-id-35:hover {
    box-shadow: 0 6px 18px rgba(30, 215, 96, 0.25) !important;
}
#CHART-r1c1 .header-title, #CHART-r1c1 [data-test="slice-header-text"],
.dashboard-chart-id-35 [data-test="slice-header-text"] {
    color: #15803D !important;
    font-weight: 700 !important;
    font-size: 14px !important;
}
#CHART-r1c1 .header-line, #CHART-r1c1 .header-line *,
.dashboard-chart-id-35 .header-line, .dashboard-chart-id-35 .header-line *,
#CHART-r1c1 .superset-legacy-chart-big-number .header-line {
    color: #1DB954 !important;
    font-weight: 800 !important;
}
#CHART-r1c1 .header-line::after, .dashboard-chart-id-35 .header-line::after {
    content: "%" !important;
    font-size: 0.65em !important;
    font-weight: 700 !important;
    margin-left: 2px !important;
    color: #1DB954 !important;
}
#CHART-r1c1 .subheader-line, .dashboard-chart-id-35 .subheader-line {
    color: #64748B !important;
    font-weight: 600 !important;
    font-size: 12.5px !important;
    margin-top: 2px !important;
}

/* --- TARJETA 3: Artistas Grammy en Spotify (Azul Océano) --- */
#CHART-r1c2, .dashboard-chart-id-36, div[data-test-chart-name="Artistas Grammy en Spotify"] {
    border-top: 4px solid #0EA5E9 !important;
    border-left: 1px solid rgba(14, 165, 233, 0.25) !important;
    border-right: 1px solid rgba(14, 165, 233, 0.25) !important;
    border-bottom: 1px solid rgba(14, 165, 233, 0.25) !important;
    background: linear-gradient(180deg, rgba(14, 165, 233, 0.12) 0%, rgba(255, 255, 255, 0.98) 100%) !important;
    box-shadow: 0 4px 12px rgba(14, 165, 233, 0.15) !important;
}
#CHART-r1c2:hover, .dashboard-chart-id-36:hover {
    box-shadow: 0 6px 18px rgba(14, 165, 233, 0.25) !important;
}
#CHART-r1c2 .header-title, #CHART-r1c2 [data-test="slice-header-text"],
.dashboard-chart-id-36 [data-test="slice-header-text"] {
    color: #0369A1 !important;
    font-weight: 700 !important;
    font-size: 14px !important;
}
#CHART-r1c2 .header-line, #CHART-r1c2 .header-line *,
.dashboard-chart-id-36 .header-line, .dashboard-chart-id-36 .header-line *,
#CHART-r1c2 .superset-legacy-chart-big-number .header-line {
    color: #0284C7 !important;
    font-weight: 800 !important;
}
#CHART-r1c2 .subheader-line, .dashboard-chart-id-36 .subheader-line {
    color: #64748B !important;
    font-weight: 600 !important;
    font-size: 12.5px !important;
    margin-top: 2px !important;
}

/* --- TARJETA 4: Cobertura Estricta % (Púrpura Amatista) --- */
#CHART-r1c3, .dashboard-chart-id-37, div[data-test-chart-name="Cobertura Estricta %"] {
    border-top: 4px solid #8B5CF6 !important;
    border-left: 1px solid rgba(139, 92, 246, 0.25) !important;
    border-right: 1px solid rgba(139, 92, 246, 0.25) !important;
    border-bottom: 1px solid rgba(139, 92, 246, 0.25) !important;
    background: linear-gradient(180deg, rgba(139, 92, 246, 0.12) 0%, rgba(255, 255, 255, 0.98) 100%) !important;
    box-shadow: 0 4px 12px rgba(139, 92, 246, 0.15) !important;
}
#CHART-r1c3:hover, .dashboard-chart-id-37:hover {
    box-shadow: 0 6px 18px rgba(139, 92, 246, 0.25) !important;
}
#CHART-r1c3 .header-title, #CHART-r1c3 [data-test="slice-header-text"],
.dashboard-chart-id-37 [data-test="slice-header-text"] {
    color: #6D28D9 !important;
    font-weight: 700 !important;
    font-size: 14px !important;
}
#CHART-r1c3 .header-line, #CHART-r1c3 .header-line *,
.dashboard-chart-id-37 .header-line, .dashboard-chart-id-37 .header-line *,
#CHART-r1c3 .superset-legacy-chart-big-number .header-line {
    color: #7C3AED !important;
    font-weight: 800 !important;
}
#CHART-r1c3 .header-line::after, .dashboard-chart-id-37 .header-line::after {
    content: "%" !important;
    font-size: 0.65em !important;
    font-weight: 700 !important;
    margin-left: 2px !important;
    color: #7C3AED !important;
}
#CHART-r1c3 .subheader-line, .dashboard-chart-id-37 .subheader-line {
    color: #64748B !important;
    font-weight: 600 !important;
    font-size: 12.5px !important;
    margin-top: 2px !important;
}

/* --- Títulos de secciones intermedias --- */
.dashboard-component-header h2 {
    font-weight: 600 !important;
    color: #1E293B !important;
    border-bottom: 2px solid #E2E8F0 !important;
    padding-bottom: 6px !important;
}
"""

DASHBOARDS: dict[str, dict[str, str]] = {
    "granularity": {"title": GRANULARITY_TITLE, "slug": "w2-granularity", "css": ""},
    "requirements": {"title": DASHBOARD_TITLE, "slug": "w2-requirements", "css": ""},
    "workshop": {"title": WORKSHOP_TITLE, "slug": "workshop-dashboard", "css": WORKSHOP_CSS},
}

# metric_name -> SQL aggregate used by the charts
DATASET_SPECS: dict[str, dict[str, str]] = {
    "kpi_0_integration_coverage": {
        "award_rows": "SUM(award_rows)",
        "matched_strict_rows": "SUM(matched_strict_rows)",
        "matched_strict_pct": "MAX(matched_strict_pct)",
        "matched_enriched_rows": "SUM(matched_enriched_rows)",
        "matched_enriched_pct": "MAX(matched_enriched_pct)",
        "rows_without_artist_pct": "MAX(rows_without_artist_pct)",
    },
    "kpi_0_coverage_by_method": {
        "award_rows": "SUM(award_rows)",
        "share_pct": "MAX(share_pct)",
    },
    "kpi_0_coverage_by_tier": {
        "award_rows": "SUM(award_rows)",
        "share_pct": "MAX(share_pct)",
    },
    "kpi_0_coverage_by_decade": {
        "award_rows": "SUM(award_rows)",
        "matched_rows": "SUM(matched_rows)",
        "match_rate_pct": "MAX(match_rate_pct)",
        "matched_strict_rows": "SUM(matched_strict_rows)",
        "match_rate_strict_pct": "MAX(match_rate_strict_pct)",
    },
    "kpi_1_popularity_by_grammy_recognition": {
        "n_tracks": "SUM(n_tracks)",
        "n_artists": "SUM(n_artists)",
        "mean_popularity": "AVG(mean_popularity)",
        "median_popularity": "AVG(median_popularity)",
        "mean_danceability": "AVG(mean_danceability)",
        "mean_energy": "AVG(mean_energy)",
        "mean_valence": "AVG(mean_valence)",
        "mean_acousticness": "AVG(mean_acousticness)",
        "mean_speechiness": "AVG(mean_speechiness)",
    },
    "kpi_1_artist_level": {
        "mean_popularity": "AVG(mean_popularity)",
        "primary_tracks": "SUM(primary_tracks)",
    },
    "kpi_1_within_genre_diff": {
        "n_grammy_artists": "SUM(n_grammy_artists)",
        "n_non_grammy_artists": "SUM(n_non_grammy_artists)",
        "mean_pop_grammy": "AVG(mean_pop_grammy)",
        "mean_pop_non": "AVG(mean_pop_non)",
        "diff": "AVG(diff)",
        "mean_pop_grammy_strict": "AVG(mean_pop_grammy_strict)",
        "diff_strict": "AVG(diff_strict)",
        "stratified_weighted_diff": "MAX(stratified_weighted_diff)",
    },
    "kpi_2_awards_by_dominant_genre": {
        "awards": "SUM(awards)",
        "n_artists": "SUM(n_artists)",
        "award_share_pct": "MAX(award_share_pct)",
        "awards_per_100_artists": "MAX(awards_per_100_artists)",
    },
    "kpi_2_heatmap": {
        "awards": "SUM(awards)",
    },
    "kpi_3_awards_and_profile_by_decade": {
        "awards": "SUM(awards)",
        "distinct_artists": "SUM(distinct_artists)",
        "matched_awards": "SUM(matched_awards)",
        "matched_share_pct": "MAX(matched_share_pct)",
        "mean_energy": "AVG(mean_energy)",
        "mean_valence": "AVG(mean_valence)",
        "mean_danceability": "AVG(mean_danceability)",
        "mean_acousticness": "AVG(mean_acousticness)",
    },
    "kpi_3_awards_per_year": {
        "awards": "SUM(awards)",
        "recognized_artists": "SUM(recognized_artists)",
        "matched_awards": "SUM(matched_awards)",
        "matched_share_pct": "MAX(matched_share_pct)",
    },
    "kpi_3_awards_by_family_decade": {
        "awards": "SUM(awards)",
    },
    "kpi_4_top_awarded_artists_on_spotify": {
        "awards": "SUM(awards)",
        "spotify_track_count": "SUM(spotify_track_count)",
        "in_spotify": "MAX(in_spotify)",
    },
    "kpi_4_top_awarded_all": {
        "awards": "SUM(awards)",
        "spotify_track_count": "SUM(spotify_track_count)",
        "in_spotify": "MAX(in_spotify)",
    },
    "etl_batch_log": {
        "rows_fact_track_artist": "MAX(rows_fact_track_artist)",
        "rows_fact_grammy_award": "MAX(rows_fact_grammy_award)",
        "rows_bridge_award_artist": "MAX(rows_bridge_award_artist)",
    },
}


# --- Granularity datasets (inline SQL, no change needed in sql/kpi_queries.sql) -------
DATASET_SPECS.update({
    "gran_table_grain": {"row_count": "SUM(row_count)"},
    "gran_award_funnel": {"row_count": "SUM(row_count)"},
    "gran_track_funnel": {"row_count": "SUM(row_count)"},
    "gran_grammy_artists": {"grammy_artists": "MAX(grammy_artists)"},
    "workshop_awards_breakdown": {"awards": "SUM(awards)"},
})

INLINE_QUERIES: dict[str, str] = {
    "gran_table_grain": (
        "SELECT 1 AS sort_order, 'Dimension' AS layer, 'dim_year' AS table_name, "
        "'one ceremony year' AS grain, count(*)::bigint AS row_count FROM dim_year "
        "UNION ALL SELECT 2, 'Dimension', 'dim_genre', 'one Spotify genre (+ genre family)', count(*) FROM dim_genre "
        "UNION ALL SELECT 3, 'Dimension', 'dim_award_category', 'one raw Grammy category (+ clean name, family)', count(*) FROM dim_award_category "
        "UNION ALL SELECT 4, 'Dimension', 'dim_artist', 'one normalized artist key', count(*) FROM dim_artist "
        "UNION ALL SELECT 5, 'Fact', 'fact_track_artist', 'track listing x genre x performing artist', count(*) FROM fact_track_artist "
        "UNION ALL SELECT 6, 'Fact', 'fact_grammy_award', 'one award row (year x category x nominee x credit)', count(*) FROM fact_grammy_award "
        "UNION ALL SELECT 7, 'Bridge', 'bridge_award_artist', 'award x resolved artist (N:M)', count(*) FROM bridge_award_artist "
        "UNION ALL SELECT 8, 'Audit', 'etl_batch_log', 'one warehouse batch load', count(*) FROM etl_batch_log"
    ),
    "gran_award_funnel": (
        "SELECT 1 AS step, 'Award rows' AS stage, count(*)::bigint AS row_count FROM fact_grammy_award "
        "UNION ALL SELECT 2, 'Awards resolved to a Spotify artist', count(DISTINCT grammy_award_sk) FROM bridge_award_artist "
        "UNION ALL SELECT 3, 'Bridge rows (award x artist)', count(*) FROM bridge_award_artist "
        "UNION ALL SELECT 4, 'Distinct artists in bridge', count(DISTINCT artist_sk) FROM bridge_award_artist"
    ),
    "gran_grammy_artists": (
        "SELECT count(DISTINCT artist_sk)::bigint AS grammy_artists "
        "FROM fact_track_artist WHERE is_grammy_artist = 1"
    ),
    "gran_track_funnel": (
        "SELECT 1 AS step, 'Track listings (track x genre x artist)' AS stage, count(*)::bigint AS row_count FROM fact_track_artist "
        "UNION ALL SELECT 2, 'Primary songs (is_primary_song = 1)', COALESCE(SUM(is_primary_song), 0)::bigint FROM fact_track_artist "
        "UNION ALL SELECT 3, 'Distinct artists', count(DISTINCT artist_sk) FROM fact_track_artist"
    ),
    "workshop_awards_breakdown": (
        "SELECT y.decade, c.category_family, "
        "COALESCE(a.dominant_genre_family, 'Other / Unclassified') AS genre_family, "
        "COALESCE(w.match_method, 'none') AS match_method, "
        "count(*)::bigint AS awards "
        "FROM fact_grammy_award w "
        "JOIN dim_year y ON y.year_sk = w.year_sk "
        "JOIN dim_award_category c ON c.category_sk = w.category_sk "
        "LEFT JOIN dim_artist a ON a.artist_sk = w.artist_sk "
        "GROUP BY y.decade, c.category_family, COALESCE(a.dominant_genre_family, 'Other / Unclassified'), COALESCE(w.match_method, 'none')"
    ),
}

# Virtual datasets whose column names differ across KPIs get an extra alias column so a
# single native filter (e.g. genre_family) drives R1 and R2 charts alike.
ALIAS_COLUMNS: dict[str, dict[str, str]] = {
    "kpi_2_awards_by_dominant_genre": {"genre_family": "dominant_genre_family"},
    "kpi_2_heatmap": {"genre_family": "dominant_genre_family"},
}


# --- chart spec helpers ---------------------------------------------------------------
def _spec(dashboard, dataset, name, requirement, description, candidates):
    return {
        "dashboard": dashboard,
        "dataset": dataset,
        "slice_name": name,
        "requirement": requirement,
        "description": description,
        "candidates": candidates,
    }


def _table(cols, limit=50, order=None, filters=None):
    form = {"query_mode": "raw", "all_columns": cols, "row_limit": limit, "include_search": False}
    if order:
        form["order_by_cols"] = order
    if filters:
        form["adhoc_filters"] = filters
    return ("table", form)


def _big(metric, subheader, fmt=".1f", color=None, header_font_size=0.55, subheader_font_size=0.28):
    form = {
        "metric": metric, "subheader": subheader, "y_axis_format": fmt,
        "header_font_size": header_font_size, "subheader_font_size": subheader_font_size,
    }
    if color:
        form["color_picker"] = color
    return [
        ("big_number_total", form),
        _table([metric], 10),
    ]


def _line(x, metrics, fmt=".2f", limit=100):
    return ("echarts_timeseries_line", {
        "x_axis": x, "metrics": metrics, "x_axis_force_categorical": True,
        "markerEnabled": True, "markerSize": 8, "y_axis_format": fmt,
        "show_legend": len(metrics) > 1, "row_limit": limit,
    })


def _hbar(x, metric, limit, fmt=".1f", ascending=False):
    return [
        ("echarts_timeseries_bar", {
            "x_axis": x, "metrics": [metric], "orientation": "horizontal", "show_value": True,
            "x_axis_sort": metric, "x_axis_sort_asc": ascending, "y_axis_format": fmt,
            "row_limit": limit,
        }),
        ("dist_bar", {
            "groupby": [x], "metrics": [metric], "show_bar_value": True,
            "order_bars": True, "y_axis_format": fmt, "row_limit": limit,
        }),
    ]


def _simple_filter(col, op, val):
    return {"expressionType": "SIMPLE", "subject": col, "operator": op,
            "comparator": val, "clause": "WHERE"}


G, R, W = "granularity", "requirements", "workshop"
ALL_REQ = "R1,R2,R3,R4"

# Charts: preferred viz type first, "table" always last as the safe fallback.
CHART_SPECS: list[dict] = [
    # ===== Dashboard 1: Granularity & Data Quality =================================
    _spec(G, "kpi_0_integration_coverage", "[Header] Coverage Enriched %", "R1,R2,R3",
          "Enriched match rate via cascade across all Grammy award rows.",
          _big("matched_enriched_pct", "% of award rows resolved to a Spotify artist (cascade)")),
    _spec(G, "kpi_0_integration_coverage", "[Header] Coverage Strict %", "R1,R2,R3",
          "Exact un-split credit match rate baseline.",
          _big("matched_strict_pct", "% resolved by exact credit only (baseline)")),
    _spec(G, "gran_grammy_artists", "[Header] Grammy Artists Matched", "R3",
          "Distinct Grammy-recognized artists (core definition) found in the Spotify catalog.",
          _big("grammy_artists", "distinct artists with is_grammy_artist = 1", ",d")),
    _spec(G, "etl_batch_log", "[Header] Awards Loaded", "R4",
          "Total Grammy award rows loaded in the latest warehouse batch.",
          _big("rows_fact_grammy_award", "award rows in fact_grammy_award", ",d")),

    _spec(G, "gran_table_grain", "[Grain] Rows and Grain per Table", ALL_REQ,
          "One row per warehouse table: layer, grain (what one row means) and current row count.",
          [_table(["sort_order", "layer", "table_name", "grain", "row_count"], 10,
                  order=[["sort_order", True]])]),
    _spec(G, "gran_award_funnel", "[Grain] Award Credits to Bridge", ALL_REQ,
          "Awards -> resolved awards -> bridge rows (award x artist) -> distinct artists. "
          "Bridge rows can exceed resolved awards because collaborative credits resolve to several artists.",
          _hbar("stage", "row_count", 10, ",d") + [_table(["step", "stage", "row_count"], 10,
                                                          order=[["step", True]])]),
    _spec(G, "gran_track_funnel", "[Grain] Track Listings to Artists", ALL_REQ,
          "Track listings repeat across genres and collaborations; primary songs deduplicate them.",
          _hbar("stage", "row_count", 10, ",d") + [_table(["step", "stage", "row_count"], 10,
                                                          order=[["step", True]])]),

    _spec(G, "kpi_0_coverage_by_method", "[Quality] Match Method Distribution", "R1,R2,R3",
          "Hierarchical cascade: exact -> split -> workers -> nominee -> fuzzy -> none.",
          [("pie", {"groupby": ["match_method"], "metric": "award_rows", "metrics": ["award_rows"],
                    "donut": True, "show_legend": True, "label_type": "key_percent", "row_limit": 10}),
           _table(["match_method", "award_rows", "share_pct"], 10)]),
    _spec(G, "kpi_0_coverage_by_tier", "[Quality] Awards by recognition tier", "R1,R2,R3",
          "Grammy awards by recognition tier (A, B, C, none) and match cascade method.",
          [("echarts_timeseries_bar", {"x_axis": "recognition_tier", "groupby": ["match_method"],
                                       "metrics": ["award_rows"], "stack": True, "show_legend": True,
                                       "y_axis_format": ",d", "row_limit": 50}),
           ("dist_bar", {"groupby": ["recognition_tier"], "columns": ["match_method"],
                         "metrics": ["award_rows"], "bar_stacked": True, "row_limit": 50}),
           _table(["recognition_tier", "match_method", "award_rows", "share_pct"], 50)]),
    _spec(G, "kpi_0_coverage_by_decade", "[Quality] Coverage Trend by Decade", "R1,R2,R3",
          "Strict match vs enriched cascade coverage over ceremony decades.",
          [_line("decade", ["match_rate_pct", "match_rate_strict_pct"], ".1f"),
           _table(["decade", "award_rows", "match_rate_pct", "match_rate_strict_pct"], 100)]),
    _spec(G, "etl_batch_log", "[Quality] Last ETL Batches", "R4",
          "Audit trail of warehouse batch loads from etl_batch_log.",
          [_table(["batch_id", "dag_id", "run_id", "status", "rows_fact_track_artist",
                   "rows_fact_grammy_award", "rows_bridge_award_artist"], 5)]),

    # ===== Dashboard 2: R1-R4 ========================================================
    _spec(R, "kpi_0_integration_coverage", "[R*] Coverage Enriched % (context)", "R1,R2,R3,R4",
          "Always-visible coverage caveat: share of award rows resolved to a Spotify artist.",
          _big("matched_enriched_pct", "% of awards matched to Spotify (name-based)")),

    # --- R1 ---
    _spec(R, "kpi_1_artist_level", "[R1] Artist Popularity Distribution", "R1",
          "Per-artist mean popularity. Keep basis/recognition filters on one value each; "
          "14.1% of raw tracks have zero popularity.",
          [("box_plot", {"columns": ["artist_group"], "groupby": ["artist_display_name"],
                         "metrics": ["mean_popularity"], "whiskerOptions": "Tukey",
                         "row_limit": 500}),
           _table(["artist_group", "artist_display_name", "mean_popularity", "primary_tracks"], 100)]),
    _spec(R, "kpi_1_popularity_by_grammy_recognition", "[R1] Audio Features: Grammy vs Non-Grammy", "R1",
          "Audio features in [0, 1]; comparisons reflect surviving catalog tracks (primary songs).",
          [("radar", {"groupby": ["artist_group"],
                      "metrics": ["mean_danceability", "mean_energy", "mean_valence",
                                  "mean_acousticness", "mean_speechiness"],
                      "show_legend": True, "row_limit": 10}),
           _table(["basis", "recognition", "artist_group", "mean_danceability", "mean_energy",
                   "mean_valence", "mean_acousticness", "mean_speechiness"], 20)]),
    _spec(R, "kpi_1_within_genre_diff", "[R1] Popularity Difference within Genre Family", "R1,R2",
          "Grammy minus non-Grammy mean popularity inside each genre family "
          "(families with >= 30 Grammy artists).",
          _hbar("genre_family", "diff", 20, ".1f", ascending=True)
          + [_table(["genre_family", "mean_pop_grammy", "mean_pop_non", "diff",
                     "n_grammy_artists", "stratified_weighted_diff"], 50)]),
    _spec(R, "kpi_1_popularity_by_grammy_recognition", "[R1] Popularity Summary Table", "R1",
          "Group-level medians and quartiles; basis separates zero-popularity tracks.",
          [_table(["basis", "recognition", "artist_group", "n_tracks", "n_artists",
                   "mean_popularity", "median_popularity", "p25_popularity", "p75_popularity"], 20)]),

    # --- R2 ---
    _spec(R, "kpi_2_heatmap", "[R2] Genre Family vs Category Family Heatmap", "R2",
          "Awards by dominant genre family (artist) x Grammy category family.",
          [("heatmap_v2", {"x_axis": "genre_family", "groupby": "category_family",
                           "metric": "awards", "normalize_across": "heatmap",
                           "legend_type": "continuous", "show_legend": True, "row_limit": 500}),
           ("heatmap", {"all_columns_x": "genre_family", "all_columns_y": "category_family",
                        "metric": "awards", "row_limit": 500}),
           _table(["dominant_genre_family", "category_family", "awards"], 200)]),
    _spec(R, "kpi_2_awards_by_dominant_genre", "[R2] Awards per 100 Artists by Dominant Genre Family", "R2",
          "Rate denominator is distinct artists classified into the dominant genre family.",
          _hbar("genre_family", "awards_per_100_artists", 15, ".1f")
          + [_table(["dominant_genre_family", "awards", "n_artists", "awards_per_100_artists"], 50)]),

    # --- R3 ---
    _spec(R, "kpi_3_awards_and_profile_by_decade", "[R3] Energy Trend by Decade", "R3",
          "Popularity is current, not historical; older decades have lower coverage.",
          [_line("decade", ["mean_energy"]), _table(["decade", "mean_energy"], 100)]),
    _spec(R, "kpi_3_awards_and_profile_by_decade", "[R3] Valence Trend by Decade", "R3",
          "Trend interpretation depends on coverage; surviving recordings bias older periods.",
          [_line("decade", ["mean_valence"]), _table(["decade", "mean_valence"], 100)]),
    _spec(R, "kpi_3_awards_and_profile_by_decade", "[R3] Danceability Trend by Decade", "R3",
          "Danceability on primary songs only, to prevent repeated-song inflation.",
          [_line("decade", ["mean_danceability"]), _table(["decade", "mean_danceability"], 100)]),
    _spec(R, "kpi_3_awards_by_family_decade", "[R3] Awards by Category Family per Decade", "R3",
          "Historical Grammy categories merged into canonical families.",
          [("echarts_timeseries_bar", {"x_axis": "decade", "groupby": ["category_family"],
                                       "metrics": ["awards"], "stack": True, "show_legend": True,
                                       "y_axis_format": ",d", "row_limit": 300}),
           ("dist_bar", {"groupby": ["decade"], "columns": ["category_family"],
                         "metrics": ["awards"], "bar_stacked": True, "row_limit": 300}),
           _table(["decade", "category_family", "awards"], 150)]),
    _spec(R, "kpi_3_awards_and_profile_by_decade", "[R3] Matched Share by Decade", "R3",
          "Trend interpretation depends on coverage; older decades have lower coverage.",
          [_line("decade", ["matched_share_pct"], ".1f"),
           _table(["decade", "awards", "matched_awards", "matched_share_pct"], 100)]),

    # --- R4 ---
    _spec(R, "kpi_4_top_awarded_artists_on_spotify", "[R4] Top-10 Awarded Artists on Spotify", "R4",
          "Excludes aggregate credits (Various Artists, Original Cast); top 10 with ties kept.",
          _hbar("artist_display_name", "awards", 10, ",d")
          + [_table(["artist_display_name", "awards", "spotify_track_count",
                     "first_award_year", "last_award_year"], 20, order=[["awards", False]])]),
    _spec(R, "kpi_4_top_awarded_all", "[R4] Top Awarded Artists Overall", "R4",
          "Includes artists absent from Spotify (in_spotify = 0) and their recognition tier.",
          [_table(["rank", "artist_display_name", "recognition_tier", "awards",
                   "spotify_track_count", "in_spotify"], 25, order=[["rank", True]])]),
    _spec(R, "kpi_4_top_awarded_all", "[R4] Top Artists Absent from Spotify", "R4",
          "Artistas galardonados en categorias tecnicas o produccion (Tier C: no catalogados como interpretes en R1).",
          [_table(["artist_display_name", "recognition_tier", "awards", "first_award_year", "last_award_year"], 15,
                  order=[["awards", False]],
                  filters=[_simple_filter("recognition_tier", "==", "C")])]),

    # ===== Dashboard 3: Workshop Dashboard ==========================================
    _spec(W, "etl_batch_log", "Premios Evaluados", ALL_REQ,
          "Total de 4.810 premios Grammy evaluados en el Data Warehouse.",
          _big("rows_fact_grammy_award", "Total Premios Grammy", ",d",
               color={"r": 201, "g": 162, "b": 39, "a": 1}, subheader_font_size=0.34)),
    _spec(W, "kpi_0_integration_coverage", "Cobertura Integración %", ALL_REQ,
          "51.1% de premios enlazados a Spotify mediante cascada completa (exacto + créditos + fuzzy).",
          _big("matched_enriched_pct", "Premios Vinculados (% Cascada)", ".1f",
               color={"r": 30, "g": 215, "b": 96, "a": 1}, subheader_font_size=0.34)),
    _spec(W, "gran_grammy_artists", "Artistas Grammy en Spotify", ALL_REQ,
          "638 artistas únicos reconocidos con Grammy presentes en Spotify.",
          _big("grammy_artists", "Artistas Galardonados en Catálogo", ",d",
               color={"r": 41, "g": 128, "b": 185, "a": 1}, subheader_font_size=0.34)),
    _spec(W, "kpi_0_integration_coverage", "Cobertura Estricta %", ALL_REQ,
          "31.8% de cruce exacto directo inicial (línea base 1 a 1 sin cascada).",
          _big("matched_strict_pct", "Cruce Estricto 1:1 (% Línea Base)", ".1f",
               color={"r": 142, "g": 68, "b": 173, "a": 1}, subheader_font_size=0.34)),

    _spec(W, "kpi_1_within_genre_diff", "Diferencia de Popularidad por Género (R1/R2)", "R1,R2",
          "Diferencia de popularidad promedio (Grammy vs No-Grammy) por familia de género musical.",
          _hbar("genre_family", "diff", 15, ".1f", ascending=True)
          + [_table(["genre_family", "diff", "mean_pop_grammy", "mean_pop_non"], 50)]),

    _spec(W, "workshop_awards_breakdown", "Evolución de Premios por Categoría y Década (R3)", "R3",
          "Distribución histórica de premios Grammy por década y familia de categoría.",
          [("echarts_timeseries_bar", {"x_axis": "decade", "groupby": ["category_family"],
                                       "metrics": ["awards"], "stack": True, "show_legend": True,
                                       "y_axis_format": ",d", "row_limit": 500}),
           ("dist_bar", {"groupby": ["decade"], "columns": ["category_family"],
                         "metrics": ["awards"], "bar_stacked": True, "row_limit": 500}),
           _table(["decade", "category_family", "awards"], 500)]),

    _spec(W, "kpi_4_top_awarded_artists_on_spotify", "Top Artistas Premiados en Spotify (R4)", "R4",
          "Artistas más galardonados con presencia en el catálogo de Spotify.",
          [_table(["rank", "artist_display_name", "awards", "spotify_track_count",
                   "first_award_year", "last_award_year"], 50, order=[["awards", False]])]),
]

# --- Layouts: str = section header, list = one row of (kind, ref, width, height) ----------
# width is in the 12-column grid; height unit = 8 px. Chart refs are slice_name values.
LAYOUTS: dict[str, list] = {
    "granularity": [
        [("md", "gran_intro", 12, 17)],
        [("chart", "[Header] Awards Loaded", 3, 17),
         ("chart", "[Header] Coverage Enriched %", 3, 17),
         ("chart", "[Header] Coverage Strict %", 3, 17),
         ("chart", "[Header] Grammy Artists Matched", 3, 17)],
        "Granularidad del modelo: que representa cada fila",
        [("chart", "[Grain] Rows and Grain per Table", 12, 36)],
        [("chart", "[Grain] Award Credits to Bridge", 4, 44),
         ("chart", "[Grain] Track Listings to Artists", 4, 44),
         ("chart", "[Quality] Match Method Distribution", 4, 44)],
        "Calidad de la integracion: que tan confiable es el cruce",
        [("chart", "[Quality] Awards by recognition tier", 6, 44),
         ("chart", "[Quality] Coverage Trend by Decade", 6, 44)],
        [("chart", "[Quality] Last ETL Batches", 12, 26)],
    ],
    "requirements": [
        [("md", "req_intro", 9, 17), ("chart", "[R*] Coverage Enriched % (context)", 3, 17)],
        "R1 — ¿Los artistas reconocidos por el Grammy rinden distinto en Spotify?",
        [("chart", "[R1] Artist Popularity Distribution", 4, 46),
         ("chart", "[R1] Audio Features: Grammy vs Non-Grammy", 4, 46),
         ("chart", "[R1] Popularity Difference within Genre Family", 4, 46)],
        [("chart", "[R1] Popularity Summary Table", 8, 30), ("md", "r1_guide", 4, 30)],
        "R2 — ¿Qué géneros dominan entre los artistas premiados?",
        [("chart", "[R2] Genre Family vs Category Family Heatmap", 7, 56),
         ("chart", "[R2] Awards per 100 Artists by Dominant Genre Family", 5, 56)],
        "R3 — ¿Cómo evoluciona el perfil de los artistas a lo largo de las décadas?",
        [("chart", "[R3] Energy Trend by Decade", 3, 36),
         ("chart", "[R3] Valence Trend by Decade", 3, 36),
         ("chart", "[R3] Danceability Trend by Decade", 3, 36),
         ("chart", "[R3] Matched Share by Decade", 3, 36)],
        [("chart", "[R3] Awards by Category Family per Decade", 8, 42), ("md", "r3_guide", 4, 42)],
        "R4 — ¿Quiénes acumulan más premios y cómo están representados en Spotify?",
        [("chart", "[R4] Top-10 Awarded Artists on Spotify", 5, 50),
         ("chart", "[R4] Top Awarded Artists Overall", 7, 50)],
        [("chart", "[R4] Top Artists Absent from Spotify", 6, 34), ("md", "r4_guide", 6, 34)],
    ],
    "workshop": [
        [("md", "workshop_intro", 12, 4)],
        [("chart", "Premios Evaluados", 3, 14),
         ("chart", "Cobertura Integración %", 3, 14),
         ("chart", "Artistas Grammy en Spotify", 3, 14),
         ("chart", "Cobertura Estricta %", 3, 14)],
        "R1 & R2: Desempeño Musical y Géneros | R3: Evolución Histórica",
        [("chart", "Diferencia de Popularidad por Género (R1/R2)", 6, 46),
         ("chart", "Evolución de Premios por Categoría y Década (R3)", 6, 46)],
        "R4: Ranking de Artistas Más Galardonados Presentes en Spotify",
        [("chart", "Top Artistas Premiados en Spotify (R4)", 12, 36)],
    ],
}

# Markdown cards (Spanish; no hard-coded figures, numbers come from the charts).
MARKDOWN: dict[str, str] = {
    "workshop_intro": (
        "**Dashboard Spotify & Grammy (R1–R4)** &nbsp;|&nbsp; "
        "Pipeline batch analítico Spotify × Premios Grammy (PostgreSQL `music_dw` → Superset) &nbsp;·&nbsp; "
        "[Ver Detalle Analítico Completo (KPIs R1–R4) →](/superset/dashboard/w2-requirements/)"
    ),
    "gran_intro": (
        "## Workshop-2 · Granularidad y calidad de datos\n"
        "**Spotify × Grammy Awards** · pipeline batch confiable "
        "(Airflow → Great Expectations → PostgreSQL → Superset).\n\n"
        "Cada tabla tiene un *grano* distinto; el cruce Grammy → Spotify se resuelve en el puente "
        "`bridge_award_artist` (premio × artista). "
        "[Ver requerimientos R1–R4 →](/superset/dashboard/w2-requirements/)"
    ),
    "req_intro": (
        "## Workshop-2 · Requerimientos analíticos R1–R4\n"
        "**Pipeline Confiable Spotify × Premios Grammy** (Airflow → Great Expectations → PostgreSQL → Superset)\n\n"
        "> **Controles interactivos para sustentación:** Utilice la barra de filtros horizontal superior para dinamizar las gráficas:\n"
        "> - **`basis` & `recognition`**: Filtros de sensibilidad para **R1** (*excl_zero* vs *all*, *core* vs *strict*).\n"
        "> - **`genre_family` & `category_family`**: Filtran por familia de género y categoría en **R1** y **R2**.\n"
        "> - **`decade`**: Filtra la evolución histórica y distribución de categorías en **R3**."
    ),
    "r1_guide": (
        "### Claves para explicar R1\n\n"
        "- **Filtro `basis`**: *excl_zero* excluye pistas con popularidad 0 (~14.6% del catálogo, no reproducidas o retiradas). *all* evalúa el catálogo entero.\n"
        "- **Filtro `recognition`**: *core* = Tiers A+B (intérpretes directos y parentéticos). *strict* = solo Tier A (crédito directo).\n"
        "- **Hallazgo estadístico**: La popularidad mediana de artistas Grammy es significativamente mayor en ambos casos (+10.22 puntos en *excl_zero*, p < 1e-30; delta de Cliff = 0.24)."
    ),
    "r3_guide": (
        "### Claves para explicar R3\n\n"
        "- **Evolución sónica**: Caída sostenida en *acousticness* junto al aumento de *energy* y *danceability* desde los 1960s.\n"
        "- **Cobertura por década**: El gráfico *Matched Share* muestra que la disponibilidad en Spotify crece de ~15% en los 1960s a ~50% en los 2010s.\n"
        "- **Uso del filtro `decade`**: Permite aislar una década para ver las categorías premiadas predominantes."
    ),
    "r4_guide": (
        "### Claves para explicar R4\n\n"
        "- **Top en Spotify**: Intérpretes principales más premiados en catálogo (Chicago Symphony Orchestra, John Williams, Beyoncé, Jay-Z).\n"
        "- **Ranking Global**: Muestra el nivel de reconocimiento (Tier A: crédito, Tier B: workers, Tier C: producción).\n"
        "- **Galardonados Tier C**: Leyendas con premios de producción o técnicos (Frank Sinatra, Quincy Jones, Miles Davis, Billie Holiday) que no inflan el estatus de intérprete en R1."
    ),
}

# --- Native filters: column must exist in the datasets of the charts to be scoped --------
FILTER_DEFS: dict[str, list[dict]] = {
    "workshop": [
        {"name": "Década", "column": "decade", "description": "Filtrar por década del premio Grammy (1950s - 2010s)"},
        {"name": "Categoría Grammy", "column": "category_family", "description": "Familia de categoría Grammy (Pop, Rock, Classical, General Field...)"},
        {"name": "Género Musical", "column": "genre_family", "description": "Familia de género musical en Spotify (Pop, Rock, Hip-Hop, Electronic...)"},
        {"name": "Método de Emparejamiento", "column": "match_method", "description": "Método de cruce entre Grammy y Spotify (exact, split, workers...)"},
    ],
    "granularity": [
        {"name": "decade", "column": "decade"},
        {"name": "match_method", "column": "match_method"},
        {"name": "recognition_tier", "column": "recognition_tier"},
    ],
    "requirements": [
        {"name": "decade", "column": "decade"},
        {"name": "genre_family", "column": "genre_family"},
        {"name": "category_family", "column": "category_family"},
        {"name": "basis", "column": "basis", "default": ["excl_zero"], "required": True,
         "multi": False,
         "description": "Default excl_zero hides the ~14.1% tracks with popularity = 0 (R1 only)"},
        {"name": "recognition", "column": "recognition", "default": ["core"], "required": True,
         "multi": False,
         "description": "core = recognition tiers A+B; strict = tier A only (R1 only)"},
    ],
}
OPTIONAL_META_KEYS = ("cross_filters_enabled", "filter_bar_orientation")

LABEL_COLORS = {
    "Grammy-recognized": "#C9A227", "Not Grammy-recognized": "#5B6C8F",
    "Grammy": "#C9A227", "Non-Grammy": "#5B6C8F",
    "exact": "#C9A227", "split": "#E5C158", "workers": "#5B6C8F",
    "nominee": "#8B9BB4", "fuzzy": "#A78BFA", "none": "#CBD5E1",
    "A": "#C9A227", "B": "#5B6C8F", "C": "#8B9BB4",
}

class SupersetClient:
    def __init__(self, base_url: str):
        self.base_url = base_url
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(CookieJar())
        )
        self.token: str | None = None
        self.csrf: str | None = None

    def call(self, method: str, path: str, payload: dict | None = None):
        request = urllib.request.Request(self.base_url + path, method=method)
        request.add_header("Content-Type", "application/json")
        if self.token:
            request.add_header("Authorization", f"Bearer {self.token}")
        if self.csrf:
            request.add_header("X-CSRFToken", self.csrf)
        data = json.dumps(payload).encode() if payload is not None else None
        try:
            with self.opener.open(request, data, timeout=180) as response:
                body = response.read().decode()
                try:
                    parsed = json.loads(body or "{}")
                except json.JSONDecodeError:
                    parsed = {"raw": body[:500]}
                return response.status, parsed
        except urllib.error.HTTPError as error:
            body = error.read().decode(errors="replace")
            try:
                parsed = json.loads(body)
            except json.JSONDecodeError:
                parsed = {"raw": body[:500]}
            return error.code, parsed

    def login(self) -> None:
        status, out = self.call("POST", "/api/v1/security/login", {
            "username": ADMIN_USER,
            "password": ADMIN_PASSWORD,
            "provider": "db",
            "refresh": True,
        })
        if status != 200 or "access_token" not in out:
            raise SystemExit(f"[superset-bootstrap] login failed: {status} {out}")
        self.token = out["access_token"]
        status, out = self.call("GET", "/api/v1/security/csrf_token/")
        self.csrf = out.get("result") if status == 200 else None

    def list(self, path: str, name_field: str) -> dict[str, dict]:
        status, out = self.call("GET", f"{path}?q=(page_size:500)")
        if status != 200:
            raise SystemExit(f"[superset-bootstrap] list {path} failed: {status} {out}")
        return {item[name_field]: item for item in out.get("result", [])}

    def ensure(self, path: str, name_field: str, name: str, payload: dict,
               update_payload: dict | None = None) -> dict:
        """Create (or update) an object identified by its name; return its record."""
        existing = self.list(path, name_field).get(name)
        if existing:
            status, out = self.call("PUT", f"{path}{existing['id']}",
                                    update_payload if update_payload is not None else payload)
            action = "updated"
        else:
            status, out = self.call("POST", path, payload)
            action = "created"
        if status not in (200, 201):
            raise SystemExit(f"[superset-bootstrap] {name_field}={name} {action} failed: "
                             f"{status} {json.dumps(out)[:400]}")
        record = out.get("result") or out.get("data") or out
        if "id" not in record:
            record = self.list(path, name_field)[name]
        print(f"[superset-bootstrap] {action}: {name} (id={record['id']})")
        return record


def load_kpi_queries() -> dict[str, str]:
    raw = open(KPI_SQL_PATH, encoding="utf-8").read()
    marks = [(m.group(1), m.start())
             for m in re.finditer(r"^--\s*@name:\s*([A-Za-z0-9_]+)\s*$", raw, flags=re.M)]
    queries: dict[str, str] = {}
    for index, (name, start) in enumerate(marks):
        body_start = raw.index("\n", start) + 1
        body_end = marks[index + 1][1] if index + 1 < len(marks) else len(raw)
        queries[name] = raw[body_start:body_end].strip()
    return queries


def ensure_database(client: SupersetClient) -> int:
    existing = client.list("/api/v1/database/", "database_name").get("music_dw")
    if existing:
        print(f"[superset-bootstrap] database exists: music_dw (id={existing['id']})")
        return existing["id"]
    record = client.ensure("/api/v1/database/", "database_name", "music_dw", {
        "database_name": "music_dw",
        "sqlalchemy_uri": DW_URI,
        "expose_in_sqllab": True,
        "allow_ctas": False,
        "allow_cvas": False,
        "allow_dml": False,
        "allows_subquery": True,
        "allows_virtual_table_explore": True,
    })
    return record["id"]




ETL_BATCH_LOG_SQL = (
    "SELECT batch_id, COALESCE(dag_id, 'manual') AS dag_id, "
    "COALESCE(run_id, batch_id) AS run_id, status, "
    "COALESCE((target_rows_after->>'fact_track_artist')::bigint, 0) AS rows_fact_track_artist, "
    "COALESCE((target_rows_after->>'fact_grammy_award')::bigint, 0) AS rows_fact_grammy_award, "
    "COALESCE((target_rows_after->>'bridge_award_artist')::bigint, 0) AS rows_bridge_award_artist "
    "FROM etl_batch_log ORDER BY started_at DESC LIMIT 5"
)


def _wrap_sql(sql: str, aliases: dict[str, str] | None) -> str:
    """Optionally expose alias columns (e.g. genre_family) next to the original ones."""
    lines = sql.strip().splitlines()
    while lines and (not lines[-1].strip() or lines[-1].strip().startswith("--")
                     or lines[-1].strip() == ";"):
        lines.pop()
    body = "\n".join(lines).strip()
    body = re.sub(r";\s*(--[^\n]*)?\s*$", "", body).strip()
    if not aliases:
        return body
    extra = ", ".join(f"q.{src} AS {alias}" for alias, src in aliases.items())
    return f"SELECT q.*, {extra}\nFROM (\n{body}\n) AS q"


def ensure_dataset(client: SupersetClient, database_id: int, table_name: str,
                   sql: str, metrics: dict[str, str],
                   aliases: dict[str, str] | None = None) -> tuple[int, list[str]]:
    sql = _wrap_sql(sql, aliases)
    record = client.ensure(
        "/api/v1/dataset/",
        "table_name",
        table_name,
        {"database": database_id, "table_name": table_name, "sql": sql},
        update_payload={"database_id": database_id, "table_name": table_name, "sql": sql},
    )
    dataset_id = record["id"]
    status, out = client.call("GET", f"/api/v1/dataset/{dataset_id}")
    existing_metrics = {
        metric["metric_name"]: metric
        for metric in ((out.get("result") or {}).get("metrics") or [])
    }
    metrics_payload = []
    for name, expression in metrics.items():
        entry = {"metric_name": name, "expression": expression, "verbose_name": name}
        if name in existing_metrics:
            entry["id"] = existing_metrics[name]["id"]  # required by PUT
        metrics_payload.append(entry)
    status, out = client.call("PUT", f"/api/v1/dataset/{dataset_id}", {
        "table_name": table_name,
        "database_id": database_id,
        "sql": sql,
        "metrics": metrics_payload,
    })
    if status != 200:
        raise SystemExit(f"[superset-bootstrap] metrics for {table_name} failed: "
                         f"{status} {json.dumps(out)[:400]}")
    client.call("PUT", f"/api/v1/dataset/{dataset_id}/refresh")
    status, out = client.call("GET", f"/api/v1/dataset/{dataset_id}")
    columns = [c["column_name"] for c in ((out.get("result") or {}).get("columns") or [])]
    return dataset_id, columns


def _validation_query(form: dict) -> dict:
    """Minimal chart query used to prove the KPI SQL runs through Superset."""
    metrics = list(form.get("metrics") or ([form["metric"]] if form.get("metric") else []))
    if "all_columns" in form:
        groupby = list(form["all_columns"])
        metrics = []
    else:
        groupby = [form[k] for k in ("x_axis", "all_columns_x", "all_columns_y") if form.get(k)]
        extra = form.get("groupby") or []
        groupby += [extra] if isinstance(extra, str) else list(extra)
        groupby += list(form.get("columns") or [])
    query = {
        "groupby": list(dict.fromkeys(groupby)),
        "metrics": metrics,
        "row_limit": min(int(form.get("row_limit", 1000)), 1000),
        "extras": {"time_grain_sqla": None},
        "applied_time_extras": {},
        "is_timeseries": False,
    }
    filters = [{"col": f["subject"], "op": f["operator"], "val": f["comparator"]}
               for f in form.get("adhoc_filters", []) if f.get("expressionType") == "SIMPLE"]
    if filters:
        query["filters"] = filters
    for column, is_ascending in form.get("order_by_cols", []):
        query.setdefault("orderby", []).append([column, bool(is_ascending)])
    return query


def ensure_chart(client: SupersetClient, spec: dict, dataset_id: int, dashboard_id: int) -> int:
    """Create the chart with the first candidate whose query actually executes."""
    failures: list[str] = []
    description = spec.get("description") or f"[{spec['requirement']}] generado por scripts/superset_bootstrap.py"
    for viz_type, form in spec["candidates"]:
        saved = dict(form)
        if "order_by_cols" in saved:  # Table charts store them as JSON strings
            saved["order_by_cols"] = [json.dumps(list(pair)) for pair in saved["order_by_cols"]]
        form_data = {"adhoc_filters": [], "time_range": "No filter", **saved,
                     "viz_type": viz_type, "datasource": f"{dataset_id}__table"}
        payload = {
            "slice_name": spec["slice_name"],
            "description": description,
            "datasource_id": dataset_id,
            "datasource_type": "table",
            "viz_type": viz_type,
            "params": json.dumps(form_data),
            "dashboards": [dashboard_id],
        }
        record = client.ensure("/api/v1/chart/", "slice_name", spec["slice_name"],
                               payload, update_payload=payload)

        query_context = {
            "datasource": {"id": dataset_id, "type": "table"},
            "queries": [_validation_query(form)],
            "form_data": form_data,
            "result_format": "json",
            "result_type": "full",
        }
        status, out = client.call("POST", "/api/v1/chart/data", query_context)
        if status == 200 and not out.get("error"):
            rows = ((out.get("result") or [{}])[0] or {}).get("rowcount")
            print(f"[superset-bootstrap] chart ok: {spec['slice_name']} ({viz_type}, rows={rows})")
            return int(record["id"])
        failures.append(f"{viz_type}: {status} {json.dumps(out)[:200]}")
    raise SystemExit(f"[superset-bootstrap] no candidate viz for {spec['slice_name']} "
                     f"executed successfully: {failures}")


def check_layouts() -> None:
    """Fail fast if a layout references a missing chart or a chart is not placed."""
    for key in DASHBOARDS:
        placed = [ref for row in LAYOUTS[key] if isinstance(row, list)
                  for kind, ref, _w, _h in row if kind == "chart"]
        declared = [s["slice_name"] for s in CHART_SPECS if s["dashboard"] == key]
        if sorted(placed) != sorted(declared):
            raise SystemExit(f"[superset-bootstrap] layout/spec mismatch in '{key}': "
                             f"{sorted(set(placed) ^ set(declared))}")
        for row in LAYOUTS[key]:
            if isinstance(row, list) and sum(item[2] for item in row) > 12:
                raise SystemExit(f"[superset-bootstrap] row wider than 12 columns in '{key}': {row}")


def build_layout(title: str, rows: list, chart_ids: dict[str, int]) -> dict:
    """Explicit single-page layout: header, section headers, rows of charts/markdown."""
    layout: dict = {
        "DASHBOARD_VERSION_KEY": "v2",
        "ROOT_ID": {"type": "ROOT", "id": "ROOT_ID", "children": ["GRID_ID"]},
        "GRID_ID": {"type": "GRID", "id": "GRID_ID", "children": [], "parents": ["ROOT_ID"]},
        "HEADER_ID": {"id": "HEADER_ID", "type": "HEADER", "meta": {"text": title}},
    }
    grid = layout["GRID_ID"]["children"]
    for n, item in enumerate(rows):
        if isinstance(item, str):
            hid = f"HEADER-sec{n}"
            layout[hid] = {"type": "HEADER", "id": hid, "children": [],
                           "parents": ["ROOT_ID", "GRID_ID"],
                           "meta": {"text": item, "headerSize": "MEDIUM_HEADER",
                                    "background": "BACKGROUND_TRANSPARENT"}}
            grid.append(hid)
            continue
        rid = f"ROW-r{n}"
        layout[rid] = {"type": "ROW", "id": rid, "children": [],
                       "parents": ["ROOT_ID", "GRID_ID"],
                       "meta": {"background": "BACKGROUND_TRANSPARENT"}}
        grid.append(rid)
        for m, (kind, ref, width, height) in enumerate(item):
            parents = ["ROOT_ID", "GRID_ID", rid]
            if kind == "chart":
                cid = f"CHART-r{n}c{m}"
                meta = {"width": width, "height": height,
                        "chartId": chart_ids[ref], "sliceName": ref}
                ctype = "CHART"
            else:
                cid = f"MARKDOWN-r{n}c{m}"
                meta = {"width": width, "height": height, "code": MARKDOWN[ref]}
                ctype = "MARKDOWN"
            layout[cid] = {"type": ctype, "id": cid, "children": [], "parents": parents, "meta": meta}
            layout[rid]["children"].append(cid)
    return layout


def build_filters(key: str, dash_chart_ids: list[int], chart_dataset: dict[int, int],
                  dataset_cols: dict[int, list[str]]) -> list[dict]:
    """Native filters scoped only to charts whose dataset really has the column."""
    filters = []
    for spec in FILTER_DEFS[key]:
        col = spec["column"]
        scoped = [c for c in dash_chart_ids if col in dataset_cols.get(chart_dataset[c], [])]
        if not scoped:
            print(f"[superset-bootstrap] filter '{spec['name']}' skipped: no chart has column '{col}'")
            continue
        default = spec.get("default")
        mask = {"extraFormData": {}, "filterState": {}, "ownState": {}}
        if default:
            mask = {"extraFormData": {"filters": [{"col": col, "op": "IN", "val": default}]},
                    "filterState": {"value": default}, "ownState": {}}
        target_datasets = list(dict.fromkeys(chart_dataset[c] for c in scoped))
        targets = [{"datasetId": ds_id, "column": {"name": col}} for ds_id in target_datasets]

        filters.append({
            "id": f"NATIVE_FILTER-w2-{key}-{spec['column']}",
            "type": "NATIVE_FILTER",
            "name": spec["name"],
            "description": spec.get("description", ""),
            "filterType": "filter_select",
            "targets": targets,
            "controlValues": {
                "multiSelect": spec.get("multi", True),
                "enableEmptyFilter": bool(spec.get("required", False)),
                "defaultToFirstItem": False,
                "inverseSelection": False,
                "searchAllOptions": False,
            },
            "defaultDataMask": mask,
            "cascadeParentIds": [],
            "scope": {"rootPath": ["ROOT_ID"],
                      "excluded": [c for c in dash_chart_ids if c not in scoped]},
            "chartsInScope": scoped,
            "tabsInScope": [],
        })
    return filters


def apply_dashboard(client: SupersetClient, dash_id: int, info: dict, layout: dict,
                    metadata: dict) -> None:
    base = {"dashboard_title": info["title"], "published": True,
            "position_json": json.dumps(layout), "json_metadata": json.dumps(metadata),
            "css": info.get("css", "")}
    slim = json.dumps({k: v for k, v in metadata.items() if k not in OPTIONAL_META_KEYS})
    attempts = [
        dict(base, slug=info["slug"]),
        dict(base, slug=info["slug"], json_metadata=slim),  # older schema: drop optional keys
        dict(base, json_metadata=slim),                      # slug already taken elsewhere
    ]
    last = None
    for payload in attempts:
        status, out = client.call("PUT", f"/api/v1/dashboard/{dash_id}", payload)
        if status == 200:
            return
        last = (status, json.dumps(out)[:300])
    raise SystemExit(f"[superset-bootstrap] dashboard '{info['title']}' update failed: {last}")


def main(argv: list[str] | None = None) -> int:
    check_layouts()
    client = SupersetClient(BASE_URL)
    client.login()
    print(f"[superset-bootstrap] logged in to {BASE_URL} as {ADMIN_USER}")

    database_id = ensure_database(client)
    all_queries = {**load_kpi_queries(), "etl_batch_log": ETL_BATCH_LOG_SQL, **INLINE_QUERIES}

    used_datasets: dict[str, int] = {}
    dataset_cols: dict[int, list[str]] = {}
    for table_name, sql in all_queries.items():
        if table_name in DATASET_SPECS:
            dataset_id, columns = ensure_dataset(
                client, database_id, table_name, sql, DATASET_SPECS[table_name],
                aliases=ALIAS_COLUMNS.get(table_name),
            )
            used_datasets[table_name] = dataset_id
            dataset_cols[dataset_id] = columns

    dashboard_ids: dict[str, int] = {}
    existing_dashboards_by_slug = client.list("/api/v1/dashboard/", "slug")
    for key, info in DASHBOARDS.items():
        existing = existing_dashboards_by_slug.get(info["slug"])
        if existing:
            status, out = client.call("PUT", f"/api/v1/dashboard/{existing['id']}", {
                "dashboard_title": info["title"], "slug": info["slug"], "published": True
            })
            dashboard_ids[key] = existing["id"]
            print(f"[superset-bootstrap] updated dashboard: {info['title']} (id={existing['id']})")
        else:
            record = client.ensure(
                "/api/v1/dashboard/", "dashboard_title", info["title"],
                {"dashboard_title": info["title"], "slug": info["slug"], "published": True, "json_metadata": "{}"},
                update_payload={"dashboard_title": info["title"], "slug": info["slug"], "published": True},
            )
            dashboard_ids[key] = record["id"]

    # Limpiar charts obsoletos con prefijos anteriores [Workshop Header] o [Workshop]
    existing_charts = client.list("/api/v1/chart/", "slice_name")
    for name, item in existing_charts.items():
        if name.startswith("[Workshop Header]") or name.startswith("[Workshop]"):
            client.call("DELETE", f"/api/v1/chart/{item['id']}")
            print(f"[superset-bootstrap] deleted obsolete chart: {name} (id={item['id']})")

    chart_ids: dict[str, dict[str, int]] = {key: {} for key in DASHBOARDS}
    chart_dataset: dict[int, int] = {}
    for spec in CHART_SPECS:
        key = spec["dashboard"]
        dataset_id = used_datasets[spec["dataset"]]
        chart_id = ensure_chart(client, spec, dataset_id, dashboard_ids[key])
        chart_ids[key][spec["slice_name"]] = chart_id
        chart_dataset[chart_id] = dataset_id

    for key, info in DASHBOARDS.items():
        dash_id = dashboard_ids[key]
        layout = build_layout(info["title"], LAYOUTS[key], chart_ids[key])
        filters = build_filters(key, list(chart_ids[key].values()), chart_dataset, dataset_cols)

        status, detail = client.call("GET", f"/api/v1/dashboard/{dash_id}")
        existing = {}
        if status == 200:
            existing = json.loads((detail.get("result") or {}).get("json_metadata") or "{}")
        existing.update({
            "label_colors": LABEL_COLORS,
            "color_scheme": "",
            "refresh_frequency": 0,
            "cross_filters_enabled": True,
            "filter_bar_orientation": "HORIZONTAL",
            "native_filter_configuration": filters,
        })
        apply_dashboard(client, dash_id, info, layout, existing)
        print(f"[superset-bootstrap] dashboard ready: {info['title']} "
              f"({len(chart_ids[key])} charts, {len(filters)} filters) "
              f"{BASE_URL}/superset/dashboard/{info['slug']}/")

    print(f"[superset-bootstrap] total datasets: {len(used_datasets)}, total charts: {len(CHART_SPECS)}, "
          "themes: managed by Superset (config/superset_config.py THEME_DEFAULT/THEME_DARK)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
