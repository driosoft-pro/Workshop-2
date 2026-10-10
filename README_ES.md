# Workshop-2 — Pipeline (Spotify × Premios Grammy)

Un pipeline por lotes de estilo producción, **con la confiabilidad como primera
prioridad**: CSV de Spotify + Premios Grammy (fuente en PostgreSQL) → dos
compuertas de validación de Great Expectations → armonización/integración →
Almacén de Datos dimensional confiable (PostgreSQL) → KPIs y un **dashboard de
Apache Superset** (Power BI como alternativa), orquestado por **Apache Airflow
3.1.8** con la API TaskFlow.

> Confiabilidad no significa que nada falle. Confiabilidad significa que los
> fallos se anticipan, se controlan y son observables — y que una re-ejecución
> nunca corrompe el destino analítico.

---

## 1. Objetivo general y objetivos específicos

**Objetivo general:** construir un Almacén de Datos confiable que integre el
catálogo de Spotify con el histórico de Premios Grammy y lo entregue como KPIs
verificables y un dashboard, con calidad medida, compuertas y evidencia en cada
lote.

**Objetivos específicos:**

1. Extraer y armonizar dos fuentes incompatibles (CSV + tabla PostgreSQL) bajo
   un contrato de columnas explícito (22 y 9 columnas).
2. Validar cada etapa con reglas de calidad declarativas (38 reglas → 45
   expectativas de Great Expectations) y **compuertas que bloquean** el lote
   cuando la severidad es crítica.
3. Transformar e integrar sin reparar valores: deduplicar, normalizar claves,
   explotar multivalores y medir la cobertura de integración en lugar de
   ocultarla.
4. Cargar un **reemplazo transaccional controlado** en un modelo dimensional
   (4 dimensiones + 2 hechos + 1 tabla puente + log de lotes), repetible ante re-ejecuciones.
5. Orquestar el flujo con Airflow (dependencias, reintentos por clase de fallo,
   logs y evidencia) y entregar KPIs + dashboard por requisito analítico.
6. Verificar todo con una suite de pruebas reproducible (`tests/`, 95 pruebas vía pytest).

## 2. Granularidad de los entregables analíticos

Granularidad a la que se lee cada requisito (los KPIs se agregan **hacia
arriba** nunca hacia abajo):

| Requisito | Granularidad de lectura | Agregación |
| --- | --- | --- |
| **R1** | canción primaria (`is_primary_song=1`) y nivel artista, agrupado por reconocimiento (`core` vs `strict`) y base (`all` vs `excl_zero`) | mediana (diferencia, Mann-Whitney U, delta de Cliff, IC 95% bootstrap) + promedio (`popularity`, `energy`, `valence`), conteo |
| **R2** | género de Spotify dominante del artista × categoría Grammy | conteo de premios, % del total, premios por cada 100 artistas |
| **R3** | década (principal) y año (secundario) | promedio de popularidad/energía/rasgos de audio, conteo de premios y artistas |
| **R4** | artista (niveles A/B únicamente) | suma de premios, nº de pistas en Spotify, top-N=10 |
| Cobertura (KPI-0) | 1 fila (todo el lote) + desglose por método, nivel y década | % de filas de premio emparejadas, tasa estricta, distribución de niveles, tasa de confirmación de canciones |

## 3. Resultados esperados

* `music_dw`: 4 dimensiones, 2 hechos, 1 tabla puente (`bridge_award_artist`) y `etl_batch_log` con auditoría por lote
  (filas antes/después).
* **14 KPIs** (`sql/kpi_queries.sql`) exportados como CSV + **4 gráficos PNG**
  en `docs/evidence/kpis/`, uno por requisito.
* Dashboard **Superset** con 22 gráficos en 5 pestañas de requisitos + fila de encabezado y,
  como alternativa, el diseño de páginas Power BI/DAX.
* Evidencia por corrida: JSON de Great Expectations por etapa, resumen y logs de
  Airflow, conteos de carga, estado de las tareas y política de reintentos.
* Estado actual del almacén (lotes confirmados): `fact_track_artist` 157.530 ·
  `fact_grammy_award` 4.810 · `bridge_award_artist` 2.772 · `dim_artist` 30.984 ·
  `dim_genre` 114 · `dim_year` 62 · `dim_award_category` 638.

## 4. Problema

El reconocimiento de premios (Grammy) y el rendimiento del catálogo de
streaming (Spotify) viven en dos fuentes incompatibles: un archivo y una tabla
relacional, sin un identificador compartido. Ninguna de las dos puede responder
por sí sola preguntas como *¿los artistas reconocidos con un Grammy se
comportan distinto en Spotify?* ni *¿qué géneros dominan entre los
galardonados?*. Además, la integración cruza por **nombre**, con 38,25% de las
filas de premio sin crédito de artista: la calidad no es un detalle, es la
condición para interpretar cualquier cifra. El pipeline convierte ese problema
en un Almacén de Datos cuya calidad está **medida, compuertada y documentada**.

## 5. Objetivo analítico y requisitos (R1–R4)

Tabla completa con preguntas, respuestas esperadas y salidas:
[`docs/analytical_requirements.md`](docs/analytical_requirements.md).

| ID | Pregunta | Se necesitan ambas fuentes porque |
| --- | --- | --- |
| **R1** | ¿Los artistas reconocidos con Grammy tienen un desempeño distinto en Spotify frente al resto del catálogo? | la bandera de reconocimiento viene de los Grammy, el perfil de popularidad/audio de Spotify |
| **R2** | ¿Qué géneros de Spotify dominan entre los artistas reconocidos con Grammy? | el género viene de Spotify, la señal de premio de los Grammy |
| **R3** | ¿Cómo ha evolucionado el perfil de los artistas reconocidos por década? | la línea temporal viene de los Grammy, el perfil del artista de Spotify |
| **R4** | ¿Qué artistas acumulan más premios y cómo se representan en el catálogo de Spotify? | el rango de premios viene de los Grammy, la cobertura del catálogo de Spotify |

