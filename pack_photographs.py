"""Quadrat photographs of the KelpObserve Sesimbra 2026 record: archives, manifest and checks.

CCMAR photographed every quadrat in July (one JPEG per quadrat, named Q1 to Q5 inside the
delivered transect folders) and every quadrat in September (a JPEG with an ARW raw file
beside it, not named by quadrat). June has no photographs. The files go into the record
under names that spell out the campaign, stratum, transect and either the quadrat (July)
or the capture order within the transect (September), packed in three ZIP archives
(stored, not recompressed) because a Zenodo record may hold at most 100 files, and
``photographs.csv`` describes each one: its archive, capture time from the camera's EXIF,
camera, size and checksum.

Sources: the two delivered photograph folders (one per campaign), each holding transect
folders named like ``16m_T1``. Their sizes and SHA-256 values are pinned in
``photo_sources.csv`` beside this script, so a rerun checks that it packs the same files.

    python pack_photographs.py --july <folder> --september <folder> --out <folder> [--tidy-dir <folder>]

writes the three ZIP archives and ``photographs.csv`` to ``--out``; with ``--tidy-dir``
(the record's ``kelp_quadrats.csv``) it also runs the checks of the record. The archives
are deterministic: each member carries its capture time, so a rerun on the same files
gives byte-identical ZIPs. ``--write-pins`` rewrites ``photo_sources.csv`` from the files
on disk, which is a deliberate act after a new delivery. Needs Pillow.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import re
import struct
import zipfile
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Any

from PIL import Image

HERE = Path(__file__).resolve().parent
PINS = HERE / "photo_sources.csv"
MANIFEST = "photographs.csv"
ARCHIVES = {
    ("july", "jpeg"): "photographs_july_jpeg.zip",
    ("september", "jpeg"): "photographs_september_jpeg.zip",
    ("september", "arw"): "photographs_september_arw.zip",
}
CAMERA = "SONY ILCE-7M4"
TIME_OFFSET = "+01:00"

_FOLDER = re.compile(r"^(?P<depth>\d+)m_T(?P<transect>[1-3])$")
_JULY_NAME = re.compile(r"^Q(?P<quadrat>[1-5])_DSC\d+\.JPG$")
_SEPTEMBER_NAME = re.compile(r"^DSC\d+\.(?P<ext>JPG|ARW)$")

# TIFF/EXIF tags read from the files.
_MAKE, _MODEL, _EXIF_IFD = 271, 272, 0x8769
_DATETIME_ORIGINAL, _OFFSET_TIME_ORIGINAL, _LENS_MODEL = 36867, 36881, 42036
_TIFF_SIZES = {1: 1, 2: 1, 3: 2, 4: 4, 5: 8, 7: 1, 9: 4, 10: 8}


@dataclass(frozen=True)
class Photo:
    """One delivered image file and what its EXIF says."""

    campaign: str
    stratum: str
    transect: int
    quadrat: int | None  # July only
    source: Path
    relative_path: str  # within the campaign's source folder
    format: str  # jpeg or arw
    stem: str  # DSC number shared by a JPEG and its ARW twin
    datetime_original: str  # ISO 8601, as the camera recorded it
    time_offset: str
    camera: str
    lens: str
    width: int | None
    height: int | None
    size: int


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _iso(exif_datetime: str) -> str:
    """'2026:09:02 11:02:13' as the camera writes it, to ISO 8601."""
    return dt.datetime.strptime(exif_datetime, "%Y:%m:%d %H:%M:%S").isoformat()


def exif_jpeg(source: Path | bytes) -> dict[str, Any]:
    with Image.open(BytesIO(source) if isinstance(source, bytes) else source) as image:
        exif = image.getexif()
        ifd = exif.get_ifd(_EXIF_IFD)
        return {
            "camera": f"{exif.get(_MAKE, '').strip()} {exif.get(_MODEL, '').strip()}".strip(),
            "lens": str(ifd.get(_LENS_MODEL, "")).strip(),
            "datetime_original": _iso(ifd[_DATETIME_ORIGINAL]),
            "time_offset": str(ifd.get(_OFFSET_TIME_ORIGINAL, "")),
            "width": image.width,
            "height": image.height,
        }


def _tiff_ifd(handle, order: str, offset: int) -> dict[int, Any]:
    handle.seek(offset)
    (count,) = struct.unpack(order + "H", handle.read(2))
    tags: dict[int, Any] = {}
    for index in range(count):
        entry = offset + 2 + 12 * index
        handle.seek(entry)
        tag, kind, number, value = struct.unpack(order + "HHII", handle.read(12))
        size = _TIFF_SIZES.get(kind, 1) * number
        if size <= 4:
            handle.seek(entry + 8)
        else:
            handle.seek(value)
        raw = handle.read(size)
        if kind == 2:
            tags[tag] = raw.rstrip(b"\x00").decode("ascii", "replace")
        elif kind in (3, 4):
            code = "H" if kind == 3 else "I"
            values = struct.unpack(order + code * number, raw)
            tags[tag] = values[0] if number == 1 else values
    return tags


def exif_arw(source: Path | bytes) -> dict[str, Any]:
    """Make, model and capture time from the TIFF structure of a Sony ARW file."""
    with (BytesIO(source) if isinstance(source, bytes) else source.open("rb")) as handle:
        header = handle.read(8)
        order = "<" if header[:2] == b"II" else ">"
        (first,) = struct.unpack(order + "I", header[4:8])
        ifd0 = _tiff_ifd(handle, order, first)
        exif = _tiff_ifd(handle, order, ifd0[_EXIF_IFD]) if _EXIF_IFD in ifd0 else {}
    return {
        "camera": f"{str(ifd0.get(_MAKE, '')).strip()} {str(ifd0.get(_MODEL, '')).strip()}".strip(),
        "lens": str(exif.get(_LENS_MODEL, "")).strip(),
        "datetime_original": _iso(exif[_DATETIME_ORIGINAL]),
        "time_offset": str(exif.get(_OFFSET_TIME_ORIGINAL, "")),
        "width": None,
        "height": None,
    }


def read_exif(source: Path | bytes, name: str | None = None) -> dict[str, Any]:
    name = name or (source.name if isinstance(source, Path) else "")
    return exif_arw(source) if name.upper().endswith(".ARW") else exif_jpeg(source)


def scan(source_dirs: dict[str, Path]) -> list[Photo]:
    """Every image file in the source folders, with its EXIF, in a fixed order."""
    photos = []
    for campaign, root in source_dirs.items():
        if not root.is_dir():
            raise FileNotFoundError(f"Photograph folder not found: {root}")
        for folder in sorted(root.iterdir()):
            match = _FOLDER.match(folder.name)
            if not folder.is_dir() or not match:
                continue
            stratum = "shallow" if int(match["depth"]) <= 10 else "deep"
            transect = int(match["transect"])
            for path in sorted(folder.iterdir()):
                if path.name.startswith("._") or path.name == ".DS_Store":
                    continue
                if campaign == "july":
                    name = _JULY_NAME.match(path.name)
                    quadrat = int(name["quadrat"]) if name else None
                else:
                    name = _SEPTEMBER_NAME.match(path.name)
                    quadrat = None
                if not name:
                    raise ValueError(f"Unexpected file in the photograph folders: {path}")
                exif = read_exif(path)
                photos.append(
                    Photo(
                        campaign=campaign,
                        stratum=stratum,
                        transect=transect,
                        quadrat=quadrat,
                        source=path,
                        relative_path=str(path.relative_to(root)),
                        format="arw" if path.suffix.upper() == ".ARW" else "jpeg",
                        stem=path.stem.split("_")[-1],
                        size=path.stat().st_size,
                        **exif,
                    )
                )
    return photos


def read_pins(path: Path = PINS) -> dict[tuple[str, str], tuple[int, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return {
            (row["campaign"], row["relative_path"]): (int(row["bytes"]), row["sha256"])
            for row in csv.DictReader(handle)
        }


def write_pins(path: Path, photos: list[Photo]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(["campaign", "relative_path", "bytes", "sha256"])
        for photo in photos:
            writer.writerow([photo.campaign, photo.relative_path, photo.size, sha256(photo.source)])


def record_name(photo: Photo, frame_order: int) -> str:
    extension = "arw" if photo.format == "arw" else "jpg"
    if photo.campaign == "july":
        return f"photo_july-{photo.stratum}-T{photo.transect}-Q{photo.quadrat}.{extension}"
    return f"photo_september-{photo.stratum}-T{photo.transect}-F{frame_order}.{extension}"


def _frame_orders(photos: list[Photo]) -> dict[tuple[str, str, int, str], int]:
    """Capture order of the September JPEGs within each transect; the ARW takes its twin's."""
    orders: dict[tuple[str, str, int, str], int] = {}
    jpegs = [p for p in photos if p.campaign == "september" and p.format == "jpeg"]
    by_transect: dict[tuple[str, int], list[Photo]] = {}
    for photo in jpegs:
        by_transect.setdefault((photo.stratum, photo.transect), []).append(photo)
    for (stratum, transect), group in by_transect.items():
        for order, photo in enumerate(
            sorted(group, key=lambda p: (p.datetime_original, p.stem)), start=1
        ):
            orders[("september", stratum, transect, photo.stem)] = order
    return orders


