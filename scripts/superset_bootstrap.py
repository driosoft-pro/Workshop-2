"""Bootstrap the Apache Superset BI layer for Workshop-2.

Orquestador central que reconcilia en Superset (de forma idempotente):
  - Conexión a base de datos PostgreSQL `music_dw`
  - Datasets virtuales y consultas analíticas (kpi_* y consultas inline)
  - Gráficos métricos y analíticos asociados a R1–R4 y calidad de datos
  - Dashboards interactivos organizados en submódulos:
      * Dashboard Spotify & Grammy (R1–R4) (scripts/dashboards/workshop.py)
      * Workshop-2 - Granularity & Data Quality (scripts/dashboards/granularity.py)
      * Workshop-2 - KPIs (R1-R4) (scripts/dashboards/requirements.py)

Uso en red Docker / Podman:
    python /app/scripts/superset_bootstrap.py
Uso en host:
    python -m scripts.superset_bootstrap
"""

from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
import urllib.request
from http.cookiejar import CookieJar

# Garantizar resolución de módulos tanto en ejecución directa desde el host como en contenedor
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.abspath(os.path.join(_SCRIPT_DIR, ".."))
for _p in (_SCRIPT_DIR, _REPO_ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)

try:
    from scripts.dashboards import (
        ALL_REQ,
        ALIAS_COLUMNS,
        CHART_SPECS,
        DASHBOARDS,
        DASHBOARD_TITLE,
        DATASET_SPECS,
        ETL_BATCH_LOG_SQL,
        FILTER_DEFS,
        G,
        GRANULARITY_CSS,
        GRANULARITY_SLUG,
        GRANULARITY_TITLE,
        INLINE_QUERIES,
        LABEL_COLORS,
        LAYOUTS,
        MARKDOWN,
        OPTIONAL_META_KEYS,
        R,
        REQUIREMENTS_CSS,
        REQUIREMENTS_SLUG,
        REQUIREMENTS_TITLE,
        W,
        WORKSHOP_CSS,
        WORKSHOP_SLUG,
        WORKSHOP_TITLE,
        _big,
        _hbar,
        _line,
        _simple_filter,
        _spec,
        _table,
        load_kpi_queries,
    )
except ImportError:
    from dashboards import (
        ALL_REQ,
        ALIAS_COLUMNS,
        CHART_SPECS,
        DASHBOARDS,
        DASHBOARD_TITLE,
        DATASET_SPECS,
        ETL_BATCH_LOG_SQL,
        FILTER_DEFS,
        G,
        GRANULARITY_CSS,
        GRANULARITY_SLUG,
        GRANULARITY_TITLE,
        INLINE_QUERIES,
        LABEL_COLORS,
        LAYOUTS,
        MARKDOWN,
        OPTIONAL_META_KEYS,
        R,
        REQUIREMENTS_CSS,
        REQUIREMENTS_SLUG,
        REQUIREMENTS_TITLE,
        W,
        WORKSHOP_CSS,
        WORKSHOP_SLUG,
        WORKSHOP_TITLE,
        _big,
        _hbar,
        _line,
        _simple_filter,
        _spec,
        _table,
        load_kpi_queries,
    )


def _load_env() -> None:
    """Best-effort loader for .env when executing on the host without compose."""
    env_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".env"))
    if not os.path.exists(env_path):
        return
    try:
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, val = line.split("=", 1)
                key = key.strip()
                val = val.strip().strip("\"'")
                if key and key not in os.environ:
                    os.environ[key] = val
    except Exception:
        pass


_load_env()

BASE_URL = os.environ.get("SUPERSET_URL", "http://localhost:8088").rstrip("/")
ADMIN_USER = os.environ.get("SUPERSET_ADMIN_USER", "admin")
ADMIN_PASSWORD = os.environ.get("SUPERSET_ADMIN_PASSWORD", "admin")


def _resolve_dw_uri() -> str:
    uri = os.environ.get("SUPERSET_DW_SQLALCHEMY_URI") or os.environ.get("MUSIC_DW_DB_URL")
    if uri:
        return uri
    user = os.environ.get("POSTGRES_USER")
    password = os.environ.get("POSTGRES_PASSWORD")
    host = os.environ.get("POSTGRES_HOST", "music-postgres")
    port = os.environ.get("MUSIC_POSTGRES_PORT", "5432")
    if user and password:
        return f"postgresql+psycopg2://{user}:{password}@{host}:{port}/music_dw"
    return f"postgresql+psycopg2://{host}:{port}/music_dw"


DW_URI = _resolve_dw_uri()
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
KPI_SQL_PATH = os.path.join(PROJECT_ROOT, "sql", "kpi_queries.sql")


