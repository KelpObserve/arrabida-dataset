"""Tidy tables of the KelpObserve Sesimbra 2026 dataset, from the files CCMAR delivered.

Reads the five delivered files (two workbooks, three GeoPackages) under the names they
carry in the Zenodo record, and writes the six tidy files of that record:

    kelp_quadrats.csv       one row per surveyed quadrat (90)
    kelp_quadrats.geojson   the same rows as points
    kelp_individuals.csv    one row per measured kelp individual
    sonde_casts.csv         one row per sonde cast (7)
    sonde_profiles.csv      one row per sonde sample
    dive_tracks.geojson     one GPS track per campaign (3)

The script renames columns, joins the quadrat positions to the quadrat records, swaps the sonde dates back from their day-first storage,
adds the evidence-based survey chronology while retaining the source date fields. 
README.md in the record describes every column and every known issue.

Run next to the delivered files::

    python make_tidy_tables.py --raw-dir . --out-dir tidy

Needs Python 3.10 or later with pandas, openpyxl, geopandas (pyogrio) and pyproj.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
from pathlib import Path
from typing import Any

import pandas as pd

# The delivered files, under the names they carry in the Zenodo record.
RAW_FILES = {
    "kelp_workbook": "raw_ccmar_kelp_quadrats_2026.xlsx",
    "sonde_workbook": "raw_ccmar_sonde_casts_2026.xlsx",
    "positions": "raw_ccmar_quadrat_positions_2026.gpkg",
    "july_dive_log": "raw_ccmar_quadrat_positions_july_dive_log.gpkg",
    "dive_tracks": "raw_ccmar_dive_tracks_2026.gpkg",
}
TIDY_FILES = [
    "kelp_quadrats.csv",
    "kelp_quadrats.geojson",
    "kelp_individuals.csv",
    "sonde_casts.csv",
    "sonde_profiles.csv",
    "dive_tracks.geojson",
]

YEAR = 2026
CAMPAIGNS = {6: "june", 7: "july", 9: "september"}
CAMPAIGN_ORDER = ["june", "july", "september"]
STRATUM_ORDER = ["shallow", "deep"]
# The position files write dates as day/month with Portuguese month abbreviations.
PT_MONTHS = {"jun": 6, "jul": 7, "set": 9}
# Nominal depth labels (m) used in either CCMAR file, per campaign. The kelp workbook and
# the position file label the same stratum differently in July and September.
STRATA = {
    "june": {8: "shallow", 15: "deep", 16: "deep"},
    "july": {7: "shallow", 16: "deep", 17: "deep"},
    "september": {6: "shallow", 7: "shallow", 15: "deep", 17: "deep"},
}
# First and last survey date recorded for each campaign in any source. The sources
# disagree within these ranges (README, known issue 1), so the range is the event date.
EVENT_DATES = {
    "june": (dt.date(2026, 6, 2), dt.date(2026, 6, 2)),
    "july": (dt.date(2026, 7, 6), dt.date(2026, 7, 8)),
    "september": (dt.date(2026, 9, 1), dt.date(2026, 9, 2)),
}

TAXON = "saccorhiza polyschides"
EMPTY = "empty"
SCIENTIFIC_NAME = "Saccorhiza polyschides"
SCIENTIFIC_NAME_ID = "urn:lsid:marinespecies.org:taxname:145735"

KELP_COLUMNS = [
    "Date",
    "Depth",
    "Transect",
    "Quadrat",
    "Species",
    "Juvenile (< 30cm)",
    "Adult (>= 30cm)",
    "Size",
    "Erosion",
    "Epibiont",
    "% cover",
    "Notes",
]
JUVENILE, ADULT, COVER = "Juvenile (< 30cm)", "Adult (>= 30cm)", "% cover"


# Outcome of the depth check on the recorded positions (README, known issue 3). The check
# compares each quadrat's nominal depth with the 2011 lidar bathymetry at its recorded
# position. It was run in the project's benchmark and is carried here as a label only.
POSITION_DEPTH_MISMATCH = {
    "june-deep-T1-Q5",
    "september-deep-T1-Q1",
    "september-deep-T1-Q2",
    "september-deep-T1-Q3",
    "september-deep-T1-Q4",
}
POSITION_NO_BATHYMETRY = {
    "september-shallow-T3-Q1",
    "september-shallow-T3-Q2",
    "september-shallow-T3-Q3",
    "september-shallow-T3-Q5",
}

QUADRAT_COLUMNS = [
    "quadrat_id",
    "campaign",
    "stratum",
    "transect",
    "quadrat",
    "survey_date",
    "survey_date_evidence",
    "event_date",
    "date_workbook",
    "date_positions",
    "date_dive_log",
    "dive_time_local",
    "tape_position_m",
    "depth_label_workbook_m",
    "depth_label_positions_m",
    "latitude",
    "longitude",
    "position_check",
    "scientific_name",
    "scientific_name_id",
    "occurrence_status",
    "cover_pct",
    "cover_pct_recorded",
    "cover_status",
    "n_individuals",
    "n_juvenile",
    "n_adult",
    "erosion_count",
    "epibiont_count",
    "notes",
    "workbook_rows",
]
QUADRAT_INTEGERS = [
    "transect",
    "quadrat",
    "tape_position_m",
    "depth_label_workbook_m",
    "depth_label_positions_m",
    "cover_pct",
    "cover_pct_recorded",
    "n_individuals",
    "n_juvenile",
    "n_adult",
    "erosion_count",
    "epibiont_count",
]
INDIVIDUAL_COLUMNS = [
    "individual_id",
    "quadrat_id",
    "campaign",
    "stratum",
    "transect",
    "quadrat",
    "life_stage",
    "size_cm",
    "erosion_recorded",
    "epibiont_recorded",
    "workbook_row",
]
INDIVIDUAL_INTEGERS = [
    "transect",
    "quadrat",
    "size_cm",
    "erosion_recorded",
    "epibiont_recorded",
    "workbook_row",
]

# Sonde sheet headers, reduced to their ASCII words by ``header_key``, and the tidy column
# each becomes. The order here is the column order of sonde_profiles.csv.
SONDE_CHANNELS = {
    "Depth m": "depth_m",
    "Temp C": "temperature_c",
    "Sal psu": "salinity_psu",
    "Cond uS/cm": "conductivity_us_cm",
    "Sp Cond uS/cm": "specific_conductance_us_cm",
    "nLFCond uS/cm": "nlf_conductivity_us_cm",
    "TDS mg/L": "tds_mg_l",
    "Resistivity ohms-cm": "resistivity_ohm_cm",
    "Water Density Sigma": "sigma_kg_m3",
    "Water Density Sigma-T": "sigma_t_kg_m3",
    "DO % Sat": "do_pct_sat",
    "DO % CB": "do_pct_cb",
    "DO mg/L": "do_mg_l",
    "pH pH": "ph",
    "pH mV": "ph_mv",
    "Chlorophyll RFU": "chlorophyll_rfu",
    "Chlorophyll ug/L": "chlorophyll_ug_l",
    "Phycoerythrin RFU": "phycoerythrin_rfu",
    "Phycoerythrin ug/L": "phycoerythrin_ug_l",
    "fDOM RFU": "fdom_rfu",
    "fDOM QSU": "fdom_qsu",
    "Turbidity FNU": "turbidity_fnu",
}
SONDE_LEADING = [
    "Project",
    "Site Name",
    "GPS Lat",
    "GPS Long",
    "Date MM/DD/YYYY",
    "Time hh mm ss tt",
]
SONDE_MONTHS = {"jun": 6, "jul": 7, "sep": 9}
# Site names end in, for example, "_Jun26_Day1_12m" or "_Sep26_6m".
SITE_RE = re.compile(r"_(?P<month>Jun|Jul|Sep)26(?:_Day(?P<day>\d+))?_(?P<depth>\d+)m$")

CAST_COLUMNS = [
    "cast_id",
    "site_name",
    "campaign",
    "station_depth_label_m",
    "date",
    "date_as_stored",
    "time_start_logged",
    "time_end_logged",
    "latitude",
    "longitude",
    "n_samples",
    "direction",
    "n_profile_samples",
    "depth_min_m",
    "depth_max_m",
]
PROFILE_COLUMNS = [
    "cast_id",
    "sample",
    "date",
    "time_logged",
    "in_profile_leg",
    *SONDE_CHANNELS.values(),
]

TRACK_COORD_DECIMALS = 7


def require(condition: Any, message: str) -> None:
    if not condition:
        raise ValueError(message)


def whole_number(value: Any, what: str) -> int | None:
    """A whole number, or None for a blank cell; anything else stops the run."""
    if value is None or pd.isna(value):
        return None
    number = float(value)
    require(number == int(number), f"{what}: expected a whole number, found {value!r}")
    return int(number)


def event_date(campaign: str) -> str:
    """ISO 8601 date, or interval, over every survey date recorded for the campaign."""
    first, last = EVENT_DATES[campaign]
    return first.isoformat() if first == last else f"{first.isoformat()}/{last.isoformat()}"


def survey_date(campaign: str, stratum: str, transect: int) -> tuple[str, str]:
    """Release chronology; raw source dates and their original envelope are retained."""
    if campaign == "june":
        return "2026-06-02", "Kelp workbook, GPS campaign record and campaign chronology"
    if campaign == "july":
        day = "2026-07-07" if stratum == "shallow" and transect in (1, 2) else "2026-07-08"
        return day, "July timed dive log and corresponding quadrat photograph EXIF dates"
    if campaign == "september":
        return "2026-09-02", "Transect photograph EXIF dates, workbook and campaign chronology"
    raise ValueError(f"Unknown campaign: {campaign}")


def quadrat_id(campaign: str, stratum: str, transect: int, quadrat: int) -> str:
    return f"{campaign}-{stratum}-T{transect}-Q{quadrat}"


def as_integers(frame: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    """Nullable integer columns, so a blank stays blank and 15 is not written as 15.0."""
    for column in columns:
        frame[column] = pd.array(
            [None if pd.isna(value) else int(value) for value in frame[column]], dtype="Int64"
        )
    return frame


# ---------------------------------------------------------------------------
# Kelp quadrats
# ---------------------------------------------------------------------------


def read_kelp_workbook(path: Path) -> pd.DataFrame:
    """The kelp workbook, with the Excel row number of every record."""
    rows = pd.read_excel(path, sheet_name=0)
    require(
        list(rows.columns) == KELP_COLUMNS,
        f"Kelp workbook columns changed: {list(rows.columns)}",
    )
    rows.insert(0, "workbook_row", rows.index + 2)  # the header is row 1
    return rows


def taxon(value: Any) -> str:
    text = str(value).strip().lower()
    require(text in (TAXON, EMPTY), f"Unmapped species entry {value!r} in the kelp workbook.")
    return text


def life_stage(row: pd.Series) -> str | None:
    """'juvenile' or 'adult' from the row's mark, or None where neither is marked."""
    where = f"Workbook row {row['workbook_row']}"
    juvenile = whole_number(row[JUVENILE], JUVENILE)
    adult = whole_number(row[ADULT], ADULT)
    require(juvenile in (None, 1) and adult in (None, 1), f"{where}: a life-stage mark is not 1.")
    require(not (juvenile and adult), f"{where}: marked both juvenile and adult.")
    return "juvenile" if juvenile else "adult" if adult else None


