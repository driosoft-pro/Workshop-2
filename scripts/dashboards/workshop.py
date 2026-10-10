"""Dashboard Spotify & Grammy (R1–R4) - Definición ejecutiva, layout y estilos."""

from __future__ import annotations

from .common import W, ALL_REQ, _spec, _big, _hbar, _table

WORKSHOP_TITLE = "Dashboard Spotify & Grammy (R1–R4)"
WORKSHOP_SLUG = "workshop-dashboard"

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
    background: rgba(128, 128, 128, 0.08) !important;
    border: 1px solid rgba(128, 128, 128, 0.30) !important;
    border-left: 4px solid #1DB954 !important;
    border-radius: 6px !important;
}
#MARKDOWN-r0c0 p {
    margin: 0 !important;
    font-size: 13.5px !important;
    line-height: 1.4 !important;
    color: inherit !important;
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

#CHART-r1c0, #CHART-r1c1, #CHART-r1c2, #CHART-r1c3,
.dashboard-chart-id-34, .dashboard-chart-id-35, .dashboard-chart-id-36, .dashboard-chart-id-37 {
    border-radius: 10px !important;
    transition: transform 0.2s ease, box-shadow 0.2s ease !important;
}
#CHART-r1c0:hover, #CHART-r1c1:hover, #CHART-r1c2:hover, #CHART-r1c3:hover,
.dashboard-chart-id-34:hover, .dashboard-chart-id-35:hover, .dashboard-chart-id-36:hover, .dashboard-chart-id-37:hover {
    transform: translateY(-2px) !important;
}

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
    background: linear-gradient(180deg, rgba(212, 175, 55, 0.12) 0%, transparent 100%) !important;
    box-shadow: 0 4px 12px rgba(212, 175, 55, 0.15) !important;
}
#CHART-r1c0:hover, .dashboard-chart-id-34:hover {
    box-shadow: 0 6px 18px rgba(212, 175, 55, 0.25) !important;
}
#CHART-r1c0 .header-title, #CHART-r1c0 [data-test="slice-header-text"],
.dashboard-chart-id-34 [data-test="slice-header-text"] {
    color: inherit !important;
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
    color: inherit !important;
    opacity: 0.72 !important;
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
    background: linear-gradient(180deg, rgba(30, 215, 96, 0.12) 0%, transparent 100%) !important;
    box-shadow: 0 4px 12px rgba(30, 215, 96, 0.15) !important;
}
#CHART-r1c1:hover, .dashboard-chart-id-35:hover {
    box-shadow: 0 6px 18px rgba(30, 215, 96, 0.25) !important;
}
#CHART-r1c1 .header-title, #CHART-r1c1 [data-test="slice-header-text"],
.dashboard-chart-id-35 [data-test="slice-header-text"] {
    color: inherit !important;
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
    color: inherit !important;
    opacity: 0.72 !important;
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
    background: linear-gradient(180deg, rgba(14, 165, 233, 0.12) 0%, transparent 100%) !important;
    box-shadow: 0 4px 12px rgba(14, 165, 233, 0.15) !important;
}
#CHART-r1c2:hover, .dashboard-chart-id-36:hover {
    box-shadow: 0 6px 18px rgba(14, 165, 233, 0.25) !important;
}
#CHART-r1c2 .header-title, #CHART-r1c2 [data-test="slice-header-text"],
.dashboard-chart-id-36 [data-test="slice-header-text"] {
    color: inherit !important;
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
    color: inherit !important;
    opacity: 0.72 !important;
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
    background: linear-gradient(180deg, rgba(139, 92, 246, 0.12) 0%, transparent 100%) !important;
    box-shadow: 0 4px 12px rgba(139, 92, 246, 0.15) !important;
}
#CHART-r1c3:hover, .dashboard-chart-id-37:hover {
    box-shadow: 0 6px 18px rgba(139, 92, 246, 0.25) !important;
}
#CHART-r1c3 .header-title, #CHART-r1c3 [data-test="slice-header-text"],
.dashboard-chart-id-37 [data-test="slice-header-text"] {
    color: inherit !important;
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
    color: inherit !important;
    opacity: 0.72 !important;
    font-weight: 600 !important;
    font-size: 12.5px !important;
    margin-top: 2px !important;
}

/* --- Títulos de secciones intermedias --- */
.dashboard-component-header h2 {
    font-weight: 600 !important;
    color: inherit !important;
    border-bottom: 2px solid rgba(128, 128, 128, 0.30) !important;
    padding-bottom: 6px !important;
}

/* ====================================================================
   FIX KPI: una sola tarjeta (se limpia toda caja anidada) y número
   completo. Colores neutros/transparentes -> compatible dark y light.
   ==================================================================== */