class SupersetClient:
    """Minimal Superset REST API client using cookie-jar session handling."""

    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")
        self.token: str | None = None
        self.csrf: str | None = None
        self.cookies = CookieJar()
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.cookies)
        )

    def call(self, method: str, path: str, payload: dict | None = None) -> tuple[int, dict]:
        url = f"{self.base_url}{path}"
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        headers = {"Accept": "application/json"}
        if data is not None:
            headers["Content-Type"] = "application/json"
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        if self.csrf:
            headers["X-CSRFToken"] = self.csrf
            headers["Referer"] = f"{self.base_url}/"

        request = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with self.opener.open(request) as response:
                body = response.read().decode("utf-8")
                try:
                    parsed = json.loads(body) if body else {}
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
        status, out = self.call("GET", f"{path}?q=(page_size:500)")
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


def _wrap_sql(sql: str, aliases: dict[str, str] | None) -> str:
    """Optionally expose alias columns (e.g. genre_family) next to the original ones."""
    lines = sql.strip().splitlines()
    while lines and (not lines[-1].strip() or lines[-1].strip().startswith("--")
                     or lines[-1].strip() == ";"):
        lines.pop()
    body = "\n".join(lines).strip()
    body = re.sub(r";\s*(--[^\n]*)?\s*$", "", body).strip()
    if not aliases:
        return body
    extra = ", ".join(f"q.{src} AS {alias}" for alias, src in aliases.items())
    return f"SELECT q.*, {extra}\nFROM (\n{body}\n) AS q"


def ensure_dataset(client: SupersetClient, database_id: int, table_name: str,
                   sql: str, metrics: dict[str, str],
                   aliases: dict[str, str] | None = None) -> tuple[int, list[str]]:
    sql = _wrap_sql(sql, aliases)
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
    status, out = client.call("GET", f"/api/v1/dataset/{dataset_id}")
    columns = [c["column_name"] for c in ((out.get("result") or {}).get("columns") or [])]
    return dataset_id, columns


def _validation_query(form: dict) -> dict:
    """Minimal chart query used to prove the KPI SQL runs through Superset."""
    metrics = list(form.get("metrics") or ([form["metric"]] if form.get("metric") else []))
    if "all_columns" in form:
        groupby = list(form["all_columns"])
        metrics = []
    else:
        groupby = [form[k] for k in ("x_axis", "all_columns_x", "all_columns_y") if form.get(k)]
        extra = form.get("groupby") or []
        groupby += [extra] if isinstance(extra, str) else list(extra)
        groupby += list(form.get("columns") or [])
    query = {
        "groupby": list(dict.fromkeys(groupby)),
        "metrics": metrics,
        "row_limit": min(int(form.get("row_limit", 1000)), 1000),
        "extras": {"time_grain_sqla": None},
        "applied_time_extras": {},
        "is_timeseries": False,
    }
    filters = [{"col": f["subject"], "op": f["operator"], "val": f["comparator"]}
               for f in form.get("adhoc_filters", []) if f.get("expressionType") == "SIMPLE"]
    if filters:
        query["filters"] = filters
    for column, is_ascending in form.get("order_by_cols", []):
        query.setdefault("orderby", []).append([column, bool(is_ascending)])
    return query


def ensure_chart(client: SupersetClient, spec: dict, dataset_id: int, dashboard_id: int) -> int:
    """Create the chart with the first candidate whose query actually executes."""
    failures: list[str] = []
    description = spec.get("description") or f"[{spec['requirement']}] generado por scripts/superset_bootstrap.py"
    for viz_type, form in spec["candidates"]:
        saved = dict(form)
        if "order_by_cols" in saved:  # Table charts store them as JSON strings
            saved["order_by_cols"] = [json.dumps(list(pair)) for pair in saved["order_by_cols"]]
        form_data = {"adhoc_filters": [], "time_range": "No filter", **saved,
                     "viz_type": viz_type, "datasource": f"{dataset_id}__table"}
        payload = {
            "slice_name": spec["slice_name"],
            "description": description,
            "datasource_id": dataset_id,
            "datasource_type": "table",
            "viz_type": viz_type,
            "params": json.dumps(form_data),
            "dashboards": [dashboard_id],
        }
        record = client.ensure("/api/v1/chart/", "slice_name", spec["slice_name"],
                               payload, update_payload=payload)

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
            print(f"[superset-bootstrap] chart ok: {spec['slice_name']} ({viz_type}, rows={rows})")
            return int(record["id"])
        failures.append(f"{viz_type}: {status} {json.dumps(out)[:200]}")
    raise SystemExit(f"[superset-bootstrap] no candidate viz for {spec['slice_name']} "
                     f"executed successfully: {failures}")


