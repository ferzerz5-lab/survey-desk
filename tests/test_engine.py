import math

import pytest

from survey_desk import engine as E

START = {"name": "A", "easting": 164500.0, "northing": 380200.0}


def rect(blunder=None):
    legs = [{"to": "B", "bearing": "090", "distance": 100.0}, {"to": "C", "bearing": "180", "distance": 50.0},
            {"to": "D", "bearing": "270", "distance": 100.0}, {"to": "A", "bearing": "000", "distance": 50.0}]
    if blunder:
        i, key, val = blunder
        legs[i][key] = val
    return legs


def polygon_legs(coords, noise=None):
    """Legs (as the field book would record them) for a known polygon."""
    legs = []
    for i, (p, q) in enumerate(zip(coords, coords[1:] + coords[:1])):
        az, d = E.inverse(*p, *q)
        if noise:
            az += noise[i][0] / 3600.0
            d += noise[i][1]
        legs.append({"to": chr(66 + i) if i < len(coords) - 1 else "A", "bearing": az, "distance": d})
    return legs


def test_bearing_formats():
    assert E.parse_bearing("45°30'20\"") == pytest.approx(45 + 30 / 60 + 20 / 3600)
    assert E.parse_bearing("045-30-20") == pytest.approx(45.505555555)
    assert E.parse_bearing("N45-30-20E") == pytest.approx(45.505555555)
    assert E.parse_bearing("S45-30-20E") == pytest.approx(180 - 45.505555555)
    assert E.parse_bearing("S45-30-20W") == pytest.approx(180 + 45.505555555)
    assert E.parse_bearing("N45-30-20W") == pytest.approx(360 - 45.505555555)
    assert E.parse_bearing(270) == 270.0
    assert E.parse_bearing("12.5") == 12.5


@pytest.mark.parametrize("bad", ["", "abc", "45-75-00", "400", "N95-00-00E", -5, True, "45-30-20-10"])
def test_bad_bearings_rejected(bad):
    with pytest.raises(E.SurveyError):
        E.parse_bearing(bad)


def test_format_bearing_rounds_with_carry():
    assert E.format_bearing(45.505555555) == "045°30'20\""
    assert E.format_bearing(359.99999999) == "000°00'00\""
    assert E.format_bearing(10.0) == "010°00'00\""


def test_rectangle_exact():
    r = E.compute_traverse(START, rect())
    assert r["area"]["square_metres"] == pytest.approx(5000.0, abs=1e-6)
    assert r["misclosure"]["linear"] == pytest.approx(0.0, abs=1e-9)
    assert r["verdict"] == "ACCEPTABLE"
    assert all(c["passed"] for c in r["checks"])


def test_dmd_matches_shoelace_on_irregular_polygon():
    coords = [(1000, 1000), (1180, 1040), (1230, 1190), (1090, 1260), (990, 1150)]
    r = E.compute_traverse({"name": "A", "easting": 1000, "northing": 1000}, polygon_legs(coords))
    shoe = E.shoelace_area(coords)
    assert r["area"]["square_metres"] == pytest.approx(shoe, rel=1e-9)
    assert next(c for c in r["checks"] if c["name"] == "area_methods_agree")["passed"]


def test_bowditch_against_independent_calculation():
    coords = [(0, 0), (200, 20), (240, 160), (90, 210), (-20, 110)]
    noise = [(30, 0.021), (-20, -0.013), (45, 0.018), (-10, -0.020), (15, 0.012)]
    legs = polygon_legs(coords, noise)
    r = E.compute_traverse({"name": "A", "easting": 0, "northing": 0}, legs)
    # independent: plain-python compass rule
    az = [E.parse_bearing(l["bearing"]) for l in legs]
    d = [l["distance"] for l in legs]
    sx = sum(di * math.sin(math.radians(a)) for a, di in zip(az, d))
    sy = sum(di * math.cos(math.radians(a)) for a, di in zip(az, d))
    P = sum(d)
    x = y = 0.0
    expect = []
    for a, di in zip(az, d):
        x += di * math.sin(math.radians(a)) - sx * di / P
        y += di * math.cos(math.radians(a)) - sy * di / P
        expect.append((x, y))
    for st, (ex, ey) in zip(r["stations"][1:], expect[:-1]):
        assert st["easting"] == pytest.approx(ex, abs=6e-4) and st["northing"] == pytest.approx(ey, abs=6e-4)
    assert expect[-1] == pytest.approx((0, 0), abs=1e-9)
    assert r["misclosure"]["delta_e"] == pytest.approx(sx, abs=1e-4)


