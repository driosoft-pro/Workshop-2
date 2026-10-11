# Diccionario de Datos y Justificación del Esquema Dimensional

**Proyecto:** Workshop 2 — Pipeline ETL e Integración Dimensional Spotify & Grammy  
**Base de Datos Destino:** `music_dw` (PostgreSQL 16)  
**DDL Asociado:** [`sql/dw_schema.sql`](../sql/dw_schema.sql)  
**Carga y Transformación:** `src/load.py`, `src/transform.py`  

---

## 1. Justificación Arquitectónica General (Por qué este modelo y no 1 sola tabla)

El almacén de datos sigue la metodología formal de Ralph Kimball (**Fact Constellation / Constelación de Hechos**) estructurado en:
* **2 tablas de hechos** (`fact_track_artist` y `fact_grammy_award`).
* **4 dimensiones conformadas** (`dim_artist`, `dim_genre`, `dim_year`, `dim_award_category`).
* **1 tabla puente** (`bridge_award_artist`) para créditos colaborativos (*many-to-many*).
* **1 tabla de control y auditoría** (`etl_batch_log`).

### ¿Por qué NO una sola tabla de hechos como un modelo simplificado?
Un error común es intentar forzar todo en una tabla de pistas de Spotify (`fact_track_genre`), convirtiendo los premios Grammy en columnas estáticas del artista (`grammy_wins_1958_2018`). Dicho enfoque genera fallas graves:
1. **Destruye el análisis histórico (R3):** Al no tener granularidad de tiempo en los premios, es imposible responder cuántos premios se entregaron por año o década (1958–2019) o analizar tendencias sonoras temporales.
2. **Multiplica o infla métricas en R2:** Al calcular premios por género musical sumando un atributo del artista a través de sus canciones en Spotify, un artista con 50 canciones quintuplica artificialmente sus premios reales.
3. **Pérdida de 465 premios Grammy sin presencia en Spotify:** 465 premios pertenecen a orquestas históricas, directores e ingenieros que no tienen canciones en el dataset de Spotify. En un modelo de un solo hecho centrado en Spotify, estos premios desaparecerían del DW.
4. **Viola la regla cardinal de Kimball:** *Nunca mezcles en la misma tabla de hechos dos procesos de negocio con granularidades y frecuencias temporales diferentes* (el catálogo de streaming es una foto de catálogo actual; los premios son eventos históricos anuales discretos).

---

## 2. Justificación Tabla por Tabla y Campo por Campo

A continuación se detalla la justificación técnica y de negocio de cada una de las 8 tablas físicas y sus 75 columnas seleccionadas.

---

### 2.1. `dim_artist` (Dimensión de Artistas)
* **Propósito y Grano:** Un registro por artista único normalizado (`artist_bk`). Dimensión conformada que conecta el catálogo de Spotify con la historia de los Grammy.
* **Total de registros:** 30.984 artistas (29.789 con presencia en Spotify y 1.195 presentes únicamente en los Grammy).

