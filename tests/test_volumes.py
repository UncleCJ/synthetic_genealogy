"""MyHeritage household-examination labels in their written variants, and
a town between farm and parish in a place (synthetic text, no people)."""
import unittest

import volumes as v


def bok(text):
    m = v.MH_BOK.search(v._squash(text))
    return m and (m["town"], m["parish"].replace("_", " ").strip(), m["series"], m["vol"])


class Labels(unittest.TestCase):
    def test_variants(self):
        cases = {
            "Bok: LandSwedenBokAnderstorp AIIa2, 1911 - 1921 ProvinsSmåland":
                (None, "Anderstorp", "AIIa", "2"),
            "Bok: Land:SwedenBok:Källeryd_AIIa3-296, 1921 - 1941 Provins:":
                (None, "Källeryd", "AIIa", "3"),
            "BokStora Åby AI 20, 1891 - 1895": (None, "Stora Åby", "AI ", "20"),
            "Bok: Land Sweden, Bok Anderstorp AI14, 1891 - 1899": (None, "Anderstorp", "AI", "14"),
            "Bok: \tLandSwedenBokSigtuna, Sankt Olof och Sankt Per AI16, 1876 - 1880\tProvins":
                ("Sigtuna", "Sankt Olof och Sankt Per", "AI", "16"),
            "Bok: LandSwedenBokRisinge,_Finspångs_kyrkobokföringsdistrikt_AIIa4-2229, 1926 - 1939":
                ("Risinge", "Finspångs kyrkobokföringsdistrikt", "AIIa", "4"),
        }
        for text, want in cases.items():
            self.assertEqual(bok(text), want, text)

    def test_town_skipped_in_place(self):
        rows = [dict(tier="mh-record", parish="Sankt Olof och Sankt Per", town="Sigtuna"),
                dict(tier="plac-only", event_place="Gården, Sigtuna, Sankt Olof och Sankt Per, "
                                                   "Stockholms, Uppland, Sweden"),
                dict(tier="plac-only", event_place="Gården, Byn, Sankt Olof och Sankt Per")]
        v.normalise(rows)
        self.assertEqual((rows[1]["parish"], rows[1]["farm"]), ("Sankt Olof och Sankt Per", "Gården"))
        self.assertEqual(rows[2]["farm"], "Byn")        # no town: the village, as before

    def test_moves_and_explicit_parishes(self):
        rows = [dict(tier="mh-record", parish="Socknen"),
                dict(tier="plac-only", event_place="fr. Aronsdal, Byn t. Gården, Socknen"),
                dict(tier="plac-only", event_place="Kyrkeby, Annan förs., Socknen, Bohuslän")]
        v.normalise(rows)
        self.assertEqual((rows[1]["parish"], rows[1]["farm"]), ("Socknen", "Gården"))
        self.assertEqual((rows[2]["parish"], rows[2]["farm"]), ("Annan", "Kyrkeby"))


class Gedcom(unittest.TestCase):
    def test_bare_line_breaks_continue_the_value(self):
        """MyHeritage's raw export breaks a label with a bare newline
        before the CONC that continues it."""
        import tempfile
        from pathlib import Path
        import gedcom_io
        text = ("0 @I1@ INDI\n1 SOUR @S1@\n2 DATA\n3 TEXT Hemvist: Mellan 1863 och 1879\n"
                "4 CONC <br>Bok: \n\tLandSwedenBokSock\n4 CONC nen AI7, 1863 - 1879\n"
                "\tProvinsVästergötlandPlatsGården\n\tLänÄlvsborgsSida78\n"
                "1 NAME Test /Person/\n0 TRLR\n")
        p = Path(tempfile.mkdtemp()) / "t.ged"
        p.write_text(text, encoding="utf-8")
        rec = gedcom_io.parse(p)[0]
        t = v._val(rec["sub"][0], "DATA", "TEXT")
        self.assertEqual(bok(t), (None, "Socknen", "AI", "7"))
        self.assertIn("Sida78", v._squash(t))
        self.assertEqual([s["tag"] for s in rec["sub"]], ["SOUR", "NAME"])


if __name__ == "__main__":
    unittest.main()
