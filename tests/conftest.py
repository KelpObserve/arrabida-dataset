"""Shared fixtures.

The tests in test_record.py compare the scripts' output with the files of the Zenodo
record. They need the files below (about 1.4 MB; the photograph archives are not needed).
"""

from pathlib import Path

import pytest

RECORD_URL = "https://zenodo.org/records/23282075/files/{name}?download=1"
RECORD_FILES = [
    "raw_ccmar_kelp_quadrats_2026.xlsx",
    "raw_ccmar_sonde_casts_2026.xlsx",
    "raw_ccmar_quadrat_positions_2026.gpkg",
    "raw_ccmar_quadrat_positions_july_dive_log.gpkg",
    "raw_ccmar_dive_tracks_2026.gpkg",
    "kelp_quadrats.csv",
    "kelp_individuals.csv",
    "sonde_casts.csv",
    "dive_tracks.geojson",
    "position_qc.csv",
    "position_qc_provenance.json",
    "overview_map.png",
    "README.md",
    "checksums.sha256",
]


@pytest.fixture(scope="session")
def record_dir(tmp_path_factory) -> Path:
    """A folder holding RECORD_FILES."""
    # TODO(human): decide where the record comes from, and what happens when it is unavailable.
    pytest.skip("record source not configured")
