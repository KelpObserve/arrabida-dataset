"""Position check of the KelpObserve Sesimbra 2026 quadrats against lidar bathymetry.

The quadrat positions come from a GPS on a towed surface float. As a check of agreement
(not of accuracy), the nominal depth label of each quadrat is compared with the EMODnet
high-resolution lidar bathymetry of 2011 at its recorded position, allowing for the
modelled tide range over the survey dates and a tolerance of 3 m. The record carries the
archived result in position_qc.csv and the inputs of the calculation in
position_qc_provenance.json.

Two uses:

    arrabida-check-positions --record <folder with position_qc.csv and position_qc_provenance.json>

recomputes every residual and status from the archived lidar samples and water levels and
reports whether they match the archived table (81 consistent, 5 depth_mismatch, 4
no_bathymetry in release 1.0.0).

    arrabida-check-positions --record <folder> --lidar emodnet_hr_lidar_sesimbra.tif --out position_qc_rebuilt.csv

also samples the lidar raster at the positions of kelp_quadrats.csv (containing cell, and
the finite range of the surrounding 3 × 3 cells), rebuilds the table and compares it with
the archived one. The raster is not part of the record; download
`590_HR_Lidar_Sul` from EMODnet Bathymetry (https://emodnet.ec.europa.eu/geonetwork/srv/api/records/SDN_CPRD_590_HR_Lidar_Sul),
clipped to the Sesimbra site, as a GeoTIFF with depths positive downwards relative to LAT.
Needs the `lidar` extra (rasterio) for this second use only.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path

TOLERANCE_M = 3.0
STATUS = {"pass": "consistent", "flag": "depth_mismatch", "no_lidar": "no_bathymetry"}
COLUMNS = [
    "event_id", "campaign", "longitude", "latitude", "workbook_depth_label_m", "lidar_depth_m",
    "lidar_nbr_min_m", "lidar_nbr_max_m", "depth_residual_low_m", "depth_residual_high_m",
    "depth_qc_status", "depth_qc_neighbour_reconciles",
]


def rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def tide_range(provenance: dict, campaign: str) -> tuple[float, float]:
    """Lowest low and highest high water (m above LAT) over the campaign's plausible dates."""
    dates = provenance["method"]["plausible_survey_dates_at_original_run"][campaign]
    water = [w for w in provenance["water_level_rows"] if w["campaign"] == campaign and w["date"] in dates]
    return min(float(w["min_m"]) for w in water), max(float(w["max_m"]) for w in water)


def evaluate(label: float, lidar: float | None, nbr_min: float | None, nbr_max: float | None, tide: tuple[float, float]) -> dict:
    """Residuals and status of one quadrat, as the archived table defines them."""
    if lidar is None or math.isnan(lidar):
        return {"low": None, "high": None, "status": "no_lidar", "neighbour": ""}
    low_tide, high_tide = tide
    low = label - lidar - high_tide
    high = label - lidar - low_tide
    status = "pass" if high >= -TOLERANCE_M and low <= TOLERANCE_M else "flag"
    neighbour = ""
    if status == "flag" and nbr_min is not None and nbr_max is not None:
        neighbour = str(label - nbr_min - low_tide >= -TOLERANCE_M and label - nbr_max - high_tide <= TOLERANCE_M).lower()
    return {"low": low, "high": high, "status": status, "neighbour": neighbour}


def verify_archived(record: Path) -> bool:
    provenance = json.loads((record / "position_qc_provenance.json").read_text(encoding="utf-8"))
    archived = rows(record / "position_qc.csv")
    problems, counts = [], {}
    for row in archived:
        lidar = float(row["lidar_depth_m"]) if row["lidar_depth_m"] else None
        result = evaluate(float(row["workbook_depth_label_m"]), lidar, None, None, tide_range(provenance, row["campaign"]))
        counts[result["status"]] = counts.get(result["status"], 0) + 1
        if result["status"] != row["depth_qc_status"]:
            problems.append(f"{row['event_id']}: status {result['status']} differs from archived {row['depth_qc_status']}")
        elif result["low"] is not None and (
            abs(result["low"] - float(row["depth_residual_low_m"])) > 1e-6 or abs(result["high"] - float(row["depth_residual_high_m"])) > 1e-6
        ):
            problems.append(f"{row['event_id']}: residuals differ from the archived values")
    print("archived table:", ", ".join(f"{counts.get(k, 0)} {STATUS[k]}" for k in ("pass", "flag", "no_lidar")))
    for problem in problems[:10]:
        print("  ", problem)
    print("archived residuals and statuses reproduce" if not problems else f"{len(problems)} rows differ")
    return not problems