def column_total(group: pd.DataFrame, column: str) -> int | None:
    """Sum of the values recorded in a column over a quadrat's rows; None if all blank."""
    values = [whole_number(value, column) for value in group[column] if not pd.isna(value)]
    return sum(values) if values else None


def kelp_tables(rows: pd.DataFrame) -> tuple[list[dict], list[dict]]:
    """Quadrat records and individual records, in workbook order."""
    quadrats: list[dict] = []
    individuals: list[dict] = []
    keys = ["Date", "Depth", "Transect", "Quadrat"]
    for (day, depth, transect, number), group in rows.groupby(keys, sort=False):
        date = pd.Timestamp(day).date()
        campaign = CAMPAIGNS[date.month]
        label = whole_number(depth, "Depth")
        require(label in STRATA[campaign], f"Unmapped workbook depth {label} m in {campaign}.")
        stratum = STRATA[campaign][label]
        transect, number = int(transect), int(number)
        identifier = quadrat_id(campaign, stratum, transect, number)
        source_rows = [int(r) for r in group["workbook_row"]]
        require(
            source_rows == list(range(source_rows[0], source_rows[-1] + 1)),
            f"{identifier}: workbook rows are not contiguous: {source_rows}",
        )
        empty = [taxon(value) == EMPTY for value in group["Species"]]
        require(all(empty) or not any(empty), f"{identifier}: EMPTY and kelp rows together.")
        absent = all(empty)

        covers = [value for value in group[COVER] if not pd.isna(value)]
        require(len(covers) <= 1, f"{identifier}: more than one cover value.")
        recorded = whole_number(covers[0], COVER) if covers else None
        erosion, epibiont = column_total(group, "Erosion"), column_total(group, "Epibiont")

        plants: list[dict] = []
        if absent:
            require(recorded in (None, 0), f"{identifier}: EMPTY with cover {recorded}.")
            require(erosion is None and epibiont is None, f"{identifier}: EMPTY with counts.")
            status = "absent_blank" if recorded is None else "absent_recorded_zero"
            cover = 0
        else:
            status = "present_not_scored" if recorded is None else "scored"
            cover = recorded
            for _, row in group.iterrows():
                stage = life_stage(row)
                size = whole_number(row["Size"], "Size")
                if stage is None and size is None:
                    continue  # the species is named but nothing was measured
                plants.append(
                    {
                        "individual_id": f"{identifier}-I{len(plants) + 1:02d}",
                        "quadrat_id": identifier,
                        "campaign": campaign,
                        "stratum": stratum,
                        "transect": transect,
                        "quadrat": number,
                        "life_stage": stage,
                        "size_cm": size,
                        "erosion_recorded": whole_number(row["Erosion"], "Erosion"),
                        "epibiont_recorded": whole_number(row["Epibiont"], "Epibiont"),
                        "workbook_row": int(row["workbook_row"]),
                    }
                )
        individuals.extend(plants)

        notes = [str(v).strip() for v in group["Notes"] if not pd.isna(v) and str(v).strip()]
        first_row, last_row = source_rows[0], source_rows[-1]
        quadrats.append(
            {
                "quadrat_id": identifier,
                "campaign": campaign,
                "stratum": stratum,
                "transect": transect,
                "quadrat": number,
                "survey_date": survey_date(campaign, stratum, transect)[0],
                "survey_date_evidence": survey_date(campaign, stratum, transect)[1],
                "event_date": event_date(campaign),
                "date_workbook": date.isoformat(),
                "depth_label_workbook_m": label,
                "scientific_name": SCIENTIFIC_NAME,
                "scientific_name_id": SCIENTIFIC_NAME_ID,
                "occurrence_status": "absent" if absent else "present",
                "cover_pct": cover,
                "cover_pct_recorded": recorded,
                "cover_status": status,
                "n_individuals": len(plants),
                "n_juvenile": sum(plant["life_stage"] == "juvenile" for plant in plants),
                "n_adult": sum(plant["life_stage"] == "adult" for plant in plants),
                "erosion_count": erosion,
                "epibiont_count": epibiont,
                "notes": "; ".join(dict.fromkeys(notes)) or None,
                "workbook_rows": str(first_row)
                if first_row == last_row
                else f"{first_row}-{last_row}",
            }
        )
    identifiers = [quadrat["quadrat_id"] for quadrat in quadrats]
    require(len(set(identifiers)) == len(identifiers), "Duplicate quadrat in the kelp workbook.")
    return quadrats, individuals


