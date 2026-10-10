"""Workshop-2 - KPIs (R1-R4) - Definición, layout, guías metodológicas y filtros interactivos."""

from __future__ import annotations

from .common import R, _spec, _big, _hbar, _line, _table, _simple_filter

REQUIREMENTS_TITLE = "KPIs Spotify & Grammy (R1-R4)"
DASHBOARD_TITLE = REQUIREMENTS_TITLE  # Compatibilidad histórica
REQUIREMENTS_SLUG = "w2-requirements"

REQUIREMENTS_CSS = """
/* ====================================================================
   DETALLE ANALÍTICO DE REQUERIMIENTOS (R1-R4) - ESTILOS PREMIUM
   ==================================================================== */

/* --- Banner intro compacto --- */
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

/* --- Tarjeta de Contexto (Cobertura Enriquecida) --- */
#CHART-r0c1, .dashboard-chart-id-52, div[data-test-chart-name="Contexto · Cobertura Enriquecida %"] {
    border-top: 4px solid #1DB954 !important;
    border-left: 1px solid rgba(30, 215, 96, 0.25) !important;
    border-right: 1px solid rgba(30, 215, 96, 0.25) !important;
    border-bottom: 1px solid rgba(30, 215, 96, 0.25) !important;
    background: linear-gradient(180deg, rgba(30, 215, 96, 0.12) 0%, transparent 100%) !important;
    box-shadow: 0 4px 12px rgba(30, 215, 96, 0.15) !important;
    border-radius: 10px !important;
}
#CHART-r0c1 .chart-slice, #CHART-r0c1 .dashboard-chart, #CHART-r0c1 .slice_container {
    background: transparent !important;
}
#CHART-r0c1 .header-title, #CHART-r0c1 [data-test="slice-header-text"],
.dashboard-chart-id-52 [data-test="slice-header-text"] {
    color: inherit !important;
    font-weight: 700 !important;
    font-size: 13.5px !important;
}
#CHART-r0c1 .header-line, #CHART-r0c1 .header-line *,
.dashboard-chart-id-52 .header-line, .dashboard-chart-id-52 .header-line *,
#CHART-r0c1 .superset-legacy-chart-big-number .header-line {
    color: #1DB954 !important;
    font-weight: 800 !important;
}
#CHART-r0c1 .header-line::after, .dashboard-chart-id-52 .header-line::after {
    content: "%" !important;
    font-size: 0.65em !important;
    font-weight: 700 !important;
    margin-left: 2px !important;
    color: #1DB954 !important;
}
#CHART-r0c1 .subheader-line, .dashboard-chart-id-52 .subheader-line {
    color: inherit !important;
    opacity: 0.72 !important;
    font-weight: 600 !important;
    font-size: 12px !important;
    margin-top: 2px !important;
}

/* --- Títulos de secciones R1-R4 --- */
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
#CHART-r0c1 .dashboard-chart-id-52,
#CHART-r0c1:hover .dashboard-chart-id-52,
#CHART-r0c1 div[data-test-chart-name="Contexto · Cobertura Enriquecida %"],
#CHART-r0c1:hover div[data-test-chart-name="Contexto · Cobertura Enriquecida %"],
.dashboard-chart-id-52 #CHART-r0c1,
.dashboard-chart-id-52:hover #CHART-r0c1,
.dashboard-chart-id-52 div[data-test-chart-name="Contexto · Cobertura Enriquecida %"],
.dashboard-chart-id-52:hover div[data-test-chart-name="Contexto · Cobertura Enriquecida %"],
div[data-test-chart-name="Contexto · Cobertura Enriquecida %"] #CHART-r0c1,
div[data-test-chart-name="Contexto · Cobertura Enriquecida %"]:hover #CHART-r0c1,
div[data-test-chart-name="Contexto · Cobertura Enriquecida %"] .dashboard-chart-id-52,
div[data-test-chart-name="Contexto · Cobertura Enriquecida %"]:hover .dashboard-chart-id-52 {
    border: none !important;
    background: transparent !important;
    box-shadow: none !important;
    border-radius: 0 !important;
    transform: none !important;
}
#CHART-r0c1 .header-line,
.dashboard-chart-id-52 .header-line {
    line-height: 1.1 !important;
    overflow: visible !important;
    white-space: nowrap !important;
}
"""