Los requisitos son la **etiqueta de trazabilidad** en todas las capas:
`RULES[*].requirement` (`src/validation.py`), `meta.requirement` de cada
expectativa GX, el comentario `-- Rn` de cada KPI SQL y la etiqueta `[Rn]` de
cada gráfico del dashboard.

## 6. Alineamiento

| Dimensión del curso | Cómo se cumple aquí |
| --- | --- |
| Pipeline por lotes | 8 tareas TaskFlow, ejecución manual/desde UI, `dagrun_timeout=2h` |
| Calidad como propiedad medida | 38 reglas con métrica/umbral/severidad → 45 expectativas GX → 2 compuertas que bloquean |
| Confianza en la entrega | reintentos por clase de fallo, logs por tarea, `etl_batch_log` transaccional, re-ejecución segura |
| Modelo dimensional | esquema estrella con claves de negocio únicas, tabla puente (`bridge_award_artist`) y grano declarado |
| Analítica y BI | 14 KPIs ligados a R1–R4 + dashboard Superset (22 gráficos) y Power BI (alternativa) |
| Reproducibilidad | entorno Nix + compose (Podman/Docker), `run.sh`/`run.bat`, suite pytest (95 pruebas), evidencia versionada |

## 7. Fuentes de datos

| Fuente | Forma usada por el pipeline | Filas | Notas |
| --- | --- | --- | --- |
| Pistas de Spotify | `data/raw/spotify_dataset.csv` (CSV) | 114.000 | 21 columnas crudas → **22 columnas del contrato** extraídas (`danceability, acousticness, speechiness, loudness, tempo, explicit` agregadas al contrato; índice sin nombre excluido) |
| Premios Grammy | PostgreSQL `music_source.grammy_awards` | 4.810 | **Preparación de la fuente**: `scripts/prepare_source_db.py` importa el CSV proporcionado (evidencia `docs/evidence/runs/source_preparation.json`, 4.810 = 4.810). Esto *no* es la Carga del ETL: la Carga escribe en `music_dw` |

Política de NA: `keep_default_na=False, na_values=[""]` — el archivo contiene
componentes de artista literales `N/A` (2 filas) que el análisis por defecto de
pandas convertiría en NaN. Contrato de columnas verificado por pruebas
(`tests/test_extract_contract.py`).

## 8. Perfilamiento y matrices de calidad (Python + GX + Airflow)

**Perfilamiento** (ejecutado):
[`notebooks/data_profiling.ipynb`](notebooks/data_profiling.ipynb) — resumen
automático en `docs/evidence/profiling_summary.json`.

| Dimensión | Hallazgos clave |
| --- | --- |
| Estructura | Spotify 114.000×21 (22 en el contrato); Grammy 4.810×10 (9 en el contrato) |
| Completitud | 1 fila de Spotify sin crédito de artista (0,0009%); en Grammy `artist` falta en **1.840 filas (38,25%)**, `nominee` en 6 (0,12%), `workers` 45,5% |
| Unicidad | 24.259 `track_id` repetidos; **450 granos duplicados `(track_id, track_genre)`**; 0 filas duplicadas por completo; la clave de negocio del premio Grammy es única |
| Categóricos | 114 géneros × exactamente 1.000 filas (100% mapeados en 12 familias de género); 638 categorías crudas de premio (579 limpias, 14 familias estándar); `winner=True` en las 4.810 filas (solo ganadores) |
| Numéricos | `popularity` 0–100 limpio (14,1% con popularidad cero marcado con bandera); 1 fila `duration_ms=0`, 603 >10 min, 16 >1 h; 90 filas con loudness >0 dB; 157 con tempo ≤0; 163 con `time_signature=0` |
| Temporal | premios 1958–2019, 62 años sin huecos; `published_at` analizable en 4.810/4.810 |
| Entre fuentes | Cascada de emparejamiento T12: **tasa de coincidencia global de 51,10%** (2.458/4.810 filas de premio); **28,05% estricta** (1.349 exacta); 704 recuperadas por workers; 343 por división de créditos; 62 por nominee; **2.772 filas en tabla puente**; 127 créditos agregados excluidos; 296 premios Nivel C (técnicos/producción); 26,22% de tasa de confirmación de canciones |

**Matriz de riesgos → reglas → expectativas → compuertas** (cuatro capas):

1. **Riesgos** con métrica observada y justificación:
   [`docs/quality_rules.md`](docs/quality_rules.md) (matriz perfilado → riesgo →
   severidad → requisito).
2. **Reglas de ejecución** en Python (`RULES` en `src/validation.py`, **38 reglas**:
   DQ-S1…S7 de esquema/contrato, DQ-G1…G14 de integridad de negocio/cascada/puente/familias/niveles/bloqueo, DQ-P1…P17 de
   perfilado/umbrales), consumidas por la política `enforce_policy`.
3. **Great Expectations**: 6 suites ↔ 6 validaciones ↔ 6 checkpoints, **45
   expectativas** con `meta.rule_id/severity/dimension/requirement`
   ([`docs/gx_design.md`](docs/gx_design.md)).
4. **Compuertas de Airflow**: `validate_spotify_raw` y `validate_grammys_raw`
   (¿puede entrar a la transformación?) y `validate_prepared` (¿puede cargarse?).
   Severidad crítica → `ValidationGateError` → aguas abajo `upstream_failed`;
   advertencia → se registra y el lote continúa.

## 9. Trazabilidad

Cadena completa (requisito → riesgo → regla → expectativa → transformación →
DW → KPI → dashboard) materializada en
[`docs/traceability_matrix.md`](docs/traceability_matrix.md):

* `RULES[*].requirement` en `src/validation.py` → etiquetas `R1`–`R4`
* `meta.rule_id` / `meta.severity` en cada expectativa GX → `docs/evidence/gx/…`
* `T1..T18` con columna de justificación → `docs/transformation_integration.md`
* comentarios `-- Rn` en `sql/kpi_queries.sql` → CSV en `docs/evidence/kpis/`
* etiqueta `[Rn]` en cada gráfico → `docs/superset_dashboard.md` (Power BI:
  `docs/powerbi_dashboard.md`)

