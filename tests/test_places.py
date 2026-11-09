"""
Tests for the places and records layer, on synthetic data only:

    python3 -m unittest discover -s tests -v

text repair (textfix), place-name parsing and variant rules (gazetteer),
whole-string resolution against a tiny gazetteer, residence aggregation
(stays), and the place import into the tree store (place_store).
"""
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import gazetteer as gz  # noqa: E402
import stays  # noqa: E402
import textfix  # noqa: E402


class TextFix(unittest.TestCase):
    def test_damaged_letters(self):
        cases = {"SkÃ¶vde": "Skövde", "Ã\x85kesson": "Åkesson", "Ã<br/>kesson": "Åkesson",
                 "GaÌ\x88stgivare": "Gästgivare", "Ka¨lleryd": "Källeryd", "Stora A°by": "Stora Åby",
                 "Gränna": "Gränna", "¨Skotte¨": "¨Skotte¨", "Ãx": "Ãx"}
        for raw, want in cases.items():
            self.assertEqual(textfix.fix(raw), want, raw)

    def test_html(self):
        self.assertEqual(textfix.fix("Rune&amp;lt;br&amp;gt;Födelse"), "Rune\nFödelse")
        self.assertEqual(textfix.fix("<p>&Ouml;desh&ouml;g</p>Ouml;desh&ouml;g"), "Ödeshög\nÖdeshög")
        self.assertEqual(textfix.fix("?s=1&amp;itemId=2"), "?s=1&itemId=2")
        self.assertEqual(textfix.fix("Smith & Co"), "Smith & Co")


class Names(unittest.TestCase):
    def test_parse_levels(self):
        self.assertEqual(gz.parse("Roten Ingarps Rote."), [("Ingarps rote", "rote")])
        self.assertEqual(gz.parse("Roten Ingarp Rote Swenshult"),
                         [("Ingarps rote", "rote"), ("Svenshult", "")])
        self.assertEqual(gz.parse("Swenshult Torpet Swenstorp"), [("Svenshult", ""), ("Svenstorp", "torp")])
        self.assertEqual(gz.parse("Moen under Askaremålen"), [("Askaremålen", ""), ("Moen", "torp")])
        self.assertEqual(gz.parse("Gettered Kollerö Rote"), [("Kollerö rote", "rote"), ("Gettered", "")])

    def test_unalias(self):
        self.assertEqual(gz.parse("Duve Eller Dårebo"), [("Dårebo", "")])
        self.assertEqual(gz.parse("Eller Kjellerö Högaberg"), [("Kjellerö Högaberg", "")])
        self.assertEqual(gz.parse("Gr. Landsförsaml. Björket"), [("Björket", "")])
        self.assertEqual(gz.parse("Rysseryd Eller. Fätorp"), [("Fätorp", "")])
        self.assertEqual(gz.modern("Tuggarp Vestergård"), "Tuggarp Västergård")

    def test_farm_kinds_differ(self):
        self.assertTrue(gz._distinct_words("Ödeshögs Riddaregård", "Ödeshögs Skattegård"))
        self.assertFalse(gz._distinct_words("Uppgrenna Länsmansgård", "Uppgrenna Lönsmansg"))

    def test_clear_variants(self):
        same = [("Algudstorp", "Algutstorp"), ("Mjerhult", "Mjärhult"), ("Kjellerö", "Källerö"),
                ("Storegården", "Storgården"), ("Staflösa Mellang", "Staflösa Mellangård"),
                ("Valdshult", "Valshult"), ("Bränninge Östergård", "Bränninge Östergården")]
        different = [("Tuggarp Vestergård", "Tuggarp Östergård"), ("Lilla Bexhult", "Stora Bexhult"),
                     ("Storgården", "Sörgården"), ("Berga", "Borga"), ("Stenshult", "Svenshult")]
        for a, b in same:
            self.assertTrue(gz.clear_variant(a, b), (a, b))
        for a, b in different:
            self.assertFalse(gz.clear_variant(a, b), (a, b))

    def test_map_hit_must_fit_the_name(self):
        import geocode
        self.assertTrue(geocode._name_fits("Sturkö", "Sturkoe"))
        self.assertTrue(geocode._name_fits("Gränna", "Granna"))
        self.assertFalse(geocode._name_fits("Deir Jarir", "W. Ryr"))
        self.assertFalse(geocode._name_fits("Aleutians West Census Area", "Mbo"))

    def test_generic_parts(self):
        for n in ("Sörgården", "Norrgård", "Torpet", "Mellangården"):
            self.assertTrue(gz.generic(n), n)
        self.assertFalse(gz.generic("Hagelstorp"))