| Columna | Tipo | Rol | Justificación de Selección y Relación con Requerimientos |
| :--- | :--- | :--- | :--- |
| `artist_sk` | `BIGSERIAL` | PK | Clave subrogada numérica de 1..n autoincremental. Aísla las claves foráneas del almacén de cambios en texto y acelera los `JOIN`. |
| `artist_bk` | `TEXT` | UK / Clave Natural | Clave de negocio normalizada (minúsculas, sin acentos ni signos de puntuación). Base del algoritmo de integración determinista entre ambas fuentes. |
| `artist_display_name` | `TEXT` | Atributo | Nombre legible original para visualizaciones y títulos en dashboards (R1, R4). |
| `from_spotify` | `BOOLEAN` | Calidad / Linaje | Flag que indica si el artista tiene catálogo en Spotify (`TRUE`) o proviene exclusivamente de los Grammy (`FALSE`). Permite filtrar poblaciones base en R4. |
| `grammy_award_count` | `INTEGER` | Atributo / Métrica | Total acumulado de premios ganados por el artista. Soporta el ordenamiento de los artistas más galardonados en R4 y la segmentación binaria en R1. |
| `spotify_track_count` | `INTEGER` | Atributo / Métrica | Total de apariciones en el catálogo de Spotify (`track × genre`). Permite evaluar la cobertura de catálogo y presencia comercial en R4. |
| `dominant_genre` | `TEXT` | Atributo de Negocio | Género de Spotify más frecuente del artista (con desempate determinista por orden alfabético). Permite clasificar a cada artista en una sola categoría musical para R2. |
| `dominant_genre_family` | `TEXT` | Atributo Jerárquico | Macro-familia a la que pertenece el género dominante (e.g. Rock, Pop, Electronic). Permite agrupaciones ejecutivas sin saturar gráficos en R2. |
| `n_genres` | `INTEGER` | Atributo Analítico | Número de géneros distintos en los que el artista tiene canciones. Mide la versatilidad o transversalidad del artista. |
| `genre_tie` | `BOOLEAN` | Auditoría de Negocio | Indica si hubo un empate de canciones al calcular el género dominante. Da transparencia metodológica a la regla de desempate en R2. |
| `loaded_at` | `TIMESTAMPTZ` | Auditoría ETL | Marca temporal de la carga en el Data Warehouse. |

---

### 2.2. `dim_genre` (Dimensión de Géneros Musicales)
* **Propósito y Grano:** Un registro por género musical único de Spotify (114 géneros).
* **Total de registros:** 114 filas.

| Columna | Tipo | Rol | Justificación de Selección y Relación con Requerimientos |
| :--- | :--- | :--- | :--- |
| `genre_sk` | `BIGSERIAL` | PK | Clave subrogada numérica para uniones de alta velocidad con `fact_track_artist`. |
| `genre` | `TEXT` | UK / Clave Natural | Nombre exacto del género en el dataset de Spotify (e.g., `synth-pop`, `salsa`, `grunge`). |
| `genre_family` | `TEXT` | Jerarquía / Dimensión | Clasificación en una de las 12 macro-familias estándar de la industria. Resuelve el requerimiento R1 (análisis por género sin dispersión de 114 series) y R2. |
| `loaded_at` | `TIMESTAMPTZ` | Auditoría ETL | Marca temporal de carga. |

---

### 2.3. `dim_year` (Dimensión de Tiempo / Años)
* **Propósito y Grano:** Un registro por año calendario histórico de los premios Grammy (1958 a 2019).
* **Total de registros:** 62 filas.

| Columna | Tipo | Rol | Justificación de Selección y Relación con Requerimientos |
| :--- | :--- | :--- | :--- |
| `year_sk` | `INTEGER` | PK | Clave del año (entero natural, e.g. 1984). Al ser una clave universal inmutable, actúa como PK sin necesidad de secuencia adicional. |
| `year` | `INTEGER` | UK / Clave Natural | Año calendario de la edición de los premios Grammy. |
| `decade` | `INTEGER` | Jerarquía Temporal | Década calculada (`year / 10 * 10`, e.g., 1980). Esencial para responder **R3** (evolución del perfil de artistas premiados por décadas: 1950s–2010s). |
| `loaded_at` | `TIMESTAMPTZ` | Auditoría ETL | Marca temporal de carga. |

---

### 2.4. `dim_award_category` (Dimensión de Categorías de Premios)
* **Propósito y Grano:** Un registro por categoría oficial de los premios Grammy (638 categorías a lo largo de 6 décadas).
* **Total de registros:** 638 filas.

| Columna | Tipo | Rol | Justificación de Selección y Relación con Requerimientos |
| :--- | :--- | :--- | :--- |
| `category_sk` | `BIGSERIAL` | PK | Clave subrogada numérica. |
| `category` | `TEXT` | UK / Clave Natural | Nombre crudo de la categoría en el historial de los premios. |
| `category_clean` | `TEXT` | Atributo Limpio | Nombre estandarizado (elimina notas entre paréntesis y unifica variantes de productor). Facilita búsquedas y filtros limpios en dashboards (R4). |
| `category_family` | `TEXT` | Jerarquía Analítica | Área de premiación (e.g., *General Field*, *Pop*, *Rock*, *Jazz*, *Classical*). Permite segmentar análisis de premios por disciplina. |
| `loaded_at` | `TIMESTAMPTZ` | Auditoría ETL | Marca temporal de carga. |

