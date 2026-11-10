"""Survey computations with no third-party dependencies.

Conventions: eastings/northings in metres, bearings are whole-circle bearings
(azimuth from grid north, clockwise, 0 <= az < 360).  v1 handles closed-loop
traverses (the last leg returns to the start station).
"""
from __future__ import annotations

import math
import re

_NUM = re.compile(r"\d+(?:\.\d+)?")
_ALLOWED = re.compile(r"^[0-9.\s\u00b0'\"\u2032\u2033:\-DMS]*$")
_ACRES_PER_HA = 2.4710538146717


class SurveyError(ValueError):
    """Raised for input the engine cannot interpret."""


# --------------------------------------------------------------------- angles
def parse_bearing(value) -> float:
    """Whole-circle (``45°30'20"``, ``45-30-20``, ``45.5056``) or quadrant
    (``N45°30'20"E``) bearing -> azimuth in decimal degrees."""
    if isinstance(value, bool):
        raise SurveyError(f"bad bearing: {value!r}")
    if isinstance(value, (int, float)):
        return _wcb(float(value), value)
    text = str(value).strip().upper()
    if not text:
        raise SurveyError("empty bearing")
    quad = re.fullmatch(r"([NS])\s*(.*?)\s*([EW])", text)
    inner = quad.group(2) if quad else text
    if not _ALLOWED.match(inner):
        raise SurveyError(f"cannot read bearing {value!r}")
    nums = _NUM.findall(inner)
    if not 1 <= len(nums) <= 3:
        raise SurveyError(f"cannot read bearing {value!r}")
    deg = float(nums[0])
    mins = float(nums[1]) if len(nums) > 1 else 0.0
    secs = float(nums[2]) if len(nums) > 2 else 0.0
    if mins >= 60 or secs >= 60:
        raise SurveyError(f"minutes/seconds must be below 60 in {value!r}")
    angle = deg + mins / 60.0 + secs / 3600.0
    if not quad:
        return _wcb(angle, value)
    if angle > 90.0:
        raise SurveyError(f"quadrant bearing cannot exceed 90 degrees: {value!r}")
    ns, ew = quad.group(1), quad.group(3)
    if ns == "N":
        return angle if ew == "E" else (360.0 - angle) % 360.0
    return 180.0 - angle if ew == "E" else 180.0 + angle


def _wcb(angle: float, raw) -> float:
    if not (0.0 <= angle <= 360.0) or math.isnan(angle):
        raise SurveyError(f"whole-circle bearing must be 0-360: {raw!r}")
    return angle % 360.0


def format_bearing(az: float, decimals: int = 0) -> str:
    """Decimal degrees -> ``045°30'20"`` (rounded, with carry)."""
    total = round((az % 360.0) * 3600.0, decimals)
    total %= 360 * 3600
    d, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    sec = f"{s:0{3 + decimals if decimals else 2}.{decimals}f}"
    return f"{int(d):03d}\u00b0{int(m):02d}'{sec}\""


# ------------------------------------------------------------------- geometry
def forward(e: float, n: float, az: float, dist: float):
    a = math.radians(az)
    return e + dist * math.sin(a), n + dist * math.cos(a)


def inverse(e1: float, n1: float, e2: float, n2: float):
    """Bearing (0-360) and distance from point 1 to point 2."""
    de, dn = e2 - e1, n2 - n1
    return math.degrees(math.atan2(de, dn)) % 360.0, math.hypot(de, dn)


def shoelace_area(pts) -> float:
    s = 0.0
    for i, (x1, y1) in enumerate(pts):
        x2, y2 = pts[(i + 1) % len(pts)]
        s += x1 * y2 - x2 * y1
    return abs(s) / 2.0


def dmd_area(dep, lat) -> float:
    """Independent area method: double meridian distances."""
    s, prev_dmd = 0.0, 0.0
    for i in range(len(dep)):
        dmd = dep[0] if i == 0 else prev_dmd + dep[i - 1] + dep[i]
        s += dmd * lat[i]
        prev_dmd = dmd
    return abs(s) / 2.0


