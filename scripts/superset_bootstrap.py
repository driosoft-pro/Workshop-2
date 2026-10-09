"""Bootstrap the Apache Superset BI layer for Workshop-2.

Creates (idempotently) on top of the analytical Data Warehouse ``music_dw``:

* database connection  ``music_dw``
* virtual datasets     ``kpi_*`` (SQL taken from sql/kpi_queries.sql)
* dataset metrics      (aggregations used by the charts)
* charts               one or more per analytical requirement R1-R4
* dashboard            "Workshop-2 - KPIs (R1-R4)"

Every chart query is executed through the Superset API as a smoke test, so a
failing KPI query fails this script (exit code 1).

Usage (inside the compose network):
    podman compose --profile debug run --rm superset-bootstrap
On the host, with the UI published on :8088:
    SUPERSET_URL=http://localhost:8088 python -m scripts.superset_bootstrap
"""

from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
import urllib.request
from http.cookiejar import CookieJar

BASE_URL = os.environ.get("SUPERSET_URL", "http://localhost:8088").rstrip("/")
ADMIN_USER = os.environ.get("SUPERSET_ADMIN_USER", "admin")
ADMIN_PASSWORD = os.environ.get("SUPERSET_ADMIN_PASSWORD", "admin")
DW_URI = os.environ.get(
    "SUPERSET_DW_SQLALCHEMY_URI",
    "postgresql+psycopg2://music:music@music-postgres:5432/music_dw",
)
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
KPI_SQL_PATH = os.path.join(PROJECT_ROOT, "sql", "kpi_queries.sql")
DASHBOARD_TITLE = "Workshop-2 - KPIs (R1-R4)"

# metric_name -> SQL aggregate used by the charts
DATASET_SPECS: dict[str, dict[str, str]] = {
    "kpi_0_integration_coverage": {
        "award_rows": "SUM(award_rows)",
        "matched_strict_rows": "SUM(matched_strict_rows)",
        "matched_strict_pct": "MAX(matched_strict_pct)",
        "matched_enriched_rows": "SUM(matched_enriched_rows)",
        "matched_enriched_pct": "MAX(matched_enriched_pct)",
        "rows_without_artist_pct": "MAX(rows_without_artist_pct)",
    },
    "kpi_0_coverage_by_method": {
        "award_rows": "SUM(award_rows)",
        "share_pct": "MAX(share_pct)",
    },
    "kpi_0_coverage_by_decade": {
        "award_rows": "SUM(award_rows)",
        "matched_rows": "SUM(matched_rows)",
        "match_rate_pct": "MAX(match_rate_pct)",
        "matched_strict_rows": "SUM(matched_strict_rows)",
        "match_rate_strict_pct": "MAX(match_rate_strict_pct)",
    },
    "kpi_1_popularity_by_grammy_recognition": {
        "n_tracks": "SUM(n_tracks)",
        "n_artists": "SUM(n_artists)",
        "mean_popularity": "AVG(mean_popularity)",
        "median_popularity": "AVG(median_popularity)",
        "mean_danceability": "AVG(mean_danceability)",
        "mean_energy": "AVG(mean_energy)",
        "mean_valence": "AVG(mean_valence)",
        "mean_acousticness": "AVG(mean_acousticness)",
        "mean_speechiness": "AVG(mean_speechiness)",
    },
    "kpi_1_artist_level": {
        "mean_popularity": "AVG(mean_popularity)",
        "primary_tracks": "SUM(primary_tracks)",
    },
    "kpi_1_within_genre_diff": {
        "n_grammy_artists": "SUM(n_grammy_artists)",
        "n_non_grammy_artists": "SUM(n_non_grammy_artists)",
        "mean_pop_grammy": "AVG(mean_pop_grammy)",
        "mean_pop_non": "AVG(mean_pop_non)",
        "diff": "AVG(diff)",
        "mean_pop_grammy_strict": "AVG(mean_pop_grammy_strict)",
        "diff_strict": "AVG(diff_strict)",
        "stratified_weighted_diff": "MAX(stratified_weighted_diff)",
    },
    "kpi_2_awards_by_dominant_genre": {
        "awards": "SUM(awards)",
        "n_artists": "SUM(n_artists)",
        "award_share_pct": "MAX(award_share_pct)",
        "awards_per_100_artists": "MAX(awards_per_100_artists)",
    },
    "kpi_2_heatmap": {
        "awards": "SUM(awards)",
    },
    "kpi_3_awards_and_profile_by_decade": {
        "awards": "SUM(awards)",
        "distinct_artists": "SUM(distinct_artists)",
        "matched_awards": "SUM(matched_awards)",
        "matched_share_pct": "MAX(matched_share_pct)",
        "mean_energy": "AVG(mean_energy)",
        "mean_valence": "AVG(mean_valence)",
        "mean_danceability": "AVG(mean_danceability)",
        "mean_acousticness": "AVG(mean_acousticness)",
    },
    "kpi_3_awards_per_year": {
        "awards": "SUM(awards)",
        "recognized_artists": "SUM(recognized_artists)",
        "matched_awards": "SUM(matched_awards)",
        "matched_share_pct": "MAX(matched_share_pct)",
    },
    "kpi_3_awards_by_family_decade": {
        "awards": "SUM(awards)",
    },
    "kpi_4_top_awarded_artists_on_spotify": {
        "awards": "SUM(awards)",
        "spotify_track_count": "SUM(spotify_track_count)",
        "in_spotify": "MAX(in_spotify)",
    },
    "kpi_4_top_awarded_all": {
        "awards": "SUM(awards)",
        "spotify_track_count": "SUM(spotify_track_count)",
        "in_spotify": "MAX(in_spotify)",
    },
    "etl_batch_log": {
        "rows_fact_track_artist": "MAX(rows_fact_track_artist)",
        "rows_fact_grammy_award": "MAX(rows_fact_grammy_award)",
        "rows_bridge_award_artist": "MAX(rows_bridge_award_artist)",
    },
}