## 10. Estrategia de preparación y correcciones estructurales

[`docs/transformation_integration.md`](docs/transformation_integration.md) —
reglas **T1…T18**: descartar filas sin clave (−1), deduplicar grano (−450),
explotar `artists` en `;`, normalizar la clave de artista (minúsculas,
espacios, puntuación), **sin reparación de valores (T5)**, derivar banderas de
reconocimiento, `winner_flag` y banderas de coincidencia, emitir métricas de
integración, cascada de coincidencia y puente colaborativo (T12), limpieza de categorías (T13),
familias de género (T14), banderas de canciones primarias (T15), perfil de género dominante (T16),
lista de bloqueo de créditos agregados (T17) y niveles de reconocimiento (T18).

Correcciones estructurales aplicadas (no se “arreglan” métricas, se arregla la
forma de los datos):

| Corrección | Efecto |
| --- | --- |
| Deduplicación `(track_id, track_genre)` | 450 filas redundantes fuera de la fact |
| Explode de `artists` | cardinalidad pista↔artistas 1..n (157.530 anuncios) |
| Normalización de nombre de artista | clave de integración estable `artist_key` (90 nombres fusionados) |
| `winner_flag` explícito | el dataset solo de ganadores no se interpreta como “candidatos” |
| Claves sustitutas generadas en la transacción | sin fugas entre corridas; secuencias realineadas con `setval` |
| Descomposición de créditos colaborativos (T12) | atribución multiautor vía `bridge_award_artist` |
| Selección de canción primaria (T15) | marca 111.206 canciones únicas (`is_primary_song=1`), eliminando dilución por reediciones |
| Bloqueo de créditos agregados (T17) | 127 entidades no artísticas bloqueadas de puente y banderas |
| Niveles de reconocimiento (T18) | categoriza premios en Nivel A (directo), B (worker), C (técnico/artesanal) |

Contrato de integración: clave `artist_key` (basada en el nombre — no existe ID
compartido), cardinalidad premio↔artista 0..n vía `bridge_award_artist`, filas sin coincidencia **medidas
y conservadas** (`is_matched_spotify=0`), limitaciones documentadas (512 filas sin coincidencia con crédito;
dataset solo de ganadores; premios de Nivel C excluidos de banderas de interpretación).

## 11. Declaración de grano

| Objeto | Grano declarado | Clave de negocio |
| --- | --- | --- |
| `fact_track_artist` | anuncio de pista × género × artista intérprete | `(track_id, track_genre, artist_sk)` (UNIQUE) |
| `fact_grammy_award` | año × categoría × nominado × artista | `award_bk` (UNIQUE, normalizado) |
| `bridge_award_artist` | premio × artista intérprete acreditado | `(grammy_award_sk, artist_sk)` (PRIMARY KEY) |
| `dim_artist` | artista | `artist_bk` |
| `dim_genre` | género de Spotify | `genre` |
| `dim_year` | año (PK natural) + `decade` derivado | `year` |
| `dim_award_category` | categoría de premio | `category` |
| `etl_batch_log` | 1 fila por lote confirmado | `batch_id = <dag_id>__<run_id>` |

El nivel más fino al que son consistentes las medidas R1–R4 es la pista ×
género × artista; todos los KPIs agregan hacia arriba desde ahí.

## 12. Modelo dimensional

[`docs/dimensional_model.md`](docs/dimensional_model.md) ·
DDL [`sql/dw_schema.sql`](sql/dw_schema.sql) · creado automáticamente por
`sql/db_init/01_create_dw.sql` al iniciar `music-postgres`.

```mermaid
erDiagram
    dim_artist ||--o{ fact_track_artist : "artist_sk"
    dim_genre ||--o{ fact_track_artist : "genre_sk"
    dim_artist ||--o{ fact_grammy_award : "artist_sk primary, nullable"
    fact_grammy_award ||--o{ bridge_award_artist : grammy_award_sk
    dim_artist ||--o{ bridge_award_artist : artist_sk
    dim_year ||--o{ fact_grammy_award : "year_sk"
    dim_award_category ||--o{ fact_grammy_award : "category_sk"

    dim_artist {
        bigint artist_sk PK
        text artist_bk UK "clave normalizada del nombre"
        text artist_display_name
        bool from_spotify
        bool from_grammy
        int grammy_award_count
        int grammy_award_count_core
        int spotify_track_count
        text dominant_genre "NUEVO T16"
        text dominant_genre_family "NUEVO T16"
        int n_genres "NUEVO T16"
        bool genre_tie "NUEVO T16"
    }
    dim_genre {
        bigint genre_sk PK
        text genre UK
        text genre_family "NUEVO T14"
    }
    dim_year {
        int year_sk PK
        int year UK
        int decade
    }
    dim_award_category {
        bigint category_sk PK
        text category UK
        text category_clean "NUEVO T13"
        text category_family "NUEVO T13"
    }
    fact_track_artist {
        bigint track_artist_sk PK
        text track_id
        text track_genre
        bigint artist_sk FK
        bigint genre_sk FK
        text track_name
        text album_name
        int popularity
        bigint duration_ms
        float energy
        float valence
        int artist_position
        int artist_total
        int is_grammy_artist "0/1"
        int is_grammy_artist_strict "0/1"
        int artist_grammy_awards
        text song_key "NUEVO T15"
        int is_primary_song "NUEVO T15"
        int is_zero_popularity "NUEVO T15"
        int is_outlier_duration "NUEVO T15"
        int is_outlier_loudness "NUEVO T15"
        int is_outlier_tempo "NUEVO T15"
        float danceability "contrato raw 22 columnas"
        float acousticness "contrato raw 22 columnas"
        float speechiness "contrato raw 22 columnas"
        float loudness "contrato raw 22 columnas"
        float tempo "contrato raw 22 columnas"
        bool explicit "contrato raw 22 columnas"
        text batch_id
        timestamptz loaded_at
    }
    fact_grammy_award {
        bigint grammy_award_sk PK
        text award_bk UK "year x category x nominee x artist"
        bigint artist_sk FK "NULL si no coincide"
        int year_sk FK
        bigint category_sk FK
        text title
        text nominee
        text artist_credit
        text workers
        bool winner
        int winner_flag "0/1"
        int is_matched_spotify "0/1"
        int is_matched_strict "NUEVO T12"
        int is_song_confirmed "NUEVO T12"
        text artist_source "NUEVO T12"
        text match_method "NUEVO T12"
        int credit_artist_count "NUEVO T12"
        text recognition_tier "NUEVO T18"
        int is_aggregate_credit "NUEVO T17"
        int spotify_track_count
        int award_count
        text batch_id
        timestamptz loaded_at
    }
    bridge_award_artist {
        bigint grammy_award_sk PK,FK
        bigint artist_sk PK,FK
        int artist_position
        text match_method
        text recognition_tier "NUEVO T18"
        text batch_id
        timestamptz loaded_at
    }
    etl_batch_log {
        text batch_id PK
        text dag_id
        text run_id
        text strategy
        jsonb target_rows_before
        jsonb target_rows_after
        text status
        timestamptz started_at
        timestamptz finished_at
        text notes
    }
```

