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

    def test_lead(self):
        nxt = [("A I/3", "1846–1850", "v3"), ("A I/4", "1851–1855", "v4")]
        self.assertEqual(lp.lead(nxt, {}, {"A I/4": ("Anna", "12")}), ("household", (nxt[1], "12", "Anna")))
        self.assertEqual(lp.lead(nxt, {"A I/4": "7"}, {"A I/3": ("Anna", "12")}), ("cited", (nxt[1], "7", "")))
        self.assertEqual(lp.lead(nxt, None, None), ("", None))


if __name__ == "__main__":
    unittest.main()


class TestStepLabels(unittest.TestCase):
    """A made-up family: father F (1790) and uncle U are brothers; F's
    children X (1820) and S (1822) leave the home farm together, X goes to
    the uncle's farm, S follows X there, X comes back to the ageing father."""

    def setUp(self):
        G = ("A-by/Gården", 57.0, 14.0)
        T = ("A-by/Torpet", 57.02, 14.0)
        St = ("B-by/Stället", 59.0, 14.0, "farm", "B-by")
        self.paths = {
            "F": lp.path([pt("household examination", 1820, *G, y1=1870)]),
            "U": lp.path([pt("household examination", 1830, *St, y1=1855)]),
            "X": lp.path([pt("birth", 1820, *G), pt("household examination", 1838, *T, y1=1842),
                          pt("household examination", 1845, *St, y1=1855), pt("household examination", 1858, *G, y1=1862)]),
            "S": lp.path([pt("birth", 1822, *G), pt("household examination", 1839, *T, y1=1842),
                          pt("household examination", 1850, *St, y1=1856)]),
        }
        self.roles = lp.kin_roles({"f0": ("GF", None), "f1": ("F", "M")}, {"f0": ["F", "U"], "f1": ["X", "S"]})
        self.life = {"F": (1790, 1875), "M": (1795, 1850), "U": (1792, 1860), "X": (1820, None), "S": (1822, None)}

    def test_roles(self):
        self.assertEqual(self.roles["X"]["U"], "uncle")
        self.assertEqual(self.roles["X"]["S"], "sibling")
        self.assertEqual(self.roles["U"]["X"], "nibling")
        self.assertEqual(self.roles["X"]["GF"], "grandparent")

    def test_labels(self):
        got = [(b["place"], [(k, r) for k, r, _ in lab]) for a, b, km, ap, lab in lp.labels("X", self.paths, self.roles, self.life)]
        self.assertEqual(got[0], ("A-by/Torpet", [("together", "S")]))
        self.assertEqual(got[1], ("B-by/Stället", [("kin", "U")]))
        # back where born, to a father aged 68 whose wife had died
        self.assertEqual(got[2], ("A-by/Gården", [("born", ""), ("ageing", "F")]))
        s = lp.labels("S", self.paths, self.roles, self.life)
        self.assertIn(("following", "X", 1845), s[1][4])
        self.assertIn(("kin", "U", None), s[1][4])


class TestSettledPath(unittest.TestCase):
    def test_citation_stands_back_for_dated_point(self):
        # three household citations sharing one volume's span (1876-1880),
        # two of them told more precisely by residence entries
        cit = lambda place, lat: dict(pt("household examination", 1876, place, lat, 14.0, y1=1880), l="record")
        res = lambda y0, y1, place, lat: dict(pt("residence", y0, place, lat, 14.0, y1=y1), l="tree")
        path = lp.path([pt("birth", 1871, "A-by/Gården", 57.0, 14.0),
                        cit("A-by/Torpet", 57.1), cit("B-by/Stället", 57.5), cit("C-by/Hagen", 58.0),
                        res(1877, 1880, "B-by/Stället", 57.5), res(1880, 1886, "C-by/Hagen", 58.0),
                        pt("death", 1900, "C-by/Hagen", 58.0, 14.0), pt("burial", 1900, "parish:A-by", 57.0, 14.0, lv="parish")])
        got = [(lp.year(b), b["place"]) for _, b, *_ in lp.steps(path)]
        # the Torpet citation has no better date and stays; the others stand back; the burial is no step
        self.assertEqual(got, [(1876, "A-by/Torpet"), (1877, "B-by/Stället"), (1880, "C-by/Hagen")])
