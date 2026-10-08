"""Source contract: the raw files expose every column the pipeline consumes."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from src import config, extract

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SPOTIFY_CSV = PROJECT_ROOT / "data" / "raw" / "spotify_dataset.csv"
GRAMMY_CSV = PROJECT_ROOT / "data" / "raw" / "the_grammy_awards.csv"


def _header(path: Path) -> list[str]:
    if not path.exists():
        pytest.skip(f"raw source not committed: {path}")
    return list(pd.read_csv(path, nrows=0, keep_default_na=False, na_values=[""]).columns)


def test_spotify_csv_has_all_contract_columns():
    header = _header(SPOTIFY_CSV)
    missing = [column for column in config.SPOTIFY_REQUIRED_COLUMNS if column not in header]
    assert not missing, missing
    assert len(config.SPOTIFY_REQUIRED_COLUMNS) == 16


def test_grammy_csv_has_all_contract_columns():
    header = _header(GRAMMY_CSV)
    missing = [column for column in config.GRAMMY_REQUIRED_COLUMNS if column not in header]
    assert not missing, missing
    assert len(config.GRAMMY_REQUIRED_COLUMNS) == 9


def test_extract_projects_exactly_the_contract_columns(tmp_path):
    header = _header(SPOTIFY_CSV)
    if not header:
        pytest.skip("raw source not committed")
    source = tmp_path / "source.csv"
    output = tmp_path / "spotify_raw.csv"
    pd.read_csv(SPOTIFY_CSV, nrows=50, keep_default_na=False, na_values=[""]).to_csv(
        source, index=False
    )
    metadata = extract.extract_spotify(source_path=source, output_path=output)
    assert metadata["columns"] == config.SPOTIFY_REQUIRED_COLUMNS
    written = list(pd.read_csv(output, nrows=0).columns)
    assert written == config.SPOTIFY_REQUIRED_COLUMNS


def test_extract_rejects_missing_column():
    frame = pd.DataFrame({"track_id": ["t1"]})
    with pytest.raises(extract.SourceContractError) as error:
        extract._verify_columns(frame, config.SPOTIFY_REQUIRED_COLUMNS, "test")
    assert "artists" in str(error.value)


def test_na_policy_keeps_literal_na_artist():
    """The Spotify file contains the literal artist token "N/A".

    Default pandas parsing would turn those values into nulls; the project NA
    policy (keep_default_na=False) keeps them as text.
    """
    na_path = SPOTIFY_CSV
    if not na_path.exists():
        pytest.skip("raw source not committed")
    project_policy = pd.read_csv(na_path, keep_default_na=False, na_values=[""],
                                 usecols=["artists"])
    components = project_policy["artists"].astype("string").str.split(";").explode()
    literal_na = int((components == "N/A").sum())
    assert literal_na > 0
    # only the genuinely blank artist field may be null (1 row, 0.0009%)
    assert project_policy["artists"].isna().sum() <= 1