# Charts: preferred viz type first, "table" always last as the safe fallback.
CHART_SPECS: list[dict] = [
    # --- Header row KPI Big Numbers ---
    {
        "dataset": "kpi_0_integration_coverage",
        "slice_name": "[Header] Coverage Enriched %",
        "requirement": "R1,R2,R3",
        "description": "Enriched match rate via cascade across all Grammy award rows.",
        "candidates": [
            ("big_number_total", {"metric": "matched_enriched_pct"}),
            ("table", {"all_columns": ["matched_enriched_pct"], "row_limit": 10}),
        ],
    },
    {
        "dataset": "kpi_0_integration_coverage",
        "slice_name": "[Header] Coverage Strict %",
        "requirement": "R1,R2,R3",
        "description": "Exact un-split credit match rate baseline.",
        "candidates": [
            ("big_number_total", {"metric": "matched_strict_pct"}),
            ("table", {"all_columns": ["matched_strict_pct"], "row_limit": 10}),
        ],
    },
    {
        "dataset": "kpi_3_awards_and_profile_by_decade",
        "slice_name": "[Header] Grammy Artists Matched",
        "requirement": "R3",
        "description": "Distinct Grammy awardee artists successfully resolved in Spotify warehouse.",
        "candidates": [
            ("big_number_total", {"metric": "distinct_artists"}),
            ("table", {"all_columns": ["distinct_artists"], "row_limit": 10}),
        ],
    },
    {
        "dataset": "etl_batch_log",
        "slice_name": "[Header] Awards Loaded",
        "requirement": "R4",
        "description": "Total Grammy award rows loaded in the latest warehouse batch.",
        "candidates": [
            ("big_number_total", {"metric": "rows_fact_grammy_award"}),
            ("table", {"all_columns": ["rows_fact_grammy_award"], "row_limit": 10}),
        ],
    },

    # --- Tab R1: Popularity & Audio Profile ---
    {
        "dataset": "kpi_1_artist_level",
        "slice_name": "[R1] Artist Popularity Distribution",
        "requirement": "R1",
        "description": "Name-based match; 14.1% of raw catalog tracks have zero popularity.",
        "candidates": [
            ("box_plot", {
                "columns": ["artist_group"],
                "metrics": ["mean_popularity"],
                "row_limit": 1000,
            }),
            ("table", {
                "all_columns": ["artist_group", "artist_display_name", "mean_popularity", "primary_tracks"],
                "row_limit": 100,
            }),
        ],
    },
    {
        "dataset": "kpi_1_popularity_by_grammy_recognition",
        "slice_name": "[R1] Audio Features: Grammy vs Non-Grammy",
        "requirement": "R1",
        "description": "Audio features in [0, 1]; comparisons reflect surviving catalog tracks.",
        "candidates": [
            ("radar", {
                "columns": ["artist_group"],
                "metrics": ["mean_danceability", "mean_energy", "mean_valence", "mean_acousticness", "mean_speechiness"],
                "row_limit": 10,
            }),
            ("table", {
                "all_columns": [
                    "basis", "artist_group", "mean_danceability", "mean_energy",
                    "mean_valence", "mean_acousticness", "mean_speechiness",
                ],
                "row_limit": 20,
            }),
        ],
    },
    {
        "dataset": "kpi_1_within_genre_diff",
        "slice_name": "[R1] Popularity Difference within Genre Family",
        "requirement": "R1,R2",
        "description": "Filtered to families with >= 30 Grammy artists; stratified weighting applied.",
        "candidates": [
            ("dist_bar", {
                "columns": ["genre_family"],
                "metrics": ["diff"],
                "row_limit": 20,
            }),
            ("table", {
                "all_columns": [
                    "genre_family", "mean_pop_grammy", "mean_pop_non", "diff",
                    "n_grammy_artists", "stratified_weighted_diff",
                ],
                "row_limit": 50,
            }),
        ],
    },
    {
        "dataset": "kpi_1_popularity_by_grammy_recognition",
        "slice_name": "[R1] Popularity Summary Table",
        "requirement": "R1",
        "description": "Group-level medians and quartiles; basis separates zero-popularity tracks.",
        "candidates": [
            ("table", {
                "all_columns": [
                    "basis", "artist_group", "n_tracks", "n_artists",
                    "mean_popularity", "median_popularity", "p25_popularity", "p75_popularity",
                ],
                "row_limit": 20,
            }),
        ],
    },

    # --- Tab R2: Genre & Award Mapping ---
    {
        "dataset": "kpi_2_heatmap",
        "slice_name": "[R2] Genre Family vs Category Family Heatmap",
        "requirement": "R2",
        "description": "Cross-domain mappings; categories without clear family fall back to Other.",
        "candidates": [
            ("heatmap", {
                "all_columns": ["dominant_genre_family", "category_family", "awards"],
                "row_limit": 200,
            }),
            ("table", {
                "all_columns": ["dominant_genre_family", "category_family", "awards"],
                "row_limit": 200,
            }),
        ],
    },
    {
        "dataset": "kpi_2_awards_by_dominant_genre",
        "slice_name": "[R2] Awards per 100 Artists by Dominant Genre Family",
        "requirement": "R2",
        "description": "Rate denominator is distinct artists classified into dominant genre family.",
        "candidates": [
            ("dist_bar", {
                "columns": ["dominant_genre_family"],
                "metrics": ["awards_per_100_artists"],
                "row_limit": 15,
            }),
            ("table", {
                "all_columns": ["dominant_genre_family", "awards", "n_artists", "awards_per_100_artists"],
                "row_limit": 50,
            }),
        ],
    },

    # --- Tab R3: Historical Evolution ---
    {
        "dataset": "kpi_3_awards_and_profile_by_decade",
        "slice_name": "[R3] Energy Trend by Decade",
        "requirement": "R3",
        "description": "Trend interpretation depends on historical coverage; older decades have fewer tracks.",
        "candidates": [
            ("echarts_timeseries_line", {
                "x_axis": "decade",
                "metrics": ["mean_energy"],
                "row_limit": 100,
            }),
            ("table", {"all_columns": ["decade", "mean_energy"], "row_limit": 100}),
        ],
    },
    {
        "dataset": "kpi_3_awards_and_profile_by_decade",
        "slice_name": "[R3] Valence Trend by Decade",
        "requirement": "R3",
        "description": "Trend interpretation depends on coverage; surviving recordings bias older periods.",
        "candidates": [
            ("echarts_timeseries_line", {
                "x_axis": "decade",
                "metrics": ["mean_valence"],
                "row_limit": 100,
            }),
            ("table", {"all_columns": ["decade", "mean_valence"], "row_limit": 100}),
        ],
    },
    {
        "dataset": "kpi_3_awards_and_profile_by_decade",
        "slice_name": "[R3] Danceability Trend by Decade",
        "requirement": "R3",
        "description": "Danceability on primary tracks only to prevent repeat song inflation.",
        "candidates": [
            ("echarts_timeseries_line", {
                "x_axis": "decade",
                "metrics": ["mean_danceability"],
                "row_limit": 100,
            }),
            ("table", {"all_columns": ["decade", "mean_danceability"], "row_limit": 100}),
        ],
    },
    {
        "dataset": "kpi_3_awards_by_family_decade",
        "slice_name": "[R3] Awards by Category Family per Decade",
        "requirement": "R3",
        "description": "Historical Grammy categories merged to 14 canonical families.",
        "candidates": [
            ("dist_bar", {
                "groupby": ["category_family"],
                "columns": ["decade"],
                "metrics": ["awards"],
                "row_limit": 150,
            }),
            ("table", {
                "all_columns": ["decade", "category_family", "awards"],
                "row_limit": 150,
            }),
        ],
    },
    {
        "dataset": "kpi_3_awards_and_profile_by_decade",
        "slice_name": "[R3] Matched Share by Decade",
        "requirement": "R3",
        "description": "Trend interpretation depends on coverage; older decades have lower coverage.",
        "candidates": [
            ("echarts_timeseries_line", {
                "x_axis": "decade",
                "metrics": ["matched_share_pct"],
                "row_limit": 100,
            }),
            ("table", {
                "all_columns": ["decade", "awards", "matched_awards", "matched_share_pct"],
                "row_limit": 100,
            }),
        ],
    },

    # --- Tab R4: Top Artists ---
    {
        "dataset": "kpi_4_top_awarded_artists_on_spotify",
        "slice_name": "[R4] Top-10 Awarded Artists on Spotify",
        "requirement": "R4",
        "description": "Excludes aggregate credits (Various Artists, Original Cast); top 10 with ties kept.",
        "candidates": [
            ("dist_bar", {
                "columns": ["artist_display_name"],
                "metrics": ["awards"],
                "row_limit": 10,
            }),
            ("table", {
                "all_columns": ["artist_display_name", "awards", "spotify_track_count", "first_award_year", "last_award_year"],
                "row_limit": 20,
            }),
        ],
    },
    {
        "dataset": "kpi_4_top_awarded_all",
        "slice_name": "[R4] Top Awarded Artists Overall",
        "requirement": "R4",
        "description": "Includes artists absent from Spotify (in_spotify = 0) linked through Grammy credits.",
        "candidates": [
            ("table", {
                "all_columns": ["artist_display_name", "awards", "spotify_track_count", "in_spotify", "rank"],
                "order_by_cols": [["rank", True]],
                "row_limit": 25,
            }),
        ],
    },
    {
        "dataset": "kpi_4_top_awarded_all",
        "slice_name": "[R4] Top Artists Absent from Spotify",
        "requirement": "R4",
        "description": "Top-N artists celebrated by Grammy Awards but absent from the Spotify dataset.",
        "candidates": [
            ("table", {
                "all_columns": ["artist_display_name", "awards", "first_award_year", "last_award_year"],
                "row_limit": 15,
            }),
        ],
    },

    # --- Tab Quality ---
    {
        "dataset": "kpi_0_coverage_by_method",
        "slice_name": "[Quality] Match Method Distribution",
        "requirement": "R1,R2,R3",
        "description": "Hierarchical cascade: exact -> split -> workers -> nominee -> fuzzy -> none.",
        "candidates": [
            ("pie", {
                "groupby": ["match_method"],
                "metrics": ["award_rows"],
                "row_limit": 10,
            }),
            ("table", {
                "all_columns": ["match_method", "award_rows", "share_pct"],
                "row_limit": 10,
            }),
        ],
    },
    {
        "dataset": "kpi_0_coverage_by_decade",
        "slice_name": "[Quality] Coverage Trend by Decade",
        "requirement": "R1,R2,R3",
        "description": "Strict match vs enriched cascade coverage over ceremony decades.",
        "candidates": [
            ("echarts_timeseries_line", {
                "x_axis": "decade",
                "metrics": ["match_rate_pct"],
                "row_limit": 100,
            }),
            ("table", {
                "all_columns": ["decade", "award_rows", "match_rate_pct", "match_rate_strict_pct"],
                "row_limit": 100,
            }),
        ],
    },
    {
        "dataset": "etl_batch_log",
        "slice_name": "[Quality] Last ETL Batches",
        "requirement": "R4",
        "description": "Audit trail of warehouse batch loads from etl_batch_log.",
        "candidates": [
            ("table", {
                "all_columns": [
                    "batch_id", "dag_id", "run_id", "status",
                    "rows_fact_track_artist", "rows_fact_grammy_award", "rows_bridge_award_artist",
                ],
                "row_limit": 5,
            }),
        ],
    },
]