def tiny_gazetteer():
    d = Path(tempfile.mkdtemp())
    (d / "parishes.toml").write_text(
        '["Källeryd"]\narchive = "SE/XXXA/00001"\nlat = 57.3\nlon = 13.7\n'
        '["Adelöv"]\nlat = 58.0\nlon = 14.6\n', encoding="utf-8")
    (d / "places.toml").write_text(
        '["Källeryd/Hagelstorp"]\nname = "Hagelstorp"\nparish = "Källeryd"\nlat = 57.37\nlon = 13.65\n'
        'geo_level = "farm"\n'
        '["Källeryd/Göhestra"]\nname = "Göhestra"\nparish = "Källeryd"\nwithin = "Källeryd/Hagelstorp"\n'
        '["Adelöv/Mjölarp"]\nname = "Mjölarp"\nparish = "Adelöv"\nlat = 58.0\nlon = 14.7\n', encoding="utf-8")
    return gz.Gazetteer(d)


class Resolve(unittest.TestCase):
    def test_whole_strings(self):
        g = tiny_gazetteer()
        self.assertEqual(g.resolve_plac("Sörgården, Göhestra, Hagelstorp, Källeryd, Jönköpings län")[0],
                         "Källeryd/Göhestra")
        self.assertEqual(g.resolve_plac("Mjölarp, Knekttorpet No 19, Adelöv, Sverige")[0], "Adelöv/Mjölarp")
        self.assertEqual(g.resolve_plac("Hagelstorp, Jönköpings län, Sverige"),
                         ("Källeryd/Hagelstorp", "unique village name"))
        self.assertEqual(g.resolve_plac("Okänd, Källeryds församling"), ("parish:Källeryd", "parish"))
        self.assertEqual(g.resolve_plac("West Hartford, Connecticut, USA"), (None, ""))

    def test_known_prefix(self):
        g = tiny_gazetteer()
        g.add_place("Källeryd", "Skogs rote", kind="rote")
        g.add_place("Källeryd", "Hjulshult")
        g.add_place("Källeryd", "Göhestra Västergård")
        self.assertEqual(g.place("Källeryd", "Skogs Hjulshult"), "Källeryd/Hjulshult")
        self.assertEqual(g.place("Källeryd", "Eller Skog Hjulshult"), "Källeryd/Hjulshult")
        self.assertIsNone(g.split_known("Källeryd", "Göhestra Västergård"))   # a part, not a farm
        self.assertIsNone(g.split_known("Källeryd", "Göhestra Hagelstorp"))   # Göhestra lies in it
        g.add_place("Källeryd", "Näs"); g.add_place("Källeryd", "Näs Hagelstorp", checked=True)
        self.assertEqual(g.add_written("Källeryd", "Näs Hagelstorp"), "Källeryd/Näs Hagelstorp")
        pid = g.add_written("Källeryd", "Skogs Hjulshult")
        self.assertEqual((pid, g.places[pid]["within"]), ("Källeryd/Hjulshult", "Källeryd/Skogs rote"))

    def test_coords_fall_back(self):
        g = tiny_gazetteer()
        self.assertEqual(g.coords("Källeryd/Hagelstorp")[2], "farm")
        self.assertEqual(g.coords("Källeryd/Göhestra")[2], "parish")     # no point: the parish's


