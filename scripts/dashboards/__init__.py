"""Módulo centralizador de dashboards de Superset.

Agrupa y reexporta todas las definiciones de gráficos, layouts, filtros,
consultas y hojas de estilo de:
  - Workshop Dashboard (Dashboard Spotify & Grammy R1–R4)
  - Granularity & Data Quality (Granularity & Data Quality - Spotify & Grammy)
  - Requirements & KPIs (KPIs Spotify & Grammy R1-R4)
"""

from __future__ import annotations

from .common import (
    ALL_REQ,
    G,
    LABEL_COLORS,
    OPTIONAL_META_KEYS,
    R,
    W,
    _big,
    _hbar,
    _line,
    _simple_filter,
    _spec,
    _table,
    load_kpi_queries,
)
from .granularity import (
    ETL_BATCH_LOG_SQL,
    GRANULARITY_CHARTS,
    GRANULARITY_CSS,
    GRANULARITY_DATASET_SPECS,
    GRANULARITY_FILTERS,
    GRANULARITY_INLINE_QUERIES,
    GRANULARITY_LAYOUT,
    GRANULARITY_MARKDOWN,
    GRANULARITY_SLUG,
    GRANULARITY_TITLE,
)
from .requirements import (
    ALIAS_COLUMNS,
    DASHBOARD_TITLE,
    REQUIREMENTS_CHARTS,
    REQUIREMENTS_CSS,
    REQUIREMENTS_FILTERS,
    REQUIREMENTS_LAYOUT,
    REQUIREMENTS_MARKDOWN,
    REQUIREMENTS_SLUG,
    REQUIREMENTS_TITLE,
)
from .workshop import (
    WORKSHOP_CHARTS,
    WORKSHOP_CSS,
    WORKSHOP_DATASET_SPECS,
    WORKSHOP_FILTERS,
    WORKSHOP_INLINE_QUERIES,
    WORKSHOP_LAYOUT,
    WORKSHOP_MARKDOWN,
    WORKSHOP_SLUG,
    WORKSHOP_TITLE,
)

# Diccionario central de dashboards registrados en Superset
DASHBOARDS: dict[str, dict[str, str]] = {
    "granularity": {
        "title": GRANULARITY_TITLE,
        "slug": GRANULARITY_SLUG,
        "css": GRANULARITY_CSS,
    },
    "requirements": {
        "title": REQUIREMENTS_TITLE,
        "slug": REQUIREMENTS_SLUG,
        "css": REQUIREMENTS_CSS,
    },
    "workshop": {
        "title": WORKSHOP_TITLE,
        "slug": WORKSHOP_SLUG,
        "css": WORKSHOP_CSS,
    },
}

# Especificaciones de agregaciones SQL por dataset
BASE_DATASET_SPECS: dict[str, dict[str, str]] = {
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

DATASET_SPECS: dict[str, dict[str, str]] = {
    **BASE_DATASET_SPECS,
    **GRANULARITY_DATASET_SPECS,
    **WORKSHOP_DATASET_SPECS,
}

# Consultas inline (tablas que no provienen de sql/kpi_queries.sql)
INLINE_QUERIES: dict[str, str] = {
    **GRANULARITY_INLINE_QUERIES,
    **WORKSHOP_INLINE_QUERIES,
}

# Consolidación total de gráficos (en el orden: Granularidad, KPIs R1-R4, Workshop)
CHART_SPECS: list[dict] = [
    *GRANULARITY_CHARTS,
    *REQUIREMENTS_CHARTS,
    *WORKSHOP_CHARTS,
]

# Estructura de filas y columnas para cada dashboard
LAYOUTS: dict[str, list] = {
    "granularity": GRANULARITY_LAYOUT,
    "requirements": REQUIREMENTS_LAYOUT,
    "workshop": WORKSHOP_LAYOUT,
}

# Bloques markdown informativos y de navegación
MARKDOWN: dict[str, str] = {
    **GRANULARITY_MARKDOWN,
    **REQUIREMENTS_MARKDOWN,
    **WORKSHOP_MARKDOWN,
}

# Definición de filtros interactivos nativos
FILTER_DEFS: dict[str, list[dict]] = {
    "granularity": GRANULARITY_FILTERS,
    "requirements": REQUIREMENTS_FILTERS,
    "workshop": WORKSHOP_FILTERS,
}

__all__ = [
    "ALL_REQ",
    "G",
    "LABEL_COLORS",
    "OPTIONAL_META_KEYS",
    "R",
    "W",
    "_big",
    "_hbar",
    "_line",
    "_simple_filter",
    "_spec",
    "_table",
    "load_kpi_queries",
    "GRANULARITY_TITLE",
    "GRANULARITY_SLUG",
    "GRANULARITY_CSS",
    "GRANULARITY_CHARTS",
    "GRANULARITY_LAYOUT",
    "GRANULARITY_MARKDOWN",
    "GRANULARITY_FILTERS",
    "GRANULARITY_INLINE_QUERIES",
    "GRANULARITY_DATASET_SPECS",
    "ETL_BATCH_LOG_SQL",
    "REQUIREMENTS_TITLE",
    "DASHBOARD_TITLE",
    "REQUIREMENTS_SLUG",
    "REQUIREMENTS_CSS",
    "REQUIREMENTS_CHARTS",
    "REQUIREMENTS_LAYOUT",
    "REQUIREMENTS_MARKDOWN",
    "REQUIREMENTS_FILTERS",
    "ALIAS_COLUMNS",
    "WORKSHOP_TITLE",
    "WORKSHOP_SLUG",
    "WORKSHOP_CSS",
    "WORKSHOP_CHARTS",
    "WORKSHOP_LAYOUT",
    "WORKSHOP_MARKDOWN",
    "WORKSHOP_FILTERS",
    "WORKSHOP_INLINE_QUERIES",
    "WORKSHOP_DATASET_SPECS",
    "DASHBOARDS",
    "BASE_DATASET_SPECS",
    "DATASET_SPECS",
    "INLINE_QUERIES",
    "CHART_SPECS",
    "LAYOUTS",
    "MARKDOWN",
    "FILTER_DEFS",
]