class SupersetClient:
    def __init__(self, base_url: str):
        self.base_url = base_url
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(CookieJar())
        )
        self.token: str | None = None
        self.csrf: str | None = None

    def call(self, method: str, path: str, payload: dict | None = None):
        request = urllib.request.Request(self.base_url + path, method=method)
        request.add_header("Content-Type", "application/json")
        if self.token:
            request.add_header("Authorization", f"Bearer {self.token}")
        if self.csrf:
            request.add_header("X-CSRFToken", self.csrf)
        data = json.dumps(payload).encode() if payload is not None else None
        try:
            with self.opener.open(request, data, timeout=180) as response:
                body = response.read().decode()
                try:
                    parsed = json.loads(body or "{}")
                except json.JSONDecodeError:
                    parsed = {"raw": body[:500]}
                return response.status, parsed
        except urllib.error.HTTPError as error:
            body = error.read().decode(errors="replace")
            try:
                parsed = json.loads(body)
            except json.JSONDecodeError:
                parsed = {"raw": body[:500]}
            return error.code, parsed

    def login(self) -> None:
        status, out = self.call("POST", "/api/v1/security/login", {
            "username": ADMIN_USER,
            "password": ADMIN_PASSWORD,
            "provider": "db",
            "refresh": True,
        })
        if status != 200 or "access_token" not in out:
            raise SystemExit(f"[superset-bootstrap] login failed: {status} {out}")
        self.token = out["access_token"]
        status, out = self.call("GET", "/api/v1/security/csrf_token/")
        self.csrf = out.get("result") if status == 200 else None

    def list(self, path: str, name_field: str) -> dict[str, dict]:
        status, out = self.call("GET", f"{path}?page_size=500")
        if status != 200:
            raise SystemExit(f"[superset-bootstrap] list {path} failed: {status} {out}")
        return {item[name_field]: item for item in out.get("result", [])}

    def ensure(self, path: str, name_field: str, name: str, payload: dict,
               update_payload: dict | None = None) -> dict:
        """Create (or update) an object identified by its name; return its record."""
        existing = self.list(path, name_field).get(name)
        if existing:
            status, out = self.call("PUT", f"{path}{existing['id']}",
                                    update_payload if update_payload is not None else payload)
            action = "updated"
        else:
            status, out = self.call("POST", path, payload)
            action = "created"
        if status not in (200, 201):
            raise SystemExit(f"[superset-bootstrap] {name_field}={name} {action} failed: "
                             f"{status} {json.dumps(out)[:400]}")
        record = out.get("result") or out.get("data") or out
        if "id" not in record:
            record = self.list(path, name_field)[name]
        print(f"[superset-bootstrap] {action}: {name} (id={record['id']})")
        return record


