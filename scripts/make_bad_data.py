"""Create the controlled-failure source for Mandatory Reliability Test B.

Injects exactly one deterministic Critical violation into a COPY of the Spotify
file (popularity = 150, outside the documented [0, 100] domain of rule DQ-S3).

The original spotify_dataset.csv is never modified. To execute Test B, switch
the source selection and trigger a new DAG Run:

    SPOTIFY_SOURCE_FILENAME=spotify_bad.csv

Usage:
    python -m scripts.make_bad_data
"""

from __future__ import annotations

from pathlib import Path

from src import config

BAD_VALUE = 150
INJECTED_RULE = "DQ-S3"


def make_bad_data(source_path: Path | None = None, output_path: Path | None = None) -> Path:
    config.ensure_directories()
    source_path = Path(source_path or config.RAW_DIR / "spotify_dataset.csv")
    output_path = Path(output_path or config.BAD_DIR / "spotify_bad.csv")

    frame = config.read_csv(source_path)
    if frame.empty:
        raise RuntimeError(f"Source file is empty: {source_path}")

    target_index = frame.index[0]
    original_value = int(frame.loc[target_index, "popularity"])
    frame.loc[target_index, "popularity"] = BAD_VALUE
    output_path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(output_path, index=False)

    print(
        f"[make_bad_data] source={source_path}\n"
        f"[make_bad_data] output={output_path}\n"
        f"[make_bad_data] injected {INJECTED_RULE}: popularity {original_value} -> {BAD_VALUE} "
        f"on row index {target_index} (track_id={frame.loc[target_index, 'track_id']})"
    )
    return output_path


def main() -> int:
    make_bad_data()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
