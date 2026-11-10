"""Survey plan drawing and file exports (PNG, PDF, DXF, KML, GeoJSON)."""
from __future__ import annotations

import datetime as _dt
import json
import math
import re
import tempfile
from pathlib import Path
from xml.sax.saxutils import escape

PLUGIN_NAME = "survey-desk"
DISCLAIMER = "Computed by survey-desk. Not a licensed survey plan: check against your field book before use."


def output_dir(title: str) -> Path:
    """Per-plan folder under the plugin's data directory (temp dir outside Hermes)."""
    try:
        from plugins.plugin_storage import plugin_data_dir
        base = plugin_data_dir(PLUGIN_NAME) / "plans"
    except Exception:  # not running inside Hermes (tests, scripts)
        base = Path(tempfile.gettempdir()) / PLUGIN_NAME / "plans"
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:40] or "plan"
    stamp = _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    folder = base / f"{slug}-{stamp}"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def _nice_length(extent: float) -> float:
    target = extent * 0.25
    mag = 10 ** math.floor(math.log10(target))
    for m in (1, 2, 5, 10):
        if m * mag >= target * 0.7:
            return m * mag
    return 10 * mag


def draw_png_pdf(result, folder: Path, title: str, crs_label: str, stem: str):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Polygon, Rectangle

    verts = result["_adjusted_vertices"]
    names = [s["name"] for s in result["stations"]]
    xs, ys = [v[0] for v in verts], [v[1] for v in verts]
    cx, cy = sum(xs) / len(xs), sum(ys) / len(ys)
    span = max(max(xs) - min(xs), max(ys) - min(ys), 1.0)

    fig, ax = plt.subplots(figsize=(11.69, 8.27))
    ax.set_aspect("equal")
    ax.add_patch(Polygon(verts, closed=True, facecolor="#e8f1fb", edgecolor="#17365d", linewidth=2.0))
    pad = span * 0.2
    ax.set_xlim(min(xs) - pad, max(xs) + pad)
    ax.set_ylim(min(ys) - pad, max(ys) + pad)
    ax.axis("off")

    off = span * 0.04
    for i, (x, y) in enumerate(verts):
        ax.plot(x, y, "o", color="#17365d", markersize=6)
        dx, dy = x - cx, y - cy
        norm = math.hypot(dx, dy) or 1.0
        ax.text(x + dx / norm * off * 1.6, y + dy / norm * off * 1.6, names[i], ha="center", va="center",
                fontsize=12, fontweight="bold", color="#17365d")
    for i, leg in enumerate(result["legs"]):
        (x1, y1), (x2, y2) = verts[i], verts[(i + 1) % len(verts)]
        mx, my = (x1 + x2) / 2, (y1 + y2) / 2
        ang = math.degrees(math.atan2(y2 - y1, x2 - x1))
        if ang > 90:
            ang -= 180
        elif ang <= -90:
            ang += 180
        nx, ny = -(y2 - y1), (x2 - x1)
        nl = math.hypot(nx, ny) or 1.0
        if (mx - cx) * nx + (my - cy) * ny < 0:
            nx, ny = -nx, -ny
        ax.text(mx + nx / nl * off, my + ny / nl * off, f"{leg['adjusted_bearing']}  {leg['adjusted_distance']:.2f} m",
                rotation=ang, rotation_mode="anchor", ha="center", va="center", fontsize=8.5, color="#333333")

    ax.annotate("", xy=(0.93, 0.93), xytext=(0.93, 0.80), xycoords="axes fraction",
                arrowprops=dict(arrowstyle="-|>", color="#17365d", lw=2))
    ax.text(0.93, 0.95, "N", transform=ax.transAxes, ha="center", va="bottom", fontsize=14, fontweight="bold")

    bar = _nice_length(span)
    x_lo, y_lo = ax.get_xlim()[0], ax.get_ylim()[0]
    bx, by, bh = x_lo + span * 0.04, y_lo + span * 0.06, span * 0.014
    for k in range(4):
        ax.add_patch(Rectangle((bx + bar * k / 4, by), bar / 4, bh, facecolor="#17365d" if k % 2 == 0 else "white",
                               edgecolor="#17365d", linewidth=0.8))
    ax.text(bx, by - bh * 1.2, "0", ha="center", va="top", fontsize=8)
    ax.text(bx + bar, by - bh * 1.2, f"{bar:g} m", ha="center", va="top", fontsize=8)

    mis, area, chk = result["misclosure"], result["area"], result["checks"]
    verified = all(c["passed"] for c in chk[:3])
    lines = [
        title.upper(),
        f"Area: {area['square_metres']:,.2f} m\u00b2  =  {area['hectares']:.4f} ha  =  {area['acres']:.4f} acres",
        f"Misclosure: {mis['linear']:.3f} m   Relative accuracy: {mis['relative_accuracy']}   "
        f"Adjustment: {result['method'].title()}",
        f"Checks: {'all internal checks passed' if verified else 'CHECK FAILED'}   Verdict: {result['verdict']}",
        f"Coordinates: {crs_label or 'local grid (no CRS given)'}",
    ]
    fig.subplots_adjust(left=0.02, right=0.98, top=0.98, bottom=0.26)
    fig.text(0.5, 0.115, "\n".join(lines), ha="center", va="center", fontsize=10,
             bbox=dict(boxstyle="round,pad=0.6", fc="white", ec="#17365d"))
    fig.text(0.5, 0.01, DISCLAIMER, ha="center", va="bottom", fontsize=7, color="#666666")
    paths = []
    for ext in ("png", "pdf"):
        p = folder / f"{stem}.{ext}"
        fig.savefig(p, dpi=200)
        paths.append(p)
    plt.close(fig)
    return paths


