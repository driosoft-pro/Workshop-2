"""Stratified audit tool for Grammy-to-Spotify artist matching validation.

Workshop-2 Phase F4:
  --sample : extract stratified sample (40/method, seed 42) to docs/evidence/match_audit.csv
  --score  : read labelled rows, compute Wilson 95% CI precision, write summary JSON
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import sys

import pandas as pd
from sqlalchemy import text

from src import config

AUDIT_CSV = config.EVIDENCE_DIR / "match_audit.csv"
AUDIT_SUMMARY_JSON = config.EVIDENCE_DIR / "match_audit_summary.json"
METHODS = ["exact", "split", "workers", "nominee"]


def wilson_score_interval(k: int, n: int, z: float = 1.959964) -> tuple[float, float]:
    """Calculate the Wilson score confidence interval for a binomial proportion."""
    if n == 0:
        return 0.0, 0.0
    p = k / n
    denominator = 1.0 + (z * z) / n
    center = (p + (z * z) / (2.0 * n)) / denominator
    spread = (z / denominator) * math.sqrt((p * (1.0 - p) / n) + (z * z) / (4.0 * n * n))
    return max(0.0, center - spread), min(1.0, center + spread)


def sample_matches(output_path: Path = AUDIT_CSV, sample_per_method: int = 40, seed: int = 42) -> pd.DataFrame:
    """Generate a stratified sample of 40 awards per match method."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    df: pd.DataFrame | None = None
    # 1. Try querying Data Warehouse
    try:
        from sqlalchemy import create_engine
        engine = create_engine(config.DW_DB_URL)
        with engine.connect() as conn:
            query = text("""
                SELECT
                    w.award_bk,
                    y.year,
                    c.category,
                    COALESCE(w.nominee, '') AS nominee,
                    COALESCE(w.artist_credit, '') AS artist_credit,
                    COALESCE(w.workers, '') AS workers,
                    a.artist_display_name AS matched_artist,
                    b.match_method,
                    b.recognition_tier
                FROM bridge_award_artist b
                JOIN fact_grammy_award w ON w.grammy_award_sk = b.grammy_award_sk
                JOIN dim_year y ON y.year_sk = w.year_sk
                JOIN dim_award_category c ON c.category_sk = w.category_sk
                JOIN dim_artist a ON a.artist_sk = b.artist_sk
                WHERE b.match_method IN ('exact', 'split', 'workers', 'nominee')
            """)
            df = pd.read_sql(query, conn)
    except Exception:
        df = None

    # 2. Fallback to local files if database is offline
    if df is None or len(df) == 0:
        bridge_path = config.DATA_PROCESSED_DIR / "prepared_bridge.csv"
        grammy_path = config.DATA_PROCESSED_DIR / "prepared_grammys.csv"
        artist_path = config.DATA_PROCESSED_DIR / "dim_artist.csv"
        if bridge_path.exists() and grammy_path.exists():
            bridge = pd.read_csv(bridge_path)
            grammys = pd.read_csv(grammy_path)
            artists = pd.read_csv(artist_path) if artist_path.exists() else pd.DataFrame(columns=["artist_key", "artist_display_name"])
            
            merged = bridge.merge(grammys, on="award_bk", how="inner", suffixes=("_bridge", "_grammy"))
            if "artist_key" in merged.columns and "artist_key" in artists.columns:
                merged = merged.merge(artists, on="artist_key", how="left")
            
            df = pd.DataFrame({
                "award_bk": merged["award_bk"],
                "year": merged["year"],
                "category": merged["category"],
                "nominee": merged.get("nominee", ""),
                "artist_credit": merged.get("artist", ""),
                "workers": merged.get("workers", ""),
                "matched_artist": merged.get("artist_display_name", merged.get("artist_key", "")),
                "match_method": merged["match_method_bridge"] if "match_method_bridge" in merged.columns else merged["match_method"],
                "recognition_tier": merged["recognition_tier_bridge"] if "recognition_tier_bridge" in merged.columns else merged.get("recognition_tier", "none"),
            })
        else:
            raise RuntimeError("Cannot sample matches: Data Warehouse unreachable and prepared CSVs missing.")

    # Stratified sampling
    sample_dfs = []
    for method in METHODS:
        method_df = df[df["match_method"] == method]
        n = min(len(method_df), sample_per_method)
        if n > 0:
            sample_dfs.append(method_df.sample(n=n, random_state=seed))

    if sample_dfs:
        sampled = pd.concat(sample_dfs, ignore_index=True)
    else:
        sampled = pd.DataFrame(columns=[
            "award_bk", "year", "category", "nominee", "artist_credit",
            "workers", "matched_artist", "match_method", "recognition_tier"
        ])

    sampled["label"] = ""
    cols = [
        "award_bk", "year", "category", "nominee", "artist_credit",
        "workers", "matched_artist", "match_method", "recognition_tier", "label"
    ]
    sampled = sampled[cols]
    sampled.to_csv(output_path, index=False)
    print(f"[match_audit] Stratified sample of {len(sampled)} rows written to {output_path}")
    return sampled