Filas actuales: `fact_track_artist` 157.530 · `fact_grammy_award` 4.810 ·
`bridge_award_artist` 2.772 · `dim_artist` 30.984 · `dim_genre` 114 ·
`dim_year` 62 · `dim_award_category` 638. Las claves sustitutas se generan dentro de la
transacción de carga; las claves de negocio tienen restricción UNIQUE; los
premios sin coincidencia conservan `artist_sk NULL` por diseño.

## 13. Pipeline ETL, puertas y orquestación

[`docs/architecture.md`](docs/architecture.md) ·
[`dags/reliable_music_pipeline.py`](dags/reliable_music_pipeline.py)

```
spotify CSV ─ extract_spotify ─ validate_spotify_raw ─┐
                                                      ├─ transform_and_integrate ─ validate_prepared ─ load_dw ─ build_kpis
postgres   ─ extract_grammys ─ validate_grammys_raw ──┘                                     (music_dw)    (KPIs/PNG)
             transform_and_integrate: +bridge, flags, match report   validate_prepared: +DQ-G6… rules
```

![Estructura del DAG implementado](docs/dag_structure.png)

* 8 tareas TaskFlow (`from airflow.sdk import dag, task, get_current_context`),
  `schedule=None`, `max_active_runs=1`, `catchup=False`, `dagrun_timeout=2h`.
* Coincidencia configurable: el parámetro del DAG `enable_fuzzy` (predeterminado `false`) habilita
  la coincidencia difusa Jaro-Winkler mediante `./run.sh trigger-fuzzy`.
* Las dependencias **codifican la política**: la transformación requiere
  ambas compuertas crudas; la carga requiere la compuerta preparada. Las
  interfaces pasan rutas/metadatos únicamente (sin DataFrames en XCom).
* Lógica reutilizable en `src/` (extract, transform, validation, load,
  analytics): el DAG solo orquesta.

**Fallos y reintentos** ([`docs/failure_retry_policy.md`](docs/failure_retry_policy.md)):

| Clase | Tareas | Reintento |
| --- | --- | --- |
| Operativo transitorio (FS/DB) | `extract_spotify`, `extract_grammys`, `load_dw` | 2 intentos, exponencial de 1 min, tope 10 min |
| Datos/contrato determinista | ambas compuertas crudas, `transform_and_integrate`, `validate_prepared` | **0** — la evidencia queda en su lugar |
| Analítica posterior a la carga | `build_kpis` | 1 intento |

Sin `retries=3` generalizado; cada reintento está justificado por su clase de fallo.

**Repetibilidad** — reemplazo controlado: una transacción por lote
(`DELETE` + `INSERT` sobre las siete tablas, claves de negocio UNIQUE como red
de seguridad, upsert en `etl_batch_log` con clave `batch_id = <dag_id>__<run_id>`, secuencias realineadas con `setval`). Un fallo
aborta completo y el destino conserva el estado anterior.

## 14. Requisitos → modelo → KPIs

| Req. | Tablas del modelo | KPI SQL (`sql/kpi_queries.sql`) | Gráfico Superset |
| --- | --- | --- | --- |
| cobertura | ambas hechos + `etl_batch_log` | `kpi_0_integration_coverage`, `kpi_0_coverage_by_method`, `kpi_0_coverage_by_tier`, `kpi_0_coverage_by_decade` | Pestañas Encabezado + Calidad |
| **R1** | `fact_track_artist` (+ `dim_genre`, `dim_year`) | `kpi_1_popularity_by_grammy_recognition`, `kpi_1_artist_level`, `kpi_1_within_genre_diff` | R1 – Popularidad (4 gráficos) |
| **R2** | `fact_grammy_award` + `fact_track_artist` + puente | `kpi_2_awards_by_dominant_genre`, `kpi_2_heatmap` | R2 – Premios por género y mapa de calor |
| **R3** | `fact_grammy_award` + `dim_year` + `fact_track_artist` | `kpi_3_awards_and_profile_by_decade`, `kpi_3_awards_per_year`, `kpi_3_awards_by_family_decade` | R3 – Décadas, series y tendencias sonoras |
| **R4** | `fact_grammy_award` + `dim_artist` + puente | `kpi_4_top_awarded_artists_on_spotify`, `kpi_4_top_awarded_all` | R4 – Top artistas en Spotify y global |

Las consultas se ejecutan también fuera de Airflow
(`python -m scripts.smoke_test`, `tests/test_sql_and_schema.py` verifica el
nombre, la etiqueta `-- Rn` y la existencia de cada objeto DDL).

## 15. Reglas de calidad, Great Expectations y resumen de validación

**38 reglas** (DQ-S1…S7 esquema/contrato · DQ-G1…G14 integridad de negocio/cascada/puente/niveles/bloqueo · DQ-P1…P17
perfilado/tasas), con métrica, umbral, severidad, justificación y etiqueta de
requisito: [`docs/quality_rules.md`](docs/quality_rules.md).