def check_layouts() -> None:
    """Fail fast if a layout references a missing chart or a chart is not placed."""
    for key in DASHBOARDS:
        placed = [ref for row in LAYOUTS[key] if isinstance(row, list)
                  for kind, ref, _w, _h in row if kind == "chart"]
        declared = [s["slice_name"] for s in CHART_SPECS if s["dashboard"] == key]
        if sorted(placed) != sorted(declared):
            raise SystemExit(f"[superset-bootstrap] layout/spec mismatch in '{key}': "
                             f"{sorted(set(placed) ^ set(declared))}")
        for row in LAYOUTS[key]:
            if isinstance(row, list) and sum(item[2] for item in row) > 12:
                raise SystemExit(f"[superset-bootstrap] row wider than 12 columns in '{key}': {row}")


def build_layout(title: str, rows: list, chart_ids: dict[str, int]) -> dict:
    """Explicit single-page layout: header, section headers, rows of charts/markdown."""
    layout: dict = {
        "DASHBOARD_VERSION_KEY": "v2",
        "ROOT_ID": {"type": "ROOT", "id": "ROOT_ID", "children": ["GRID_ID"]},
        "GRID_ID": {"type": "GRID", "id": "GRID_ID", "children": [], "parents": ["ROOT_ID"]},
        "HEADER_ID": {"id": "HEADER_ID", "type": "HEADER", "meta": {"text": title}},
    }
    grid = layout["GRID_ID"]["children"]
    for n, item in enumerate(rows):
        if isinstance(item, str):
            hid = f"HEADER-sec{n}"
            layout[hid] = {"type": "HEADER", "id": hid, "children": [],
                           "parents": ["ROOT_ID", "GRID_ID"],
                           "meta": {"text": item, "headerSize": "MEDIUM_HEADER",
                                    "background": "BACKGROUND_TRANSPARENT"}}
            grid.append(hid)
            continue
        rid = f"ROW-r{n}"
        layout[rid] = {"type": "ROW", "id": rid, "children": [],
                       "parents": ["ROOT_ID", "GRID_ID"],
                       "meta": {"background": "BACKGROUND_TRANSPARENT"}}
        grid.append(rid)
        for m, (kind, ref, width, height) in enumerate(item):
            parents = ["ROOT_ID", "GRID_ID", rid]
            if kind == "chart":
                cid = f"CHART-r{n}c{m}"
                meta = {"width": width, "height": height,
                        "chartId": chart_ids[ref], "sliceName": ref}
                ctype = "CHART"
            else:
                cid = f"MARKDOWN-r{n}c{m}"
                meta = {"width": width, "height": height, "code": MARKDOWN[ref]}
                ctype = "MARKDOWN"
            layout[cid] = {"type": ctype, "id": cid, "children": [], "parents": parents, "meta": meta}
            layout[rid]["children"].append(cid)
    return layout


def build_filters(key: str, dash_chart_ids: list[int], chart_dataset: dict[int, int],
                  dataset_cols: dict[int, list[str]]) -> list[dict]:
    """Native filters scoped only to charts whose dataset really has the column."""
    filters = []
    for spec in FILTER_DEFS[key]:
        col = spec["column"]
        scoped = [c for c in dash_chart_ids if col in dataset_cols.get(chart_dataset[c], [])]
        if not scoped:
            print(f"[superset-bootstrap] filter '{spec['name']}' skipped: no chart has column '{col}'")
            continue
        default = spec.get("default")
        mask = {"extraFormData": {}, "filterState": {}, "ownState": {}}
        if default:
            mask = {"extraFormData": {"filters": [{"col": col, "op": "IN", "val": default}]},
                    "filterState": {"value": default}, "ownState": {}}
        target_datasets = list(dict.fromkeys(chart_dataset[c] for c in scoped))
        targets = [{"datasetId": ds_id, "column": {"name": col}} for ds_id in target_datasets]

        filters.append({
            "id": f"NATIVE_FILTER-w2-{key}-{spec['column']}",
            "type": "NATIVE_FILTER",
            "name": spec["name"],
            "description": spec.get("description", ""),
            "filterType": "filter_select",
            "targets": targets,
            "controlValues": {
                "multiSelect": spec.get("multi", True),
                "enableEmptyFilter": bool(spec.get("required", False)),
                "defaultToFirstItem": False,
                "inverseSelection": False,
                "searchAllOptions": False,
            },
            "defaultDataMask": mask,
            "cascadeParentIds": [],
            "scope": {"rootPath": ["ROOT_ID"],
                      "excluded": [c for c in dash_chart_ids if c not in scoped]},
            "chartsInScope": scoped,
            "tabsInScope": [],
        })
    return filters


