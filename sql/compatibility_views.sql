-- ============================================================================
-- Backward compatibility views for analytical consumers / legacy tools
-- Preserves column names and denormalized joins without polluting the core DW.
-- ============================================================================

CREATE OR REPLACE VIEW vw_fact_track_artist AS
SELECT 
    f.track_artist_sk,
    f.track_id,
    f.artist_sk,
    f.genre_sk,
    g.genre AS track_genre,
    g.genre_family,
    a.artist_display_name,
    f.popularity,
    f.danceability,
    f.energy,
    f.valence,
    f.acousticness,
    f.speechiness,
    f.is_grammy_artist,
    f.is_grammy_artist_strict,
    f.song_key,
    f.is_zero_popularity,
    f.is_primary_song,
    f.batch_id,
    f.loaded_at
FROM fact_track_artist f
JOIN dim_genre g ON g.genre_sk = f.genre_sk
JOIN dim_artist a ON a.artist_sk = f.artist_sk;

CREATE OR REPLACE VIEW vw_fact_grammy_award AS
SELECT 
    w.grammy_award_sk,
    w.award_bk,
    w.artist_sk,
    w.year_sk,
    y.year,
    y.decade,
    w.category_sk,
    c.category,
    c.category_family,
    COALESCE(a.artist_display_name, 'Unmatched / No Artist') AS artist_name,
    w.winner_flag,
    w.is_matched_spotify,
    w.is_matched_strict,
    w.is_song_confirmed,
    w.match_method,
    w.recognition_tier,
    w.batch_id,
    w.loaded_at
FROM fact_grammy_award w
JOIN dim_year y ON y.year_sk = w.year_sk
JOIN dim_award_category c ON c.category_sk = w.category_sk
LEFT JOIN dim_artist a ON a.artist_sk = w.artist_sk;