class Stays(unittest.TestCase):
    def items(self):
        e = lambda place, date, y0, y1: dict(place=place, date=date, y0=y0, y1=y1)
        return [e("Groröd", "BET 1854 AND 1860", 1854, 1860)] + \
            [e("Groröd", "BET 1861 AND 1867", 1861, 1867)] * 3 + \
            [e("Röd", "BET 1861 AND 1867", 1861, 1867),
             e("Kuröd", "BET 1861 AND 1867", 1861, 1867),
             e("Munkebo rote", "BET 1870 AND 1882", 1870, 1882),
             e("Möjered", "BET 1870 AND 1882", 1870, 1882),
             e("Mjölarp", "BET 9 NOV 1901 AND 1907", 1901, 1907),
             e("Mjölarp", "BET 1901 AND 1909", 1901, 1909)]

    def test_aggregate(self):
        st = {s["key"]: s for s in stays.aggregate(self.items(), key=lambda i: i["place"])}
        self.assertEqual((st["Groröd"]["y0"], st["Groröd"]["y1"], st["Groröd"]["n"]), (1854, 1867, 4))
        self.assertEqual(st["Röd"]["group"], "1861–1867")
        self.assertIsNone(st["Groröd"]["group"])
        self.assertTrue(st["Mjölarp"]["dated"])
        self.assertEqual(st["Mjölarp"]["label"], "BET 9 NOV 1901 AND 1907")

    def test_farm_before_district(self):
        agg = stays.aggregate(self.items(), key=lambda i: i["place"])
        out = stays.drop_general(agg, lambda k: "P", lambda k: k.endswith(" rote"))
        keys = [s["key"] for s in out]
        self.assertNotIn("Munkebo rote", keys)
        self.assertEqual([a["key"] for a in next(s for s in out if s["key"] == "Möjered")["also"]],
                         ["Munkebo rote"])

    def test_touching_is_not_overlap(self):
        e = lambda place, y0, y1: dict(place=place, date=f"BET {y0} AND {y1}", y0=y0, y1=y1)
        agg = stays.aggregate([e("Kallebäcken", 1901, 1907), e("(parish)", 1907, 1935)],
                              key=lambda i: i["place"], gap=0)
        out = stays.drop_general(agg, lambda k: "P", lambda k: k == "(parish)")
        self.assertEqual(len(out), 2)


class PlaceStore(unittest.TestCase):
    def test_import_links_events(self):
        import place_store
        import tree_store
        d = Path(tempfile.mkdtemp())
        s = tree_store.Store(d / "tree.sqlite")
        s.db.execute("insert into event (owner, tag, date, place, extra, origin) values "
                     "('I1','BIRT','1 JAN 1900','Göhestra, Hagelstorp, Källeryd','[]','import:t')")
        s.db.execute("insert into event (owner, tag, date, place, extra, origin) values "
                     "('I1','RESI','BET 1901 AND 1909','', ?, 'import:t')",
                     ('[{"tag":"ADDR","value":"","sub":[{"tag":"ADR1","value":"Mjölarp","sub":[]},'
                      '{"tag":"CITY","value":"Adelöv","sub":[]}]}]',))
        s.db.commit()
        import geocode
        geocode.OFFLINE[0] = True
        r = place_store.import_places(s, "test", gaz=tiny_gazetteer())
        links = dict(s.db.execute("select tag, place_id from event").fetchall())
        self.assertEqual(links, {"BIRT": "Källeryd/Göhestra", "RESI": "Adelöv/Mjölarp"})
        self.assertEqual(r["places"], 3)
        self.assertGreater(len(place_store.events_with_coords(s)), 0)


if __name__ == "__main__":
    unittest.main()