def position_date(text: Any) -> dt.date:
    """Dates such as '01/set' in the position files (day/Portuguese month)."""
    day, _, month = str(text).strip().lower().partition("/")
    require(day.isdigit() and month in PT_MONTHS, f"Unrecognised position date {text!r}")
    return dt.date(YEAR, PT_MONTHS[month], int(day))


def numbered(text: Any, prefix: str) -> int:
    match = re.fullmatch(re.escape(prefix) + r"(\d+)", str(text).strip())
    require(match is not None, f"Unrecognised identifier {text!r}; expected {prefix}<n>")
    return int(match.group(1))


def depth_label(text: Any) -> int:
    match = re.fullmatch(r"(\d+)m", str(text).strip())
    require(match is not None, f"Unrecognised depth label {text!r}")
    return int(match.group(1))


def read_positions(path: Path) -> dict[str, dict]:
    """Quadrat positions of the final delivery, keyed by quadrat id."""
    import geopandas as gpd

    points = gpd.read_file(path, layer="transects")
    require(points.crs is not None and points.crs.to_epsg() == 4326, "Positions are not WGS84.")
    positions: dict[str, dict] = {}
    for _, row in points.iterrows():
        date = position_date(row["Date"])
        campaign = CAMPAIGNS[date.month]
        label = depth_label(row["Depth"])
        require(label in STRATA[campaign], f"Unmapped position depth {label} m in {campaign}.")
        identifier = quadrat_id(
            campaign,
            STRATA[campaign][label],
            numbered(row["Transect number"], "T"),
            numbered(row["Quadrat"], "Q"),
        )
        require(identifier not in positions, f"{identifier}: two positions.")
        longitude, latitude = float(row.geometry.x), float(row.geometry.y)
        require(
            abs(longitude - float(row["GPS Long"])) < 1e-9
            and abs(latitude - float(row["GPS Lat"])) < 1e-9,
            f"{identifier}: the geometry and the GPS attributes differ.",
        )
        positions[identifier] = {
            "date_positions": date.isoformat(),
            "depth_label_positions_m": label,
            "latitude": latitude,
            "longitude": longitude,
        }
    return positions


