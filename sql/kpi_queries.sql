-- ============================================================================
-- KPI queries over the dimensional Data Warehouse (PostgreSQL, music_dw)
-- Parsed by src/analytics.py (marker: -- @name: <query_name>).
-- Each KPI is linked to an analytical requirement (AR) in docs/traceability_matrix.md
-- and is also usable directly in Power BI (docs/powerbi_dashboard.md).
-- ============================================================================

-- @name: kpi_0_integration_coverage
-- AR1/AR2/AR3 - integration coverage of the cross-source join.
SELECT
    COUNT(*)                                                        AS award_rows,
    SUM(is_matched_spotify)                                         AS matched_award_rows,
    ROUND(100.0 * SUM(is_matched_spotify) / COUNT(*), 2)            AS matched_award_pct,
    ROUND(100.0 * COUNT(*) FILTER (WHERE artist_sk IS NULL) / COUNT(*), 2) AS rows_without_artist_pct
FROM fact_grammy_award;

-- @name: kpi_1_popularity_by_grammy_recognition
-- AR1 - do Grammy-recognized artists perform differently on Spotify?
SELECT
    CASE WHEN a.from_grammy THEN 'Grammy-recognized'
         ELSE 'Not Grammy-recognized' END                          AS artist_group,
    COUNT(*)                                                       AS track_listings,
    COUNT(DISTINCT f.track_id)                                     AS distinct_tracks,
    ROUND(AVG(f.popularity)::numeric, 2)                           AS avg_popularity,
    ROUND(AVG(f.energy)::numeric, 4)                               AS avg_energy,
    ROUND(AVG(f.danceability)::numeric, 4)                         AS avg_danceability,
    ROUND(AVG(f.valence)::numeric, 4)                              AS avg_valence
FROM fact_track_artist f
JOIN dim_artist a ON a.artist_sk = f.artist_sk
GROUP BY 1
ORDER BY avg_popularity DESC;

-- @name: kpi_1_genre_split
-- AR1/AR2 - popularity comparison inside the highest-volume Spotify genres.
WITH genre_totals AS (
    SELECT g.genre, COUNT(*) AS listing_count
    FROM fact_track_artist f
    JOIN dim_genre g ON g.genre_sk = f.genre_sk
    GROUP BY g.genre
    ORDER BY COUNT(*) DESC
    LIMIT 12
)
SELECT
    g.genre,
    COUNT(*)                                                       AS track_listings,
    ROUND(AVG(f.popularity) FILTER (WHERE a.from_grammy)::numeric, 2)  AS avg_popularity_grammy_artist,
    ROUND(AVG(f.popularity) FILTER (WHERE NOT a.from_grammy)::numeric, 2) AS avg_popularity_other_artist
FROM fact_track_artist f
JOIN dim_genre g ON g.genre_sk = f.genre_sk
JOIN dim_artist a ON a.artist_sk = f.artist_sk
WHERE g.genre IN (SELECT genre FROM genre_totals)
GROUP BY g.genre
ORDER BY track_listings DESC;

-- @name: kpi_2_awards_by_dominant_genre
-- AR2 - which Spotify genres dominate among Grammy-recognized artists?
WITH artist_genre AS (
    SELECT
        f.artist_sk,
        g.genre,
        COUNT(*) AS listing_count,
        ROW_NUMBER() OVER (
            PARTITION BY f.artist_sk ORDER BY COUNT(*) DESC, g.genre
        ) AS genre_rank
    FROM fact_track_artist f
    JOIN dim_genre g ON g.genre_sk = f.genre_sk
    GROUP BY f.artist_sk, g.genre
),
dominant AS (
    SELECT artist_sk, genre FROM artist_genre WHERE genre_rank = 1
)
SELECT
    d.genre                                        AS dominant_spotify_genre,
    COUNT(*)                                       AS grammy_awards,
    COUNT(DISTINCT w.artist_sk)                    AS recognized_artists,
    ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 2) AS award_share_pct
FROM fact_grammy_award w
JOIN dominant d ON d.artist_sk = w.artist_sk
GROUP BY d.genre
ORDER BY grammy_awards DESC
LIMIT 15;

-- @name: kpi_3_awards_and_profile_by_decade
-- AR3 - how did the profile of recognized artists evolve over the decades?
WITH artist_profile AS (
    SELECT
        artist_sk,
        ROUND(AVG(popularity)::numeric, 2)   AS avg_artist_popularity,
        ROUND(AVG(energy)::numeric, 4)       AS avg_artist_energy
    FROM fact_track_artist
    GROUP BY artist_sk
)
SELECT
    y.decade,
    COUNT(*)                                                        AS grammy_awards,
    COUNT(DISTINCT w.artist_sk)                                     AS recognized_artists,
    ROUND(AVG(p.avg_artist_popularity)::numeric, 2)                 AS avg_artist_popularity,
    ROUND(AVG(p.avg_artist_energy)::numeric, 4)                     AS avg_artist_energy
FROM fact_grammy_award w
JOIN dim_year y ON y.year_sk = w.year_sk
LEFT JOIN artist_profile p ON p.artist_sk = w.artist_sk
GROUP BY y.decade
ORDER BY y.decade;

-- @name: kpi_3_awards_per_year
-- AR3 - award volume over time (trend line of the dashboard).
SELECT
    y.year,
    COUNT(*)                             AS grammy_awards,
    COUNT(DISTINCT w.artist_sk)          AS recognized_artists,
    SUM(w.is_matched_spotify)            AS matched_award_rows
FROM fact_grammy_award w
JOIN dim_year y ON y.year_sk = w.year_sk
GROUP BY y.year
ORDER BY y.year;

-- @name: kpi_4_top_awarded_artists_on_spotify
-- AR1/AR4 - most awarded artists measured inside the Spotify catalog.
-- Only award rows whose artist is present in the Spotify catalog are counted,
-- and the "(Various Artists)" credit is excluded because it is an aggregate
-- credit rather than a single performing artist.
WITH artist_track_profile AS (
    SELECT artist_sk, ROUND(AVG(popularity)::numeric, 2) AS avg_track_popularity
    FROM fact_track_artist
    GROUP BY artist_sk
)
SELECT
    a.artist_display_name,
    COUNT(*)                              AS grammy_awards,
    MIN(y.year)                           AS first_award_year,
    MAX(y.year)                           AS last_award_year,
    a.spotify_track_count,
    p.avg_track_popularity
FROM fact_grammy_award w
JOIN dim_artist a ON a.artist_sk = w.artist_sk
JOIN dim_year y ON y.year_sk = w.year_sk
LEFT JOIN artist_track_profile p ON p.artist_sk = w.artist_sk
WHERE w.is_matched_spotify = 1
  AND a.artist_bk <> 'various artists'
GROUP BY a.artist_display_name, a.spotify_track_count, p.avg_track_popularity
ORDER BY grammy_awards DESC, avg_track_popularity DESC NULLS LAST
LIMIT 10;