def _segments_cross(p1, p2, p3, p4) -> bool:
    def orient(a, b, c):
        v = (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
        return 0 if abs(v) < 1e-12 else (1 if v > 0 else -1)

    o1, o2, o3, o4 = orient(p1, p2, p3), orient(p1, p2, p4), orient(p3, p4, p1), orient(p3, p4, p2)
    return o1 != o2 and o3 != o4 and 0 not in (o1, o2, o3, o4)


def self_intersects(pts) -> bool:
    n = len(pts)
    for i in range(n):
        a1, a2 = pts[i], pts[(i + 1) % n]
        for j in range(i + 1, n):
            if j == i or (j + 1) % n == i or (i + 1) % n == j:
                continue
            if _segments_cross(a1, a2, pts[j], pts[(j + 1) % n]):
                return True
    return False


# ------------------------------------------------------------------- traverse
def _station_names(start: str, legs: list) -> list[str]:
    names = [start]
    for i, leg in enumerate(legs):
        names.append(str(leg.get("to") or _auto_name(i + 1)))
    names[-1] = start  # closed loop: last leg returns to the start station
    return names


def _auto_name(i: int) -> str:
    s = ""
    while True:
        i, r = divmod(i, 26)
        s = chr(65 + r) + s
        if i == 0:
            return s
        i -= 1


def compute_traverse(start, legs, *, method="bowditch", tolerance_ratio=5000.0):
    """Closed-loop traverse: compute, adjust, area, cross-checks, blunder hints.

    ``start`` = {"name": "A", "easting": E, "northing": N};
    ``legs`` = [{"to": "B", "bearing": "45-30-20", "distance": 120.45}, ...].
    """
    if len(legs) < 3:
        raise SurveyError("a closed traverse needs at least 3 legs")
    if method not in ("bowditch", "transit"):
        raise SurveyError("method must be 'bowditch' or 'transit'")
    e0, n0 = float(start["easting"]), float(start["northing"])
    names = _station_names(str(start.get("name") or "A"), legs)
    az, dist = [], []
    for i, leg in enumerate(legs):
        d = float(leg["distance"])
        if not d > 0 or math.isinf(d):
            raise SurveyError(f"leg {names[i]}-{names[i + 1]}: distance must be positive")
        az.append(parse_bearing(leg["bearing"]))
        dist.append(d)
    de = [d * math.sin(math.radians(a)) for a, d in zip(az, dist)]
    dn = [d * math.cos(math.radians(a)) for a, d in zip(az, dist)]
    mis_e, mis_n = sum(de), sum(dn)
    perimeter = sum(dist)
    linear = math.hypot(mis_e, mis_n)
    ratio = math.inf if linear < 1e-9 else perimeter / linear

    if method == "bowditch":
        ce = [-mis_e * d / perimeter for d in dist]
        cn = [-mis_n * d / perimeter for d in dist]
    else:
        se, sn = sum(abs(x) for x in de), sum(abs(x) for x in dn)
        ce = [-mis_e * abs(x) / se if se else 0.0 for x in de]
        cn = [-mis_n * abs(x) / sn if sn else 0.0 for x in dn]
    ade = [a + c for a, c in zip(de, ce)]
    adn = [a + c for a, c in zip(dn, cn)]

    obs, adj = [(e0, n0)], [(e0, n0)]
    for i in range(len(legs)):
        obs.append((obs[-1][0] + de[i], obs[-1][1] + dn[i]))
        adj.append((adj[-1][0] + ade[i], adj[-1][1] + adn[i]))
    verts = adj[:-1]
    closing_gap = math.hypot(adj[-1][0] - e0, adj[-1][1] - n0)

    area_coord = shoelace_area(verts)
    area_dmd = dmd_area(ade, adn)
    simple = not self_intersects(verts)

    leg_rows = []
    for i in range(len(legs)):
        a2, d2 = inverse(*adj[i], *adj[i + 1])
        leg_rows.append({
            "from": names[i], "to": names[i + 1],
            "observed_bearing": format_bearing(az[i]), "observed_distance": round(dist[i], 3),
            "adjusted_bearing": format_bearing(a2), "adjusted_distance": round(d2, 3),
            "correction_e": round(ce[i], 4), "correction_n": round(cn[i], 4),
        })
    stations = [{"name": names[i], "easting": round(adj[i][0], 3), "northing": round(adj[i][1], 3)}
                for i in range(len(legs))]

    checks = [
        {"name": "closes_after_adjustment", "passed": closing_gap < 1e-6,
         "detail": f"adjusted traverse returns to start within {closing_gap:.2e} m"},
        {"name": "area_methods_agree", "passed": abs(area_coord - area_dmd) <= 1e-6 * max(area_coord, 1.0),
         "detail": f"coordinate method {area_coord:.4f} m2 vs DMD method {area_dmd:.4f} m2"},
        {"name": "simple_polygon", "passed": simple,
         "detail": "boundary does not cross itself" if simple else
                   "boundary crosses itself: check station order and bearings; area is not a valid parcel"},
    ]
    meets = ratio >= tolerance_ratio
    checks.append({"name": "meets_accuracy_tolerance", "passed": meets,
                   "detail": f"relative accuracy {_ratio_text(ratio)} vs required 1:{tolerance_ratio:,.0f}"})
    hard_ok = all(c["passed"] for c in checks[:3])
    verdict = ("RE-OBSERVE: outside tolerance" if hard_ok and not meets else
               "ACCEPTABLE" if hard_ok else "CHECK FAILED")
    mis_az = math.degrees(math.atan2(mis_e, mis_n)) % 360.0 if linear > 1e-9 else 0.0

    return {
        "method": method,
        "verdict": verdict,
        "stations": stations,
        "legs": leg_rows,
        "misclosure": {
            "delta_e": round(mis_e, 4), "delta_n": round(mis_n, 4), "linear": round(linear, 4),
            "bearing": format_bearing(mis_az) if linear > 1e-9 else "n/a",
            "perimeter": round(perimeter, 3), "relative_accuracy": _ratio_text(ratio),
        },
        "area": {"square_metres": round(area_coord, 3), "hectares": round(area_coord / 1e4, 5),
                 "acres": round(area_coord / 1e4 * _ACRES_PER_HA, 4)},
        "checks": checks,
        "suspects": [] if meets else find_suspects(az, dist, names, mis_e, mis_n),
        "_adjusted_vertices": verts,  # internal: used by exporters, stripped from tool output
    }


def _ratio_text(ratio: float) -> str:
    return "perfect closure" if math.isinf(ratio) else f"1:{ratio:,.0f}"


def find_suspects(az, dist, names, mis_e, mis_n, max_residual=0.10, top=3):
    """Which single leg's blunder best explains the misclosure vector?

    Each leg is tested two ways.  A wrong distance leaves a misclosure parallel
    to the leg; a wrong bearing rotates the leg and leaves a chord-shaped
    misclosure.  Fit = share of the misclosure explained (100% = exact).
    """
    m = math.hypot(mis_e, mis_n)
    if m < 1e-6:
        return []
    found = []
    for i, (a, d) in enumerate(zip(az, dist)):
        ux, uy = math.sin(math.radians(a)), math.cos(math.radians(a))
        leg = f"{names[i]}-{names[i + 1]}"
        shift = mis_e * ux + mis_n * uy
        res = math.hypot(mis_e - shift * ux, mis_n - shift * uy) / m
        if res <= max_residual and d - shift > 0:
            found.append((res, {
                "leg": leg, "kind": "distance", "fit_percent": round((1 - res) * 100, 1),
                "recorded": round(d, 3), "likely": round(d - shift, 3),
                "note": f"distance looks {abs(shift):.3f} m {'long' if shift > 0 else 'short'}"}))
        wx, wy = ux - mis_e / d, uy - mis_n / d
        res_b = abs(math.hypot(wx, wy) - 1.0) * d / m
        if res_b <= max_residual:
            likely = math.degrees(math.atan2(wx, wy)) % 360.0
            diff = ((a - likely + 180.0) % 360.0) - 180.0
            if abs(diff) > 1e-6:
                found.append((res_b, {
                    "leg": leg, "kind": "bearing", "fit_percent": round((1 - res_b) * 100, 1),
                    "recorded": format_bearing(a), "likely": format_bearing(likely),
                    "note": f"bearing looks {abs(diff):.4f} deg {'high' if diff > 0 else 'low'}"}))
    found.sort(key=lambda t: t[0])
    return [item for _, item in found[:top]]