Diseño GX ([`docs/gx_design.md`](docs/gx_design.md)): proyecto 1.23.1 en modo
archivo dentro de `gx/` — 6 suites ↔ 6 definiciones ↔ 6 checkpoints, **45
expectativas** con `meta.rule_id/severity/dimension/requirement`. Los
resultados se escriben como JSON legible por máquina en
`docs/evidence/gx/<stage>/<stamp>_<run_id>.json` (conteos por regla, muestra de
valores inesperados, ids de reglas fallidas).

**Resumen de validación por ejecución:**

| Corrida | Resultado |
| --- | --- |
| Test A (`test_a_success`) | 8/8 tareas `success`, try=1, 61,3 s; conteos `157.530 / 4.810 / 30.984 / 114 / 62 / 638 / 2.772 puente` (`docs/evidence/runs/`) |
| Test B (`test_b_critical_failure`) | `extract_spotify` success → `validate_spotify_raw` **failed** (`ValidationGateError … DQ-S3 … unexpected_count=1`); 4 tareas `upstream_failed`; Almacén intacto (sin fila en `etl_batch_log`) |
| Test C (`test_c_safe_rerun`) | misma entrada que el Test A: conteos idénticos antes/después, dos lotes confirmados con `target_rows_after` iguales |

![Estados de las tareas en las tres pruebas de confiabilidad](docs/evidence/runs/airflow_task_states.png)

**Pruebas automatizadas** (`tests/`, `pytest.ini`, marker `integration`):
**95 pruebas** — 91 offline (catálogo de reglas, consistencia GX, transform con
CSVs sintéticos, contrato de extracción, KPI/DDL, compuerta de validación,
DagBag del DAG, coincidencia en cascada, mapeos, banderas de pista primaria,
género dominante, contrato del bootstrap de Superset, niveles de reconocimiento, lista de bloqueo agregada, auditoría de coincidencias, estadísticas R1, reporte de validación) + 4 de integración que se
auto-omiten (`skip`) si no hay base disponible.

```bash
./run.sh test     # o: nix develop -c python -m pytest
```

## 16. Inteligencia de negocios: Superset (principal) y Power BI (alternativa)

**Apache Superset es la capa BI principal** y está automatizada en el repositorio:

| Elemento | Valor |
| --- | --- |
| URL / login | `http://localhost:8088` — `admin` / `admin` |
| Conexión | datasets virtuales, SQL sobre `music_dw` (PostgreSQL en `music-postgres:5432`) |
| Objetos | 1 base de datos, **15 datasets** (construidos desde `sql/kpi_queries.sql` + `etl_batch_log`), **22 gráficos**, **1 dashboard** (`Workshop-2 – KPIs (R1-R4)`, publicado) en 5 pestañas de requisitos + fila de Encabezado |
| Bootstrap | `./run.sh superset` → `scripts/superset_bootstrap.py` (idempotente; valida cada consulta con la API de Superset) |
| Documentación | [`docs/superset_dashboard.md`](docs/superset_dashboard.md) |

Como los datasets son *virtuales*, cada gráfico refleja el estado del Almacén
después de la última corrida del DAG: refrescar = re-ejecutar el pipeline, no
hay extracto que refrescar. Detalle por gráfico (tipo, requisito, filas
validadas) y lectura analítica en el documento anterior.

**Power BI como alternativa** ([`docs/powerbi_dashboard.md`](docs/powerbi_dashboard.md)):
mismas 4 páginas (una por requisito), medidas DAX y relaciones sobre el mismo
`music_dw`; se conecta desde la VM de Windows 11 (§18.3). Ambas capas son
intercambiables porque consumen los mismos KPIs.

Artefactos generados por el pipeline (14 CSV + 4 PNG) en `docs/evidence/kpis/`.

## 17. Arquitectura, salidas y evidencia

| Capa | Implementación | Ubicación |
| --- | --- | --- |
| Orquestación | Airflow 3.1.8, TaskFlow, LocalExecutor | `dags/reliable_music_pipeline.py`, `docker-compose.yaml` |
| Lógica | extract / transform / validation / load / analytics | `src/*.py` |
| Emparejamiento y niveles | Cascada de coincidencia, derivación de niveles, diccionarios de género/categoría | `src/artist_match.py`, `src/mappings.py` |
| Validación | Great Expectations 1.23.1, 6 suites / 45 expectativas, 2 compuertas | `gx/`, `src/validation.py` |
| Fuente Grammys | PostgreSQL 16 `music_source` | `sql/source_setup.sql`, `scripts/prepare_source_db.py` |
| Almacén | PostgreSQL 16 `music_dw` (esquema estrella + puente, 7 tablas) | `sql/dw_schema.sql`, `src/load.py` |
| Analítica | 14 consultas KPI + scipy/numpy/pandas/matplotlib | `sql/kpi_queries.sql`, `src/analytics.py` |
| BI | **Apache Superset 6.1.0** (principal) · Power BI (alternativa) | `scripts/superset_bootstrap.py`, `docs/superset_dashboard.md`, `docs/powerbi_dashboard.md` |
| Evidencia | JSON GX, resúmenes de corrida, KPI CSV/PNG, logs de tareas, muestra de auditoría | `docs/evidence/` |
| Verificación | pytest (95) + `scripts/validate_report.py` + `scripts/match_audit.py` | `tests/`, `scripts/` |

Evidencia registrada: [`docs/evidence_register.md`](docs/evidence_register.md)
(IDs E1–E19 → artefacto → afirmación → sección del informe).

## 18. Cómo usar el repositorio

### 18.1 Requisitos

* Nix con flakes: `nix develop` provee Python 3.12, `uv`, cliente de
  PostgreSQL y Podman (`flake.nix`); `requirements.txt` (+ `requirements-dev.txt`
  para pytest)
* **Podman ≥ 4** (rootless) con `podman compose`/`podman-compose`, o Docker +
  Compose; el compose está adaptado del oficial de Airflow 3.1.8 (LocalExecutor,
  sin Redis/Celery)