def apply_dashboard(client: SupersetClient, dash_id: int, info: dict, layout: dict,
                    metadata: dict) -> None:
    base = {"dashboard_title": info["title"], "published": True,
            "position_json": json.dumps(layout), "json_metadata": json.dumps(metadata),
            "css": info.get("css", "")}
    slim = json.dumps({k: v for k, v in metadata.items() if k not in OPTIONAL_META_KEYS})
    attempts = [
        dict(base, slug=info["slug"]),
        dict(base, slug=info["slug"], json_metadata=slim),  # older schema: drop optional keys
        dict(base, json_metadata=slim),                      # slug already taken elsewhere
    ]
    last = None
    for payload in attempts:
        status, out = client.call("PUT", f"/api/v1/dashboard/{dash_id}", payload)
        if status == 200:
            return
        last = (status, json.dumps(out)[:300])
    raise SystemExit(f"[superset-bootstrap] dashboard '{info['title']}' update failed: {last}")


def main(argv: list[str] | None = None) -> int:
    check_layouts()
    client = SupersetClient(BASE_URL)
    client.login()
    print(f"[superset-bootstrap] logged in to {BASE_URL} as {ADMIN_USER}")

    database_id = ensure_database(client)
    all_queries = {**load_kpi_queries(), "etl_batch_log": ETL_BATCH_LOG_SQL, **INLINE_QUERIES}

    used_datasets: dict[str, int] = {}
    dataset_cols: dict[int, list[str]] = {}
    for table_name, sql in all_queries.items():
        if table_name in DATASET_SPECS:
            dataset_id, columns = ensure_dataset(
                client, database_id, table_name, sql, DATASET_SPECS[table_name],
                aliases=ALIAS_COLUMNS.get(table_name),
            )
            used_datasets[table_name] = dataset_id
            dataset_cols[dataset_id] = columns

    dashboard_ids: dict[str, int] = {}
    existing_dashboards_by_slug = client.list("/api/v1/dashboard/", "slug")
    for key, info in DASHBOARDS.items():
        existing = existing_dashboards_by_slug.get(info["slug"])
        if existing:
            status, out = client.call("PUT", f"/api/v1/dashboard/{existing['id']}", {
                "dashboard_title": info["title"], "slug": info["slug"], "published": True
            })
            dashboard_ids[key] = existing["id"]
            print(f"[superset-bootstrap] updated dashboard: {info['title']} (id={existing['id']})")
        else:
            record = client.ensure(
                "/api/v1/dashboard/", "dashboard_title", info["title"],
                {"dashboard_title": info["title"], "slug": info["slug"], "published": True, "json_metadata": "{}"},
                update_payload={"dashboard_title": info["title"], "slug": info["slug"], "published": True},
            )
            dashboard_ids[key] = record["id"]

    # Limpiar charts obsoletos con prefijos anteriores en inglés o nombres viejos
    obsolete_prefixes = (
        "[Header]", "[Grain]", "[Quality]", "[R1]", "[R2]", "[R3]", "[R4]", "[R*]",
        "[Workshop Header]", "[Workshop]",
    )
    existing_charts = client.list("/api/v1/chart/", "slice_name")
    for name, item in existing_charts.items():
        if any(name.startswith(p) for p in obsolete_prefixes):
            client.call("DELETE", f"/api/v1/chart/{item['id']}")
            print(f"[superset-bootstrap] deleted obsolete chart: {name} (id={item['id']})")

    chart_ids: dict[str, dict[str, int]] = {key: {} for key in DASHBOARDS}
    chart_dataset: dict[int, int] = {}
    for spec in CHART_SPECS:
        key = spec["dashboard"]
        dataset_id = used_datasets[spec["dataset"]]
        chart_id = ensure_chart(client, spec, dataset_id, dashboard_ids[key])
        chart_ids[key][spec["slice_name"]] = chart_id
        chart_dataset[chart_id] = dataset_id

    for key, info in DASHBOARDS.items():
        dash_id = dashboard_ids[key]
        layout = build_layout(info["title"], LAYOUTS[key], chart_ids[key])
        filters = build_filters(key, list(chart_ids[key].values()), chart_dataset, dataset_cols)

        status, detail = client.call("GET", f"/api/v1/dashboard/{dash_id}")
        existing = {}
        if status == 200:
            existing = json.loads((detail.get("result") or {}).get("json_metadata") or "{}")
        existing.update({
            "label_colors": LABEL_COLORS,
            "color_scheme": "",
            "refresh_frequency": 0,
            "cross_filters_enabled": True,
            "filter_bar_orientation": "HORIZONTAL",
            "native_filter_configuration": filters,
        })
        apply_dashboard(client, dash_id, info, layout, existing)
        print(f"[superset-bootstrap] dashboard ready: {info['title']} "
              f"({len(chart_ids[key])} charts, {len(filters)} filters) "
              f"{BASE_URL}/superset/dashboard/{info['slug']}/")

    print(f"[superset-bootstrap] total datasets: {len(used_datasets)}, total charts: {len(CHART_SPECS)}, "
          "themes: managed by Superset (config/superset_config.py THEME_DEFAULT/THEME_DARK)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
