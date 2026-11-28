"""MyHeritage household-examination labels in their written variants, and
a town between farm and parish in a place (synthetic text, no people)."""
import unittest

from sg.records import homes
from sg.records import volumes as v


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

    def test_rightmost_parish_wins(self):
        """A farm, village or county that shares a parish's name does not
        take the parish's place."""
        rows = [dict(tier="mh-record", parish=p) for p in ("Ekeby", "Storsocken", "Älvsborg", "Kalmar")]
        places = ["Ekeby, Storsocken, Södermanlands, Södermanland, Sweden",   # farm named like a parish
                  "Lillby, Storsocken, Älvsborgs, Västergötland, Sweden",      # county named like one
                  "Ekeby, Ekeby, Södermanlands län",                           # church village
                  "Kalmar, Sweden",                                            # parish named like its county
                  "Lillby, Storsocken, Älvsborg, Sverige",                     # county without its s
                  "Gården, Storsocken, Sweden, Lillby, Ekeby, Sverige",        # two places run together
                  "Hartford, Connecticut, United States, Storsocken, Sverige"] # the first has no parish
        rows += [dict(tier="plac-only", event_place=p) for p in places]
        v.normalise(rows)
        got = [(r["parish"], r["farm"]) for r in rows[4:]]
        self.assertEqual(got, [("Storsocken", "Ekeby"), ("Storsocken", "Lillby"),
                               ("Ekeby", "Ekeby"), ("Kalmar", ""),
                               ("Storsocken", "Lillby"), ("Storsocken", "Gården"),
                               ("Storsocken", "United States")])


class Gedcom(unittest.TestCase):
    def test_bare_line_breaks_continue_the_value(self):
        """MyHeritage's raw export breaks a label with a bare newline
        before the CONC that continues it."""
        import tempfile
        from pathlib import Path
        from sg.readers import gedcom_io
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