def read_july_dive_log(path: Path) -> dict[tuple[float, float], dict]:
    """The July delivery's timed points: date, time and tape mark, keyed by position."""
    import geopandas as gpd
    import pyogrio

    timed = [
        name
        for name, _ in pyogrio.list_layers(path)
        if "Time" in list(pyogrio.read_info(path, layer=name)["fields"])
    ]
    require(len(timed) == 1, f"Expected one timed layer in the July delivery, found {timed}")
    points = gpd.read_file(path, layer=timed[0])
    log: dict[tuple[float, float], dict] = {}
    for _, row in points.iterrows():
        date = position_date(row["Date"])
        require(CAMPAIGNS[date.month] == "july", "The timed layer holds non-July points.")
        key = (float(row.geometry.x), float(row.geometry.y))
        require(key not in log, f"Two timed points at {key}.")
        log[key] = {
            "date_dive_log": date.isoformat(),
            "dive_time_local": clock(row["Time"]).strftime("%H:%M:%S"),
            "tape_position_m": numbered(row["Quadrat"], "#"),
            "stratum": STRATA["july"][depth_label(row["Depth"])],
            "transect": numbered(row["Transect number"], "T"),
        }
    return log


def position_check(identifier: str) -> str:
    if identifier in POSITION_DEPTH_MISMATCH:
        return "depth_mismatch"
    if identifier in POSITION_NO_BATHYMETRY:
        return "no_bathymetry"
    return "consistent"


