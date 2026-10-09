-- ============================================================================
-- KPI queries over the dimensional Data Warehouse (PostgreSQL, music_dw)
-- Parsed by src/analytics.py (marker: -- @name: <query_name>).
-- Each KPI is linked to an analytical requirement (R1-R4) in docs/traceability_matrix.md
-- and is also usable directly in Power BI (docs/powerbi_dashboard.md).
-- All track-level metrics filter is_primary_song = 1 to prevent song inflation.
-- ============================================================================

-- @name: kpi_0_integration_coverage
-- R1/R2/R3 - integration coverage of the cross-source join (strict vs enriched).
SELECT
    COUNT(*)                                                               AS award_rows,
    COUNT(*) FILTER (WHERE is_matched_strict = 1)                          AS matched_strict_rows,
    ROUND(100.0 * COUNT(*) FILTER (WHERE is_matched_strict = 1) / COUNT(*), 2) AS matched_strict_pct,
    SUM(is_matched_spotify)                                                AS matched_enriched_rows,
    ROUND(100.0 * SUM(is_matched_spotify) / COUNT(*), 2)                   AS matched_enriched_pct,
    COUNT(*) FILTER (WHERE artist_sk IS NULL)                              AS rows_without_artist,
    ROUND(100.0 * COUNT(*) FILTER (WHERE artist_sk IS NULL) / COUNT(*), 2) AS rows_without_artist_pct
FROM fact_grammy_award;

-- @name: kpi_0_coverage_by_method
-- R1/R2/R3 - integration coverage broken down by artist match cascade method.
SELECT
    COALESCE(match_method, 'none')                                         AS match_method,
    COUNT(*)                                                               AS award_rows,
    ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 2)                     AS share_pct
FROM fact_grammy_award
GROUP BY match_method
ORDER BY award_rows DESC;

-- @name: kpi_0_coverage_by_decade
-- R1/R2/R3 - integration coverage trend across ceremony decades.
SELECT
    y.decade,
    COUNT(*)                                                               AS award_rows,
    SUM(w.is_matched_spotify)                                              AS matched_rows,
    ROUND(100.0 * SUM(w.is_matched_spotify) / COUNT(*), 2)                 AS match_rate_pct,
    COUNT(*) FILTER (WHERE w.is_matched_strict = 1)                        AS matched_strict_rows,
    ROUND(100.0 * COUNT(*) FILTER (WHERE w.is_matched_strict = 1) / COUNT(*), 2) AS match_rate_strict_pct
FROM fact_grammy_award w
JOIN dim_year y ON y.year_sk = w.year_sk
GROUP BY y.decade
ORDER BY y.decade;

-- @name: kpi_1_popularity_by_grammy_recognition
-- R1 - do Grammy-recognized artists perform differently on Spotify?
WITH base_tracks AS (
    SELECT
        f.artist_sk,
        f.popularity,
        f.danceability,
        f.energy,
        f.valence,
        f.acousticness,
        f.speechiness,
        f.is_grammy_artist,
        f.is_zero_popularity
    FROM fact_track_artist f
    WHERE f.is_primary_song = 1
),
grouped_stats AS (
    SELECT
        'all'                                                              AS basis,
        CASE WHEN is_grammy_artist = 1 THEN 'Grammy-recognized'
             ELSE 'Not Grammy-recognized' END                              AS artist_group,
        is_grammy_artist,
        COUNT(*)                                                           AS n_tracks,
        COUNT(DISTINCT artist_sk)                                          AS n_artists,
        ROUND(AVG(popularity)::numeric, 2)                                 AS mean_popularity,
        ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY popularity)::numeric, 2) AS median_popularity,
        ROUND(PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY popularity)::numeric, 2) AS p25_popularity,
        ROUND(PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY popularity)::numeric, 2) AS p75_popularity,
        ROUND(STDDEV(popularity)::numeric, 2)                              AS stddev_popularity,
        ROUND(AVG(danceability)::numeric, 4)                               AS mean_danceability,
        ROUND(AVG(energy)::numeric, 4)                                     AS mean_energy,
        ROUND(AVG(valence)::numeric, 4)                                    AS mean_valence,
        ROUND(AVG(acousticness)::numeric, 4)                               AS mean_acousticness,
        ROUND(AVG(speechiness)::numeric, 4)                                AS mean_speechiness
    FROM base_tracks
    GROUP BY is_grammy_artist

    UNION ALL

    SELECT
        'excl_zero'                                                        AS basis,
        CASE WHEN is_grammy_artist = 1 THEN 'Grammy-recognized'
             ELSE 'Not Grammy-recognized' END                              AS artist_group,
        is_grammy_artist,
        COUNT(*)                                                           AS n_tracks,
        COUNT(DISTINCT artist_sk)                                          AS n_artists,
        ROUND(AVG(popularity)::numeric, 2)                                 AS mean_popularity,
        ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY popularity)::numeric, 2) AS median_popularity,
        ROUND(PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY popularity)::numeric, 2) AS p25_popularity,
        ROUND(PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY popularity)::numeric, 2) AS p75_popularity,
        ROUND(STDDEV(popularity)::numeric, 2)                              AS stddev_popularity,
        ROUND(AVG(danceability)::numeric, 4)                               AS mean_danceability,
        ROUND(AVG(energy)::numeric, 4)                                     AS mean_energy,
        ROUND(AVG(valence)::numeric, 4)                                    AS mean_valence,
        ROUND(AVG(acousticness)::numeric, 4)                               AS mean_acousticness,
        ROUND(AVG(speechiness)::numeric, 4)                                AS mean_speechiness
    FROM base_tracks
    WHERE is_zero_popularity = 0
    GROUP BY is_grammy_artist
)
SELECT * FROM grouped_stats
ORDER BY basis, is_grammy_artist DESC;

