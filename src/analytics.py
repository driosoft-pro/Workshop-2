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
import pandas as pd
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