---

### 2.5. `fact_track_artist` (Tabla de Hechos: Catálogo de Canciones)
* **Propósito y Grano:** Una aparición de una canción de Spotify (`track_id`) asociada a un género (`genre_sk`) y a un artista participante (`artist_sk`).
* **Total de registros:** 157.530 filas.
* **Unicidad:** `UNIQUE(track_id, genre_sk, artist_sk)`.

| Columna | Tipo | Rol | Justificación de Selección y Relación con Requerimientos |
| :--- | :--- | :--- | :--- |
| `track_artist_sk` | `BIGSERIAL` | PK | Clave primaria técnica del hecho. |
| `track_id` | `TEXT` | Clave Operacional | Identificador único de Spotify. Permite contar canciones únicas (`COUNT(DISTINCT track_id)` = 111.206). |
| `artist_sk` | `BIGINT` | FK | Relación con `dim_artist`. Conecta la canción con el artista y su estado en los Grammy. |
| `genre_sk` | `BIGINT` | FK | Relación con `dim_genre`. Asocia la canción con su género musical asignado en Spotify. |
| `popularity` | `INTEGER` | Métrica Principal | Popularidad en Spotify ($0 - 100$). Métrica base de **R1** para comparar si los artistas con Grammy son más escuchados que el resto. |
| `danceability` | `DOUBLE PRECISION` | Métrica de Audio | Nivel de adecuación para bailar ($0.0 - 1.0$). Usado en el perfil sonoro comparativo de **R1** y evolución temporal en **R3**. |
| `energy` | `DOUBLE PRECISION` | Métrica de Audio | Medida perceptual de intensidad y actividad ($0.0 - 1.0$). Consumido por **R1** y **R3**. |
| `valence` | `DOUBLE PRECISION` | Métrica de Audio | Positividad musical / alegría ($0.0 - 1.0$). Consumido por el radar/comparador de audio en **R1**. |
| `acousticness` | `DOUBLE PRECISION` | Métrica de Audio | Probabilidad de que la pista sea acústica ($0.0 - 1.0$). Métrica de audio en **R1**. |
| `speechiness` | `DOUBLE PRECISION` | Métrica de Audio | Presencia de palabras habladas ($0.0 - 1.0$). Identifica géneros hablados vs musicales en **R1**. |
| `is_grammy_artist` | `SMALLINT` | Dimensión Degenerada / Flag | `1` si el artista tiene al menos un premio Grammy (método amplio); `0` si no. Segmentación principal de **R1**. |
| `is_grammy_artist_strict` | `SMALLINT` | Calidad / Flag Estricto | `1` si el cruce fue exacto y verificado. Permite análisis de sensibilidad en **R1** sin ruido de empates. |
| `song_key` | `TEXT` | Clave de Deduplicación | Hash normalizado (`artist_bk::track_name_norm`). Permite agrupar versiones y medir el catálogo canónico de canciones. |
| `is_zero_popularity` | `SMALLINT` | Calidad / Flag de Sesgo | `1` si la popularidad es 0. Permite filtrar canciones inactivas en **R1** para que no distorsionen los promedios. |
| `is_primary_song` | `SMALLINT` | Flag de Deduplicación | `1` para el registro canónico de una canción multietiquetada; `0` para duplicados por género. **Vital para evitar ponderar 3 veces un tema en R1**. |
| `batch_id` | `TEXT` | Auditoría / Linaje | Identificador del lote ETL (`dag_id__run_id`). Asegura trazabilidad completa. |
| `loaded_at` | `TIMESTAMPTZ` | Auditoría ETL | Marca temporal de inserción. |

---