# Virtual datasets whose column names differ across KPIs get an extra alias column so a
# single native filter (e.g. genre_family) drives R1 and R2 charts alike.
ALIAS_COLUMNS: dict[str, dict[str, str]] = {
    "kpi_2_awards_by_dominant_genre": {"genre_family": "dominant_genre_family"},
    "kpi_2_heatmap": {"genre_family": "dominant_genre_family"},
}

REQUIREMENTS_CHARTS: list[dict] = [
    _spec(R, "kpi_0_integration_coverage", "Contexto · Cobertura Enriquecida %", "R1,R2,R3,R4",
          "Porcentaje de premios vinculados exitosamente a Spotify (contexto analítico permanente).",
          _big("matched_enriched_pct", "Cobertura Integración (% Cascada)", ".1f",
               color={"r": 30, "g": 215, "b": 96, "a": 1}, subheader_font_size=0.34)),

    # --- R1 ---
    _spec(R, "kpi_1_artist_level", "R1 · Distribución de popularidad por artista", "R1",
          "Distribución de popularidad promedio por artista (Grammy vs No-Grammy).",
          [("box_plot", {"columns": ["artist_group"], "groupby": ["artist_display_name"],
                         "metrics": ["mean_popularity"], "whiskerOptions": "Tukey",
                         "row_limit": 500}),
           _table(["artist_group", "artist_display_name", "mean_popularity", "primary_tracks"], 100)]),
    _spec(R, "kpi_1_popularity_by_grammy_recognition", "R1 · Perfil de audio: Grammy vs No-Grammy", "R1",
          "Características sonoras promedio normalizadas en rango [0, 1] en canciones principales.",
          [("radar", {"groupby": ["artist_group"],
                      "metrics": ["mean_danceability", "mean_energy", "mean_valence",
                                  "mean_acousticness", "mean_speechiness"],
                      "show_legend": True, "row_limit": 10}),
           _table(["basis", "recognition", "artist_group", "mean_danceability", "mean_energy",
                   "mean_valence", "mean_acousticness", "mean_speechiness"], 20)]),
    _spec(R, "kpi_1_within_genre_diff", "R1 · Diferencia de popularidad por familia de género", "R1,R2",
          "Diferencia de popularidad (Grammy menos No-Grammy) por familia de género.",
          _hbar("genre_family", "diff", 20, ".1f", ascending=True)
          + [_table(["genre_family", "mean_pop_grammy", "mean_pop_non", "diff",
                     "n_grammy_artists", "stratified_weighted_diff"], 50)]),
    _spec(R, "kpi_1_popularity_by_grammy_recognition", "R1 · Resumen de popularidad por grupo", "R1",
          "Medianas, cuartiles y recuentos de popularidad por grupo y condición de catálogo.",
          [_table(["basis", "recognition", "artist_group", "n_tracks", "n_artists",
                   "mean_popularity", "median_popularity", "p25_popularity", "p75_popularity"], 20)]),

    # --- R2 ---
    _spec(R, "kpi_2_heatmap", "R2 · Mapa de calor: género vs categoría", "R2",
          "Premios por familia de género dominante del artista vs familia de categoría Grammy.",
          [("heatmap_v2", {"x_axis": "genre_family", "groupby": "category_family",
                           "metric": "awards", "normalize_across": "heatmap",
                           "legend_type": "continuous", "show_legend": True, "row_limit": 500}),
           ("heatmap", {"all_columns_x": "genre_family", "all_columns_y": "category_family",
                        "metric": "awards", "row_limit": 500}),
           _table(["dominant_genre_family", "category_family", "awards"], 200)]),
    _spec(R, "kpi_2_awards_by_dominant_genre", "R2 · Premios por 100 artistas según género dominante", "R2",
          "Tasa de premios por cada 100 artistas clasificados en la familia de género dominante.",
          _hbar("genre_family", "awards_per_100_artists", 15, ".1f")
          + [_table(["dominant_genre_family", "awards", "n_artists", "awards_per_100_artists"], 50)]),

    # --- R3 ---
    _spec(R, "kpi_3_awards_and_profile_by_decade", "R3 · Tendencia de energía por década", "R3",
          "Evolución histórica de la energía promedio de grabaciones premiadas por década.",
          [_line("decade", ["mean_energy"]), _table(["decade", "mean_energy"], 100)]),
    _spec(R, "kpi_3_awards_and_profile_by_decade", "R3 · Tendencia de valencia por década", "R3",
          "Evolución histórica de la valencia / positividad musical promedio por década.",
          [_line("decade", ["mean_valence"]), _table(["decade", "mean_valence"], 100)]),
    _spec(R, "kpi_3_awards_and_profile_by_decade", "R3 · Tendencia de bailabilidad por década", "R3",
          "Evolución histórica de bailabilidad en canciones principales por década.",
          [_line("decade", ["mean_danceability"]), _table(["decade", "mean_danceability"], 100)]),
    _spec(R, "kpi_3_awards_and_profile_by_decade", "R3 · Cobertura Spotify por década", "R3",
          "Porcentaje de premios con presencia identificada en Spotify por década.",
          [_line("decade", ["matched_share_pct"], ".1f"),
           _table(["decade", "awards", "matched_awards", "matched_share_pct"], 100)]),
    _spec(R, "kpi_3_awards_by_family_decade", "R3 · Premios por familia de categoría y década", "R3",
          "Distribución histórica de premios agrupados en familias canónicas por década.",
          [("echarts_timeseries_bar", {"x_axis": "decade", "groupby": ["category_family"],
                                       "metrics": ["awards"], "stack": True, "show_legend": True,
                                       "y_axis_format": ",d", "row_limit": 300}),
           ("dist_bar", {"groupby": ["decade"], "columns": ["category_family"],
                         "metrics": ["awards"], "bar_stacked": True, "row_limit": 300}),
           _table(["decade", "category_family", "awards"], 150)]),

    # --- R4 ---
    _spec(R, "kpi_4_top_awarded_artists_on_spotify", "R4 · Top 10 artistas premiados en Spotify", "R4",
          "Top 10 de artistas más premiados con presencia en el catálogo de Spotify.",
          _hbar("artist_display_name", "awards", 10, ",d")
          + [_table(["artist_display_name", "awards", "spotify_track_count",
                     "first_award_year", "last_award_year"], 20, order=[["awards", False]])]),
    _spec(R, "kpi_4_top_awarded_all", "R4 · Ranking global de artistas premiados", "R4",
          "Ranking general de galardonados incluyendo artistas ausentes de Spotify (Tier C).",
          [_table(["rank", "artist_display_name", "recognition_tier", "awards",
                   "spotify_track_count", "in_spotify"], 1500, order=[["rank", True]])]),
    _spec(R, "kpi_4_top_awarded_all", "R4 · Premiados ausentes de Spotify", "R4",
          "Galardonados en categorías técnicas o de producción no catalogados como intérpretes en R1.",
          [_table(["artist_display_name", "recognition_tier", "awards", "first_award_year", "last_award_year"], 250,
                  order=[["awards", False]],
                  filters=[_simple_filter("recognition_tier", "==", "C")])]),
]

