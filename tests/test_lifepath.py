"""Life path, steps and loose ends (lifepath.py) on synthetic points."""
import unittest
from datetime import date

from sg.records import lifepath as lp


def pt(t, y0, place, lat, lon, lv="farm", parish="A-by", y1=None):
    return dict(t=t, y0=y0, y1=y1 if y1 is not None else y0, place=place, lat=lat, lon=lon, lv=lv, parish=parish)


class TestLifePath(unittest.TestCase):
    def setUp(self):
        self.birth = pt("birth", 1820, "A-by/Gården", 57.0, 14.0)
        self.bapt = pt("baptism", 1820, "parish:A-by", 57.01, 14.01, lv="parish")
        self.hh = pt("household examination", 1840, "A-by/Torpet", 57.02, 14.0, y1=1845)
        self.far = pt("residence", 1850, "B-by/Stället", 59.0, 14.0, parish="B-by")
        self.path = lp.path([self.far, self.hh, self.bapt, self.birth, pt("birth", None, "", 0, 0)])

    def test_order_and_undated_left_out(self):
        self.assertEqual([p["t"] for p in self.path], ["birth", "baptism", "household examination", "residence"])

    def test_parish_point_is_not_a_move(self):
        st = lp.steps(self.path)
        self.assertEqual([(a["place"], b["place"]) for a, b, *_ in st],
                         [("A-by/Gården", "A-by/Torpet"), ("A-by/Torpet", "B-by/Stället")])
        self.assertFalse(st[0][3])               # farm to farm across the parish-level baptism
        self.assertAlmostEqual(st[1][2], 220.2, delta=0.5)
        self.assertFalse(st[1][3])

    def test_loose_end(self):
        today = date(2026, 1, 1)
        end = lp.loose_end(self.path, born=1820, today=today)
        self.assertEqual((end["year"], end["age"], end["left"]), (1850, 30, ""))
        self.assertIsNone(lp.loose_end(self.path, born=1820, died=1890, today=today))
        self.assertIsNone(lp.loose_end(self.path + [pt("burial", 1890, "B-by", 59, 14)], born=1820, today=today))
        self.assertIsNone(lp.loose_end(self.path, born=1950, today=today))        # presumed living
        left = lp.loose_end(self.path + [pt("emigration", 1860, "B-by", 59, 14)], born=1820, today=today)
        self.assertEqual(left["left"], "emigrated")

    def test_next_volumes(self):
        inv = {"SE/X/1/A I/3": dict(years="1846–1850", viewer="v3"), "SE/X/1/A I/2": dict(years="1841–1845"),
               "SE/X/1/C/1": dict(years="1800–1900"), "SE/X/1/A II a/1": dict(years="1895–1905", viewer="v9")}
        self.assertEqual(lp.next_volumes(inv, 1845), [("SE/X/1/A I/3", "1846–1850", "v3"),
                                                      ("SE/X/1/A II a/1", "1895–1905", "v9")])


if __name__ == "__main__":
    unittest.main()