### 18.2 Clonar y arrancar el proyecto

```bash
git clone git@github.com:driosoft-pro/Workshop-2.git   # o con HTTPS
cd Workshop-2
cp .env.example .env                # revisar AIRFLOW_UID, puertos y credenciales
./run.sh up                         # valida/libera puertos + stack + fuente + Superset
./run.sh test                       # 95 pruebas (unidad + integración)
./run.sh trigger                    # DAG Test A → 8/8 success
```

`./run.sh up` ejecuta primero `./run.sh ports`: libera los puertos que este
proyecto necesita (5432, 8080, 8088) si otro proyecto los tiene ocupados, y
solo entonces levanta el stack. Verificación rápida:

```bash
./run.sh status    # contenedores + URLs
./run.sh urls      # solo URLs
# Airflow     http://localhost:8080  (airflow / airflow)
# Superset    http://localhost:8088  (admin / admin)
# PostgreSQL  localhost:5432         (music / music)
```

Opcional (solo si no usas Nix): `python -m venv .venv && pip install -r
requirements.txt`.

#### 18.2.1 Variables de entorno e higiene de seguridad (`.env` / `.env.example`)

Para evitar filtraciones de seguridad y exposición de credenciales sensibles:
* **Cero credenciales fijas en el código fuente**: Todas las URLs de conexión a bases de datos y secretos (`DEFAULT_ADMIN_URI`, `SUPERSET_METADATA_ADMIN_URI`, `SUPERSET_SQLALCHEMY_DATABASE_URI`, `SUPERSET_DW_SQLALCHEMY_URI`, `MUSIC_SOURCE_DB_URL`, `MUSIC_DW_DB_URL`, etc.) están externalizadas en `.env` y nunca codificadas directamente en Python (`scripts/superset_create_metadata_db.py`, `scripts/superset_bootstrap.py`, `config/superset_config.py`, `src/config.py`) ni en `docker-compose.yaml`.
* **`.env` está estrictamente excluido por Git** (`.gitignore`), garantizando que contraseñas locales o de entornos compartidos no se suban al repositorio.
* **`.env.example`** sirve como plantilla completa que documenta todas las variables requeridas con valores de ejemplo y configuración por defecto para desarrollo.
* **Descubrimiento y carga automática de `.env`**: Al ejecutar scripts localmente en el host (fuera de Docker/Podman Compose), estos leen automáticamente el archivo `.env` si existe y construyen las conexiones de forma dinámica a partir de las variables de entorno, sin valores por defecto con credenciales en texto plano.
* **Variables de entorno administradas**:
  * **Airflow**: `AIRFLOW_UID`, `_AIRFLOW_WWW_USER_USERNAME`, `_AIRFLOW_WWW_USER_PASSWORD`, `AIRFLOW__API_AUTH__JWT_SECRET`, `AIRFLOW_DATABASE_USER`, `AIRFLOW_DATABASE_PASSWORD`, `AIRFLOW_DATABASE_NAME`, `AIRFLOW__DATABASE__SQL_ALCHEMY_CONN`.
  * **PostgreSQL (fuente Grammy y Data Warehouse)**: `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`, `MUSIC_POSTGRES_PORT`, `MUSIC_SOURCE_DB_URL`, `MUSIC_DW_DB_URL`.
  * **Apache Superset**: `SUPERSET_SECRET_KEY`, `SUPERSET_PORT`, `SUPERSET_ADMIN_USER`, `SUPERSET_ADMIN_PASSWORD`, `DEFAULT_ADMIN_URI`, `SUPERSET_METADATA_ADMIN_URI`, `SUPERSET_METADATA_DB_NAME`, `SUPERSET_SQLALCHEMY_DATABASE_URI`, `SUPERSET_DW_SQLALCHEMY_URI`.

### 18.3 `run.sh` / `run.bat` (punto de entrada único)


```bash
./run.sh up                    # valida/libera puertos + compose up -d --build + fuente + bootstrap Superset
./run.sh ports [--yes]         # valida contenedores/puertos activos y detiene los ajenos (--yes omite confirmación)
./run.sh down                  # baja TODOS los servicios del proyecto (volúmenes intactos)
./run.sh stop                  # alias de down
./run.sh fresh [--yes]         # limpieza TOTAL y arranque desde cero (clean-all + up)
./run.sh clean-all [--yes]     # limpieza TOTAL (contenedores, BDs, logs de Airflow y datos temporales)
./run.sh clean-airflow         # limpia solo los logs de Airflow (logs/)
./run.sh clean-db [--yes]      # detiene contenedores y borra volúmenes de bases de datos (PostgreSQL/Superset)
./run.sh clean-data            # limpia datos intermedios y de salida (data/work, output, bad, gx)
./run.sh clean [--yes]         # alias de clean-all
./run.sh reset [--yes]         # alias de clean-all
./run.sh trigger               # DAG Test A (8/8 success)
./run.sh trigger-bad           # crea data/bad/spotify_bad.csv y dispara el Test B (bloqueo controlado)
./run.sh trigger-fuzzy         # ejecuta pipeline con enable_fuzzy=true
./run.sh validate [--superset] # reporte automatizado de validación de extremo a extremo (V1-V16, --superset, --json)
./run.sh test                  # pytest (unidad + integración, 95 pruebas)
./run.sh unit                  # solo pruebas offline (91 pruebas)
./run.sh status                # contenedores y URLs
./run.sh superset              # re-ejecuta el bootstrap de Superset (idempotente)
./run.sh logs                  # logs del scheduler
./run.sh smoke                 # pipeline local sin Airflow
```

`ports` recorre los contenedores en ejecución de **podman o docker**, detecta
quién publica 5432/8080/8088, **detiene automáticamente** los que no pertenecen
a este proyecto y avisa si el puerto lo ocupa un proceso que no es contenedor
(ahí hay que liberarlo a mano). Pase `--yes` o establezca `ASSUME_YES=1` para ejecución no interactiva. Agregue puertos extras con `EXTRA_PORTS="9000"`.

