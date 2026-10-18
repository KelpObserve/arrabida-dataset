"""Comparisons with the files of the Zenodo record; they need the `record_dir` fixture."""

import hashlib
import struct

import pytest

from arrabida_dataset import check_positions, make_tidy_tables, summarize


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def recorded_hashes(record):
    lines = (record / "checksums.sha256").read_text(encoding="utf-8").splitlines()
    return {name: digest for digest, name in (line.split("  ", 1) for line in lines)}


def png_size(path):
    return struct.unpack(">II", path.read_bytes()[16:24])


def test_tidy_tables_rebuild_byte_for_byte(record_dir, tmp_path):
    make_tidy_tables.build(record_dir, tmp_path)
    expected = recorded_hashes(record_dir)
    assert {n: sha256(tmp_path / n) for n in make_tidy_tables.TIDY_FILES} == {
        n: expected[n] for n in make_tidy_tables.TIDY_FILES
    }


def test_summary_table_is_the_one_in_the_record_readme(record_dir):
    assert summarize.summary_table(record_dir) in (record_dir / "README.md").read_text(encoding="utf-8")


def test_archived_position_check_reproduces(record_dir):
    assert check_positions.verify_archived(record_dir)


def test_overview_map_has_the_record_geometry(record_dir, tmp_path):
    pytest.importorskip("matplotlib")
    from arrabida_dataset.overview_map import draw

    draw(record_dir, tmp_path / "overview_map.png")
    assert png_size(tmp_path / "overview_map.png") == png_size(record_dir / "overview_map.png")
