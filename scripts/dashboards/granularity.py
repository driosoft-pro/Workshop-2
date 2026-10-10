"""Workshop-2 - Granularity & Data Quality - Definición, layout, estilos y datasets inline."""

from __future__ import annotations

from .common import G, ALL_REQ, _spec, _big, _hbar, _line, _table

GRANULARITY_TITLE = "Workshop-2 - Granularity & Data Quality"
GRANULARITY_SLUG = "w2-granularity"

GRANULARITY_CSS = """
/* ====================================================================
   GRANULARIDAD & CALIDAD DE DATOS - ESTILOS PREMIUM
   ==================================================================== */

/* --- Banner intro compacto --- */
#MARKDOWN-r0c0 {
    margin-bottom: 2px !important;
}
#MARKDOWN-r0c0 .dashboard-markdown {
    padding: 6px 12px !important;
    background: #f8fafc !important;
    border: 1px solid #e2e8f0 !important;
    border-left: 4px solid #0EA5E9 !important;
    border-radius: 6px !important;
}
#MARKDOWN-r0c0 p {
    margin: 0 !important;
    font-size: 13.5px !important;
    line-height: 1.4 !important;
    color: #334155 !important;
}
#MARKDOWN-r0c0 a {
    color: #0284C7 !important;
    font-weight: 600 !important;
    text-decoration: none !important;
}
#MARKDOWN-r0c0 a:hover {
    text-decoration: underline !important;
}

/* ====================================================================
   TARJETAS KPI / HEADERS (4 COLORES VIBRANTES)
   ==================================================================== */

#CHART-r1c0, #CHART-r1c1, #CHART-r1c2, #CHART-r1c3,
.dashboard-chart-id-41, .dashboard-chart-id-42, .dashboard-chart-id-43, .dashboard-chart-id-44 {
    border-radius: 10px !important;
    transition: transform 0.2s ease, box-shadow 0.2s ease !important;
}
#CHART-r1c0:hover, #CHART-r1c1:hover, #CHART-r1c2:hover, #CHART-r1c3:hover,
.dashboard-chart-id-41:hover, .dashboard-chart-id-42:hover, .dashboard-chart-id-43:hover, .dashboard-chart-id-44:hover {
    transform: translateY(-2px) !important;
}

#CHART-r1c0 .chart-slice, #CHART-r1c0 .dashboard-chart, #CHART-r1c0 .slice_container,
#CHART-r1c1 .chart-slice, #CHART-r1c1 .dashboard-chart, #CHART-r1c1 .slice_container,
#CHART-r1c2 .chart-slice, #CHART-r1c2 .dashboard-chart, #CHART-r1c2 .slice_container,
#CHART-r1c3 .chart-slice, #CHART-r1c3 .dashboard-chart, #CHART-r1c3 .slice_container {
    background: transparent !important;
}

/* --- TARJETA 1: Premios Cargados (Dorado Grammy) --- */
#CHART-r1c0, .dashboard-chart-id-41, div[data-test-chart-name="Premios Cargados"] {
    border-top: 4px solid #D4AF37 !important;
    border-left: 1px solid rgba(212, 175, 55, 0.25) !important;
    border-right: 1px solid rgba(212, 175, 55, 0.25) !important;
    border-bottom: 1px solid rgba(212, 175, 55, 0.25) !important;
    background: linear-gradient(180deg, rgba(212, 175, 55, 0.12) 0%, rgba(255, 255, 255, 0.98) 100%) !important;
    box-shadow: 0 4px 12px rgba(212, 175, 55, 0.15) !important;
}
#CHART-r1c0:hover, .dashboard-chart-id-41:hover {
    box-shadow: 0 6px 18px rgba(212, 175, 55, 0.25) !important;
}
#CHART-r1c0 .header-title, #CHART-r1c0 [data-test="slice-header-text"],
.dashboard-chart-id-41 [data-test="slice-header-text"] {
    color: #997A15 !important;
    font-weight: 700 !important;
    font-size: 14px !important;
}
#CHART-r1c0 .header-line, #CHART-r1c0 .header-line *,
.dashboard-chart-id-41 .header-line, .dashboard-chart-id-41 .header-line *,
#CHART-r1c0 .superset-legacy-chart-big-number .header-line {
    color: #C9A227 !important;
    font-weight: 800 !important;
}
#CHART-r1c0 .subheader-line, .dashboard-chart-id-41 .subheader-line {
    color: #64748B !important;
    font-weight: 600 !important;
    font-size: 12.5px !important;
    margin-top: 2px !important;
}

/* --- TARJETA 2: Cobertura Enriquecida % (Verde Spotify) --- */
#CHART-r1c1, .dashboard-chart-id-42, div[data-test-chart-name="Cobertura Enriquecida %"] {
    border-top: 4px solid #1DB954 !important;
    border-left: 1px solid rgba(30, 215, 96, 0.25) !important;
    border-right: 1px solid rgba(30, 215, 96, 0.25) !important;
    border-bottom: 1px solid rgba(30, 215, 96, 0.25) !important;
    background: linear-gradient(180deg, rgba(30, 215, 96, 0.12) 0%, rgba(255, 255, 255, 0.98) 100%) !important;
    box-shadow: 0 4px 12px rgba(30, 215, 96, 0.15) !important;
}
#CHART-r1c1:hover, .dashboard-chart-id-42:hover {
    box-shadow: 0 6px 18px rgba(30, 215, 96, 0.25) !important;
}
#CHART-r1c1 .header-title, #CHART-r1c1 [data-test="slice-header-text"],
.dashboard-chart-id-42 [data-test="slice-header-text"] {
    color: #15803D !important;
    font-weight: 700 !important;
    font-size: 14px !important;
}
#CHART-r1c1 .header-line, #CHART-r1c1 .header-line *,
.dashboard-chart-id-42 .header-line, .dashboard-chart-id-42 .header-line *,
#CHART-r1c1 .superset-legacy-chart-big-number .header-line {
    color: #1DB954 !important;
    font-weight: 800 !important;
}
#CHART-r1c1 .header-line::after, .dashboard-chart-id-42 .header-line::after {
    content: "%" !important;
    font-size: 0.65em !important;
    font-weight: 700 !important;
    margin-left: 2px !important;
    color: #1DB954 !important;
}
#CHART-r1c1 .subheader-line, .dashboard-chart-id-42 .subheader-line {
    color: #64748B !important;
    font-weight: 600 !important;
    font-size: 12.5px !important;
    margin-top: 2px !important;
}

/* --- TARJETA 3: Cobertura Estricta (Línea Base) (Púrpura Amatista) --- */
#CHART-r1c2, .dashboard-chart-id-43, div[data-test-chart-name="Cobertura Estricta (Línea Base)"] {
    border-top: 4px solid #8B5CF6 !important;
    border-left: 1px solid rgba(139, 92, 246, 0.25) !important;
    border-right: 1px solid rgba(139, 92, 246, 0.25) !important;
    border-bottom: 1px solid rgba(139, 92, 246, 0.25) !important;
    background: linear-gradient(180deg, rgba(139, 92, 246, 0.12) 0%, rgba(255, 255, 255, 0.98) 100%) !important;
    box-shadow: 0 4px 12px rgba(139, 92, 246, 0.15) !important;
}
#CHART-r1c2:hover, .dashboard-chart-id-43:hover {
    box-shadow: 0 6px 18px rgba(139, 92, 246, 0.25) !important;
}
#CHART-r1c2 .header-title, #CHART-r1c2 [data-test="slice-header-text"],
.dashboard-chart-id-43 [data-test="slice-header-text"] {
    color: #6D28D9 !important;
    font-weight: 700 !important;
    font-size: 14px !important;
}
#CHART-r1c2 .header-line, #CHART-r1c2 .header-line *,
.dashboard-chart-id-43 .header-line, .dashboard-chart-id-43 .header-line *,
#CHART-r1c2 .superset-legacy-chart-big-number .header-line {
    color: #7C3AED !important;
    font-weight: 800 !important;
}
#CHART-r1c2 .header-line::after, .dashboard-chart-id-43 .header-line::after {
    content: "%" !important;
    font-size: 0.65em !important;
    font-weight: 700 !important;
    margin-left: 2px !important;
    color: #7C3AED !important;
}
#CHART-r1c2 .subheader-line, .dashboard-chart-id-43 .subheader-line {
    color: #64748B !important;
    font-weight: 600 !important;
    font-size: 12.5px !important;
    margin-top: 2px !important;
}

/* --- TARJETA 4: Artistas Grammy Vinculados (Azul Océano) --- */
#CHART-r1c3, .dashboard-chart-id-44, div[data-test-chart-name="Artistas Grammy Vinculados"] {
    border-top: 4px solid #0EA5E9 !important;
    border-left: 1px solid rgba(14, 165, 233, 0.25) !important;
    border-right: 1px solid rgba(14, 165, 233, 0.25) !important;
    border-bottom: 1px solid rgba(14, 165, 233, 0.25) !important;
    background: linear-gradient(180deg, rgba(14, 165, 233, 0.12) 0%, rgba(255, 255, 255, 0.98) 100%) !important;
    box-shadow: 0 4px 12px rgba(14, 165, 233, 0.15) !important;
}
#CHART-r1c3:hover, .dashboard-chart-id-44:hover {
    box-shadow: 0 6px 18px rgba(14, 165, 233, 0.25) !important;
}
#CHART-r1c3 .header-title, #CHART-r1c3 [data-test="slice-header-text"],
.dashboard-chart-id-44 [data-test="slice-header-text"] {
    color: #0369A1 !important;
    font-weight: 700 !important;
    font-size: 14px !important;
}
#CHART-r1c3 .header-line, #CHART-r1c3 .header-line *,
.dashboard-chart-id-44 .header-line, .dashboard-chart-id-44 .header-line *,
#CHART-r1c3 .superset-legacy-chart-big-number .header-line {
    color: #0284C7 !important;
    font-weight: 800 !important;
}
#CHART-r1c3 .subheader-line, .dashboard-chart-id-44 .subheader-line {
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

ETL_BATCH_LOG_SQL = (
    "SELECT batch_id, COALESCE(dag_id, 'manual') AS dag_id, "
    "COALESCE(run_id, batch_id) AS run_id, status, "
    "COALESCE((target_rows_after->>'fact_track_artist')::bigint, 0) AS rows_fact_track_artist, "
    "COALESCE((target_rows_after->>'fact_grammy_award')::bigint, 0) AS rows_fact_grammy_award, "
    "COALESCE((target_rows_after->>'bridge_award_artist')::bigint, 0) AS rows_bridge_award_artist "
    "FROM etl_batch_log ORDER BY started_at DESC LIMIT 5"
)

GRANULARITY_INLINE_QUERIES: dict[str, str] = {
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
}

GRANULARITY_DATASET_SPECS: dict[str, dict[str, str]] = {
    "gran_table_grain": {"row_count": "SUM(row_count)"},
    "gran_award_funnel": {"row_count": "SUM(row_count)"},
    "gran_track_funnel": {"row_count": "SUM(row_count)"},
    "gran_grammy_artists": {"grammy_artists": "MAX(grammy_artists)"},
}

GRANULARITY_CHARTS: list[dict] = [
    _spec(G, "etl_batch_log", "Premios Cargados", "R4",
          "Total de filas de premios Grammy cargadas en el último lote del Data Warehouse.",
          _big("rows_fact_grammy_award", "Total Premios Grammy en DW", ",d",
               color={"r": 201, "g": 162, "b": 39, "a": 1}, subheader_font_size=0.34)),
    _spec(G, "kpi_0_integration_coverage", "Cobertura Enriquecida %", "R1,R2,R3",
          "Tasa de emparejamiento enriquecido mediante cascada completa a Spotify.",
          _big("matched_enriched_pct", "Premios Vinculados (% Cascada)", ".1f",
               color={"r": 30, "g": 215, "b": 96, "a": 1}, subheader_font_size=0.34)),
    _spec(G, "kpi_0_integration_coverage", "Cobertura Estricta (Línea Base)", "R1,R2,R3",
          "Tasa de coincidencia directa exacta sin separación de créditos ni cascada.",
          _big("matched_strict_pct", "Cruce Directo 1:1 (% Línea Base)", ".1f",
               color={"r": 142, "g": 68, "b": 173, "a": 1}, subheader_font_size=0.34)),
    _spec(G, "gran_grammy_artists", "Artistas Grammy Vinculados", "R3",
          "Artistas reconocidos por el Grammy identificados en el catálogo de Spotify.",
          _big("grammy_artists", "Artistas Galardonados Únicos", ",d",
               color={"r": 41, "g": 128, "b": 185, "a": 1}, subheader_font_size=0.34)),

    _spec(G, "gran_table_grain", "Granularidad · Filas y grano por tabla", ALL_REQ,
          "Una fila por tabla del almacén de datos: capa, grano y volumen actual.",
          [_table(["sort_order", "layer", "table_name", "grain", "row_count"], 10,
                  order=[["sort_order", True]])]),
    _spec(G, "gran_award_funnel", "Granularidad · De créditos a puente", ALL_REQ,
          "Premios -> premios resueltos -> filas puente (premio x artista) -> artistas distintos.",
          _hbar("stage", "row_count", 10, ",d") + [_table(["step", "stage", "row_count"], 10,
                                                          order=[["step", True]])]),
    _spec(G, "gran_track_funnel", "Granularidad · De listados a artistas", ALL_REQ,
          "Listados de pistas que se repiten por género y colaboraciones vs pistas principales.",
          _hbar("stage", "row_count", 10, ",d") + [_table(["step", "stage", "row_count"], 10,
                                                          order=[["step", True]])]),

    _spec(G, "kpi_0_coverage_by_method", "Calidad · Método de emparejamiento", "R1,R2,R3",
          "Distribución de la cascada jerárquica: exact -> split -> workers -> nominee -> fuzzy -> none.",
          [("pie", {"groupby": ["match_method"], "metric": "award_rows", "metrics": ["award_rows"],
                    "donut": True, "show_legend": True, "label_type": "key_percent", "row_limit": 10}),
           _table(["match_method", "award_rows", "share_pct"], 10)]),
    _spec(G, "kpi_0_coverage_by_tier", "Calidad · Premios por nivel de reconocimiento", "R1,R2,R3",
          "Premios Grammy por nivel de reconocimiento (Tier A, B, C, ninguno) y método de cruce.",
          [("echarts_timeseries_bar", {"x_axis": "recognition_tier", "groupby": ["match_method"],
                                       "metrics": ["award_rows"], "stack": True, "show_legend": True,
                                       "y_axis_format": ",d", "row_limit": 50}),
           ("dist_bar", {"groupby": ["recognition_tier"], "columns": ["match_method"],
                         "metrics": ["award_rows"], "bar_stacked": True, "row_limit": 50}),
           _table(["recognition_tier", "match_method", "award_rows", "share_pct"], 50)]),
    _spec(G, "kpi_0_coverage_by_decade", "Calidad · Cobertura por década", "R1,R2,R3",
          "Comparativa de coincidencia estricta vs enriquecida a lo largo de las décadas.",
          [_line("decade", ["match_rate_pct", "match_rate_strict_pct"], ".1f"),
           _table(["decade", "award_rows", "match_rate_pct", "match_rate_strict_pct"], 100)]),
    _spec(G, "etl_batch_log", "Calidad · Últimas cargas ETL", "R4",
          "Pista de auditoría de cargas por lote en el Data Warehouse desde etl_batch_log.",
          [_table(["batch_id", "dag_id", "run_id", "status", "rows_fact_track_artist",
                   "rows_fact_grammy_award", "rows_bridge_award_artist"], 5)]),
]

GRANULARITY_LAYOUT: list = [
    [("md", "gran_intro", 12, 4)],
    [("chart", "Premios Cargados", 3, 14),
     ("chart", "Cobertura Enriquecida %", 3, 14),
     ("chart", "Cobertura Estricta (Línea Base)", 3, 14),
     ("chart", "Artistas Grammy Vinculados", 3, 14)],
    "Granularidad del Data Warehouse: Modelado y Grano por Tabla",
    [("chart", "Granularidad · Filas y grano por tabla", 12, 34)],
    [("chart", "Granularidad · De créditos a puente", 4, 42),
     ("chart", "Granularidad · De listados a artistas", 4, 42),
     ("chart", "Calidad · Método de emparejamiento", 4, 42)],
    "Calidad y Confiabilidad del Enlace: Auditoría de Cascada y Lotes ETL",
    [("chart", "Calidad · Premios por nivel de reconocimiento", 6, 42),
     ("chart", "Calidad · Cobertura por década", 6, 42)],
    [("chart", "Calidad · Últimas cargas ETL", 12, 24)],
]

GRANULARITY_MARKDOWN: dict[str, str] = {
    "gran_intro": (
        "**Workshop · Granularidad & Calidad de Datos** &nbsp;|&nbsp; "
        "Auditoría del modelado dimensional y estrategia de integración Spotify × Grammy (Airflow → PostgreSQL `music_dw`) &nbsp;·&nbsp; "
        "[Ver Dashboard Principal (R1–R4) →](/superset/dashboard/workshop-dashboard/) &nbsp;·&nbsp; "
        "[Ver Detalle Analítico R1–R4 →](/superset/dashboard/w2-requirements/)"
    ),
}

GRANULARITY_FILTERS: list[dict] = [
    {"name": "Década", "column": "decade", "description": "Filtrar por década de ceremonia Grammy (1950s - 2010s)"},
    {"name": "Método de Emparejamiento", "column": "match_method", "description": "Método de resolución (exact, split, workers, nominee, fuzzy)"},
    {"name": "Nivel de Reconocimiento", "column": "recognition_tier", "description": "Nivel de acreditación (Tier A: directo, Tier B: colaborador, Tier C: técnico)"},
]
