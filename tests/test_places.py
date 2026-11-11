"""
Tests for the places and records layer, on synthetic data only:

    python3 -m unittest discover -s tests -v

text repair (textfix), place-name parsing and variant rules (gazetteer),
whole-string resolution against a tiny gazetteer, residence aggregation
(stays), and the place import into the tree store (place_store).
"""
import os
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

    def test_jordnatur(self):
        self.assertEqual(gz.jordnatur("Possarp Skatte"), ("Possarp", "skatte"))
        self.assertEqual(gz.jordnatur("Skatte Porssarp"), ("Porssarp", "skatte"))
        self.assertEqual(gz.jordnatur("Mantal Elmtomta Södergård Frälse"), ("Elmtomta Södergård", "frälse"))
        self.assertEqual(gz.jordnatur("Krono-skatte Hult"), ("Hult", "kronoskatte"))
        for n in ("Ödeshögs Skattegård", "Skinstad Frälsegård", "Råcklunda Kronolänsm", "Kronoberg", "Skatte"):
            self.assertEqual(gz.jordnatur(n), (n, ""), n)
        self.assertEqual(gz.parse("Klöfvedahla Skatte"), [("Klövedahla", "")])

    def test_generic_parts(self):
        for n in ("Skatte", "Frälsegården", "Riddaregården", "Prästgård"):
            self.assertTrue(gz.generic(n), n)
        self.assertFalse(gz.generic("Ödeshögs Skattegård"))
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

    def test_build_adds_no_redundant_aliases(self):
        g = tiny_gazetteer()
        rows = [dict(parish="Källeryd", volume="A I/1", ra_archive=a) for a in
                ("Källeryds kyrkoarkiv", "Källa: Källeryds kyrkoarkiv",
                 "In- och utflyttningslängder", "Kjelleryds kyrkoarkiv")]
        gz.build(g, rows)
        self.assertEqual(g.parishes["Källeryd"].get("aliases"), ["Kjelleryd"])
        self.assertEqual(g.parish("Källeryds"), "Källeryd")

    def test_short_regions_and_county_letters(self):
        for written, region in (("Älvsb. l.", "älvsborgs"), ("Ög. l.", "östergötland"), ("Krist.", "kristianstads"),
                                ("Jnkpng", "jönköpings"), ("Swdn", "sweden"), ("Jonk.", "jönköpings"),
                                ("AB-län", "stockholms"), ("Älfsborgs l.", "älvsborgs")):
            self.assertEqual(gz.region_abbrev(written), region, written)
        for written in ("stad.", "St.", "Mbo.", "Lom.", "Vas.", "Malma"):
            self.assertEqual(gz.region_abbrev(written), "", written)
        self.assertEqual(gz.county_code("Gällstad (P)"), "Älvsborgs län")

    def test_parts_split(self):
        self.assertEqual(gz.plac_parts("Sjötofta Älvsb. l."), ["Sjötofta", "Älvsb. l."])
        self.assertEqual(gz.plac_parts("Norra Ryr Göteborgs och Bohus län"), ["Norra Ryr", "Göteborgs och Bohus län"])
        self.assertEqual(gz.plac_parts("Dagsberg (E) Tångstad"), ["Tångstad", "Dagsberg (E)"])
        self.assertEqual(gz.plac_parts("Stadsförsamlingen (K), Karlskrona"), ["Karlskrona Stadsförsamlingen"])
        self.assertEqual(gz.plac_parts("Sala stad."), ["Sala stad."])
        self.assertEqual(gz.plac_parts("Halsingborg, Malmohus"), ["Helsingborg", "Malmohus"])
        self.assertEqual(gz.plac_parts("Hälsingborgs Maria"), ["Helsingborgs Maria"])

    def test_written_short_or_old(self):
        g = tiny_gazetteer()
        g.parishes["Valdshult"] = {}
        g._index()
        self.assertEqual(g.parish("Källeryd sn"), "Källeryd")
        self.assertEqual(g.parish("Källeryd Stadsf."), "Källeryd")
        self.assertEqual(g.parish("Valdshult (Waldshult)"), "Valdshult")
        self.assertEqual(g.parish_rule("Valdshult (Waldshult)", strict=True), (None, ""))
        self.assertEqual(g.loose_parish("Adelöf"), ("Adelöv", "parish, old spelling"))
        self.assertEqual(g.loose_parish("Kalleryd"), ("Källeryd", "parish, letters lost"))
        self.assertEqual(g.explain_plac("Mjölarp, Adelöf (F)")[0], "Adelöv/Mjölarp")
        self.assertEqual(gz.old_spelling("Jerfsö"), gz.old_spelling("Järvsö"))
        self.assertNotEqual(gz.old_spelling("Hagstad"), gz.old_spelling("Hogstad"))

    def test_namesake_in_another_parish(self):
        g = tiny_gazetteer()
        # an unknown name after the farm may be its parish: no guess elsewhere
        self.assertEqual(g.resolve_plac("Hagelstorp, Okändby, Älvsborgs, Västergötland, Sweden"),
                         (None, ""))
        # a county letter, a misspelt parish, a kommun or another place of the
        # same parish may follow it
        self.assertEqual(g.resolve_plac("Hagelstorp, Källeryd (F)")[0], "Källeryd/Hagelstorp")
        self.assertEqual(g.resolve_plac("Hagelstorp, Källaryd, Jönköpings län")[0],
                         "Källeryd/Hagelstorp")
        self.assertEqual(g.resolve_plac("Göhestra, Gislaveds kommun")[0], "Källeryd/Göhestra")
        self.assertEqual(g.explain_plac("Göhestra, Källeryd (F)")[1:3], ("place name", "parish name"))

    def test_moves_and_regions(self):
        self.assertEqual(gz.plac_parts("fr. Aronsdal, Byn t. Gården, Socknen"), ["Gården", "Socknen"])
        self.assertEqual(gz.plac_parts("fr. Byn t. Socknen"), ["Socknen"])
        # MyHeritage's bracket style, no commas
        self.assertEqual(gz.plac_parts("Byn (Gatan 1) (Orts Kommun) (Skåne Län) Skåne Sverige"
                                       " (Kyrkobokförd Socknen)"),
                         ["Gatan 1", "Byn", "Socknen", "Orts Kommun", "Skåne Län", "Skåne", "Sverige"])
        self.assertEqual(gz.plac_parts("Socknen (Orts Kommun) (Skåne Län) Skåne Sverige")[0], "Socknen")
        self.assertEqual(gz.plac_parts("Källeryd (F)"), ["Källeryd (F)"])   # a county letter stays

    def test_parish_list_fallback(self):
        """No gazetteer parish in the string: the full parish list names one
        (parish_names), with the same reading as volumes.normalise."""
        import parish_names
        from tests.test_parish_names import names
        saved, parish_names._DEFAULT = parish_names._DEFAULT, names()
        try:
            g = gz.Gazetteer(root=self.tmp) if hasattr(self, "tmp") else gz.Gazetteer.__new__(gz.Gazetteer)
            g.parishes, g.places, g.plac_map = {}, {}, {}
            g._index()
            self.assertEqual(g.explain_plac("Byn (Gatan 1) (Burlöv Kommun) (Skåne Län) Skåne Sverige"
                                            " (Kyrkobokförd Burlöv)")[:2], ("parish:Burlöv", "parish list"))
            self.assertEqual(g.explain_plac("Haurida, Aneby, Jönköpings län")[0], "parish:Haurida")
            # a lone name, when no farm of the gazetteer takes it
            self.assertEqual(g.explain_plac("Högalid")[:2], ("parish:Högalid", "parish list, lone name"))
            self.assertEqual(g.explain_plac("Ystad, Skåne")[:2], (None, "town (geocoded in the store)"))
            self.assertEqual(g.resolve_plac("Ystad, Skåne"), (None, ""))
        finally:
            parish_names._DEFAULT = saved
        for x in ("Jönköpings län", "Älvsborgs", "Västergötland", "Sweden", "Göteborgs och Bohus"):
            self.assertTrue(gz.region(x), x)
        self.assertFalse(gz.region("Källeryd"))
        self.assertEqual(gz.drop_county_code("Lane-Ryr (O)"), "Lane-Ryr")

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
        self.assertEqual(g.coords("Källeryd/Göhestra")[:3], (57.37, 13.65, "village"))   # the village it lies in
        del g.places["Källeryd/Hagelstorp"]["lat"]
        self.assertEqual(g.coords("Källeryd/Göhestra")[2], "parish")     # no point anywhere: the parish's


