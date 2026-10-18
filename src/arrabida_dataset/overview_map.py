"""Overview map of the dataset: dive tracks, quadrats and sonde stations.

Drawn from the tidy files of the Zenodo record only, so it carries no third-party imagery.
No coastline is drawn; the shore lies north of the quadrats.

Campaign is the colour, in a fixed order (June, July, September). The three hues are the
first three slots of the dataviz reference palette, which pass its colour-vision checks
for every pair. Stratum is the marker shape, and tracks and stations carry text labels,
so no reading rests on colour alone.
"""

from __future__ import annotations

import csv
import json
import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import Rectangle
from matplotlib.ticker import MultipleLocator

SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK_SECONDARY = "#52514e"
INK_MUTED = "#898781"
GRID = "#e1e0d9"
AXIS = "#c3c2b7"
CAMPAIGN_COLOURS = {"june": "#2a78d6", "july": "#eb6834", "september": "#1baf7a"}
CAMPAIGN_LABELS = {"june": "June", "july": "July", "september": "September"}
CAMPAIGN_SHORT = {"june": "Jun", "july": "Jul", "september": "Sep"}
STRATUM_MARKERS = {"shallow": "o", "deep": "s"}
STRATUM_LABELS = {"shallow": "Shallow quadrat (6 to 8 m)", "deep": "Deep quadrat (15 to 17 m)"}

FONT = ["Helvetica Neue", "Helvetica", "Arial", "DejaVu Sans"]
METRES_PER_DEGREE = 111_320.0
FIGURE_WIDTH_IN = 11.0
MARGINS_IN = {"left": 0.95, "gap": 1.0, "right": 0.5, "top": 0.45, "bottom": 0.85}

# Where each sonde station's label sits relative to its marker (points, alignment),
# chosen so that the labels clear the quadrats and one another.
STATION_LABELS = {
    "8 m · Jun, Jul": (8, -10, "left", "center"),
    "17 m · Jun, Jul": (-8, 0, "right", "center"),
    "12 m · Jun": (9, -5, "left", "center"),
    "6 m · Sep": (9, -6, "left", "center"),
    "17 m · Sep": (0, -9, "center", "top"),
}
# Where each track's name sits: which end of the track, and the offset from it in points.
TRACK_LABELS = {
    "june": ("north", (0, 5), "center", "bottom"),
    "july": ("east", (7, 0), "left", "center"),
    "september": ("south", (0, -6), "center", "top"),
}


def _rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _degrees(metres: float, latitude: float, east_west: bool) -> float:
    scale = METRES_PER_DEGREE * (math.cos(math.radians(latitude)) if east_west else 1.0)
    return metres / scale


def _padded(values: list[float], pad: float) -> tuple[float, float]:
    return min(values) - pad, max(values) + pad


def _style(ax, latitude: float, x_step: float, y_step: float, decimals: int) -> None:
    ax.set_facecolor(SURFACE)
    ax.set_aspect(1.0 / math.cos(math.radians(latitude)), adjustable="box")
    ax.grid(True, color=GRID, linewidth=0.6, linestyle="-")
    ax.set_axisbelow(True)
    for spine in ax.spines.values():
        spine.set_color(AXIS)
        spine.set_linewidth(0.8)
    ax.tick_params(colors=INK_MUTED, labelsize=7.5, length=3, width=0.6)
    ax.xaxis.set_major_locator(MultipleLocator(x_step))
    ax.yaxis.set_major_locator(MultipleLocator(y_step))
    ax.xaxis.set_major_formatter(lambda value, _: f"{abs(value):.{decimals}f}° W")
    ax.yaxis.set_major_formatter(lambda value, _: f"{value:.{decimals}f}° N")


def _scale_bar(ax, length_m: float, latitude: float) -> None:
    x0, x1 = ax.get_xlim()
    y0, y1 = ax.get_ylim()
    width = _degrees(length_m, latitude, east_west=True)
    left, base = x0 + 0.04 * (x1 - x0), y0 + 0.06 * (y1 - y0)
    ax.plot([left, left + width], [base, base], color=INK, linewidth=1.5, solid_capstyle="butt")
    ax.annotate(
        f"{length_m:.0f} m",
        xy=(left + width / 2, base),
        xytext=(0, 4),
        textcoords="offset points",
        ha="center",
        va="bottom",
        fontsize=8,
        color=INK_SECONDARY,
    )