-- @name: kpi_1_artist_level
-- R1 - artist-level popularity distribution for box plots.
SELECT
    f.artist_sk,
    a.artist_display_name,
    CASE WHEN f.is_grammy_artist = 1 THEN 'Grammy-recognized'
         ELSE 'Not Grammy-recognized' END                                  AS artist_group,
    f.is_grammy_artist,
    ROUND(AVG(f.popularity)::numeric, 2)                                   AS mean_popularity,
    COUNT(*)                                                               AS primary_tracks
FROM fact_track_artist f
JOIN dim_artist a ON a.artist_sk = f.artist_sk
WHERE f.is_primary_song = 1
GROUP BY f.artist_sk, a.artist_display_name, f.is_grammy_artist
ORDER BY f.artist_sk;

-- @name: kpi_1_within_genre_diff
-- R1/R2 - within-genre popularity differences and stratified weighted comparison.
WITH strict_grammy_artists AS (
    SELECT DISTINCT artist_sk
    FROM bridge_award_artist
    WHERE match_method = 'exact'
),
artist_genre_pop AS (
    SELECT
        g.genre_family,
        f.artist_sk,
        MAX(f.is_grammy_artist) AS is_grammy_artist,
        CASE WHEN s.artist_sk IS NOT NULL THEN 1 ELSE 0 END AS is_grammy_artist_strict,
        AVG(f.popularity) AS artist_pop
    FROM fact_track_artist f
    JOIN dim_genre g ON g.genre_sk = f.genre_sk
    LEFT JOIN strict_grammy_artists s ON s.artist_sk = f.artist_sk
    WHERE f.is_primary_song = 1
    GROUP BY g.genre_family, f.artist_sk, s.artist_sk
),
family_diffs AS (
    SELECT
        genre_family,
        COUNT(DISTINCT artist_sk) FILTER (WHERE is_grammy_artist = 1) AS n_grammy_artists,
        COUNT(DISTINCT artist_sk) FILTER (WHERE is_grammy_artist = 0) AS n_non_grammy_artists,
        ROUND(AVG(artist_pop) FILTER (WHERE is_grammy_artist = 1)::numeric, 2) AS mean_pop_grammy,
        ROUND(AVG(artist_pop) FILTER (WHERE is_grammy_artist = 0)::numeric, 2) AS mean_pop_non,
        ROUND((AVG(artist_pop) FILTER (WHERE is_grammy_artist = 1) -
               AVG(artist_pop) FILTER (WHERE is_grammy_artist = 0))::numeric, 2) AS diff,
        ROUND(AVG(artist_pop) FILTER (WHERE is_grammy_artist_strict = 1)::numeric, 2) AS mean_pop_grammy_strict,
        ROUND((AVG(artist_pop) FILTER (WHERE is_grammy_artist_strict = 1) -
               AVG(artist_pop) FILTER (WHERE is_grammy_artist = 0))::numeric, 2) AS diff_strict
    FROM artist_genre_pop
    GROUP BY genre_family
    HAVING COUNT(DISTINCT artist_sk) FILTER (WHERE is_grammy_artist = 1) >= 30
),
total_weight AS (
    SELECT SUM(n_grammy_artists) AS sum_w FROM family_diffs
)
SELECT
    f.genre_family,
    f.n_grammy_artists,
    f.n_non_grammy_artists,
    f.mean_pop_grammy,
    f.mean_pop_non,
    f.diff,
    f.mean_pop_grammy_strict,
    f.diff_strict,
    ROUND(SUM(f.diff * f.n_grammy_artists) OVER () / t.sum_w, 2) AS stratified_weighted_diff