def quadrat_table(
    quadrats: list[dict], positions: dict[str, dict], dive_log: dict[tuple[float, float], dict]
) -> pd.DataFrame:
    """Join the positions and the July dive log to the quadrat records."""
    require(
        {quadrat["quadrat_id"] for quadrat in quadrats} == set(positions),
        "The kelp workbook and the position file do not hold the same quadrats.",
    )
    matched = set()
    records = []
    for quadrat in quadrats:
        identifier = quadrat["quadrat_id"]
        record = {**quadrat, **positions[identifier], "position_check": position_check(identifier)}
        if record["campaign"] == "july":
            key = (record["longitude"], record["latitude"])
            require(key in dive_log, f"{identifier}: no timed point at its position.")
            entry = dive_log[key]
            require(
                (entry["stratum"], entry["transect"]) == (record["stratum"], record["transect"]),
                f"{identifier}: the timed point at its position belongs to another transect.",
            )
            matched.add(key)
            for field in ("date_dive_log", "dive_time_local", "tape_position_m"):
                record[field] = entry[field]
        first, last = EVENT_DATES[record["campaign"]]
        for field in ("date_workbook", "date_positions", "date_dive_log"):
            if record.get(field):
                recorded = dt.date.fromisoformat(record[field])
                require(
                    first <= recorded <= last,
                    f"{identifier}: {field} {recorded} is outside {first} to {last}.",
                )
        records.append(record)
    require(matched == set(dive_log), "Timed July points without a quadrat.")

    frame = pd.DataFrame(records).reindex(columns=QUADRAT_COLUMNS)
    frame["_campaign"] = frame["campaign"].map(CAMPAIGN_ORDER.index)
    frame["_stratum"] = frame["stratum"].map(STRATUM_ORDER.index)
    frame = (
        frame.sort_values(["_campaign", "_stratum", "transect", "quadrat"], kind="stable")
        .drop(columns=["_campaign", "_stratum"])
        .reset_index(drop=True)
    )
    return as_integers(frame, QUADRAT_INTEGERS)


