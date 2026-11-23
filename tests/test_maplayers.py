"""maplayers.py on synthetic input: grids, sheet names, print-out text, frame finding."""
import math
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from sg.views import maplayers as ml


def test_central_meridian_and_scale():
    lat, lon = ml.grid_to_latlon(6600000, 500000, "SWEREF 99 TM")
    assert abs(lon - 15) < 1e-9 and 59 < lat < 60
    # a metre north on the central meridian is k0 metres of grid less than a metre of arc
    lat2, _ = ml.grid_to_latlon(6601000, 500000, "SWEREF 99 TM")
    metres = (lat2 - lat) * math.pi / 180 * 6378137 * (1 - 0.00669438) / (1 - 0.00669438 * math.sin(math.radians(lat)) ** 2) ** 1.5
    assert abs(metres - 1000 / 0.9996) < 0.5


def test_grids_agree_roughly():
    # the same ground in both grids differs by its false easting and the meridian offset
    a = ml.grid_to_latlon(6700000, 1500000, "RT 90")
    b = ml.grid_to_latlon(6700000, 545000, "SWEREF 99 TM")
    assert abs(a[0] - b[0]) < 0.05 and abs(a[1] - b[1]) < 0.1


def test_archive_id_and_sheet():
    name = "Example rak2_" + "RAK_J133-12F3b60".encode().hex() + "_1_1.jpg"
    assert ml.archive_id(name) == "RAK_J133-12F3b60"
    assert ml.sheet_square("RAK_J133-12F3b60") == ("RT 90", 6665000, 6670000, 1455000, 1460000, "60")
    assert ml.sheet_square("RAK_J243-67-1") is None


def test_printout_frame():
    text = "  N 6400100\nE 401000\n   N\n      E 414200\n   N 6391400\n Skala 1:33 000, SWEREF 99 TM, RH 2000."
    assert ml.printout_frame(text) == ("SWEREF 99 TM", 6391400, 6400100, 401000, 414200)
    assert ml.printout_frame("Skala 1:10 000") is None


def test_frame_corners_on_a_tilted_sheet():
    h, w = 600, 700
    img = np.full((h, w, 3), (250, 247, 235), np.uint8)              # paper
    ys, xs = np.mgrid[0:h, 0:w]
    tilt = 0.01
    u = xs - 100 + tilt * (ys - 50)                                   # map square, turned a little
    v = ys - 50 - tilt * (xs - 100)
    inside = (u >= 0) & (u < 450) & (v >= 0) & (v < 450)
    img[inside] = (90, 160, 60)
    img[(u > 100) & (u < 160) & (v > 100) & (v < 200)] = (245, 245, 240)   # a pale field inside
    img[200:215, 600:620] = (220, 200, 40)                             # a legend swatch
    got = ml.frame_corners(img)
    want = []
    for uu, vv in [(0, 0), (0, 450), (450, 450), (450, 0)]:
        # invert the small rotation
        d = 1 + tilt * tilt
        x = (uu - tilt * vv) / d + 100
        y = (vv + tilt * uu) / d + 50
        want.append((x, y))
    for (gx, gy), (wx, wy) in zip(got, want):
        assert abs(gx - wx) < 2 and abs(gy - wy) < 2, (got, want)
