import json
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from survey_desk import geo, tools

LEGS = [{"to": "B", "bearing": "45-30-20", "distance": 120.45}, {"to": "C", "bearing": "135-10-00", "distance": 98.30},
        {"to": "D", "bearing": "225-40-10", "distance": 121.00}, {"to": "A", "bearing": "315-20-30", "distance": 97.80}]
START = {"name": "A", "easting": 164500.0, "northing": 380200.0}


def test_round_trip_and_accuracy_disclosure():
    r = geo.transform_points([{"name": "P", "x": 164500, "y": 380200}], "minna_west", "wgs84")
    assert r["round_trip_ok"]
    assert r["datum_shift_accuracy_m"] == 15.0
    assert 3.8 < r["points"][0]["x"] < 4.0 and 7.3 < r["points"][0]["y"] < 7.6


def test_same_datum_belt_to_belt_has_no_datum_shift():
    r = geo.transform_points([[164500, 380200]], "minna_west", "minna_mid")
    assert r["round_trip_ok"] and r["datum_shift_accuracy_m"] is None


def test_area_of_use_warning():
    r = geo.transform_points([[4.0, 7.4]], "wgs84", "minna_utm31")
    assert any("area of use" in w for w in r["warnings"])


def test_unknown_crs():
    with pytest.raises(Exception):
        geo.resolve_crs("nowhere")


def test_known_epsg_values():
    r = geo.transform_points([[4.0, 7.4]], "wgs84", "minna_west")
    assert r["points"][0]["x"] == pytest.approx(175637.4, abs=1.0)
    assert r["points"][0]["y"] == pytest.approx(375849.1, abs=1.0)


def test_plan_files_and_formats(tmp_path):
    out = json.loads(tools.survey_plan({"start": START, "legs": LEGS, "title": "Plot 14", "crs": "minna_west"}))
    assert "error" not in out
    suffixes = sorted(Path(p).suffix for p in out["files"])
    assert suffixes == [".dxf", ".geojson", ".kml", ".pdf", ".png"]
    assert all(Path(p).stat().st_size > 500 for p in out["files"])
    assert out["attachments"][0].startswith("MEDIA:") and out["attachments"][0].endswith(".png")
    kml = next(p for p in out["files"] if p.endswith(".kml"))
    ns = {"k": "http://www.opengis.net/kml/2.2"}
    coords = ET.parse(kml).getroot().find(".//k:Polygon//k:coordinates", ns).text.split()
    assert len(coords) == 5 and coords[0] == coords[-1]
    gj = json.loads(Path(next(p for p in out["files"] if p.endswith(".geojson"))).read_text())
    assert gj["features"][0]["geometry"]["type"] == "Polygon"
    import ezdxf
    doc = ezdxf.readfile(next(p for p in out["files"] if p.endswith(".dxf")))
    assert any(e.dxftype() == "LWPOLYLINE" and e.closed for e in doc.modelspace())


def test_kml_needs_crs():
    out = json.loads(tools.survey_plan({"start": START, "legs": LEGS, "formats": ["png", "kml"]}))
    assert any("skipped" in n for n in out["notes"]) and not any(p.endswith(".kml") for p in out["files"])


def test_errors_are_json():
    assert "error" in json.loads(tools.survey_traverse({"start": START, "legs": LEGS[:2]}))
    assert "error" in json.loads(tools.survey_convert({"points": [[1, 2]], "from_crs": "x", "to_crs": "wgs84"}))
    assert "error" in json.loads(tools.survey_plan({"legs": LEGS}))


FIELD_BOOK = """title: Plot 14, Block C
crs: minna_west
start: A 164500.00 380200.00
A-B 45-30-20 120.45
B-C 135-10-00 98.30
C-D 225-40-10 121.00
D-A 315-20-30 97.80
"""


def test_field_book_command():
    text = tools.survey_command(FIELD_BOOK)
    assert "Plot 14, Block C" in text and "MEDIA:" in text and "relative accuracy" in text
    assert tools.survey_command("").startswith("Usage")
    assert "Could not compute" in tools.survey_command("start: A 1 2\nnonsense line")


def test_command_flags_blunder():
    bad = FIELD_BOOK.replace("98.30", "89.30")
    text = tools.survey_command(bad)
    assert "RE-OBSERVE" in text and "Suspect leg" in text


def test_register_with_fake_ctx():
    import survey_desk
    seen = {"tools": [], "cmds": [], "skills": []}

    class Ctx:
        def register_tool(self, name, **kw): seen["tools"].append(name)
        def register_command(self, name, handler, **kw): seen["cmds"].append(name)
        def register_skill(self, name, path, **kw): seen["skills"].append(name)

    survey_desk.register(Ctx())
    assert seen["tools"] == ["survey_traverse", "survey_plan", "survey_convert", "survey_inverse"]
    assert seen["cmds"] == ["survey"] and seen["skills"] == ["field-book"]


DEMO = (Path(__file__).resolve().parent.parent / "examples" / "demo-fieldbook.txt").read_text()


def test_demo_fieldbook_is_clean():
    text = tools.survey_command(DEMO)
    assert "ACCEPTABLE" in text and "1:12,812" in text


@pytest.mark.parametrize("old,new,leg,kind", [
    ("87.05", "78.05", "D-E", "distance"),
    ("95.90", "59.90", "E-A", "distance"),
    ("94.72", "49.72", "C-D", "distance"),
    ("067-45-46", "076-45-46", "A-B", "bearing"),
    ("213-02-26", "231-02-26", "C-D", "bearing"),
])
def test_demo_fieldbook_digit_transposition_blunders(old, new, leg, kind):
    args = tools.parse_field_book(DEMO.replace(old, new))
    out = json.loads(tools.survey_traverse(args))
    top = out["suspects"][0]
    assert (top["leg"], top["kind"]) == (leg, kind)
    assert top["fit_percent"] > 95