def individual_table(individuals: list[dict], quadrats: pd.DataFrame) -> pd.DataFrame:
    """Individuals in the order of the quadrat table, then of the workbook."""
    frame = pd.DataFrame(individuals).reindex(columns=INDIVIDUAL_COLUMNS)
    order = {identifier: i for i, identifier in enumerate(quadrats["quadrat_id"])}
    frame["_quadrat"] = frame["quadrat_id"].map(order)
    frame = (
        frame.sort_values(["_quadrat", "workbook_row"], kind="stable")
        .drop(columns="_quadrat")
        .reset_index(drop=True)
    )
    return as_integers(frame, INDIVIDUAL_INTEGERS)


# ---------------------------------------------------------------------------
# Sonde casts
# ---------------------------------------------------------------------------


def header_key(header: Any) -> str:
    """ASCII words of a sheet header: 'Cond ( µS/cm )' becomes 'Cond uS/cm'.

    The temperature header carries a mis-encoded degree sign; this drops it.
    """
    text = str(header).replace("µ", "u").replace("μ", "u")
    return " ".join(re.findall(r"[A-Za-z0-9%/-]+", text))


def clock(value: Any) -> dt.time:
    if isinstance(value, dt.datetime):
        return value.time()
    if isinstance(value, dt.time):
        return value
    return dt.datetime.strptime(str(value).strip(), "%H:%M:%S").time()


def sonde_date(stored: Any, month: int) -> dt.date:
    """The cast date from the sheet's day-first value.

    The column is headed MM/DD/YYYY but holds DD/MM values, so 1 June reads as 6 January.
    Day and month are swapped back. The result must fall in ``month``, the month in the
    site name; otherwise the sheet is not the one this script was written for.
    """
    stamp = pd.Timestamp(stored)
    require(not pd.isna(stamp), "A sonde sample has no date.")
    require(stamp.day <= 12, f"{stamp.date()} cannot be a day-first date read month-first.")
    swapped = dt.date(stamp.year, stamp.day, stamp.month)
    require(
        swapped.month == month,
        f"{stamp.date()}: swapping day and month gives {swapped}, not month {month}.",
    )
    return swapped


def profile_leg(depths: list[float]) -> tuple[int, int, str]:
    """First and last index of the leg between the shallowest and the deepest reading.

    Casts were logged on the way down in June and on the way up in July and September.
    Samples outside the leg are the sonde waiting at the surface or at the bottom.
    """
    shallowest = min(range(len(depths)), key=depths.__getitem__)
    deepest = max(range(len(depths)), key=depths.__getitem__)
    if shallowest <= deepest:
        return shallowest, deepest, "down"
    return deepest, shallowest, "up"