def archive_name(campaign: str, fmt: str) -> str:
    return ARCHIVES[(campaign, fmt)]


def _zip_date(iso: str) -> tuple[int, int, int, int, int, int]:
    moment = dt.datetime.fromisoformat(iso)
    return (moment.year, moment.month, moment.day, moment.hour, moment.minute, moment.second)


def stage(upload: Path, checks, source_dirs: dict[str, Path], pins_path: Path = PINS) -> list[dict[str, Any]]:
    """Put the photographs into the record and write ``photographs.csv``; return its rows."""
    photos = scan(source_dirs)
    pins = read_pins(pins_path)
    found = {(p.campaign, p.relative_path): (p.size, sha256(p.source)) for p in photos}
    checks.record(
        "photographs: the source files are exactly those pinned in photo_sources.csv, "
        "byte for byte",
        found == pins,
        ""
        if found == pins
        else (
            str(sorted(set(found) ^ set(pins))[:5])
            if set(found) != set(pins)
            else "a checksum differs"
        ),
    )
    orders = _frame_orders(photos)
    counts: dict[tuple[str, str, int], int] = {}
    for photo in photos:
        if photo.format == "jpeg":
            key = (photo.campaign, photo.stratum, photo.transect)
            counts[key] = counts.get(key, 0) + 1
    rows = []
    for photo in photos:
        if photo.campaign == "july":
            order = photo.quadrat
        else:
            order = orders[("september", photo.stratum, photo.transect, photo.stem)]
        name = record_name(photo, order)
        twin = None
        if photo.campaign == "september":
            twin_format = "jpeg" if photo.format == "arw" else "arw"
            twin = record_name(
                Photo(**{**photo.__dict__, "format": twin_format}), order
            )
        quadrat_id = (
            f"july-{photo.stratum}-T{photo.transect}-Q{photo.quadrat}"
            if photo.campaign == "july"
            else ""
        )
        rows.append(
            {
                "file": name,
                "archive": archive_name(photo.campaign, photo.format),
                "campaign": photo.campaign,
                "stratum": photo.stratum,
                "transect": photo.transect,
                "quadrat": photo.quadrat if photo.quadrat is not None else "",
                "frame_order": order,
                "n_frames_in_transect": counts[(photo.campaign, photo.stratum, photo.transect)],
                "quadrat_id": quadrat_id,
                "format": photo.format,
                "paired_file": twin or "",
                "datetime_original": photo.datetime_original,
                "exif_time_offset": photo.time_offset,
                "camera": photo.camera,
                "lens": photo.lens,
                "width_px": photo.width if photo.width is not None else "",
                "height_px": photo.height if photo.height is not None else "",
                "bytes": photo.size,
                "sha256": found[(photo.campaign, photo.relative_path)][1],
                "original_folder": str(Path(photo.relative_path).parent),
                "original_name": Path(photo.relative_path).name,
            }
        )
    rows.sort(key=lambda row: row["file"])
    sources = {
        (photo.campaign, photo.relative_path): photo
        for photo in photos
    }
    by_name = {
        record_name(photo, photo.quadrat if photo.campaign == "july" else orders[("september", photo.stratum, photo.transect, photo.stem)]): photo
        for photo in photos
    }
    for archive in sorted(set(ARCHIVES.values())):
        members = [row for row in rows if row["archive"] == archive]
        with zipfile.ZipFile(upload / archive, "w", zipfile.ZIP_STORED, allowZip64=True) as zf:
            for row in members:
                info = zipfile.ZipInfo(row["file"], date_time=_zip_date(row["datetime_original"]))
                info.compress_type = zipfile.ZIP_STORED
                info.external_attr = 0o644 << 16
                zf.writestr(info, by_name[row["file"]].source.read_bytes())
    with (upload / MANIFEST).open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    return rows