FROM family_diffs f
CROSS JOIN total_weight t
ORDER BY f.diff DESC;

-- @name: kpi_2_awards_by_dominant_genre
-- R2 - Grammy awards by artist dominant genre family and award category family.
WITH matched_awards_per_artist AS (
    SELECT DISTINCT
        w.year_sk,
        w.category_sk,
        b.artist_sk,
        a.dominant_genre_family
    FROM bridge_award_artist b
    JOIN fact_grammy_award w ON w.grammy_award_sk = b.grammy_award_sk
    JOIN dim_artist a ON a.artist_sk = b.artist_sk
    WHERE a.dominant_genre_family IS NOT NULL
),
artists_in_family AS (
    SELECT dominant_genre_family, COUNT(*) AS n_artists
    FROM dim_artist
    WHERE dominant_genre_family IS NOT NULL
    GROUP BY dominant_genre_family
),
genre_awards AS (
    SELECT
        m.dominant_genre_family,
        COUNT(DISTINCT (m.year_sk, m.category_sk)) AS awards
    FROM matched_awards_per_artist m
    GROUP BY m.dominant_genre_family
)
SELECT
    g.dominant_genre_family,
    g.awards,
    af.n_artists,
    ROUND(100.0 * g.awards / SUM(g.awards) OVER (), 2)                     AS award_share_pct,
    ROUND(100.0 * g.awards / af.n_artists, 2)                              AS awards_per_100_artists
FROM genre_awards g
JOIN artists_in_family af ON af.dominant_genre_family = g.dominant_genre_family
ORDER BY g.awards DESC;

-- @name: kpi_2_heatmap
-- R2 - Heatmap long format: dominant genre family vs award category family.
SELECT
    a.dominant_genre_family,
    c.category_family,
    COUNT(DISTINCT (w.year_sk, w.category_sk))                             AS awards
FROM bridge_award_artist b
JOIN fact_grammy_award w ON w.grammy_award_sk = b.grammy_award_sk
JOIN dim_artist a ON a.artist_sk = b.artist_sk
JOIN dim_award_category c ON c.category_sk = w.category_sk
WHERE a.dominant_genre_family IS NOT NULL
  AND c.category_family IS NOT NULL
GROUP BY a.dominant_genre_family, c.category_family
ORDER BY awards DESC;

-- @name: kpi_3_awards_and_profile_by_decade
-- R3 - how did the profile of recognized artists evolve over the decades?
WITH matched_artists_decade AS (
    SELECT DISTINCT
        y.decade,
        b.artist_sk
    FROM bridge_award_artist b
    JOIN fact_grammy_award w ON w.grammy_award_sk = b.grammy_award_sk
    JOIN dim_year y ON y.year_sk = w.year_sk
),
artist_primary_audio AS (
    SELECT
        f.artist_sk,
        AVG(f.energy)       AS avg_energy,
        AVG(f.valence)      AS avg_valence,
        AVG(f.danceability) AS avg_danceability,
        AVG(f.acousticness) AS avg_acousticness
    FROM fact_track_artist f
    WHERE f.is_primary_song = 1
    GROUP BY f.artist_sk
),
decade_audio AS (
    SELECT
        m.decade,
        COUNT(DISTINCT m.artist_sk)                                        AS distinct_matched_artists,
        ROUND(AVG(p.avg_energy)::numeric, 4)                              AS mean_energy,
        ROUND(AVG(p.avg_valence)::numeric, 4)                             AS mean_valence,
        ROUND(AVG(p.avg_danceability)::numeric, 4)                         AS mean_danceability,
        ROUND(AVG(p.avg_acousticness)::numeric, 4)                         AS mean_acousticness
    FROM matched_artists_decade m
    JOIN artist_primary_audio p ON p.artist_sk = m.artist_sk
    GROUP BY m.decade
)
SELECT
    y.decade,
    COUNT(*)                                                               AS awards,
    COUNT(DISTINCT w.artist_sk)                                            AS distinct_artists,
    SUM(w.is_matched_spotify)                                              AS matched_awards,
    ROUND(100.0 * SUM(w.is_matched_spotify) / COUNT(*), 2)                 AS matched_share_pct,
    da.mean_energy,
    da.mean_valence,
    da.mean_danceability,
    da.mean_acousticness