class PlacesRules(unittest.TestCase):
    """places_rules.py: the per-string trace must agree with resolve_plac."""

    def test_trace_agrees(self):
        import places_rules
        g = tiny_gazetteer()
        g.add_place("Källeryd", "Hjulshult", variants=["Hjulsholt Skatte"])
        cases = {"Sörgården, Göhestra, Hagelstorp, Källeryd, Jönköpings län": "place name",
                 "Hjulsholt, Källeryd": "variant without jordnatur",
                 "Hjulsholt Skatte, Källeryd": "place variant",
                 "Hagelstorp, Jönköpings län, Sverige": "unique village name",
                 "Okänd, Källeryds församling": "parish only (farm part unknown)",
                 "West Hartford, Connecticut, USA": "unresolved"}
        for plac, rule in cases.items():
            pid, how, *_ = places_rules.explain_plac(g, plac)
            self.assertEqual(pid, g.resolve_plac(plac)[0], plac)
            self.assertEqual(how, rule, plac)
        self.assertEqual(places_rules.parish_how(g, "Källeryds församling"),
                         ("Källeryd", "parish, genitive s dropped"))

    def test_page(self):
        import places_rules
        page = places_rules.generic_html()
        self.assertNotIn("error:", page)
        d = Path(tempfile.mkdtemp())
        data = places_rules.data_html(tiny_gazetteer(), dict(
            plac_map=d / "none.toml", errata=d / "none.toml", volume_refs=d / "none.csv",
            store=d / "none.sqlite"))
        self.assertIn("No tree store yet", data)


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
        # A throwaway family.toml, so the test needs no private files.
        (d / "family.toml").write_text(f'data_dir = "{d}"\n', encoding="utf-8")
        old = os.environ.get("FAMILY_CONFIG")
        os.environ["FAMILY_CONFIG"] = str(d / "family.toml")
        self.addCleanup(lambda: os.environ.__setitem__("FAMILY_CONFIG", old) if old is not None
                        else os.environ.pop("FAMILY_CONFIG", None))
        s = tree_store.Store(d / "tree.sqlite")
        s.db.execute("insert into event (owner, tag, date, place, extra, origin) values "
                     "('I1','BIRT','1 JAN 1900','Göhestra, Hagelstorp, Källeryd','[]','import:t')")
        s.db.execute("insert into event (owner, tag, date, place, extra, origin) values "
                     "('I1','RESI','BET 1901 AND 1909','', ?, 'import:t')",
                     ('[{"tag":"ADDR","value":"","sub":[{"tag":"ADR1","value":"Mjölarp","sub":[]},'
                      '{"tag":"CITY","value":"Adelöv","sub":[]}]}]',))
        # a parish the gazetteer lacks, read from the full parish list
        s.db.execute("insert into event (owner, tag, date, place, extra, origin) values "
                     "('I1','DEAT','1 JAN 1960','Byn (Gatan 1) (Burlöv Kommun) (Skåne Län) Skåne "
                     "Sverige (Kyrkobokförd Burlöv)','[]','import:t')")
        s.db.commit()
        import geocode
        import parish_names
        from tests.test_parish_names import names
        saved, parish_names._DEFAULT = parish_names._DEFAULT, names()
        self.addCleanup(lambda: setattr(parish_names, "_DEFAULT", saved))
        geocode.OFFLINE[0] = True
        r = place_store.import_places(s, "test", gaz=tiny_gazetteer())
        links = dict(s.db.execute("select tag, place_id from event").fetchall())
        self.assertEqual(links, {"BIRT": "Källeryd/Göhestra", "RESI": "Adelöv/Mjölarp",
                                 "DEAT": "parish:Burlöv"})
        self.assertEqual(r["places"], 3)
        mapped = {row[2]: row[8:10] for row in place_store.events_with_coords(s)}
        self.assertEqual(mapped["DEAT"], (55.6, 13.1))     # the list's point, via its own place row


if __name__ == "__main__":
    unittest.main()