def test_transit_rule_also_closes():
    coords = [(0, 0), (200, 20), (240, 160), (90, 210), (-20, 110)]
    legs = polygon_legs(coords, [(30, 0.02), (-20, -0.01), (40, 0.02), (-10, -0.02), (15, 0.01)])
    r = E.compute_traverse({"name": "A", "easting": 0, "northing": 0}, legs, method="transit")
    assert next(c for c in r["checks"] if c["name"] == "closes_after_adjustment")["passed"]


def test_perfect_closure_text():
    assert E.compute_traverse(START, rect())["misclosure"]["relative_accuracy"] == "perfect closure"


def test_distance_blunder_names_the_leg():
    coords = [(1000, 1000), (1180, 1040), (1230, 1190), (1090, 1260), (990, 1150)]
    legs = polygon_legs(coords)
    true = legs[2]["distance"]
    legs[2]["distance"] = round(true - 18.0, 3)
    r = E.compute_traverse({"name": "A", "easting": 1000, "northing": 1000}, legs)
    assert r["verdict"].startswith("RE-OBSERVE")
    best = r["suspects"][0]
    assert best["leg"] == "C-D" and best["kind"] == "distance"
    assert best["likely"] == pytest.approx(true, abs=0.01)


def test_bearing_blunder_names_the_leg():
    coords = [(1000, 1000), (1180, 1040), (1230, 1190), (1090, 1260), (990, 1150)]
    legs = polygon_legs(coords)
    true_az = legs[1]["bearing"]
    legs[1]["bearing"] = true_az + 5.0
    r = E.compute_traverse({"name": "A", "easting": 1000, "northing": 1000}, legs)
    best = r["suspects"][0]
    assert best["leg"] == "B-C" and best["kind"] == "bearing"
    assert E.parse_bearing(best["likely"]) == pytest.approx(true_az, abs=0.01)


def test_reversed_bearing_blunder():
    coords = [(1000, 1000), (1180, 1040), (1230, 1190), (1090, 1260), (990, 1150)]
    legs = polygon_legs(coords)
    legs[3]["bearing"] = (legs[3]["bearing"] + 180.0) % 360.0
    r = E.compute_traverse({"name": "A", "easting": 1000, "northing": 1000}, legs)
    assert r["suspects"][0]["leg"] == "D-E" or r["suspects"][0]["leg"] == "D-A"


def test_bowtie_order_is_flagged():
    legs = [{"to": "B", "bearing": "045", "distance": 100.0}, {"to": "C", "bearing": "180", "distance": 70.71},
            {"to": "D", "bearing": "315", "distance": 100.0}, {"to": "A", "bearing": "180", "distance": 70.71}]
    r = E.compute_traverse({"name": "A", "easting": 0, "northing": 0}, legs, tolerance_ratio=1)
    assert not next(c for c in r["checks"] if c["name"] == "simple_polygon")["passed"]
    assert r["verdict"] == "CHECK FAILED"


def test_inputs_validated():
    with pytest.raises(E.SurveyError):
        E.compute_traverse(START, rect()[:2])
    bad = rect()
    bad[0]["distance"] = -5
    with pytest.raises(E.SurveyError):
        E.compute_traverse(START, bad)


def test_inverse_round_trip():
    az, d = E.inverse(100, 100, 200, 100)
    assert az == pytest.approx(90.0) and d == pytest.approx(100.0)
    e, n = E.forward(100, 100, az, d)
    assert (e, n) == pytest.approx((200, 100))