FROM fact_grammy_award w
JOIN dim_year y ON y.year_sk = w.year_sk
LEFT JOIN decade_audio da ON da.decade = y.decade
GROUP BY y.decade, da.mean_energy, da.mean_valence, da.mean_danceability, da.mean_acousticness
ORDER BY y.decade;

-- @name: kpi_3_awards_per_year
-- R3 - award volume and matched share over time (trend line of the dashboard).
SELECT
    y.year,
    COUNT(*)                                                               AS awards,
    COUNT(DISTINCT w.artist_sk)                                            AS recognized_artists,
    SUM(w.is_matched_spotify)                                              AS matched_awards,
    ROUND(100.0 * SUM(w.is_matched_spotify) / COUNT(*), 2)                 AS matched_share_pct
FROM fact_grammy_award w
JOIN dim_year y ON y.year_sk = w.year_sk
GROUP BY y.year
ORDER BY y.year;

-- @name: kpi_3_awards_by_family_decade
-- R3 - distribution of awards across category families by decade.
SELECT
    y.decade,
    c.category_family,
    COUNT(*)                                                               AS awards
FROM fact_grammy_award w
JOIN dim_year y ON y.year_sk = w.year_sk
JOIN dim_award_category c ON c.category_sk = w.category_sk
GROUP BY y.decade, c.category_family
ORDER BY y.decade, awards DESC;

-- @name: kpi_4_top_awarded_artists_on_spotify
-- R1/R4 - most awarded artists measured inside the Spotify catalog.
WITH artist_awards AS (
    SELECT
        b.artist_sk,
        COUNT(DISTINCT (w.year_sk, w.category_sk)) AS awards,
        MIN(y.year)                                AS first_award_year,
        MAX(y.year)                                AS last_award_year
    FROM bridge_award_artist b
    JOIN fact_grammy_award w ON w.grammy_award_sk = b.grammy_award_sk
    JOIN dim_year y ON y.year_sk = w.year_sk
    GROUP BY b.artist_sk
),
ranked AS (
    SELECT
        a.artist_display_name,
        aw.awards,
        aw.first_award_year,
        aw.last_award_year,
        COALESCE(a.spotify_track_count, 0)         AS spotify_track_count,
        CASE WHEN a.from_spotify THEN 1 ELSE 0 END AS in_spotify,
        DENSE_RANK() OVER (ORDER BY aw.awards DESC) AS rank
    FROM artist_awards aw
    JOIN dim_artist a ON a.artist_sk = aw.artist_sk
    WHERE a.from_spotify = TRUE
      AND a.artist_bk NOT IN ('various artists', 'original cast')
)
SELECT
    artist_display_name,
    awards,
    first_award_year,
    last_award_year,
    spotify_track_count,
    in_spotify,
    rank
FROM ranked
WHERE rank <= 10
ORDER BY rank, awards DESC, artist_display_name;

-- @name: kpi_4_top_awarded_all
-- R4 - all top awarded Grammy artists including those absent from Spotify.
WITH artist_awards AS (
    SELECT
        b.artist_sk,
        COUNT(DISTINCT (w.year_sk, w.category_sk)) AS awards,
        MIN(y.year)                                AS first_award_year,
        MAX(y.year)                                AS last_award_year
    FROM bridge_award_artist b
    JOIN fact_grammy_award w ON w.grammy_award_sk = b.grammy_award_sk
    JOIN dim_year y ON y.year_sk = w.year_sk
    GROUP BY b.artist_sk
),
ranked AS (
    SELECT
        a.artist_display_name,
        aw.awards,
        aw.first_award_year,
        aw.last_award_year,
        COALESCE(a.spotify_track_count, 0)         AS spotify_track_count,
        CASE WHEN a.from_spotify THEN 1 ELSE 0 END AS in_spotify,
        DENSE_RANK() OVER (ORDER BY aw.awards DESC) AS rank
    FROM artist_awards aw
    JOIN dim_artist a ON a.artist_sk = aw.artist_sk
    WHERE a.artist_bk NOT IN ('various artists', 'original cast')
)
SELECT
    artist_display_name,
    awards,
    first_award_year,
    last_award_year,
    spotify_track_count,
    in_spotify,
    rank
FROM ranked
WHERE rank <= 20
ORDER BY rank, awards DESC, artist_display_name;