def load_kpi_queries() -> dict[str, str]:
    raw = open(KPI_SQL_PATH, encoding="utf-8").read()
    marks = [(m.group(1), m.start())
             for m in re.finditer(r"^--\s*@name:\s*([A-Za-z0-9_]+)\s*$", raw, flags=re.M)]
    queries: dict[str, str] = {}
    for index, (name, start) in enumerate(marks):
        body_start = raw.index("\n", start) + 1
        body_end = marks[index + 1][1] if index + 1 < len(marks) else len(raw)
        queries[name] = raw[body_start:body_end].strip()
    return queries


def ensure_database(client: SupersetClient) -> int:
    existing = client.list("/api/v1/database/", "database_name").get("music_dw")
    if existing:
        print(f"[superset-bootstrap] database exists: music_dw (id={existing['id']})")
        return existing["id"]
    record = client.ensure("/api/v1/database/", "database_name", "music_dw", {
        "database_name": "music_dw",
        "sqlalchemy_uri": DW_URI,
        "expose_in_sqllab": True,
        "allow_ctas": False,
        "allow_cvas": False,
        "allow_dml": False,
        "allows_subquery": True,
        "allows_virtual_table_explore": True,
    })
    return record["id"]


def ensure_dataset(client: SupersetClient, database_id: int, table_name: str,
                   sql: str, metrics: dict[str, str]) -> int:
    record = client.ensure(
        "/api/v1/dataset/",
        "table_name",
        table_name,
        {"database": database_id, "table_name": table_name, "sql": sql},
        update_payload={"database_id": database_id, "table_name": table_name, "sql": sql},
    )
    dataset_id = record["id"]
    status, out = client.call("GET", f"/api/v1/dataset/{dataset_id}")
    existing_metrics = {
        metric["metric_name"]: metric
        for metric in ((out.get("result") or {}).get("metrics") or [])
    }
    metrics_payload = []
    for name, expression in metrics.items():
        entry = {"metric_name": name, "expression": expression, "verbose_name": name}
        if name in existing_metrics:
            entry["id"] = existing_metrics[name]["id"]  # required by PUT
        metrics_payload.append(entry)
    status, out = client.call("PUT", f"/api/v1/dataset/{dataset_id}", {
        "table_name": table_name,
        "database_id": database_id,
        "sql": sql,
        "metrics": metrics_payload,
    })
    if status != 200:
        raise SystemExit(f"[superset-bootstrap] metrics for {table_name} failed: "
                         f"{status} {json.dumps(out)[:400]}")
    client.call("PUT", f"/api/v1/dataset/{dataset_id}/refresh")
    return dataset_id


