import csv

from arrabida_dataset.summarize import summary_table


def write(path, rows):
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def test_mean_cover_counts_absence_as_zero_and_skips_blank_cover(tmp_path):
    quadrat = {"campaign": "june", "stratum": "shallow", "cover_pct": "0", "occurrence_status": "absent"}
    write(tmp_path / "kelp_quadrats.csv", [
        quadrat,
        {**quadrat, "cover_pct": "50", "occurrence_status": "present"},
        {**quadrat, "campaign": "september", "stratum": "deep", "cover_pct": "", "occurrence_status": "present"},
    ])
    write(tmp_path / "kelp_individuals.csv", [{"campaign": "june"}, {"campaign": "june"}])
    write(tmp_path / "sonde_casts.csv", [{"campaign": "july"}])
    lines = summary_table(tmp_path).splitlines()
    assert lines[0] == "| | June | July | September |"
    assert "| Quadrats with kelp recorded | 1 | 0 | 1 |" in lines
    assert "| Kelp individuals measured | 2 | 0 | 0 |" in lines
    assert "| Mean cover, shallow stratum (%) | 25.0 | – | – |" in lines
    assert "| Mean cover, deep stratum (%) | – | – | – |" in lines
    assert "| Sonde casts | 0 | 1 | 0 |" in lines