REQUIREMENTS_LAYOUT: list = [
    [("md", "req_intro", 9, 17), ("chart", "Contexto · Cobertura Enriquecida %", 3, 17)],
    "R1 — ¿Los artistas reconocidos por el Grammy rinden distinto en Spotify?",
    [("chart", "R1 · Distribución de popularidad por artista", 4, 46),
     ("chart", "R1 · Perfil de audio: Grammy vs No-Grammy", 4, 46),
     ("chart", "R1 · Diferencia de popularidad por familia de género", 4, 46)],
    [("chart", "R1 · Resumen de popularidad por grupo", 8, 30), ("md", "r1_guide", 4, 30)],
    "R2 — ¿Qué géneros dominan entre los artistas premiados?",
    [("chart", "R2 · Mapa de calor: género vs categoría", 7, 56),
     ("chart", "R2 · Premios por 100 artistas según género dominante", 5, 56)],
    "R3 — ¿Cómo evoluciona el perfil de los artistas a lo largo de las décadas?",
    [("chart", "R3 · Tendencia de energía por década", 3, 36),
     ("chart", "R3 · Tendencia de valencia por década", 3, 36),
     ("chart", "R3 · Tendencia de bailabilidad por década", 3, 36),
     ("chart", "R3 · Cobertura Spotify por década", 3, 36)],
    [("chart", "R3 · Premios por familia de categoría y década", 8, 42), ("md", "r3_guide", 4, 42)],
    "R4 — ¿Quiénes acumulan más premios y cómo están representados en Spotify?",
    [("chart", "R4 · Top 10 artistas premiados en Spotify", 5, 50),
     ("chart", "R4 · Ranking global de artistas premiados", 7, 50)],
    [("chart", "R4 · Premiados ausentes de Spotify", 6, 34), ("md", "r4_guide", 6, 34)],
]