def sonde_tables(path: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    """The cast table and the sample table, from the sonde workbook."""
    sheet = pd.read_excel(path, sheet_name=0, header=2)
    sheet.columns = [header_key(column) for column in sheet.columns]
    leading = len(SONDE_LEADING)
    require(
        list(sheet.columns[:leading]) == SONDE_LEADING
        and sorted(sheet.columns[leading:]) == sorted(SONDE_CHANNELS),
        f"Sonde sheet columns changed: {list(sheet.columns)}",
    )
    require(not sheet.isna().any().any(), "The sonde sheet has blank cells.")

    casts: list[dict] = []
    samples: list[pd.DataFrame] = []
    for site, group in sheet.groupby("Site Name", sort=False):
        match = SITE_RE.search(str(site))
        require(match is not None, f"Cannot parse sonde site name {site!r}")
        month = SONDE_MONTHS[match.group("month").lower()]
        campaign = CAMPAIGNS[month]
        label = int(match.group("depth"))
        identifier = f"{campaign}-{label}m"
        require(identifier not in [cast["cast_id"] for cast in casts], f"Two casts {identifier}.")

        stored = {pd.Timestamp(value) for value in group["Date MM/DD/YYYY"]}
        require(len(stored) == 1, f"{site}: more than one stored date.")
        stored_date = stored.pop()
        date = sonde_date(stored_date, month)
        places = {(float(lat), float(lon)) for lat, lon in zip(group["GPS Lat"], group["GPS Long"])}
        require(len(places) == 1, f"{site}: more than one position.")
        latitude, longitude = places.pop()

        clocks = [clock(value) for value in group["Time hh mm ss tt"]]
        require(clocks == sorted(clocks), f"{site}: samples are not in time order.")
        depths = [float(value) for value in group["Depth m"]]
        first, last, direction = profile_leg(depths)

        frame = group[list(SONDE_CHANNELS)].rename(columns=SONDE_CHANNELS).reset_index(drop=True)
        frame.insert(0, "in_profile_leg", [first <= i <= last for i in range(len(frame))])
        frame.insert(0, "time_logged", [time.strftime("%H:%M:%S") for time in clocks])
        frame.insert(0, "date", date.isoformat())
        frame.insert(0, "sample", range(1, len(frame) + 1))
        frame.insert(0, "cast_id", identifier)
        samples.append(frame)

        casts.append(
            {
                "cast_id": identifier,
                "site_name": str(site),
                "campaign": campaign,
                "station_depth_label_m": label,
                "date": date.isoformat(),
                "date_as_stored": stored_date.date().isoformat(),
                "time_start_logged": clocks[0].strftime("%H:%M:%S"),
                "time_end_logged": clocks[-1].strftime("%H:%M:%S"),
                "latitude": latitude,
                "longitude": longitude,
                "n_samples": len(frame),
                "direction": direction,
                "n_profile_samples": last - first + 1,
                "depth_min_m": min(depths),
                "depth_max_m": max(depths),
            }
        )
    cast_table = pd.DataFrame(casts).reindex(columns=CAST_COLUMNS)
    profile_table = pd.concat(samples, ignore_index=True).reindex(columns=PROFILE_COLUMNS)
    return cast_table, profile_table


# ---------------------------------------------------------------------------
# Dive tracks
# ---------------------------------------------------------------------------


def track_campaign(name: Any) -> str:
    """'June 2026', 'July 2026', or a GPS track name such as '01/09/26, 15:33:37'."""
    text = str(name).strip()
    for campaign in CAMPAIGN_ORDER:
        if text.lower().startswith(campaign):
            return campaign
    match = re.match(r"(\d{2})/(\d{2})/(\d{2}),", text)
    require(match is not None, f"Unrecognised track name {name!r}")
    return CAMPAIGNS[int(match.group(2))]


def dive_tracks(path: Path) -> dict:
    """The three tracks as an RFC 7946 FeatureCollection, without the Z values."""
    import geopandas as gpd
    from pyproj import Geod

    tracks = gpd.read_file(path, layer="maps")
    require(tracks.crs is not None and tracks.crs.to_epsg() == 4326, "Tracks are not WGS84.")
    geod = Geod(ellps="WGS84")
    features: dict[str, dict] = {}
    for _, row in tracks.iterrows():
        campaign = track_campaign(row["Name"])
        require(campaign not in features, f"Two tracks for {campaign}.")
        parts, length = [], 0.0
        for part in row.geometry.geoms:
            longitudes = [point[0] for point in part.coords]
            latitudes = [point[1] for point in part.coords]
            length += geod.line_length(longitudes, latitudes)
            parts.append(
                [
                    [round(lon, TRACK_COORD_DECIMALS), round(lat, TRACK_COORD_DECIMALS)]
                    for lon, lat in zip(longitudes, latitudes)
                ]
            )
        features[campaign] = {
            "type": "Feature",
            "properties": {
                "campaign": campaign,
                "label": str(row["Name"]).strip(),
                "n_parts": len(parts),
                "n_vertices": sum(len(part) for part in parts),
                "length_m": round(length, 1),
            },
            "geometry": {"type": "MultiLineString", "coordinates": parts},
        }
    require(set(features) == set(CAMPAIGN_ORDER), f"Tracks found for {sorted(features)} only.")
    return {
        "type": "FeatureCollection",
        "name": "dive_tracks",
        "features": [features[campaign] for campaign in CAMPAIGN_ORDER],
    }


# ---------------------------------------------------------------------------
# Writers
# ---------------------------------------------------------------------------


def write_csv(frame: pd.DataFrame, path: Path) -> None:
    """UTF-8, comma-separated, LF line ends, empty cells for missing, true/false."""
    out = frame.copy()
    for column in out.columns:
        if pd.api.types.is_bool_dtype(out[column]):
            out[column] = out[column].map({True: "true", False: "false"})
    out.to_csv(path, index=False, lineterminator="\n", encoding="utf-8", na_rep="")


def json_value(value: Any) -> Any:
    if value is None or pd.isna(value):
        return None
    return value.item() if hasattr(value, "item") else value


def quadrat_geojson(quadrats: pd.DataFrame) -> dict:
    """The quadrat table as RFC 7946 points, every column as a property."""
    features = []
    for record in quadrats.to_dict(orient="records"):
        properties = {key: json_value(value) for key, value in record.items()}
        features.append(
            {
                "type": "Feature",
                "properties": properties,
                "geometry": {
                    "type": "Point",
                    "coordinates": [properties["longitude"], properties["latitude"]],
                },
            }
        )
    return {"type": "FeatureCollection", "name": "kelp_quadrats", "features": features}


def write_json(value: dict, path: Path, compact: bool = False) -> None:
    if compact:
        text = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    else:
        text = json.dumps(value, ensure_ascii=False, indent=1)
    path.write_text(text + "\n", encoding="utf-8")


def build(raw_dir: Path, out_dir: Path) -> dict[str, Path]:
    """Write the six tidy files; return their paths by file name."""
    raw = {role: raw_dir / name for role, name in RAW_FILES.items()}
    absent = [str(path) for path in raw.values() if not path.exists()]
    require(not absent, f"Delivered files not found: {absent}")
    out_dir.mkdir(parents=True, exist_ok=True)

    quadrat_records, individual_records = kelp_tables(read_kelp_workbook(raw["kelp_workbook"]))
    quadrats = quadrat_table(
        quadrat_records, read_positions(raw["positions"]), read_july_dive_log(raw["july_dive_log"])
    )
    individuals = individual_table(individual_records, quadrats)
    casts, profiles = sonde_tables(raw["sonde_workbook"])

    paths = {name: out_dir / name for name in TIDY_FILES}
    write_csv(quadrats, paths["kelp_quadrats.csv"])
    write_json(quadrat_geojson(quadrats), paths["kelp_quadrats.geojson"])
    write_csv(individuals, paths["kelp_individuals.csv"])
    write_csv(casts, paths["sonde_casts.csv"])
    write_csv(profiles, paths["sonde_profiles.csv"])
    write_json(dive_tracks(raw["dive_tracks"]), paths["dive_tracks.geojson"], compact=True)
    return paths


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--raw-dir", type=Path, default=Path("."), help="folder holding the raw_ccmar_* files"
    )
    parser.add_argument(
        "--out-dir", type=Path, default=Path("tidy"), help="folder to write the tidy files to"
    )
    args = parser.parse_args()
    for path in build(args.raw_dir, args.out_dir).values():
        print(f"wrote {path} ({path.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
