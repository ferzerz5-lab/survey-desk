"""Coordinate conversion on top of PROJ (pyproj).  No network access is used."""
from __future__ import annotations

import math

from .engine import SurveyError

ALIASES = {
    "wgs84": "EPSG:4326",
    "minna": "EPSG:4263",
    "minna_utm31": "EPSG:26331",
    "minna_utm32": "EPSG:26332",
    "minna_west": "EPSG:26391",
    "minna_mid": "EPSG:26392",
    "minna_east": "EPSG:26393",
    "utm31n": "EPSG:32631",
    "utm32n": "EPSG:32632",
}


def resolve_crs(value) -> str:
    """'minna_west', 'EPSG:26391' or '26391' -> 'EPSG:26391'."""
    text = str(value).strip()
    key = text.lower().replace("-", "_").replace(" ", "_")
    if key in ALIASES:
        return ALIASES[key]
    if text.isdigit():
        return f"EPSG:{text}"
    if text.upper().startswith("EPSG:") and text[5:].isdigit():
        return text.upper()
    raise SurveyError(
        f"unknown CRS {value!r}: use an EPSG code (e.g. EPSG:26391) or one of {', '.join(sorted(ALIASES))}")


def _xy(point, i):
    if isinstance(point, (list, tuple)) and len(point) >= 2:
        return str(i + 1), float(point[0]), float(point[1])
    if isinstance(point, dict):
        x = next((point[k] for k in ("x", "easting", "lon", "lng", "longitude") if k in point), None)
        y = next((point[k] for k in ("y", "northing", "lat", "latitude") if k in point), None)
        if x is not None and y is not None:
            return str(point.get("name") or i + 1), float(x), float(y)
    raise SurveyError(f"point {i + 1} needs x/y (or easting/northing, lon/lat)")


def transform_points(points, from_crs, to_crs):
    from pyproj import CRS, Geod, Transformer
    from pyproj.aoi import AreaOfInterest
    from pyproj.transformer import TransformerGroup

    src, dst = resolve_crs(from_crs), resolve_crs(to_crs)
    if not points:
        raise SurveyError("no points given")
    rows = [_xy(p, i) for i, p in enumerate(points)]

    probe = Transformer.from_crs(src, "EPSG:4326", always_xy=True)
    lonlat = [probe.transform(x, y) for _, x, y in rows]
    if any(not (math.isfinite(a) and math.isfinite(b)) for a, b in lonlat):
        raise SurveyError("coordinates are not valid for the source CRS")
    pad = 0.05
    aoi = AreaOfInterest(min(a for a, _ in lonlat) - pad, min(b for _, b in lonlat) - pad,
                         max(a for a, _ in lonlat) + pad, max(b for _, b in lonlat) + pad)
    group = TransformerGroup(src, dst, always_xy=True, area_of_interest=aoi)
    if not group.transformers:
        raise SurveyError("PROJ has no transformation between these CRSs here")
    tr = group.transformers[0]
    desc = tr.description or ""

    raw = [tr.transform(x, y) for (_, x, y) in rows]
    dp = 8 if _geographic(dst) else 3
    out = [{"name": name, "x": round(x2, dp), "y": round(y2, dp)}
           for (name, _, _), (x2, y2) in zip(rows, raw)]

    worst = 0.0
    geod = Geod(ellps="WGS84")
    for (_, x, y), (x2, y2) in zip(rows, raw):
        bx, by = tr.transform(x2, y2, direction="INVERSE")
        if _geographic(src):
            worst = max(worst, geod.inv(x, y, bx, by)[2])
        else:
            worst = max(worst, math.hypot(bx - x, by - y))

    warnings = []
    if "ballpark" in desc.lower():
        warnings.append("PROJ used a ballpark datum shift (no published transformation): "
                        "expect errors of tens to hundreds of metres")
    for label, code, pts in (("source", src, lonlat),):
        b = CRS.from_user_input(code).area_of_use
        if b and any(not (b.west - 0.01 <= lo <= b.east + 0.01 and b.south - 0.01 <= la <= b.north + 0.01)
                     for lo, la in pts):
            warnings.append(f"some points lie outside the {label} CRS area of use "
                            f"(lon {b.west}..{b.east}, lat {b.south}..{b.north}): pick the right zone/belt")
    dst_area = CRS.from_user_input(dst).area_of_use
    if dst_area:
        dll = [Transformer.from_crs(dst, "EPSG:4326", always_xy=True).transform(o["x"], o["y"]) for o in out]
        if any(not (dst_area.west - 0.01 <= lo <= dst_area.east + 0.01 and
                    dst_area.south - 0.01 <= la <= dst_area.north + 0.01) for lo, la in dll):
            warnings.append(f"result lies outside the target CRS area of use "
                            f"(lon {dst_area.west}..{dst_area.east}, lat {dst_area.south}..{dst_area.north})")

    accuracy = tr.accuracy if tr.accuracy and tr.accuracy > 0 else None
    return {
        "from": src, "to": dst, "points": out,
        "operation": desc.replace(" (with axis order normalized for visualization)", ""),
        "datum_shift_accuracy_m": accuracy,
        "round_trip_max_error_m": round(worst, 6),
        "round_trip_ok": worst < 0.005,
        "warnings": warnings,
        "note": "x is easting/longitude, y is northing/latitude (lon, lat order for geographic CRSs)",
    }


def _geographic(code: str) -> bool:
    from pyproj import CRS
    return CRS.from_user_input(code).is_geographic


def to_wgs84(points_xy, crs):
    """[(x, y), ...] in ``crs`` -> [(lon, lat), ...]."""
    res = transform_points(list(points_xy), crs, "EPSG:4326")
    return [(p["x"], p["y"]) for p in res["points"]], res