def sample_lidar(raster: Path, points: list[tuple[float, float]]) -> list[tuple[float | None, float | None, float | None]]:
    """Depth of the containing cell and the finite range of its 3 × 3 neighbourhood."""
    import numpy as np
    import rasterio
    from pyproj import Transformer

    out = []
    with rasterio.open(raster) as src:
        band = src.read(1, masked=True).astype("float64")
        nodata = band.mask
        to_raster = Transformer.from_crs("EPSG:4326", src.crs, always_xy=True)
        for lon, lat in points:
            x, y = to_raster.transform(lon, lat)
            row, col = src.index(x, y)
            if not (0 <= row < src.height and 0 <= col < src.width) or nodata[row, col]:
                out.append((None, None, None))
                continue
            window = band[max(row - 1, 0): row + 2, max(col - 1, 0): col + 2]
            finite = window.compressed() if np.ma.isMaskedArray(window) else window[np.isfinite(window)]
            out.append((float(band[row, col]), float(finite.min()), float(finite.max())))
    return out


def rebuild(record: Path, raster: Path, out: Path) -> bool:
    provenance = json.loads((record / "position_qc_provenance.json").read_text(encoding="utf-8"))
    quadrats = rows(record / "kelp_quadrats.csv")
    samples = sample_lidar(raster, [(float(q["longitude"]), float(q["latitude"])) for q in quadrats])
    rebuilt = []
    for q, (lidar, nbr_min, nbr_max) in zip(quadrats, samples):
        label = float(q["depth_label_workbook_m"])
        result = evaluate(label, lidar, nbr_min, nbr_max, tide_range(provenance, q["campaign"]))
        rebuilt.append({
            "event_id": q["quadrat_id"], "campaign": q["campaign"], "longitude": q["longitude"], "latitude": q["latitude"],
            "workbook_depth_label_m": q["depth_label_workbook_m"],
            "lidar_depth_m": "" if lidar is None else repr(lidar), "lidar_nbr_min_m": "" if nbr_min is None else repr(nbr_min),
            "lidar_nbr_max_m": "" if nbr_max is None else repr(nbr_max),
            "depth_residual_low_m": "" if result["low"] is None else repr(result["low"]),
            "depth_residual_high_m": "" if result["high"] is None else repr(result["high"]),
            "depth_qc_status": result["status"], "depth_qc_neighbour_reconciles": result["neighbour"],
        })
    with out.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rebuilt)
    archived = {r["event_id"]: r for r in rows(record / "position_qc.csv")}
    differing = []
    for r in rebuilt:
        a = archived.get(r["event_id"])
        if a is None:
            differing.append(f"{r['event_id']}: not in the archived table")
            continue
        same_depth = (a["lidar_depth_m"] == "" and r["lidar_depth_m"] == "") or (
            a["lidar_depth_m"] and r["lidar_depth_m"] and abs(float(a["lidar_depth_m"]) - float(r["lidar_depth_m"])) < 1e-3
        )
        if not same_depth or a["depth_qc_status"] != r["depth_qc_status"]:
            differing.append(f"{r['event_id']}: lidar {a['lidar_depth_m'] or 'none'} / {r['lidar_depth_m'] or 'none'}, status {a['depth_qc_status']} / {r['depth_qc_status']}")
    for line in differing[:10]:
        print("  ", line)
    print(f"wrote {out}; " + ("lidar depths and statuses match the archived table" if not differing else f"{len(differing)} rows differ"))
    return not differing


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--record", type=Path, default=Path("."), help="folder with position_qc.csv, position_qc_provenance.json and kelp_quadrats.csv")
    parser.add_argument("--lidar", type=Path, help="EMODnet lidar GeoTIFF; when given, the table is rebuilt from the raster")
    parser.add_argument("--out", type=Path, default=Path("position_qc_rebuilt.csv"))
    args = parser.parse_args()
    ok = verify_archived(args.record)
    if args.lidar:
        ok = rebuild(args.record, args.lidar, args.out) and ok
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
