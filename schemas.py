"""Tool schemas (OpenAI function-calling format)."""

_START = {
    "type": "object",
    "description": "Known start station of the closed traverse (metres).",
    "properties": {
        "name": {"type": "string", "description": "Station name, e.g. A or BN1."},
        "easting": {"type": "number"},
        "northing": {"type": "number"},
    },
    "required": ["easting", "northing"],
}
_LEGS = {
    "type": "array",
    "description": "Legs in order around the boundary. The last leg returns to the start station.",
    "items": {
        "type": "object",
        "properties": {
            "to": {"type": "string", "description": "Name of the station this leg ends at."},
            "bearing": {"type": ["string", "number"],
                        "description": "Whole-circle bearing (45-30-20, 045°30'20\", 45.5056) or quadrant bearing (N45-30-20E)."},
            "distance": {"type": "number", "description": "Horizontal distance in metres."},
        },
        "required": ["bearing", "distance"],
    },
}
_METHOD = {"type": "string", "enum": ["bowditch", "transit"], "description": "Misclosure adjustment rule. Default bowditch."}
_TOL = {"type": "number", "description": "Required relative accuracy as N in 1:N. Default 5000; use your authority's limit."}

TRAVERSE = {
    "name": "survey_traverse",
    "description": (
        "Exact closed-traverse computation from field-book bearings and distances: misclosure, relative accuracy, "
        "Bowditch/transit adjustment, adjusted coordinates, area (cross-checked by two independent methods), and "
        "a hint at which leg holds a blunder when the traverse fails tolerance. Use this instead of doing survey "
        "arithmetic yourself. Returns numbers only; call survey_plan for the drawing and files."),
    "parameters": {"type": "object",
                   "properties": {"start": _START, "legs": _LEGS, "method": _METHOD, "tolerance_ratio": _TOL},
                   "required": ["start", "legs"]},
}
PLAN = {
    "name": "survey_plan",
    "description": (
        "Do survey_traverse and also draw a survey plan (bearings and distances on every line, beacons, north arrow, "
        "scale bar, area, misclosure) and export files: png, pdf, dxf always available; kml and geojson when 'crs' "
        "is given (they are georeferenced, open the kml in Google Earth). Reply to the user with the summary and "
        "include every line of 'attachments' verbatim so the files are delivered in chat."),
    "parameters": {"type": "object", "properties": {
        "start": _START, "legs": _LEGS, "method": _METHOD, "tolerance_ratio": _TOL,
        "title": {"type": "string", "description": "Plan title, e.g. 'Plot 14, Block C'."},
        "crs": {"type": "string",
                "description": "CRS of the coordinates: EPSG code (EPSG:26391) or minna_west, minna_mid, minna_east, "
                               "minna_utm31, minna_utm32, utm31n, utm32n, wgs84. Needed for kml/geojson."},
        "formats": {"type": "array", "items": {"type": "string", "enum": ["png", "pdf", "dxf", "kml", "geojson"]},
                    "description": "Default: png, pdf, dxf (+ kml, geojson when crs is given)."}},
        "required": ["start", "legs"]},
}
CONVERT = {
    "name": "survey_convert",
    "description": (
        "Convert coordinates between coordinate systems with PROJ: WGS84 lat/lon, Minna datum, Nigeria West/Mid/East "
        "belts, UTM zones, or any EPSG code. Reports the transformation used, its published datum-shift accuracy, a "
        "round-trip check, and warns when points fall outside the CRS area of use. Geographic points are lon (x), lat (y)."),
    "parameters": {"type": "object", "properties": {
        "points": {"type": "array", "description": "Points as {name, x, y} (or easting/northing, lon/lat) or [x, y].",
                   "items": {"type": ["object", "array"]}},
        "from_crs": {"type": "string"}, "to_crs": {"type": "string"}},
        "required": ["points", "from_crs", "to_crs"]},
}
INVERSE = {
    "name": "survey_inverse",
    "description": "Bearing and distance between two coordinate pairs (a 'join' / inverse computation), in metres.",
    "parameters": {"type": "object", "properties": {
        "from_easting": {"type": "number"}, "from_northing": {"type": "number"},
        "to_easting": {"type": "number"}, "to_northing": {"type": "number"}},
        "required": ["from_easting", "from_northing", "to_easting", "to_northing"]},
}