def check(upload: Path, tables: dict[str, list[dict[str, str]]], checks) -> None:
    """``photographs.csv`` against the staged files and the quadrat table."""
    with (upload / MANIFEST).open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    quadrats = {q["quadrat_id"]: q for q in tables["kelp_quadrats"]}

    mismatched = []
    archives: dict[str, zipfile.ZipFile] = {}
    for name in sorted({row["archive"] for row in rows}):
        if (upload / name).is_file():
            archives[name] = zipfile.ZipFile(upload / name)
    listed = {(row["archive"], row["file"]) for row in rows}
    extra = sorted(
        (name, member) for name, zf in archives.items() for member in zf.namelist()
        if (name, member) not in listed
    )
    checks.record(
        "photographs: the archives hold exactly the files photographs.csv lists, stored "
        "without recompression",
        set(archives) == set(ARCHIVES.values())
        and not extra
        and all(info.compress_type == zipfile.ZIP_STORED for zf in archives.values() for info in zf.infolist()),
        f"archives {sorted(archives)}; extra members {extra[:3]}",
    )
    for row in rows:
        zf = archives.get(row["archive"])
        if zf is None or row["file"] not in zf.namelist():
            mismatched.append(row["file"] + " (missing)")
            continue
        data = zf.read(row["file"])
        exif = read_exif(data, row["file"])
        same = (
            int(row["bytes"]) == len(data)
            and row["sha256"] == hashlib.sha256(data).hexdigest()
            and row["datetime_original"] == exif["datetime_original"]
            and row["exif_time_offset"] == exif["time_offset"]
            and row["camera"] == exif["camera"]
            and row["lens"] == exif["lens"]
            and row["width_px"] == ("" if exif["width"] is None else str(exif["width"]))
            and row["height_px"] == ("" if exif["height"] is None else str(exif["height"]))
        )
        if not same:
            mismatched.append(row["file"])
    for zf in archives.values():
        zf.close()
    checks.record(
        "photographs.csv: size, checksum and EXIF of every row equal the staged file's",
        not mismatched,
        str(mismatched[:5]),
    )

    july = [row for row in rows if row["campaign"] == "july"]
    july_ids = sorted(row["quadrat_id"] for row in july)
    expected_july = sorted(q for q in quadrats if q.startswith("july-"))
    checks.record(
        "photographs.csv: one JPEG for each of the 30 July quadrats, named by its quadrat_id",
        july_ids == expected_july
        and all(row["format"] == "jpeg" for row in july)
        and all(row["file"] == f"photo_{row['quadrat_id']}.jpg" for row in july),
        f"{len(july)} July rows",
    )

    september = [row for row in rows if row["campaign"] == "september"]
    jpegs = [row for row in september if row["format"] == "jpeg"]
    arws = [row for row in september if row["format"] == "arw"]
    by_file = {row["file"]: row for row in september}
    paired = all(
        row["paired_file"] in by_file
        and by_file[row["paired_file"]]["paired_file"] == row["file"]
        and by_file[row["paired_file"]]["original_name"].split(".")[0]
        == row["original_name"].split(".")[0]
        and by_file[row["paired_file"]]["datetime_original"] == row["datetime_original"]
        for row in september
    )
    per_transect: dict[tuple[str, str], list[dict[str, str]]] = {}
    for row in jpegs:
        per_transect.setdefault((row["stratum"], row["transect"]), []).append(row)
    orders_fit = all(
        sorted(int(row["frame_order"]) for row in group) == list(range(1, len(group) + 1))
        and all(int(row["n_frames_in_transect"]) == len(group) for row in group)
        and [
            row["datetime_original"]
            for row in sorted(group, key=lambda row: int(row["frame_order"]))
        ]
        == sorted(row["datetime_original"] for row in group)
        for group in per_transect.values()
    )
    checks.record(
        "photographs.csv: September has 33 JPEG frames with their ARW twins, 5 to 7 per "
        "transect, numbered in capture order",
        len(jpegs) == 33
        and len(arws) == 33
        and paired
        and len(per_transect) == 6
        and all(5 <= len(group) <= 7 for group in per_transect.values())
        and orders_fit
        and all(row["quadrat_id"] == "" and row["quadrat"] == "" for row in september),
        f"{len(jpegs)} JPEG, {len(arws)} ARW, transects {sorted(per_transect)}",
    )

    date_problems = []
    for row in rows:
        day = row["datetime_original"][:10]
        if row["campaign"] == "july":
            expected = quadrats[row["quadrat_id"]]["date_dive_log"]
        else:
            group = [
                q
                for q in quadrats.values()
                if (q["campaign"], q["stratum"], q["transect"])
                == ("september", row["stratum"], row["transect"])
            ]
            expected = group[0]["date_workbook"] if group else ""
        relevant = [quadrats[row['quadrat_id']]] if row['campaign'] == 'july' else group
        if any(q['survey_date'] != day for q in relevant):
            date_problems.append(f"{row['file']}: survey_date differs from photograph date")
        if day != expected:
            date_problems.append(f"{row['file']}: {day} not {expected}")
    checks.record(
        "photographs.csv: each capture date is the dive-log day (July) or the workbook day "
        "(September) of its transect",
        not date_problems,
        "; ".join(date_problems[:5]),
    )

    july_groups: dict[tuple[str, str], list[dict[str, str]]] = {}
    for row in july:
        july_groups.setdefault((row["stratum"], row["transect"]), []).append(row)
    checks.record(
        "photographs.csv: July capture times rise with the quadrat number in every transect",
        all(
            [row["datetime_original"] for row in sorted(group, key=lambda r: int(r["quadrat"]))]
            == sorted(row["datetime_original"] for row in group)
            for group in july_groups.values()
        ),
    )
    checks.record(
        f"photographs.csv: one camera ({CAMERA}) and a {TIME_OFFSET} EXIF offset throughout",
        all(row["camera"] == CAMERA and row["exif_time_offset"] == TIME_OFFSET for row in rows),
    )


