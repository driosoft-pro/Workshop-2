"""Helpers and shared definitions for Superset dashboards."""

from __future__ import annotations

import os
import re

G, R, W = "granularity", "requirements", "workshop"
ALL_REQ = "R1,R2,R3,R4"

OPTIONAL_META_KEYS = ("cross_filters_enabled", "filter_bar_orientation")

LABEL_COLORS = {
    "Grammy-recognized": "#C9A227", "Not Grammy-recognized": "#5B6C8F",
    "Grammy": "#C9A227", "Non-Grammy": "#5B6C8F",
    "exact": "#C9A227", "split": "#E5C158", "workers": "#5B6C8F",
    "nominee": "#8B9BB4", "fuzzy": "#A78BFA", "none": "#CBD5E1",
    "A": "#C9A227", "B": "#5B6C8F", "C": "#8B9BB4",
}


def load_kpi_queries(sql_path: str | None = None) -> dict[str, str]:
    """Parse sql/kpi_queries.sql into a dict of query_name -> sql_text."""
    if not sql_path:
        root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        sql_path = os.path.join(root, "sql", "kpi_queries.sql")
    raw = open(sql_path, encoding="utf-8").read()
    marks = [(m.group(1), m.start())
             for m in re.finditer(r"^--\s*@name:\s*([A-Za-z0-9_]+)\s*$", raw, flags=re.M)]
    queries: dict[str, str] = {}
    for index, (name, start) in enumerate(marks):
        body_start = raw.index("\n", start) + 1
        body_end = marks[index + 1][1] if index + 1 < len(marks) else len(raw)
        queries[name] = raw[body_start:body_end].strip()
    return queries


def _spec(dashboard: str, dataset: str, name: str, requirement: str, description: str, candidates: list):
    return {
        "dashboard": dashboard,
        "dataset": dataset,
        "slice_name": name,
        "requirement": requirement,
        "description": description,
        "candidates": candidates,
    }


def _table(cols: list[str], limit: int = 50, order: list | None = None, filters: list | None = None):
    form = {"query_mode": "raw", "all_columns": cols, "row_limit": limit, "include_search": False}
    if order:
        form["order_by_cols"] = order
    if filters:
        form["adhoc_filters"] = filters
    return ("table", form)


def _big(metric: str, subheader: str, fmt: str = ".1f", color: dict | None = None,
         header_font_size: float = 0.55, subheader_font_size: float = 0.28):
    form = {
        "metric": metric, "subheader": subheader, "y_axis_format": fmt,
        "header_font_size": header_font_size, "subheader_font_size": subheader_font_size,
    }
    if color:
        form["color_picker"] = color
    return [
        ("big_number_total", form),
        _table([metric], 10),
    ]


def _line(x: str, metrics: list[str], fmt: str = ".2f", limit: int = 100):
    return ("echarts_timeseries_line", {
        "x_axis": x, "metrics": metrics, "x_axis_force_categorical": True,
        "markerEnabled": True, "markerSize": 8, "y_axis_format": fmt,
        "show_legend": len(metrics) > 1, "row_limit": limit,
    })


def _hbar(x: str, metric: str, limit: int, fmt: str = ".1f", ascending: bool = False):
    return [
        ("echarts_timeseries_bar", {
            "x_axis": x, "metrics": [metric], "orientation": "horizontal", "show_value": True,
            "x_axis_sort": metric, "x_axis_sort_asc": ascending, "y_axis_format": fmt,
            "row_limit": limit,
        }),
        ("dist_bar", {
            "groupby": [x], "metrics": [metric], "show_bar_value": True,
            "order_bars": True, "y_axis_format": fmt, "row_limit": limit,
        }),
    ]


def _simple_filter(col: str, op: str, val: str):
    return {"expressionType": "SIMPLE", "subject": col, "operator": op,
            "comparator": val, "clause": "WHERE"}