def write_dxf(result, folder: Path, title: str, stem: str) -> Path:
    import ezdxf
    verts = result["_adjusted_vertices"]
    names = [s["name"] for s in result["stations"]]
    span = max(max(v[0] for v in verts) - min(v[0] for v in verts),
               max(v[1] for v in verts) - min(v[1] for v in verts), 1.0)
    h = span * 0.012
    doc = ezdxf.new("R2010")
    doc.layers.add("PARCEL", color=5)
    doc.layers.add("BEACONS", color=1)
    doc.layers.add("LABELS", color=7)
    msp = doc.modelspace()
    msp.add_lwpolyline(verts, close=True, dxfattribs={"layer": "PARCEL"})
    for i, (x, y) in enumerate(verts):
        msp.add_point((x, y), dxfattribs={"layer": "BEACONS"})
        msp.add_text(names[i], height=h * 1.4, dxfattribs={"layer": "LABELS"}).set_placement((x + h, y + h))
    for i, leg in enumerate(result["legs"]):
        (x1, y1), (x2, y2) = verts[i], verts[(i + 1) % len(verts)]
        ang = math.degrees(math.atan2(y2 - y1, x2 - x1))
        if ang > 90:
            ang -= 180
        elif ang <= -90:
            ang += 180
        t = msp.add_text(f"{leg['adjusted_bearing']} {leg['adjusted_distance']:.2f}m", height=h,
                         dxfattribs={"layer": "LABELS", "rotation": ang})
        t.set_placement(((x1 + x2) / 2, (y1 + y2) / 2))
    msp.add_text(f"{title}  AREA {result['area']['square_metres']:.2f} m2", height=h * 1.5,
                 dxfattribs={"layer": "LABELS"}).set_placement((min(v[0] for v in verts), min(v[1] for v in verts) - h * 6))
    path = folder / f"{stem}.dxf"
    doc.saveas(path)
    return path


def write_geojson_kml(result, lonlat, folder: Path, title: str, stem: str, crs_label: str):
    names = [s["name"] for s in result["stations"]]
    ring = [list(p) for p in lonlat] + [list(lonlat[0])]
    props = {"title": title, "area_m2": result["area"]["square_metres"],
             "hectares": result["area"]["hectares"], "relative_accuracy": result["misclosure"]["relative_accuracy"],
             "source_crs": crs_label}
    features = [{"type": "Feature", "properties": props, "geometry": {"type": "Polygon", "coordinates": [ring]}}]
    for n, p in zip(names, lonlat):
        features.append({"type": "Feature", "properties": {"name": n},
                         "geometry": {"type": "Point", "coordinates": list(p)}})
    gj = folder / f"{stem}.geojson"
    gj.write_text(json.dumps({"type": "FeatureCollection", "features": features}, indent=1), encoding="utf-8")

    coords = " ".join(f"{lo:.8f},{la:.8f},0" for lo, la in ring)
    marks = "".join(
        f"<Placemark><name>{escape(n)}</name><Point><coordinates>{lo:.8f},{la:.8f},0</coordinates></Point></Placemark>"
        for n, (lo, la) in zip(names, lonlat))
    desc = escape(f"Area {result['area']['square_metres']:,.2f} m2 ({result['area']['hectares']:.4f} ha); "
                  f"relative accuracy {result['misclosure']['relative_accuracy']}")
    kml_text = (
        '<?xml version="1.0" encoding="UTF-8"?>\n<kml xmlns="http://www.opengis.net/kml/2.2"><Document>'
        f"<name>{escape(title)}</name>"
        '<Style id="p"><LineStyle><color>ff5d3617</color><width>3</width></LineStyle>'
        "<PolyStyle><color>55fbf1e8</color></PolyStyle></Style>"
        f"<Placemark><name>{escape(title)}</name><description>{desc}</description><styleUrl>#p</styleUrl>"
        f"<Polygon><outerBoundaryIs><LinearRing><coordinates>{coords}</coordinates></LinearRing></outerBoundaryIs></Polygon></Placemark>"
        f"{marks}</Document></kml>")
    kml = folder / f"{stem}.kml"
    kml.write_text(kml_text, encoding="utf-8")
    return [gj, kml]