### 2.6. `fact_grammy_award` (Tabla de Hechos: Eventos de Premiación Grammy)
* **Propósito y Grano:** Un registro por galardón otorgado en la historia de los Grammy (`year × category × nominee × artist`).
* **Total de registros:** 4.810 filas (100% de los premios históricos del dataset).
* **Unicidad:** `award_bk` (`UNIQUE`).

| Columna | Tipo | Rol | Justificación de Selección y Relación con Requerimientos |
| :--- | :--- | :--- | :--- |
| `grammy_award_sk` | `BIGSERIAL` | PK | Clave primaria técnica del premio. |
| `award_bk` | `TEXT` | UK / Clave Natural | Clave de negocio compuesta (`year|category|nominee|artist`). Garantiza idempotencia ante reejecuciones. |
| `artist_sk` | `BIGINT` | FK (Nullable) | Artista principal acreditado en `dim_artist`. **Es NULL por diseño para los 465 premios sin match en Spotify**, preservando la integridad del historial. |
| `year_sk` | `INTEGER` | FK | Relación con `dim_year`. Habilita cortes analíticos por año y por década (**R3**). |
| `category_sk` | `BIGINT` | FK | Relación con `dim_award_category`. Habilita el drill-down por categoría y familia de premio (**R4**). |
| `title` | `TEXT` | Atributo Descriptivo | Título de la obra o álbum premiado. |
| `nominee` | `TEXT` | Atributo Descriptivo | Nombre del nominado tal cual apareció en el registro oficial. |
| `artist_credit` | `TEXT` | Atributo Descriptivo | Texto textual de los créditos de artistas (e.g., *"Santana Featuring Rob Thomas"*). |
| `workers` | `TEXT` | Atributo Descriptivo | Créditos de producción, arreglos o ingeniería. |
| `winner_flag` | `SMALLINT` | Métrica Aditiva | `1` si es ganador oficial (permite usar `SUM(winner_flag)` o `COUNT(*)` como métrica aditiva). |
| `is_matched_spotify` | `SMALLINT` | Métrica / Calidad | `1` si el premio se vinculó con éxito a un artista de Spotify; `0` si quedó sin coincidencia. Alimenta el indicador de cobertura **KPI-0**. |
| `is_matched_strict` | `SMALLINT` | Calidad Metodológica | `1` si el cruce fue por nombre exacto sin ambigüedad. |
| `is_song_confirmed` | `SMALLINT` | Calidad Metodológica | `1` si además del artista, el título de la canción premiada se verificó dentro del catálogo de Spotify. |
| `match_method` | `TEXT` | Linaje Algorítmico | Algoritmo que produjo el vínculo (`exact`, `fuzzy`, `token`, `collaborative`). Da transparencia técnica. |
| `recognition_tier` | `TEXT` | Segmentación Analítica | Nivel de reconocimiento del premio (`solo_winner`, `collaborative_winner`, `featured_artist`). Soporta **R4**. |
| `batch_id` | `TEXT` | Auditoría / Linaje | Identificador del lote ETL que cargó el registro. |
| `loaded_at` | `TIMESTAMPTZ` | Auditoría ETL | Marca temporal de inserción. |

---

### 2.7. `bridge_award_artist` (Tabla Puente: Créditos Colaborativos)
* **Propósito y Grano:** Resuelve la relación muchos a muchos (*Many-to-Many*) cuando un premio Grammy involucra a más de un artista de Spotify (e.g., colaboraciones, duetos, bandas compuestas).
* **Total de registros:** 2.772 filas (cubre 246 premios con múltiples artistas acreditados).
* **Clave Primaria Compuesta:** `(grammy_award_sk, artist_sk)`.

