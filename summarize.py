"""Summary of the KelpObserve Sesimbra 2026 tidy tables, as printed in the record's README.

Reads kelp_quadrats.csv, kelp_individuals.csv and sonde_casts.csv and prints the
per-campaign table: quadrats surveyed, quadrats with kelp recorded, individuals measured,
mean cover per stratum and sonde casts. Mean cover counts a quadrat without kelp as 0 %
(column cover_pct) and leaves out the one quadrat whose cover is blank.

    python summarize.py --tidy-dir tidy [--map overview_map.png]
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path
from statistics import mean

CAMPAIGNS = ["june", "july", "september"]
LABELS = {"june": "June", "july": "July", "september": "September"}


def rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def cover_mean(quadrats: list[dict[str, str]], campaign: str, stratum: str) -> str:
    values = [
        int(q["cover_pct"])
        for q in quadrats
        if (q["campaign"], q["stratum"]) == (campaign, stratum) and q["cover_pct"] != ""
    ]
    return f"{mean(values):.1f}" if values else "–"


def summary_table(tidy_dir: Path) -> str:
    quadrats = rows(tidy_dir / "kelp_quadrats.csv")
    individuals = rows(tidy_dir / "kelp_individuals.csv")
    casts = rows(tidy_dir / "sonde_casts.csv")
    lines = [
        ("Quadrats surveyed", lambda c: sum(q["campaign"] == c for q in quadrats)),
        ("Quadrats with kelp recorded", lambda c: sum(q["campaign"] == c and q["occurrence_status"] == "present" for q in quadrats)),
        ("Kelp individuals measured", lambda c: sum(i["campaign"] == c for i in individuals)),
        ("Mean cover, shallow stratum (%)", lambda c: cover_mean(quadrats, c, "shallow")),
        ("Mean cover, deep stratum (%)", lambda c: cover_mean(quadrats, c, "deep")),
        ("Sonde casts", lambda c: sum(cast["campaign"] == c for cast in casts)),
    ]
    out = ["| | " + " | ".join(LABELS[c] for c in CAMPAIGNS) + " |", "|---|---|---|---|"]
    out += [f"| {label} | " + " | ".join(str(value(c)) for c in CAMPAIGNS) + " |" for label, value in lines]
    return "\n".join(out)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--tidy-dir", type=Path, default=Path("."), help="folder with the tidy tables of the record")
    parser.add_argument("--map", type=Path, help="also draw the overview map to this PNG (needs matplotlib)")
    args = parser.parse_args()
    print(summary_table(args.tidy_dir))
    if args.map:
        from overview_map import draw

        draw(args.tidy_dir, args.map)
        print(f"\nwrote {args.map}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