#CHART-r1c0 .dashboard-chart-id-34,
#CHART-r1c0:hover .dashboard-chart-id-34,
#CHART-r1c0 div[data-test-chart-name="Premios Evaluados"],
#CHART-r1c0:hover div[data-test-chart-name="Premios Evaluados"],
.dashboard-chart-id-34 #CHART-r1c0,
.dashboard-chart-id-34:hover #CHART-r1c0,
.dashboard-chart-id-34 div[data-test-chart-name="Premios Evaluados"],
.dashboard-chart-id-34:hover div[data-test-chart-name="Premios Evaluados"],
div[data-test-chart-name="Premios Evaluados"] #CHART-r1c0,
div[data-test-chart-name="Premios Evaluados"]:hover #CHART-r1c0,
div[data-test-chart-name="Premios Evaluados"] .dashboard-chart-id-34,
div[data-test-chart-name="Premios Evaluados"]:hover .dashboard-chart-id-34,
#CHART-r1c1 .dashboard-chart-id-35,
#CHART-r1c1:hover .dashboard-chart-id-35,
#CHART-r1c1 div[data-test-chart-name="Cobertura Integración %"],
#CHART-r1c1:hover div[data-test-chart-name="Cobertura Integración %"],
.dashboard-chart-id-35 #CHART-r1c1,
.dashboard-chart-id-35:hover #CHART-r1c1,
.dashboard-chart-id-35 div[data-test-chart-name="Cobertura Integración %"],
.dashboard-chart-id-35:hover div[data-test-chart-name="Cobertura Integración %"],
div[data-test-chart-name="Cobertura Integración %"] #CHART-r1c1,
div[data-test-chart-name="Cobertura Integración %"]:hover #CHART-r1c1,
div[data-test-chart-name="Cobertura Integración %"] .dashboard-chart-id-35,
div[data-test-chart-name="Cobertura Integración %"]:hover .dashboard-chart-id-35,
#CHART-r1c2 .dashboard-chart-id-36,
#CHART-r1c2:hover .dashboard-chart-id-36,
#CHART-r1c2 div[data-test-chart-name="Artistas Grammy en Spotify"],
#CHART-r1c2:hover div[data-test-chart-name="Artistas Grammy en Spotify"],
.dashboard-chart-id-36 #CHART-r1c2,
.dashboard-chart-id-36:hover #CHART-r1c2,
.dashboard-chart-id-36 div[data-test-chart-name="Artistas Grammy en Spotify"],
.dashboard-chart-id-36:hover div[data-test-chart-name="Artistas Grammy en Spotify"],
div[data-test-chart-name="Artistas Grammy en Spotify"] #CHART-r1c2,
div[data-test-chart-name="Artistas Grammy en Spotify"]:hover #CHART-r1c2,
div[data-test-chart-name="Artistas Grammy en Spotify"] .dashboard-chart-id-36,
div[data-test-chart-name="Artistas Grammy en Spotify"]:hover .dashboard-chart-id-36,
#CHART-r1c3 .dashboard-chart-id-37,
#CHART-r1c3:hover .dashboard-chart-id-37,
#CHART-r1c3 div[data-test-chart-name="Cobertura Estricta %"],
#CHART-r1c3:hover div[data-test-chart-name="Cobertura Estricta %"],
.dashboard-chart-id-37 #CHART-r1c3,
.dashboard-chart-id-37:hover #CHART-r1c3,
.dashboard-chart-id-37 div[data-test-chart-name="Cobertura Estricta %"],
.dashboard-chart-id-37:hover div[data-test-chart-name="Cobertura Estricta %"],
div[data-test-chart-name="Cobertura Estricta %"] #CHART-r1c3,
div[data-test-chart-name="Cobertura Estricta %"]:hover #CHART-r1c3,
div[data-test-chart-name="Cobertura Estricta %"] .dashboard-chart-id-37,
div[data-test-chart-name="Cobertura Estricta %"]:hover .dashboard-chart-id-37 {
    border: none !important;
    background: transparent !important;
    box-shadow: none !important;
    border-radius: 0 !important;
    transform: none !important;
}
#CHART-r1c0 .header-line,
.dashboard-chart-id-34 .header-line,
#CHART-r1c1 .header-line,
.dashboard-chart-id-35 .header-line,
#CHART-r1c2 .header-line,
.dashboard-chart-id-36 .header-line,
#CHART-r1c3 .header-line,
.dashboard-chart-id-37 .header-line {
    line-height: 1.1 !important;
    overflow: visible !important;
    white-space: nowrap !important;
}
"""

WORKSHOP_CHARTS: list[dict] = [
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

WORKSHOP_LAYOUT: list = [
    [("md", "workshop_intro", 12, 4)],
    [("chart", "Premios Evaluados", 3, 17),
     ("chart", "Cobertura Integración %", 3, 17),
     ("chart", "Artistas Grammy en Spotify", 3, 17),
     ("chart", "Cobertura Estricta %", 3, 17)],
    "R1 & R2: Desempeño Musical y Géneros | R3: Evolución Histórica",
    [("chart", "Diferencia de Popularidad por Género (R1/R2)", 6, 46),
     ("chart", "Evolución de Premios por Categoría y Década (R3)", 6, 46)],
    "R4: Ranking de Artistas Más Galardonados Presentes en Spotify",
    [("chart", "Top Artistas Premiados en Spotify (R4)", 12, 36)],
]

WORKSHOP_MARKDOWN: dict[str, str] = {
    "workshop_intro": (
        "**Dashboard Spotify & Grammy (R1–R4)** &nbsp;|&nbsp; "
        "Pipeline batch analítico Spotify × Premios Grammy (PostgreSQL `music_dw` → Superset) &nbsp;·&nbsp; "
        "[Ver Detalle Analítico Completo (KPIs R1–R4) →](/superset/dashboard/w2-requirements/)"
    ),
}

WORKSHOP_FILTERS: list[dict] = [
    {"name": "Década", "column": "decade", "description": "Filtrar por década del premio Grammy (1950s - 2010s)"},
    {"name": "Categoría Grammy", "column": "category_family", "description": "Familia de categoría Grammy (Pop, Rock, Classical, General Field...)"},
    {"name": "Género Musical", "column": "genre_family", "description": "Familia de género musical en Spotify (Pop, Rock, Hip-Hop, Electronic...)"},
    {"name": "Método de Emparejamiento", "column": "match_method", "description": "Método de cruce entre Grammy y Spotify (exact, split, workers...)"},
]

WORKSHOP_INLINE_QUERIES: dict[str, str] = {
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

WORKSHOP_DATASET_SPECS: dict[str, dict[str, str]] = {
    "workshop_awards_breakdown": {"awards": "SUM(awards)"},
}