En Windows: `run.bat up`, `run.bat ports`, `run.bat test`, `run.bat trigger`, …
(`run.bat help`). Los comandos usan `podman compose` si existe y, si no,
`docker compose`.

### 18.4 Servicios, puertos y clientes (VM Windows 11)

| Puerto | Servicio | Consumidor típico |
| --- | --- | --- |
| `8080` | `airflow-apiserver` — UI/API (`airflow`/`airflow`) | navegador |
| `8088` | `superset` — UI (`admin`/`admin`) | navegador (principal BI) |
| `5432` | `music-postgres` — `music_source` + `music_dw` | Superset / Power BI Desktop |

Los puertos se publican en **`0.0.0.0`**: la máquina invitada los alcanza con la
dirección del host. Firewall en la configuración NixOS
(`/etc/nixos/env.nix`, `allowedTCPPorts = [ 5432 8080 8088 ]`; reconstruir con
`doas nixos-rebuild switch`).

Power BI Desktop en la **VM de Windows 11** (NAT de libvirt `default`, host
`192.168.122.1`; en la LAN `192.168.1.14`):

| Parámetro | Valor |
| --- | --- |
| Servidor | `192.168.122.1,5432` (LAN: `192.168.1.14,5432`) |
| Base de datos | `music_dw` · usuario `music` / contraseña `music` |
| Superset | `http://192.168.122.1:8088` (`admin`/`admin`) |
| Airflow | `http://192.168.122.1:8080` (`airflow`/`airflow`) |

Verificación de conectividad desde la VM: `Test-NetConnection 192.168.122.1 -Port 5432`.

### 18.5 Conexión con DBeaver (explorar `music_dw`)