def _validation_query(form: dict) -> dict:
    """Minimal chart query used to prove the KPI SQL runs through Superset."""
    if "all_columns" in form:
        groupby = list(form["all_columns"])
        metrics: list = []
    elif "x_axis" in form:
        groupby = [form["x_axis"]]
        metrics = list(form.get("metrics", []))
    else:
        groupby = list(form.get("groupby") or form.get("columns") or [])
        metrics = list(form.get("metrics", []))
    query = {
        "groupby": groupby,
        "metrics": metrics,
        "row_limit": int(form.get("row_limit", 1000)),
        "extras": {"time_grain_sqla": None},
        "applied_time_extras": {},
        "is_timeseries": False,
    }
    for column, is_ascending in form.get("order_by_cols", []):
        query.setdefault("orderby", []).append([column, bool(is_ascending)])
    return query


def ensure_chart(client: SupersetClient, spec: dict, dataset_id: int, dashboard_id: int) -> str:
    """Create the chart with the first candidate whose query actually executes."""
    failures: list[str] = []
    description = spec.get("description") or f"[{spec['requirement']}] generado por scripts/superset_bootstrap.py"
    for viz_type, form in spec["candidates"]:
        form_data = {**form, "viz_type": viz_type, "datasource": f"{dataset_id}__table"}
        payload = {
            "slice_name": spec["slice_name"],
            "description": description,
            "datasource_id": dataset_id,
            "datasource_type": "table",
            "viz_type": viz_type,
            "params": json.dumps(form_data),
            "dashboards": [dashboard_id],
        }
        record = client.ensure(
            "/api/v1/chart/",
            "slice_name",
            spec["slice_name"],
            payload,
            update_payload=payload,
        )

        query_context = {
            "datasource": {"id": dataset_id, "type": "table"},
            "queries": [_validation_query(form)],
            "form_data": form_data,
            "result_format": "json",
            "result_type": "full",
        }
        status, out = client.call("POST", "/api/v1/chart/data", query_context)
        if status == 200 and not out.get("error"):
            rows = ((out.get("result") or [{}])[0] or {}).get("rowcount")
            print(f"[superset-bootstrap] chart ok: {spec['slice_name']} "
                  f"({viz_type}, rows={rows})")
            return viz_type
        failures.append(f"{viz_type}: {status} {json.dumps(out)[:200]}")
    raise SystemExit(f"[superset-bootstrap] no candidate viz for {spec['slice_name']} "
                     f"executed successfully: {failures}")


