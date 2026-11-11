"""Archive references in their written forms, and references kept in notes
and addresses rather than source citations (synthetic text, no people)."""
import unittest

import references as R
import volumes as v


def one(text, **kw):
    refs = R.find(text, **kw)
    return {k: x for k, x in refs[0].items() if k not in ("text", "start", "end", "label")} if refs else None


class Readers(unittest.TestCase):
    def test_arkivdigital(self):
        r = one("Hfl boken.Socken AI:9 (1847-1849) Bild 300 / sid 577 "
                "(AID: v11111.b300.s577, NAD: SE/VALA/00999)")
        self.assertEqual((r["format"], r["parish"], r["series"], r["vol"], r["years"], r["page"],
                          r["archive_code"], r["ad_image"]),
                         ("arkivdigital", "Socken", "A I", "9", "1847-1849", "577",
                          "SE/VALA/00999", "300"))
        self.assertNotIn("image_no", r)          # Arkiv Digital's own image number
        r = one("Gift i Byn; Västra Socken (F) C:1 (1689-1735) bild 190 / sid 373")
        self.assertEqual((r["parish"], r["county"], r["series"], r["vol"]),
                         ("Västra Socken", "F", "C", "1"))
        r = one("Sankt Olof och Sankt Per AIIa:3b (1900-1905)")
        self.assertEqual((r["parish"], r["series"], r["vol"]), ("Sankt Olof och Sankt Per", "A II a", "3b"))
        r = one("Socken (D) C:3 (1861-1894) Bild 87 (AID: v22222.b87, NAD: SE/ULA/10999)")
        self.assertEqual((r["ad_image"], r["archive_code"], r.get("page")), ("87", "SE/ULA/10999", None))

    def test_riksarkivet(self):
        r = one("Socknens kyrkoarkiv, Husförhörslängder, SE/VALA/00999/A I/5 (1843-1854), "
                "bildid: C0001234_00138, sida 12")
        self.assertEqual((r["archive"], r["series"], r["vol"], r["page"], r["image_id"], r["image_no"]),
                         ("Socknens kyrkoarkiv", "A I", "5", "12", "C0001234", "138"))
        r = one("Källa: Socknens kyrkoarkiv, F&ouml;delse- och dopb&ouml;cker, SE/VALA/00999/C/11 (1861-1879)")
        self.assertEqual((r["series_name"], r["series"], r["vol"]), ("Födelse- och dopböcker", "C", "11"))

    def test_code_led(self):
        refs = R.find("Gården: SE/GLA/10999/A I/5 (1843-1854), bildid: C0001234_00138\n\n"
                      "Gården: SE/GLA/10999/A I/6 (1854-1860), bildid: C0001235_00098")
        self.assertEqual([(r["farm"], r["vol"], r["image_no"]) for r in refs],
                         [("Gården", "5", "138"), ("Gården", "6", "98")])
        # an image link just after a volume reference is the same reference
        r = one("Se SE/VALA/00999/A I/4 (1825-1834), sida 170 "
                "https://sok.riksarkivet.se/bildvisning/C0001234_00093")
        self.assertEqual((r["vol"], r["page"], r["image_id"], r["image_no"]), ("4", "170", "C0001234", "93"))
        self.assertEqual(R.find("SE/VALA/00999"), [])            # an archive, not a volume

    def test_myheritage(self):
        r = one("Bok: LandSwedenBokStaden_S:t_Olai_AIIaa84-1397, 1935 - 1940ProvinsÖstergötland"
                "PlatsGårdenLänÖstergötland", mh=True)
        self.assertEqual((r["parish"], r["series"], r["vol"], r["vol_suffix"], r["years"], r["farm"]),
                         ("Staden S:t Olai", "A II aa", "84", "1397", "1935-1940", "Gården"))
        r = one("Bok: LandSwedenBokSocken AI86, 1869ProvinsUpplandPlatsGårdenLänStockholmsSida1Församling")
        self.assertEqual((r["series"], r["vol"], r["years"], r["page"]), ("A I", "86", "1869", "1"))

    def test_series(self):
        for raw, want in {"AIIa": "A II a", "A II a": "A II a", "EI": "E I", "C": "C",
                          "AIIaa": "A II aa", "CII": "C II"}.items():
            self.assertEqual(R.series(raw), want, raw)

    def test_not_a_reference(self):
        for text in ("Gården, Socken, Jönköpings län", "Bor här fram till 1830.",
                     "till Socken Församling, Staden", "AI:9"):
            self.assertEqual(R.find(text), [], text)


def node(tag, value="", *sub, xref=None):
    return dict(tag=tag, xref=xref, value=value, sub=list(sub))


class Noted(unittest.TestCase):
    AD = "Socken AI:7 (1821-1831) Bild 261 / sid 509 (AID: v11111.b261.s509, NAD: SE/VALA/00999)"

    def test_address_note_and_event(self):
        records = [node("INDI", "", node("RESI", "", node("DATE", "1823"),
                                         node("ADDR", "", node("ADR1", "1823-1827. " + self.AD),
                                              node("CITY", "Socken"))),
                        node("BIRT", "", node("PLAC", "Byn, Socken"),
                             node("NOTE", "Socken (F) C:2 (1735-1789) bild 52 / sid 97")),
                        node("EVEN", "Socken (F) AI:1 (1793-1793) bild 40 / sid 61",
                             node("TYPE", "Settlement")), xref="@I1@")]
        rows = v.extract(records)
        got = sorted((r["event"], r["ref_in"], r["series"], r["vol"], r["page"], r["event_place"])
                     for r in rows)
        self.assertEqual(got, [
            ("Settlement", "note:EVEN", "A I", "1", "61", ""),
            ("birth", "note:NOTE", "C", "2", "97", "Byn, Socken"),
            ("residence", "note:ADDR", "A I", "7", "509", "Socken"),   # the reference left the place
        ])

    def test_note_repeating_a_citation_is_dropped(self):
        cite = node("SOUR", "@S1@", node("DATA", "", node("TEXT", self.AD)))
        records = [node("SOUR", "", node("TITL", "Arkiv Digital"), xref="@S1@"),
                   node("INDI", "", node("BIRT", "", node("PLAC", "Socken"), cite,
                                         node("NOTE", self.AD)), xref="@I1@")]
        rows = v.extract(records)
        self.assertEqual([(r["ref_in"], r["tier"], r["ref_format"]) for r in rows],
                         [("citation", "ra-full", "arkivdigital")])

    def test_arkivdigital_parish_not_degenitived(self):
        rows = [dict(tier="ra-full", parish="Vårdnäs", ref_format="arkivdigital"),
                dict(tier="ra-full", parish="Byarps", ref_format="riksarkivet")]
        v.normalise(rows)
        self.assertEqual([r["parish"] for r in rows], ["Vårdnäs", "Byarp"])

    def test_parish_from_code(self):
        rows = [dict(tier="ra-full", parish="Socken", archive_code="SE/VALA/00999"),
                dict(tier="ra-full", parish="", archive_code="SE/VALA/00999", series="A I", vol="5")]
        v.normalise(rows)
        self.assertEqual(rows[1]["parish"], "Socken")


if __name__ == "__main__":
    unittest.main()
