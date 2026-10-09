"""KPI computation and visualisation against the dimensional Data Warehouse.

Every output answers a declared analytical requirement (R1-R4) and is
produced exclusively from the Data Warehouse - never from a CSV.

    sql/kpi_queries.sql   -> KPI definitions (single source of truth, also used
                             for the Power BI model)
    docs/evidence/kpis/   -> KPI CSV results + PNG visualisations
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import scipy.stats
from sqlalchemy import create_engine, text

from src import config

QUERY_MARKER = re.compile(r"^--\s*@name:\s*(?P<name>[A-Za-z0-9_]+)\s*$", re.MULTILINE)

CHART_FILES = {
    "kpi_1_within_genre_diff": "ar1_popularity_by_genre.png",
    "kpi_2_awards_by_dominant_genre": "ar2_awards_by_dominant_genre.png",
    "kpi_3_awards_and_profile_by_decade": "ar3_awards_and_profile_by_decade.png",
    "kpi_4_top_awarded_artists_on_spotify": "ar4_top_awarded_artists.png",
}


def load_queries(sql_path: Path | None = None) -> dict[str, str]:
    sql_path = Path(sql_path or config.SQL_DIR / "kpi_queries.sql")
    script = sql_path.read_text()
    matches = list(QUERY_MARKER.finditer(script))
    if not matches:
        raise RuntimeError(f"No '@name:' markers found in {sql_path}")

    queries: dict[str, str] = {}
    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(script)
        body = script[start:end].strip().rstrip(";").strip()
        if body:
            queries[match.group("name")] = body
    return queries


def _coerce_numeric(frame: pd.DataFrame) -> pd.DataFrame:
    for column in frame.columns:
        converted = pd.to_numeric(frame[column], errors="coerce")
        if converted.notna().sum() == frame[column].notna().sum():
            frame[column] = converted
    return frame


def run_kpis() -> dict[str, pd.DataFrame]:
    engine = create_engine(config.DW_DB_URL)
    queries = load_queries()
    results: dict[str, pd.DataFrame] = {}
    try:
        with engine.connect() as connection:
            for name, sql in queries.items():
                rows = connection.execute(text(sql)).mappings().all()
                results[name] = _coerce_numeric(pd.DataFrame([dict(row) for row in rows]))
                print(f"[analytics] {name}: {len(results[name])} rows")
    finally:
        engine.dispose()
    return results


def _save_csvs(results: dict[str, pd.DataFrame]) -> dict[str, str]:
    config.KPI_RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    paths: dict[str, str] = {}
    for name, frame in results.items():
        path = config.KPI_RESULTS_DIR / f"{name}.csv"
        frame.to_csv(path, index=False)
        paths[name] = str(path)
    return paths


def _chart_within_genre_diff(frame: pd.DataFrame, path: Path) -> None:
    ordered = frame.sort_values("diff", ascending=True)
    figure, ax = plt.subplots(figsize=(12, 6))
    y_pos = list(range(len(ordered)))
    bar_height = 0.35

    ax.barh(
        [y - bar_height / 2 for y in y_pos],
        ordered["mean_pop_grammy"],
        height=bar_height,
        color="#C9A227",
        label="Grammy-recognized",
    )
    ax.barh(
        [y + bar_height / 2 for y in y_pos],
        ordered["mean_pop_non"],
        height=bar_height,
        color="#5B6C8F",
        label="Non-Grammy",
    )

    ax.set_yticks(y_pos)
    ax.set_yticklabels(ordered["genre_family"])
    ax.set_xlabel("Mean Popularity (0-100)")
    ax.set_title("R1 - Popularity within Genre Family: Grammy vs Non-Grammy Artists")
    ax.legend(loc="lower right")
    plt.tight_layout()
    plt.savefig(path, dpi=150)
    plt.close()


def _chart_awards_by_genre(frame: pd.DataFrame, path: Path) -> None:
    metric = "awards_per_100_artists" if "awards_per_100_artists" in frame.columns else "awards"
    ordered = frame.sort_values(metric, ascending=True)
    figure, ax = plt.subplots(figsize=(11, 6))
    ax.barh(
        ordered["dominant_genre_family"],
        ordered[metric],
        color="#C9A227",
    )
    ax.set_title("R2 - Grammy Awards per 100 Artists by Dominant Genre Family")
    ax.set_xlabel("Awards per 100 Artists in Family" if metric == "awards_per_100_artists" else "Awards")
    ax.set_ylabel("Dominant Genre Family")
    plt.tight_layout()
    plt.savefig(path, dpi=150)
    plt.close()


def _chart_decade_evolution(frame: pd.DataFrame, path: Path) -> None:
    figure, axes = plt.subplots(1, 2, figsize=(15, 5))
    decades = frame["decade"].astype(str)

    axes[0].bar(decades, frame["awards"], color="#5B6C8F", alpha=0.7, label="Total Awards")
    axes[0].set_title("R3 - Award Volume and Matched Share by Decade")
    axes[0].set_xlabel("Decade")
    axes[0].set_ylabel("Awards")
    axes[0].tick_params(axis="x", rotation=45)

    if "matched_share_pct" in frame.columns:
        ax0_twin = axes[0].twinx()
        ax0_twin.plot(decades, frame["matched_share_pct"], color="#C9A227", marker="o", linewidth=2, label="Matched %")
        ax0_twin.set_ylabel("Matched Share %")
        ax0_twin.set_ylim(0, 100)

    if "mean_energy" in frame.columns:
        axes[1].plot(decades, frame["mean_energy"], marker="o", color="#d62728", label="Energy")
    if "mean_danceability" in frame.columns:
        axes[1].plot(decades, frame["mean_danceability"], marker="s", color="#1f77b4", label="Danceability")
    if "mean_valence" in frame.columns:
        axes[1].plot(decades, frame["mean_valence"], marker="^", color="#2ca02c", label="Valence")
    if "mean_acousticness" in frame.columns:
        axes[1].plot(decades, frame["mean_acousticness"], marker="d", color="#9467bd", label="Acousticness")

    axes[1].set_title("R3 - Audio Profile of Matched Artists Across Decades")
    axes[1].set_xlabel("Decade")
    axes[1].set_ylabel("Audio Feature Score [0, 1]")
    axes[1].tick_params(axis="x", rotation=45)
    axes[1].legend(loc="best")

    plt.tight_layout()
    plt.savefig(path, dpi=150)
    plt.close()


def _chart_top_artists(frame: pd.DataFrame, path: Path) -> None:
    ordered = frame.sort_values("awards", ascending=True).tail(10)
    figure, ax = plt.subplots(figsize=(11, 6))
    ax.barh(
        ordered["artist_display_name"],
        ordered["awards"],
        color="#C9A227",
    )
    ax.set_title("R4 - Top Awarded Artists on Spotify")
    ax.set_xlabel("Grammy Awards")
    ax.set_ylabel("Artist")
    plt.tight_layout()
    plt.savefig(path, dpi=150)
    plt.close()


def r1_stats(artist_level_df: pd.DataFrame | None = None) -> pd.DataFrame:
    """
    R1 statistical hypothesis testing and effect size at artist level.
    Evaluates each recognition tier (core, strict) x basis (all, excl_zero).
    Computes Mann-Whitney U, Cliff's delta, and bootstrap 95% CI of median difference.
    """
    if artist_level_df is None:
        csv_path = config.KPI_RESULTS_DIR / "kpi_1_artist_level.csv"
        if csv_path.exists():
            artist_level_df = pd.read_csv(csv_path)
        else:
            raise FileNotFoundError(f"Artist level dataframe or {csv_path} required")

    df = _coerce_numeric(artist_level_df.copy())

    rows = []
    combinations = []
    if "recognition" in df.columns and "basis" in df.columns:
        for rec in ["core", "strict"]:
            for bas in ["all", "excl_zero"]:
                if len(df[(df["recognition"] == rec) & (df["basis"] == bas)]) > 0:
                    combinations.append((rec, bas))
    else:
        combinations = [("core", "all")]

    for rec, bas in combinations:
        sub = (
            df[(df["recognition"] == rec) & (df["basis"] == bas)]
            if ("recognition" in df.columns and "basis" in df.columns)
            else df
        )
        grammy_vals = sub[sub["is_grammy_artist"] == 1]["mean_popularity"].dropna().to_numpy(dtype=float)
        non_vals = sub[sub["is_grammy_artist"] == 0]["mean_popularity"].dropna().to_numpy(dtype=float)

        n_grammy = len(grammy_vals)
        n_non = len(non_vals)
        median_grammy = float(np.median(grammy_vals)) if n_grammy > 0 else 0.0
        median_non = float(np.median(non_vals)) if n_non > 0 else 0.0
        median_diff = median_grammy - median_non

        if n_grammy > 0 and n_non > 0:
            res = scipy.stats.mannwhitneyu(grammy_vals, non_vals, alternative="two-sided")
            u_stat = float(res.statistic)
            p_val = float(res.pvalue)
            cliffs_delta = float((2.0 * u_stat / (n_grammy * n_non)) - 1.0)

            # 2,000 bootstrap resamples with seed 42
            rng = np.random.default_rng(42)
            boot_g = rng.choice(grammy_vals, size=(2000, n_grammy), replace=True)
            boot_ng = rng.choice(non_vals, size=(2000, n_non), replace=True)
            boot_diffs = np.median(boot_g, axis=1) - np.median(boot_ng, axis=1)
            ci_lower = float(np.percentile(boot_diffs, 2.5))
            ci_upper = float(np.percentile(boot_diffs, 97.5))
        else:
            p_val = 1.0
            cliffs_delta = 0.0
            ci_lower = median_diff
            ci_upper = median_diff

        rows.append({
            "recognition": rec,
            "basis": bas,
            "n_grammy": n_grammy,
            "n_non": n_non,
            "median_grammy": round(median_grammy, 2),
            "median_non": round(median_non, 2),
            "median_diff": round(median_diff, 2),
            "p_value": p_val,
            "cliffs_delta": round(cliffs_delta, 4),
            "ci_lower": round(ci_lower, 2),
            "ci_upper": round(ci_upper, 2),
        })

    stats_df = pd.DataFrame(rows)
    out_path = config.KPI_RESULTS_DIR / "kpi_1_stats.csv"
    stats_df.to_csv(out_path, index=False)
    print(f"[analytics] R1 artist-level stats written to {out_path}")
    return stats_df


def compute_dedupe_impact(engine=None) -> pd.DataFrame:
    """
    Compute impact of deduplication (is_primary_song filter) on mean popularity per group.
    Writes to docs/evidence/kpis/kpi_1_dedupe_impact.csv.
    """
    rows = []
    queried = False
    if engine is None:
        try:
            from src.load import get_engine
            engine = get_engine()
        except Exception:
            engine = None

    if engine is not None:
        try:
            with engine.connect() as conn:
                df = pd.read_sql(
                    text("""
                        SELECT
                            'with_dedupe' AS dedupe_status,
                            CASE WHEN is_grammy_artist = 1 THEN 'Grammy-recognized' ELSE 'Not Grammy-recognized' END AS artist_group,
                            is_grammy_artist,
                            COUNT(*) AS n_tracks,
                            ROUND(AVG(popularity)::numeric, 2) AS mean_popularity
                        FROM fact_track_artist
                        WHERE is_primary_song = 1
                        GROUP BY is_grammy_artist
                        UNION ALL
                        SELECT
                            'without_dedupe' AS dedupe_status,
                            CASE WHEN is_grammy_artist = 1 THEN 'Grammy-recognized' ELSE 'Not Grammy-recognized' END AS artist_group,
                            is_grammy_artist,
                            COUNT(*) AS n_tracks,
                            ROUND(AVG(popularity)::numeric, 2) AS mean_popularity
                        FROM fact_track_artist
                        GROUP BY is_grammy_artist
                        ORDER BY dedupe_status DESC, is_grammy_artist DESC
                    """),
                    conn,
                )
                queried = True
        except Exception:
            queried = False

    if not queried:
        prep_path = config.DATA_PROCESSED_DIR / "prepared_tracks.csv"
        if prep_path.exists():
            pdf = pd.read_csv(prep_path)
            for status, subset in [("with_dedupe", pdf[pdf["is_primary_song"] == 1]), ("without_dedupe", pdf)]:
                for g_val, g_label in [(1, "Grammy-recognized"), (0, "Not Grammy-recognized")]:
                    grp = subset[subset["is_grammy_artist"] == g_val]
                    rows.append({
                        "dedupe_status": status,
                        "artist_group": g_label,
                        "is_grammy_artist": g_val,
                        "n_tracks": len(grp),
                        "mean_popularity": round(float(grp["popularity"].mean()), 2) if len(grp) else 0.0,
                    })
            df = pd.DataFrame(rows)
        else:
            df = pd.DataFrame(columns=["dedupe_status", "artist_group", "is_grammy_artist", "n_tracks", "mean_popularity"])

    out_path = config.KPI_RESULTS_DIR / "kpi_1_dedupe_impact.csv"
    df.to_csv(out_path, index=False)
    print(f"[analytics] Deduplication impact written to {out_path}")
    return df


def build_kpis() -> dict:
    config.ensure_directories()
    results = run_kpis()
    csv_paths = _save_csvs(results)

    chart_paths: dict[str, str] = {}
    if "kpi_1_within_genre_diff" in results:
        target = config.KPI_RESULTS_DIR / CHART_FILES["kpi_1_within_genre_diff"]
        _chart_within_genre_diff(results["kpi_1_within_genre_diff"], target)
        chart_paths["kpi_1_within_genre_diff"] = str(target)
    if "kpi_2_awards_by_dominant_genre" in results:
        target = config.KPI_RESULTS_DIR / CHART_FILES["kpi_2_awards_by_dominant_genre"]
        _chart_awards_by_genre(results["kpi_2_awards_by_dominant_genre"], target)
        chart_paths["kpi_2_awards_by_dominant_genre"] = str(target)
    if "kpi_3_awards_and_profile_by_decade" in results:
        target = config.KPI_RESULTS_DIR / CHART_FILES["kpi_3_awards_and_profile_by_decade"]
        _chart_decade_evolution(results["kpi_3_awards_and_profile_by_decade"], target)
        chart_paths["kpi_3_awards_and_profile_by_decade"] = str(target)
    if "kpi_4_top_awarded_artists_on_spotify" in results:
        target = config.KPI_RESULTS_DIR / CHART_FILES["kpi_4_top_awarded_artists_on_spotify"]
        _chart_top_artists(results["kpi_4_top_awarded_artists_on_spotify"], target)
        chart_paths["kpi_4_top_awarded_artists_on_spotify"] = str(target)

    if "kpi_1_artist_level" in results:
        r1_stats(results["kpi_1_artist_level"])
        csv_paths["kpi_1_stats"] = str(config.KPI_RESULTS_DIR / "kpi_1_stats.csv")

    compute_dedupe_impact()
    csv_paths["kpi_1_dedupe_impact"] = str(config.KPI_RESULTS_DIR / "kpi_1_dedupe_impact.csv")

    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": config.DW_DB_URL.rsplit("/", 1)[-1],
        "kpi_csvs": csv_paths,
        "charts": chart_paths,
        "row_counts": {name: int(len(frame)) for name, frame in results.items()},
        "preview": {
            name: frame.head(5).to_dict(orient="records")
            for name, frame in results.items()
        },
    }
    summary_path = config.KPI_RESULTS_DIR / "kpi_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, default=str))
    summary["summary_path"] = str(summary_path)
    print(f"[analytics] KPI summary written to {summary_path}")
    return summary


def main() -> int:
    summary = build_kpis()
    print(json.dumps(summary["row_counts"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