def main() -> int:
    client = SupersetClient(BASE_URL)
    client.login()
    print(f"[superset-bootstrap] logged in to {BASE_URL} as {ADMIN_USER}")

    database_id = ensure_database(client)
    queries = load_kpi_queries()
    all_queries = {
        **queries,
        "etl_batch_log": (
            "SELECT batch_id, COALESCE(dag_id, 'manual') AS dag_id, "
            "COALESCE(run_id, batch_id) AS run_id, status, "
            "COALESCE((target_rows_after->>'fact_track_artist')::bigint, 0) AS rows_fact_track_artist, "
            "COALESCE((target_rows_after->>'fact_grammy_award')::bigint, 0) AS rows_fact_grammy_award, "
            "COALESCE((target_rows_after->>'bridge_award_artist')::bigint, 0) AS rows_bridge_award_artist "
            "FROM etl_batch_log ORDER BY started_at DESC LIMIT 5"
        ),
    }

    dashboard_metadata = {
        "label_colors": {
            "Grammy-recognized": "#C9A227",
            "Not Grammy-recognized": "#5B6C8F",
            "Grammy": "#C9A227",
            "Non-Grammy": "#5B6C8F",
            "exact": "#C9A227",
            "split": "#E5C158",
            "workers": "#5B6C8F",
            "nominee": "#8B9BB4",
            "none": "#CBD5E1",
        },
        "native_filter_configuration": [
            {
                "id": "NATIVE_FILTER_decade",
                "name": "decade",
                "filterType": "filter_select",
                "targets": [{"column": {"name": "decade"}}],
                "defaultDataMask": {"filterState": {"value": None}},
            },
            {
                "id": "NATIVE_FILTER_genre_family",
                "name": "genre_family",
                "filterType": "filter_select",
                "targets": [{"column": {"name": "genre_family"}}],
                "defaultDataMask": {"filterState": {"value": None}},
            },
            {
                "id": "NATIVE_FILTER_category_family",
                "name": "category_family",
                "filterType": "filter_select",
                "targets": [{"column": {"name": "category_family"}}],
                "defaultDataMask": {"filterState": {"value": None}},
            },
            {
                "id": "NATIVE_FILTER_match_method",
                "name": "match_method",
                "filterType": "filter_select",
                "targets": [{"column": {"name": "match_method"}}],
                "defaultDataMask": {"filterState": {"value": None}},
            },
            {
                "id": "NATIVE_FILTER_basis",
                "name": "basis",
                "filterType": "filter_select",
                "description": "Default excl_zero accounts for 14.1% tracks with popularity=0",
                "targets": [{"column": {"name": "basis"}}],
                "defaultDataMask": {"filterState": {"value": ["excl_zero"]}},
            },
        ],
    }

    dashboard = client.ensure(
        "/api/v1/dashboard/",
        "dashboard_title",
        DASHBOARD_TITLE,
        {
            "dashboard_title": DASHBOARD_TITLE,
            "published": True,
            "json_metadata": json.dumps(dashboard_metadata),
        },
        update_payload={
            "dashboard_title": DASHBOARD_TITLE,
            "published": True,
            "json_metadata": json.dumps(dashboard_metadata),
        },
    )

    used_datasets: dict[str, int] = {}
    for table_name, sql in all_queries.items():
        if table_name in DATASET_SPECS:
            used_datasets[table_name] = ensure_dataset(
                client,
                database_id,
                table_name,
                sql,
                DATASET_SPECS[table_name],
            )

    for spec in CHART_SPECS:
        table_name = spec["dataset"]
        ensure_chart(client, spec, used_datasets[table_name], dashboard["id"])

    print(f"[superset-bootstrap] dashboard ready: {BASE_URL}/superset/dashboard/{dashboard['id']}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