REQUIREMENTS_MARKDOWN: dict[str, str] = {
    "req_intro": (
        "**KPIs Spotify & Grammy (R1–R4)** &nbsp;|&nbsp; "
        "Exploración profunda de hipótesis musicales, popularidad e impacto histórico en Spotify &nbsp;·&nbsp; "
        "[Ver Dashboard Ejecutivo →](/superset/dashboard/workshop-dashboard/) &nbsp;·&nbsp; "
        "[Ver Granularidad & Calidad →](/superset/dashboard/w2-granularity/)\n\n"
        "> **Controles Interactivos:** Filtre por **Base de Análisis** (*excl_zero* vs *all*) y **Criterio de Reconocimiento** (*core* vs *strict*) en la barra superior."
    ),
    "r1_guide": (
        "### Claves para explicar R1\n\n"
        "- **Base de Análisis (`basis`)**: *excl_zero* excluye pistas con popularidad 0 (~14.1% del catálogo). *all* evalúa todo el catálogo.\n"
        "- **Reconocimiento (`recognition`)**: *core* = Tiers A+B (intérpretes directos y colaboradores). *strict* = solo Tier A (crédito directo).\n"
        "- **Hallazgo estadístico**: La popularidad mediana de artistas Grammy es significativamente mayor (+10.22 puntos en *excl_zero*, p < 1e-30; delta de Cliff = 0.24)."
    ),
    "r3_guide": (
        "### Claves para explicar R3\n\n"
        "- **Evolución sónica**: Caída sostenida en *acousticness* junto al aumento de *energy* y *danceability* desde los 1960s.\n"
        "- **Cobertura por década**: La disponibilidad en Spotify crece de ~15% en los 1960s a ~50% en los 2010s.\n"
        "- **Uso del filtro `Década`**: Permite aislar una década para ver las familias de categorías predominantes."
    ),
    "r4_guide": (
        "### Claves para explicar R4\n\n"
        "- **Top en Spotify**: Intérpretes principales más premiados en catálogo (Chicago Symphony Orchestra, John Williams, Beyoncé, Jay-Z).\n"
        "- **Ranking Global**: Muestra el nivel de reconocimiento (Tier A: crédito, Tier B: colaboradores, Tier C: producción).\n"
        "- **Galardonados Tier C**: Leyendas con premios técnicos o de producción (Frank Sinatra, Quincy Jones, Miles Davis, Billie Holiday)."
    ),
}

REQUIREMENTS_FILTERS: list[dict] = [
    {"name": "Década", "column": "decade", "description": "Filtrar por década histórica de entrega del premio Grammy"},
    {"name": "Género Musical", "column": "genre_family", "description": "Familia de género musical del artista en catálogo Spotify"},
    {"name": "Categoría Grammy", "column": "category_family", "description": "Familia canónica de categoría de premio Grammy"},
    {"name": "Base de Análisis (Popularidad)", "column": "basis", "default": ["excl_zero"], "required": True,
     "multi": False,
     "description": "excl_zero oculta el ~14.1% de canciones con popularidad = 0. all evalúa catálogo completo (R1)."},
    {"name": "Criterio de Reconocimiento", "column": "recognition", "default": ["core"], "required": True,
     "multi": False,
     "description": "core: evalúa Tiers A y B (intérpretes directos y colaboradores). strict: solo Tier A (R1)."},
]