class Homes(unittest.TestCase):
    """The parental household at birth, on made-up rows and inventory."""

    class RA:
        inv = {"SE/X/1": {
            "SE/X/1/A I/1": dict(code="SE/X/1/A I/1", years="1800–1804", viewer="v1", images="i1"),
            "SE/X/1/A I/2": dict(code="SE/X/1/A I/2", years="1805–1809", viewer="v2", images="i2"),
            "SE/X/1/C/1": dict(code="SE/X/1/C/1", years="1790–1820", viewer="c1", images="c1"),
        }}

        def inventory(self, a, offline=True):
            return self.inv.get(a)

        def archive_codes(self, p, offline=True):
            return []

    def rows(self):
        base = dict(parish="Exempelby", archive_code="SE/X/1", tier="mh-record", series="A I")
        return [
            dict(person="c", label="Child", kin="ancestor", event="birth", event_date="3 MAR 1802",
                 event_place="Exempelby", parish="Exempelby", archive_code="SE/X/1"),
            dict(base, person="f", label="Father", kin="ancestor", event="person", volume="Exempelby A I/2",
                 ra_code="SE/X/1/A I/2", years="1805-1809", page="12", farm="Bytorp"),
            dict(base, person="n", label="Neighbour", kin="unlinked", event="person", volume="Exempelby A I/1",
                 ra_code="SE/X/1/A I/1", years="1800-1804", page="9", farm="Bytorp"),
        ]

    def test_page_from_others_on_the_farm(self):
        out = homes.homes(self.rows(), {"c": ["f"]}, self.RA(), people=["c"])
        o = out[0]
        self.assertFalse(o["found"])
        self.assertEqual([b["code"] for b in o["births"]], ["SE/X/1/C/1"])
        self.assertEqual([x["code"] for x in o["volumes"]], ["SE/X/1/A I/1"])
        look = o["volumes"][0]["looks"][0]
        self.assertEqual((look["farm"], look["pages"]), ("Bytorp", ["9"]))

    def test_found_when_a_parent_covers_the_year(self):
        rows = self.rows()
        rows[0]["event_date"] = "1806"
        self.assertEqual(homes.homes(rows, {"c": ["f"]}, self.RA(), people=["c"])[0]["found"],
                         ["Exempelby A I/2 p.12"])

    def test_birth_column_stands_in(self):
        rows = self.rows()[1:]
        rows.append(dict(rows[0], person="c", label="Child", born="1 jan 1801 - Bytorp"))
        out = homes.homes(rows, {"c": ["f"]}, self.RA(), people=["c"],
                      parish_of=lambda w, here: ("Exempelby", "Exempelby/Bytorp"))
        self.assertEqual((out[0]["year"], out[0]["parish"], out[0]["farm"]), (1801, "Exempelby", "Bytorp"))

    def test_born_read_from_record_text(self):
        self.assertEqual(v.FODELSE.search("Namn<br>Födelse: 5 okt 1801 - Exempelby sn<br>Hemvist")[1],
                         "5 okt 1801 - Exempelby sn")

    def test_page_guess(self):
        from sg.records import riksarkivet
        page_guess = riksarkivet.page_guess
        lab = {10: 5, 11: 6, 20: 15}                        # one page an image, a gap from 12 to 19
        self.assertEqual(page_guess(lab, 15, 30), [9, 10, 11])
        self.assertEqual(page_guess(lab, 25, 30), [19, 20, 21])      # past the last label: extrapolated
        self.assertEqual(page_guess(lab, 60, 30), [])                # past the volume's end
        self.assertEqual(page_guess({10: 5, 12: 6}, 15, 30), [6, 7, 8])  # spreads: half an image a page
        spreads = riksarkivet.page_images(["Bild 1 / Sida 10", "Bild 2 / Sida 12"])   # 11 filled in
        self.assertEqual(page_guess(spreads, 17, 30), [3, 4, 5])     # 16-17 on image 4
        self.assertEqual(page_guess({10: 5}, 15, 30), [])            # one label: no line
        self.assertEqual(page_guess(lab, 10, 30), [])                # labelled: no guess

    def test_side_page(self):
        """One label an image (each opening numbered once): a cited page past
        the last label is MyHeritage counting sides, read at half."""
        from sg.records import riksarkivet as ra
        folio = {p: p + 10 for p in range(1, 201)}          # p. 1-200 on images 11-210
        self.assertEqual(ra.side_page(folio, 257), 128)
        self.assertIsNone(ra.side_page(folio, 150))           # labelled range: as cited
        self.assertEqual(ra.cited_guess(folio, 257, 220), list(range(130, 143)))
        part = {p: p + 10 for p in range(1, 101)}            # labels stop at p. 100 of 220 images
        self.assertEqual(ra.cited_guess(part, 250, 220), list(range(127, 140)))
        pages = {p: (p + 1) // 2 + 5 for p in range(1, 401)}  # two pages an image: no halving
        self.assertIsNone(ra.side_page(pages, 450))

    def test_same_citations(self):
        from sg.records import riksarkivet
        pages = {"X1": riksarkivet.page_images(["Bild 1", "Bild 2 / Sida 10", "Bild 3 / Sida 12"])}
        self.assertEqual(pages["X1"], {10: 2, 11: 2, 12: 3})          # 11: a spread's right page
        row = dict(person="@I1@", volume="Socken A I/5", ra_images="X1", image_id="", image_no="",
                   event="person")
        rows = [dict(row, tier="mh-record", page="11"), dict(row, tier="ra-full", page="10"),
                dict(row, tier="mh-record", page="12"), dict(row, tier="mh-record", page="12")]
        v.mark_same_citations(rows, pages)
        self.assertEqual([r.get("same_as", "") for r in rows],
                         ["ra-full Socken A I/5 p. 10 bild 2 (person)", "",
                          "", "mh-record Socken A I/5 p. 12 bild 3 (person)"])
