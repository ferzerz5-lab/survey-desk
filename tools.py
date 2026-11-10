"""Tool handlers and the /survey field-book command.  Handlers return JSON strings."""
from __future__ import annotations

import json
import re

from . import engine, geo, plan

_DEFAULT_FORMATS = ["png", "pdf", "dxf"]


def _public(result: dict) -> dict:
    out = {k: v for k, v in result.items() if not k.startswith("_")}
    sus = out.get("suspects") or []
    if sus:
        out["suspects_note"] = ("Candidates are ranked by how well a single-leg error explains the misclosure. They are "
                                "hints, not proof: re-measure the top leg before changing the record.")
    if len(sus) >= 2 and sus[0]["fit_percent"] - sus[1]["fit_percent"] < 1.0:
        out["suspects_note"] = ("Several legs explain the misclosure equally well (parallel or symmetric legs): "
                                "re-observe all the listed legs.")
    return out


def _fail(exc: Exception) -> str:
    return json.dumps({"error": str(exc)})


def _compute(args: dict) -> dict:
    return engine.compute_traverse(
        args["start"], args["legs"], method=args.get("method") or "bowditch",
        tolerance_ratio=float(args.get("tolerance_ratio") or 5000))


def survey_traverse(args: dict, **kwargs) -> str:
    try:
        return json.dumps(_public(_compute(args)), indent=1)
    except (engine.SurveyError, KeyError, TypeError, ValueError) as exc:
        return _fail(exc)


def _export(result: dict, args: dict):
    title = str(args.get("title") or "Survey plan")
    crs = args.get("crs")
    crs_code = geo.resolve_crs(crs) if crs else ""
    formats = list(args.get("formats") or (_DEFAULT_FORMATS + (["kml", "geojson"] if crs else [])))
    folder = plan.output_dir(title)
    stem = folder.name
    files, notes = [], []
    if "png" in formats or "pdf" in formats:
        drawn = plan.draw_png_pdf(result, folder, title, crs_code, stem)
        files += [p for p in drawn if p.suffix[1:] in formats]
    if "dxf" in formats:
        files.append(plan.write_dxf(result, folder, title, stem))
    if {"kml", "geojson"} & set(formats):
        if not crs_code:
            notes.append("kml/geojson skipped: give 'crs' so the parcel can be placed on the globe")
        else:
            lonlat, conv = geo.to_wgs84(result["_adjusted_vertices"], crs_code)
            written = plan.write_geojson_kml(result, lonlat, folder, title, stem, crs_code)
            files += [p for p in written if p.suffix[1:] in formats or
                      (p.suffix == ".geojson" and "geojson" in formats)]
            notes += conv["warnings"]
            if conv["datum_shift_accuracy_m"]:
                notes.append(f"placement on the globe is only as good as the datum shift: about "
                             f"+/-{conv['datum_shift_accuracy_m']:g} m ({conv['operation']})")
    order = {".png": 0, ".pdf": 1, ".dxf": 2, ".kml": 3, ".geojson": 4}
    files.sort(key=lambda p: order.get(p.suffix, 9))
    return files, notes


def survey_plan(args: dict, **kwargs) -> str:
    try:
        result = _compute(args)
        files, notes = _export(result, args)
        out = _public(result)
        out["files"] = [str(p) for p in files]
        out["attachments"] = [f"MEDIA:{p}" for p in files]
        if notes:
            out["notes"] = notes
        return json.dumps(out, indent=1)
    except (engine.SurveyError, KeyError, TypeError, ValueError) as exc:
        return _fail(exc)


def survey_convert(args: dict, **kwargs) -> str:
    try:
        return json.dumps(geo.transform_points(args["points"], args["from_crs"], args["to_crs"]), indent=1)
    except (engine.SurveyError, KeyError, TypeError, ValueError) as exc:
        return _fail(exc)
    except Exception as exc:  # pyproj raises its own error types
        return _fail(exc)


def survey_inverse(args: dict, **kwargs) -> str:
    try:
        az, dist = engine.inverse(float(args["from_easting"]), float(args["from_northing"]),
                                  float(args["to_easting"]), float(args["to_northing"]))
        return json.dumps({"bearing": engine.format_bearing(az), "bearing_decimal": round(az, 6),
                           "distance": round(dist, 3)})
    except (KeyError, TypeError, ValueError) as exc:
        return _fail(exc)


# ------------------------------------------------------------ /survey command
_LEG = re.compile(r"^([A-Za-z0-9_]+)\s*-\s*([A-Za-z0-9_]+)\s+(.+?)\s+(\d+(?:\.\d+)?)\s*m?$", re.I)
HELP = """Usage: /survey followed by a field book, one item per line:

title: Plot 14, Block C
crs: minna_west
start: A 164500.00 380200.00
A-B 45-30-20 120.45
B-C 135-10-00 98.30
C-D 225-40-10 121.00
D-A 315-20-30 97.80

Optional: method: transit, tolerance: 10000. Bearings are whole-circle (or N45-30-20E)."""


def parse_field_book(text: str) -> dict:
    args: dict = {"legs": []}
    for raw in text.replace(";", "\n").splitlines():
        line = raw.strip()
        if not line:
            continue
        low = line.lower()
        if low.startswith("title:"):
            args["title"] = line[6:].strip()
        elif low.startswith("crs:"):
            args["crs"] = line[4:].strip()
        elif low.startswith("method:"):
            args["method"] = line[7:].strip().lower()
        elif low.startswith("tolerance:"):
            args["tolerance_ratio"] = float(line[10:].strip().replace(",", "").replace("1:", ""))
        elif low.startswith("start:"):
            parts = line[6:].split()
            if len(parts) != 3:
                raise engine.SurveyError("start needs: name easting northing")
            args["start"] = {"name": parts[0], "easting": float(parts[1]), "northing": float(parts[2])}
        else:
            m = _LEG.match(line)
            if not m:
                raise engine.SurveyError(f"cannot read line: {line!r} (expected like: A-B 45-30-20 120.45)")
            args["legs"].append({"to": m.group(2), "bearing": m.group(3), "distance": float(m.group(4))})
    if "start" not in args:
        raise engine.SurveyError("missing 'start: NAME EASTING NORTHING'")
    return args


def survey_command(raw_args: str) -> str:
    if not raw_args or not raw_args.strip() or raw_args.strip().lower() in ("help", "?"):
        return HELP
    try:
        args = parse_field_book(raw_args)
        result = _compute(args)
        files, notes = _export(result, args)
    except (engine.SurveyError, KeyError, ValueError) as exc:
        return f"Could not compute: {exc}\n\n{HELP}"
    pub = _public(result)
    mis, area = pub["misclosure"], pub["area"]
    lines = [f"{args.get('title', 'Survey plan')}: {pub['verdict']}",
             f"Area {area['square_metres']:,.2f} m2 ({area['hectares']:.4f} ha, {area['acres']:.3f} acres)",
             f"Misclosure {mis['linear']:.3f} m, relative accuracy {mis['relative_accuracy']} ({pub['method']})"]
    lines += [f"{'OK  ' if c['passed'] else 'FAIL'} {c['name']}: {c['detail']}" for c in pub["checks"]]
    for s in pub["suspects"]:
        lines.append(f"Suspect leg {s['leg']} ({s['kind']}): {s['recorded']} -> {s['likely']} ({s['note']}, fit {s['fit_percent']}%)")
    if pub.get("suspects_note"):
        lines.append(pub["suspects_note"])
    lines += notes
    lines += [f"MEDIA:{p}" for p in files]
    return "\n".join(lines)
