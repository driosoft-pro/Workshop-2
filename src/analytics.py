"""KPI computation and visualisation against the dimensional Data Warehouse.

Every output answers a declared analytical requirement (AR1-AR4) and is
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
    "kpi_1_genre_split": "ar1_popularity_by_genre.png",
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


def _chart_genre_split(frame: pd.DataFrame, path: Path) -> None:
    plot = frame.plot(
        x="genre",
        y=["avg_popularity_grammy_artist", "avg_popularity_other_artist"],
        kind="bar",
        figsize=(13, 6),
        color=["#1f77b4", "#ff7f0e"],
    )
    plot.set_title("AR1 - Average Spotify popularity by genre\n"
                   "Grammy-recognized vs other artists")
    plot.set_xlabel("Spotify genre")
    plot.set_ylabel("Average popularity (0-100)")
    plot.tick_params(axis="x", rotation=60)
    plot.legend(["Grammy-recognized artists", "Other artists"])
    plt.tight_layout()
    plt.savefig(path, dpi=150)
    plt.close()


def _chart_awards_by_genre(frame: pd.DataFrame, path: Path) -> None:
    ordered = frame.sort_values("grammy_awards")
    ax = ordered.plot(
        x="dominant_spotify_genre",
        y="grammy_awards",
        kind="barh",
        figsize=(10, 7),
        color="#2ca02c",
        legend=False,
    )
    ax.set_title("AR2 - Grammy awards by the awardee's dominant Spotify genre")
    ax.set_xlabel("Grammy awards")
    ax.set_ylabel("Dominant Spotify genre")
    plt.tight_layout()
    plt.savefig(path, dpi=150)
    plt.close()


def _chart_decade_evolution(frame: pd.DataFrame, path: Path) -> None:
    figure, axes = plt.subplots(1, 2, figsize=(14, 5))
    axes[0].bar(frame["decade"].astype(str), frame["grammy_awards"], color="#9467bd")
    axes[0].set_title("AR3 - Grammy awards per decade")
    axes[0].set_xlabel("Decade")
    axes[0].set_ylabel("Awards")
    axes[0].tick_params(axis="x", rotation=45)

    axes[1].plot(
        frame["decade"].astype(str),
        frame["avg_artist_popularity"],
        marker="o",
        color="#1f77b4",
        label="Avg popularity",
    )
    axes[1].plot(
        frame["decade"].astype(str),
        (frame["avg_artist_energy"].astype(float) * 100).round(2),
        marker="s",
        color="#d62728",
        label="Avg energy (x100)",
    )
    axes[1].set_title("AR3 - Audio profile of recognized artists")
    axes[1].set_xlabel("Decade")
    axes[1].set_ylabel("Score")
    axes[1].tick_params(axis="x", rotation=45)
    axes[1].legend()
    figure.suptitle("AR3 - Evolution of Grammy-recognized artists over time")
    plt.tight_layout()
    plt.savefig(path, dpi=150)
    plt.close()


def _chart_top_artists(frame: pd.DataFrame, path: Path) -> None:
    ordered = frame.sort_values("grammy_awards")
    ax = ordered.plot(
        x="artist_display_name",
        y="grammy_awards",
        kind="barh",
        figsize=(10, 6),
        color="#e377c2",
        legend=False,
    )
    ax.set_title("AR4 - Most awarded artists present in the Spotify catalog")
    ax.set_xlabel("Grammy awards")
    ax.set_ylabel("Artist")
    plt.tight_layout()
    plt.savefig(path, dpi=150)
    plt.close()


def build_kpis() -> dict:
    config.ensure_directories()
    results = run_kpis()
    csv_paths = _save_csvs(results)

    chart_paths: dict[str, str] = {}
    if "kpi_1_genre_split" in results:
        target = config.KPI_RESULTS_DIR / CHART_FILES["kpi_1_genre_split"]
        _chart_genre_split(results["kpi_1_genre_split"], target)
        chart_paths["kpi_1_genre_split"] = str(target)
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