| Columna | Tipo | Rol | Justificación de Selección y Relación con Requerimientos |
| :--- | :--- | :--- | :--- |
| `grammy_award_sk` | `BIGINT` | PK, FK | Clave foránea al premio en `fact_grammy_award`. Con `ON DELETE CASCADE`. |
| `artist_sk` | `BIGINT` | PK, FK | Clave foránea al artista en `dim_artist`. Permite que cada coautor reciba su crédito en **R4**. |
| `artist_position` | `INTEGER` | Atributo de Crédito | Orden de aparición en el crédito (`1` = artista principal, `2` = colaborador/featuring). |
| `match_method` | `TEXT` | Linaje Algorítmico | Método por el cual se reconoció al coautor individual. |
| `recognition_tier` | `TEXT` | Clasificación | Nivel de crédito asignado a este artista específico en la colaboración. |
| `batch_id` | `TEXT` | Auditoría ETL | Lote de carga. |
| `loaded_at` | `TIMESTAMPTZ` | Auditoría ETL | Marca temporal. |

---

### 2.8. `etl_batch_log` (Control y Auditoría de Cargas)
* **Propósito y Grano:** Un registro por ejecución de pipeline ETL (`batch_id`).
* **Justificación:** Garantiza la **idempotencia** y la trazabilidad operativa requerida por la sección de confiabilidad del Workshop 2.

| Columna | Tipo | Rol | Justificación de Selección |
| :--- | :--- | :--- | :--- |
| `batch_id` | `TEXT` | PK | Identificador único de ejecución (`dag_id__run_id`). |
| `dag_id` | `TEXT` | Auditoría Airflow | Nombre del DAG que ejecutó el proceso (`reliable_music_pipeline`, etc.). |
| `run_id` | `TEXT` | Auditoría Airflow | Identificador de corrida generado por el orquestador. |
| `strategy` | `TEXT` | Política de Carga | Estrategia de carga ejecutada (`replace` controlado transaccional). |
| `target_rows_before` | `JSONB` | Conteo Pre-Carga | Captura el conteo de filas en cada una de las 7 tablas antes de la transacción. |
| `target_rows_after` | `JSONB` | Conteo Post-Carga | Conteo verificado después del commit. Demuestra cero crecimiento no deseado en reejecuciones. |
| `status` | `TEXT` | Estado Operativo | `SUCCESS`, `ROLLED_BACK` o `FAILED`. |
| `started_at` | `TIMESTAMPTZ` | SLA / Monitoreo | Hora de inicio de la transacción de carga. |
| `finished_at` | `TIMESTAMPTZ` | SLA / Monitoreo | Hora de finalización. |
| `notes` | `TEXT` | Bitácora | Resumen de tablas modificadas o advertencias de carga. |

---

## 3. Resumen de Columnas Retiradas en la Auditoría (Por qué NO están)

Para evitar la sobrecarga y reducir el ancho del modelo de **98 a 75 columnas**, se descartaron atributos innecesarios que no alimentaban ningún KPI:

1. **`track_name`, `album_name` en la tabla de hechos:** Eran cadenas de texto repetidas 157.530 veces. La identidad la llevan de forma compacta `track_id` y `song_key`.
2. **`duration_ms`, `explicit`, `liveness`, `loudness`, `tempo`:** Atributos secundarios de audio no consumidos por los requerimientos R1–R4. Permanecen disponibles en la capa staging (`prepared_*.csv`).
3. **Banderas de atípicos (`is_outlier_*`):** Se validan y auditan en las compuertas de Great Expectations sobre staging; no tienen consumidores en el Data Warehouse.
4. **`track_genre` como texto en la tabla de hechos:** Duplicaba `genre_sk`. Se retiró para normalizar el grano y ahorrar espacio.
5. **`from_grammy` en `dim_artist`:** Era redundante con `grammy_award_count > 0`.
6. **`winner` en `fact_grammy_award`:** Duplicaba el valor numérico `winner_flag`.

---

## 4. Conclusión

El diseño resultante cuenta con **exactamente la complejidad necesaria y justificada**:
* No está subdimensionado como un modelo plano que pierde la historia de los Grammy y los análisis temporales.
* No está sobrecargado, pues retiró 23 columnas redundantes en la optimización de ancho.
* Ofrece todas las banderas analíticas (`is_primary_song`, `is_zero_popularity`, `is_matched_strict`) necesarias para generar análisis de calidad profesional en Superset y Power BI.