[DBeaver Community](https://dbeaver.io/download/) (gratis) con el driver
PostgreSQL que trae por defecto. **Nueva conexión → PostgreSQL**:

| Parámetro | Valor (host NixOS) | Valor (desde la VM Windows 11) |
| --- | --- | --- |
| Servidor | `localhost` | `192.168.122.1` (LAN: `192.168.1.14`) |
| Puerto | `5432` | `5432` |
| Base de datos | `music_dw` | igual |
| Usuario | `music` | igual |
| Contraseña | `music` | igual |
| Sin SSL (opcional) | pestaña *Main* → desactivar *Use SSL* | igual |

Conexiones adicionales del mismo servidor (mismo usuario/puerto):

| Base | Contenido |
| --- | --- |
| `music_dw` | esquema estrella: `dim_*`, `fact_*`, `bridge_award_artist`, `etl_batch_log` |
| `music_source` | tabla fuente `grammy_awards` (4.810 filas) |
| `superset` | metadatos de Superset (no modificar) |

Verificación en la consola SQL de DBeaver (debe devolver `157530`):

```sql
select count(*) from fact_track_artist;              -- 157530
select count(*) from fact_grammy_award;              -- 4810
select count(*) from bridge_award_artist;            -- 2772
select * from etl_batch_log order by started_at desc limit 5;
select track_id, track_name, popularity              -- top R1 (artistas Grammy)
  from fact_track_artist
 where is_grammy_artist = 1
 order by popularity desc limit 10;
```

Si la conexión falla con *Connection refused*: el puerto 5432 está ocupado u
otro proyecto lo tiene — ejecuta `./run.sh ports` (o `./run.sh status` para ver
el mapeo) y reintenta. Desde la VM: `Test-NetConnection 192.168.122.1 -Port 5432`.

### 18.6 Ejecución manual (sin `run.sh`)

```bash
cp .env.example .env                          # revisar AIRFLOW_UID, puertos, credenciales
podman compose -f docker-compose.yaml up -d --build
podman compose exec -T airflow-apiserver python -m scripts.prepare_source_db
podman compose exec -T airflow-apiserver airflow dags trigger reliable_music_pipeline
podman compose exec -T superset python /app/scripts/superset_bootstrap.py
curl -s http://localhost:8080/api/v2/monitor/health
```

### 18.7 Pipeline local en el host (sin Airflow)

```bash
export PYTHONPATH=. MUSIC_DATA_DIR="$PWD/data" MUSIC_GX_DIR="$PWD/gx" \
       MUSIC_EVIDENCE_DIR="$PWD/docs/evidence" \
       MUSIC_SOURCE_DB_URL=postgresql+psycopg2://music:music@localhost:5432/music_source \
       MUSIC_DW_DB_URL=postgresql+psycopg2://music:music@localhost:5432/music_dw
python -m scripts.smoke_test                          # Test A completo
python -m scripts.make_bad_data                       # crea data/bad/spotify_bad.csv
python -m scripts.smoke_test --source spotify_bad.csv # Test B: salida BLOQUEADO (código 2)
python -m src.validation init                         # (re)construir assets de gx/
python -m src.validation rules                        # imprimir el catálogo de 38 reglas
python -m scripts.validate_report                     # ejecutar reporte de validación (V1-V16)
python -m scripts.match_audit --sample                # generar muestra de auditoría
```

### 18.8 Estructura del repositorio

```
workshop-2/
|-- run.sh  run.bat                     # punto de entrada único (up/ports/down/test/trigger/validate/…)
|-- dags/reliable_music_pipeline.py     # DAG TaskFlow (solo flujo de trabajo + política)
|-- src/                                # lógica reutilizable
|   |-- config.py  extract.py  transform.py  validation.py  load.py  analytics.py
|   |-- artist_match.py  mappings.py    # cascada de emparejamiento, derivación de niveles, diccionarios
|-- tests/                              # pytest: offline unit + integración (marker)
|-- gx/                                 # proyecto Great Expectations (suites/validations/checkpoints)
|-- notebooks/data_profiling.ipynb      # notebook de perfilado ejecutado
|-- sql/source_setup.sql  dw_schema.sql # DDL fuente y esquema estrella
|-- sql/db_init/01_create_dw.sql        # creado al iniciar music-postgres
|-- sql/db_init/02_create_superset.sql  # base de metadatos de Superset
|-- sql/kpi_queries.sql                 # 14 KPI (etiquetas -- Rn)
|-- scripts/                            # prepare_source_db, make_bad_data, smoke_test,
|   |                                   # superset_bootstrap, superset_create_metadata_db,
|   |                                   # match_audit.py, validate_report.py
|-- config/superset_config.py  Dockerfile.superset
|-- docs/                               # analytical_requirements, architecture, quality_rules,
|   |                                   # gx_design, transformation_integration, dimensional_model,
|   |                                   # failure_retry_policy, traceability_matrix,
|   |                                   # superset_dashboard, powerbi_dashboard, evidence_register
|   `-- evidence/                       # gx/, kpis/, runs/, profiling_summary.json, match_audit.csv
|-- data/{raw,work,output,bad}/         # entradas (raw confirmado en el repo) / generadas
|-- requirements.txt  requirements-dev.txt  pytest.ini
|-- docker-compose.yaml  flake.nix  .env.example  .gitignore
```

### 18.9 Supuestos y limitaciones

1. **Integración por nombre**: no hay ID de artista compartido; el emparejamiento
   depende de la normalización de nombres. 512 filas de premio con crédito
   quedan sin coincidir y 1.840 (38,25%) no tienen crédito.
2. **Solo ganadores**: `winner` es `True` en 4.810/4.810 filas (histórico de
   nominaciones fuera de alcance, acotado por regla de dominio DQ-G3).
3. **Créditos de grupo y entidades compuestas**: los créditos colaborativos se
   descomponen en sus artistas individuales mediante T12 (`bridge_award_artist`).
   Los créditos agregados (`"various artists"`, `"original cast"`, `"soundtrack"`)
   están estrictamente bloqueados mediante T17 (`AGGREGATE_CREDITS`) y nunca ingresan
   al puente ni a las banderas de premiación.
4. **Niveles de reconocimiento**: los premios en categorías de Producción y Técnicas
   (Nivel C, 296 filas) se conservan en el puente y en la cobertura de KPI-0, pero nunca
   activan `is_grammy_artist` ni `is_grammy_artist_strict` para evitar atribuir
   reconocimiento de ingeniería/diseño a los intérpretes musicales.
5. **Auditoría de precisión**: la validación manual de coincidencias muestreadas
   (`scripts/match_audit.py`) proporciona un límite empírico de confianza; actualmente AUDIT PENDING.
6. **Sin reparación de valores** (T5): fuera de rango (603 duraciones largas, 1
   duración cero, …) se reportan, nunca se corrigen.
7. **Columnas del contrato**: 22 columnas extraídas para Spotify, 9 para Grammy;
   los metadatos de audio fuera de los necesarios para R1/R3 están fuera de alcance.
8. **Estrategia de lote**: reemplazo transaccional completo por corrida (sin carga incremental/SCD);
   seguro para volúmenes de 157k filas.
9. **BI**: Superset es la capa principal (automatizada); Power BI Desktop queda
   como alternativa para el estándar del puesto de trabajo.

## 19. Hallazgos clave (R1–R4)

Todas las cifras provienen directamente de la ejecución del pipeline y de artefactos validados:

* **R1 (Popularidad y Rendimiento)**:
  - Los artistas reconocidos por el Grammy alcanzan una popularidad mediana en Spotify estadísticamente más alta que los no reconocidos en ambas definiciones de sensibilidad.
  - **Reconocimiento principal (Core)** (Niveles A y B): diferencia mediana = **+2,69** en todas las pistas ($p = 2,69 \times 10^{-4}$, delta de Cliff = $0,0733$, IC bootstrap 95% $[-0,80; 5,23]$); al excluir pistas de popularidad cero, la diferencia mediana se amplía a **+10,22** ($p = 1,02 \times 10^{-30}$, delta de Cliff = $0,2421$, IC $[8,00; 12,15]$).
  - **Reconocimiento estricto (Strict)** (Solo Nivel A): diferencia mediana = **+4,82** en todas las pistas ($p = 8,53 \times 10^{-8}$, delta de Cliff = $0,1152$, IC $[1,98; 8,07]$); al excluir pistas de popularidad cero, la diferencia mediana asciende a **+12,00** ($p = 1,23 \times 10^{-37}$, delta de Cliff = $0,2879$, IC $[10,00; 15,00]$).
  - **Impacto de deduplicación**: filtrar a canciones primarias (`is_primary_song=1`, 111.206 pistas) elimina la dilución por relanzamientos multigénero, elevando la popularidad media de artistas Grammy de **30,82** a **40,55** (incremento de +9,73 pp).
* **R2 (Dominancia por Género)**:
  - Entre artistas reconocidos por el Grammy, **Jazz Blues Soul** concentra la mayor proporción de premios con un **26,38%** (655 premios, 35,50 premios por cada 100 artistas), seguido de **Country & Folk** con **19,98%** (496 premios, 38,27 premios por cada 100 artistas), **Rock** con **12,00%** (298 premios, 10,90 por cada 100 artistas) y **Classical & Instrumental** con **11,36%** (282 premios, 10,34 por cada 100 artistas).
* **R3 (Evolución Longitudinal)**:
  - La tasa de coincidencia cruzada exhibe un crecimiento pronunciado por década: desde ~15% en los años 1960 hasta ~50% en los 2010, reflejando la disponibilidad del catálogo moderno en streaming.
  - Las tendencias temporales de audio muestran caídas sostenidas en acousticness junto a aumentos en danceability y loudness.
* **R4 (Top Artistas Premiados)**:
  - Los artistas más premiados con presencia en Spotify incluyen a Chicago Symphony Orchestra (29 premios), John Williams (24 premios), Beyoncé (23 premios), Jay-Z (22 premios) y Stevie Wonder (21 premios).
* **Limitaciones Analíticas**:
  - La popularidad en Spotify representa la interacción actual de streaming, no la popularidad histórica en la fecha de la ceremonia.
  - El catálogo de Spotify es una muestra de la música global: solo el 26,22% de las canciones galardonadas con el Grammy existen en el catálogo.