def score_audit(input_path: Path = AUDIT_CSV, summary_path: Path = AUDIT_SUMMARY_JSON) -> dict:
    """Read labelled rows, compute precision with Wilson 95% CI, and print table."""
    if not input_path.exists():
        print("AUDIT PENDING")
        return {"status": "AUDIT PENDING"}

    df = pd.read_csv(input_path)
    if "label" not in df.columns:
        print("AUDIT PENDING")
        return {"status": "AUDIT PENDING"}

    # Filter valid labels: y or n (case-insensitive)
    df["clean_label"] = df["label"].astype(str).str.strip().str.lower()
    labelled = df[df["clean_label"].isin(["y", "n"])].copy()

    if len(labelled) == 0:
        print("AUDIT PENDING")
        result = {"status": "AUDIT PENDING"}
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        summary_path.write_text(json.dumps(result, indent=2))
        return result

    summary: dict = {
        "status": "COMPLETED",
        "total_labelled": len(labelled),
        "methods": {},
    }

    # Print 6-line table: header, 4 methods, overall
    print(f"{'method':<10} | {'n':<4} | {'y':<4} | {'precision':<9} | {'95% CI':<16}")
    print("-" * 55)

    for method in METHODS:
        m_df = labelled[labelled["match_method"] == method]
        n = len(m_df)
        k = int((m_df["clean_label"] == "y").sum())
        prec = (k / n) if n > 0 else 0.0
        ci_low, ci_high = wilson_score_interval(k, n)
        summary["methods"][method] = {
            "n": n,
            "y": k,
            "precision": round(prec, 4),
            "ci_lower": round(ci_low, 4),
            "ci_upper": round(ci_high, 4),
        }
        ci_str = f"[{ci_low*100:.1f}%, {ci_high*100:.1f}%]" if n > 0 else "N/A"
        prec_str = f"{prec*100:.1f}%" if n > 0 else "N/A"
        print(f"{method:<10} | {n:<4} | {k:<4} | {prec_str:<9} | {ci_str:<16}")

    tot_n = len(labelled)
    tot_k = int((labelled["clean_label"] == "y").sum())
    tot_prec = (tot_k / tot_n) if tot_n > 0 else 0.0
    tot_low, tot_high = wilson_score_interval(tot_k, tot_n)
    summary["overall"] = {
        "n": tot_n,
        "y": tot_k,
        "precision": round(tot_prec, 4),
        "ci_lower": round(tot_low, 4),
        "ci_upper": round(tot_high, 4),
    }
    tot_ci_str = f"[{tot_low*100:.1f}%, {tot_high*100:.1f}%]"
    print(f"{'overall':<10} | {tot_n:<4} | {tot_k:<4} | {tot_prec*100:.1f}%    | {tot_ci_str:<16}")

    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, indent=2))
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Match audit sampling and scoring tool.")
    parser.add_argument("--sample", action="store_true", help="Generate stratified sample of 40 rows per method")
    parser.add_argument("--score", action="store_true", help="Score labelled sample and output precision metrics")
    args = parser.parse_args()

    if args.sample:
        sample_matches()
        return 0
    elif args.score:
        score_audit()
        return 0
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