class Checks:
    """Collects named checks; prints each outcome; fails the run if any check failed."""

    def __init__(self) -> None:
        self.failed: list[str] = []

    def record(self, name: str, passed: bool, detail: str = "") -> None:
        print(("pass  " if passed else "FAIL  ") + name + ("" if passed or not detail else f": {detail}"))
        if not passed:
            self.failed.append(name)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--july", type=Path, required=True, help="delivered July photograph folder")
    parser.add_argument("--september", type=Path, required=True, help="delivered September photograph folder")
    parser.add_argument("--out", type=Path, help="folder for the three archives and photographs.csv")
    parser.add_argument("--tidy-dir", type=Path, help="folder with kelp_quadrats.csv, to run the checks of the record")
    parser.add_argument("--pins", type=Path, default=PINS, help="pinned sizes and hashes of the source files")
    parser.add_argument("--write-pins", action="store_true", help="rewrite the pins from the files on disk and stop")
    args = parser.parse_args()
    source_dirs = {"july": args.july, "september": args.september}
    if args.write_pins:
        write_pins(args.pins, scan(source_dirs))
        print(f"pinned {sum(1 for _ in open(args.pins)) - 1} files in {args.pins}")
        return 0
    if not args.out:
        for photo in scan(source_dirs):
            print(photo.campaign, photo.relative_path, photo.datetime_original, photo.size)
        return 0
    args.out.mkdir(parents=True, exist_ok=True)
    checks = Checks()
    rows = stage(args.out, checks, source_dirs, args.pins)
    print(f"{len(rows)} files in {sorted({r['archive'] for r in rows})}, manifest {args.out / MANIFEST}")
    if args.tidy_dir:
        with (args.tidy_dir / "kelp_quadrats.csv").open(newline="", encoding="utf-8") as handle:
            check(args.out, {"kelp_quadrats": list(csv.DictReader(handle))}, checks)
    return 1 if checks.failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