def _stations(casts: list[dict[str, str]]) -> list[dict]:
    """Distinct cast positions, each with its depth label and the campaigns that used it."""
    stations: dict[tuple[str, str], dict] = {}
    for cast in casts:
        station = stations.setdefault(
            (cast["longitude"], cast["latitude"]),
            {
                "longitude": float(cast["longitude"]),
                "latitude": float(cast["latitude"]),
                "depth": cast["station_depth_label_m"],
                "campaigns": [],
            },
        )
        station["campaigns"].append(CAMPAIGN_SHORT[cast["campaign"]])
    for station in stations.values():
        station["label"] = f"{station['depth']} m · {', '.join(station['campaigns'])}"
    return list(stations.values())


def _track_end(points: list[list[float]], end: str) -> list[float]:
    """The track's most northerly, easterly or southerly fix."""
    if end == "north":
        return max(points, key=lambda point: point[1])
    if end == "east":
        return max(points, key=lambda point: point[0])
    return min(points, key=lambda point: point[1])


def draw(tidy_dir: Path, path: Path) -> None:
    quadrats = _rows(tidy_dir / "kelp_quadrats.csv")
    stations = _stations(_rows(tidy_dir / "sonde_casts.csv"))
    tracks = json.loads((tidy_dir / "dive_tracks.geojson").read_text(encoding="utf-8"))

    longitudes = [float(q["longitude"]) for q in quadrats] + [s["longitude"] for s in stations]
    latitudes = [float(q["latitude"]) for q in quadrats] + [s["latitude"] for s in stations]
    latitude = sum(latitudes) / len(latitudes)
    near_x = _padded(longitudes, _degrees(30.0, latitude, east_west=True))
    near_y = _padded(latitudes, _degrees(24.0, latitude, east_west=False))
    vertices = [
        point
        for feature in tracks["features"]
        for part in feature["geometry"]["coordinates"]
        for point in part
    ]
    wide_x = _padded([point[0] for point in vertices], _degrees(75.0, latitude, east_west=True))
    wide_y = _padded([point[1] for point in vertices], _degrees(45.0, latitude, east_west=False))

    # Both panels get the same height: each one's width follows from its ground extent.
    def shape(x: tuple[float, float], y: tuple[float, float]) -> float:
        return (x[1] - x[0]) * math.cos(math.radians(latitude)) / (y[1] - y[0])

    m = MARGINS_IN
    panels_width = FIGURE_WIDTH_IN - m["left"] - m["gap"] - m["right"]
    height = panels_width / (shape(wide_x, wide_y) + shape(near_x, near_y))
    figure_height = height + m["top"] + m["bottom"]
    wide_width = height * shape(wide_x, wide_y)

    plt.rcParams.update({"font.family": FONT, "text.color": INK})
    fig = plt.figure(figsize=(FIGURE_WIDTH_IN, figure_height), dpi=200)
    fig.patch.set_facecolor(SURFACE)
    bottom, tall = m["bottom"] / figure_height, height / figure_height
    wide = fig.add_axes([m["left"] / FIGURE_WIDTH_IN, bottom, wide_width / FIGURE_WIDTH_IN, tall])
    near = fig.add_axes(
        [
            (m["left"] + wide_width + m["gap"]) / FIGURE_WIDTH_IN,
            bottom,
            (panels_width - wide_width) / FIGURE_WIDTH_IN,
            tall,
        ]
    )

    # Left: the dive tracks, with the area of the right panel outlined.
    for feature in tracks["features"]:
        campaign = feature["properties"]["campaign"]
        parts = feature["geometry"]["coordinates"]
        for part in parts:
            wide.plot(
                [point[0] for point in part],
                [point[1] for point in part],
                color=CAMPAIGN_COLOURS[campaign],
                linewidth=1.5,
                solid_capstyle="round",
                solid_joinstyle="round",
            )
        end, offset, align, valign = TRACK_LABELS[campaign]
        wide.annotate(
            CAMPAIGN_LABELS[campaign],
            xy=_track_end([point for part in parts for point in part], end),
            xytext=offset,
            textcoords="offset points",
            ha=align,
            va=valign,
            fontsize=8,
            color=INK_SECONDARY,
        )
    wide.set_xlim(*wide_x)
    wide.set_ylim(*wide_y)
    _style(wide, latitude, x_step=0.002, y_step=0.001, decimals=3)
    wide.add_patch(
        Rectangle(
            (near_x[0], near_y[0]),
            near_x[1] - near_x[0],
            near_y[1] - near_y[0],
            fill=False,
            edgecolor=INK_SECONDARY,
            linewidth=0.9,
            zorder=5,
        )
    )
    wide.annotate(
        "area of the right panel",
        xy=((near_x[0] + near_x[1]) / 2, near_y[1]),
        xytext=(0, 4),
        textcoords="offset points",
        ha="center",
        va="bottom",
        fontsize=8,
        color=INK_SECONDARY,
    )
    wide.set_title("Dive tracks (surface-float GPS)", fontsize=10, color=INK, loc="left", pad=8)
    _scale_bar(wide, 200.0, latitude)

    # Right: quadrats by campaign (colour) and stratum (shape), and the sonde stations.
    for campaign, colour in CAMPAIGN_COLOURS.items():
        for stratum, marker in STRATUM_MARKERS.items():
            chosen = [q for q in quadrats if (q["campaign"], q["stratum"]) == (campaign, stratum)]
            near.scatter(
                [float(q["longitude"]) for q in chosen],
                [float(q["latitude"]) for q in chosen],
                s=38,
                marker=marker,
                color=colour,
                edgecolors=SURFACE,
                linewidths=1.0,
                zorder=3,
            )
    for station in stations:
        near.scatter(
            [station["longitude"]],
            [station["latitude"]],
            s=62,
            marker="D",
            color=INK,
            edgecolors=SURFACE,
            linewidths=1.0,
            zorder=4,
        )
        dx, dy, align, valign = STATION_LABELS.get(station["label"], (8, 0, "left", "center"))
        near.annotate(
            station["label"],
            xy=(station["longitude"], station["latitude"]),
            xytext=(dx, dy),
            textcoords="offset points",
            ha=align,
            va=valign,
            fontsize=7.5,
            color=INK_SECONDARY,
            zorder=6,
        )
    near.set_xlim(*near_x)
    near.set_ylim(*near_y)
    _style(near, latitude, x_step=0.0005, y_step=0.0005, decimals=4)
    near.set_title("Quadrats and sonde stations", fontsize=10, color=INK, loc="left", pad=8)
    _scale_bar(near, 50.0, latitude)

    marker_style = {"markersize": 6.5, "markeredgecolor": SURFACE, "markeredgewidth": 1.0}
    handles = [
        Line2D(
            [],
            [],
            color=colour,
            linewidth=1.5,
            marker="o",
            label=CAMPAIGN_LABELS[campaign],
            **marker_style,
        )
        for campaign, colour in CAMPAIGN_COLOURS.items()
    ]
    handles += [
        Line2D(
            [],
            [],
            linestyle="none",
            marker=marker,
            color=INK_MUTED,
            label=STRATUM_LABELS[stratum],
            **marker_style,
        )
        for stratum, marker in STRATUM_MARKERS.items()
    ]
    handles.append(
        Line2D(
            [],
            [],
            linestyle="none",
            marker="D",
            color=INK,
            label="Sonde station (depth label · campaigns)",
            **marker_style,
        )
    )
    legend = fig.legend(
        handles=handles,
        loc="lower center",
        ncol=len(handles),
        frameon=False,
        fontsize=8.5,
        handletextpad=0.5,
        columnspacing=1.6,
        bbox_to_anchor=(0.5, 0.03),
    )
    for text in legend.get_texts():
        text.set_color(INK_SECONDARY)
    fig.savefig(path, facecolor=SURFACE, metadata={"Software": None})
    plt.close(fig)


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--tidy-dir", type=Path, default=Path("."), help="folder with kelp_quadrats.csv, sonde_casts.csv and dive_tracks.geojson")
    parser.add_argument("--out", type=Path, default=Path("overview_map.png"))
    args = parser.parse_args()
    draw(args.tidy_dir, args.out)
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
