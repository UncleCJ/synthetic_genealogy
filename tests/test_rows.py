"""rows.py (experiments/register_ocr): rows and remarks from line files, on made-up lines."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "experiments/register_ocr"))
import rows  # noqa: E402


def L(x, y, t, w=0.15, h=0.02, alt=""):
    return (x, y, w, h, t, alt)


class TestRows(unittest.TestCase):
    def test_words_fuzzy(self):
        self.assertEqual(rows.words("vinnesjuk 11 2 11/40"), ["sinnessjuk"])   # TrOCR's misreading
        self.assertEqual(rows.words("Fattighjon"), ["fattighjon", "fattig"])
        self.assertEqual(rows.words("Anders Persson 1831"), [])

    def test_columns_from_headers(self):
        lines = [L(0.05, 0.10, "Personens för- och tillnamn"), L(0.30, 0.10, "Födelse"),
                 L(0.60, 0.10, "Lyte", w=0.03), L(0.80, 0.10, "Anmärkningar")]
        heads = [k for k, *_ in rows.page_heads(lines)]
        self.assertEqual(heads, ["name", "born", "lyte", "notes"])

    def test_rows_and_remarks(self):
        cols = [("name", 0.12), ("born", 0.37), ("lyte", 0.615), ("notes", 0.875)]
        lines = [
            L(0.05, 0.30, "Anna Svensdotter"), L(0.35, 0.30, "1840 3/5", w=0.05),
            L(0.05, 0.34, "Per Persson"), L(0.35, 0.34, "1838 1/2", w=0.05),
            L(0.80, 0.33, "dömd för stöld"),                  # a note starting above the name line
            L(0.60, 0.34, "blind", w=0.04),
            L(0.05, 0.38, "Per Persson"), L(0.35, 0.38, "1838 1/2", w=0.05),   # back again, a second row
        ]
        body, names = rows.name_lines(lines, cols, 0.12)
        per = {l[1]: rows.line_score(body, l, "Per Persson", (1838, 2, 1)) for l in names}
        anna = {l[1]: rows.line_score(body, l, "Anna Svensdotter", (1840, 5, 3)) for l in names}
        self.assertGreater(per[0.34], 0.9)
        self.assertGreater(per[0.38], 0.9)               # both of Per's rows count
        self.assertIsNone(per[0.30])                     # no given name of his on Anna's line
        self.assertGreater(anna[0.30], per[0.34] - 0.5)
        row = rows.row_of(body, names, [l for l in names if l[1] == 0.34][0])
        self.assertIn("dömd för stöld", [l[4] for l in row])
        self.assertIn("blind", [l[4] for l in row])
        self.assertNotIn("Anna Svensdotter", [l[4] for l in row])
        r = dict(mh_id="MH:X", volume="V A I/1", years="1836-1840", page="1", label="Per Persson", born="")
        nl = [l for l in names if l[1] == 0.34][0]
        res = rows.read_row(r, 1, 1.5, nl, "Per Persson", row, cols, "/nonexistent.vision.tsv", set(), names)
        got = {(m["column"], m["flag"]) for m in res["remarks"]}
        self.assertEqual(got, {("notes", "dömd stöld"), ("lyte", "blind")})

    def test_move_abroad_and_header(self):
        self.assertEqual(rows.move("N. Amerika 91 11/8", (1886, 1895), set())["verdict"], "abroad")
        self.assertEqual(rows.move("boken öfver obefantl.", (1886, 1895), set())["verdict"], "empty")


if __name__ == "__main__":
    unittest.main()


class TestHousehold(unittest.TestCase):
    def test_titles(self):
        self.assertEqual(rows.title("S. Johan Oskar"), "son")
        self.assertEqual(rows.title("Pig. Anna Greta"), "piga")
        self.assertEqual(rows.title("æ. d. Gulli Elisabeth"), "daughter")     # a stray token skipped
        self.assertEqual(rows.title("Enk. Greta Lisa"), "widow")
        self.assertIsNone(rows.title("Anders Persson"))

    def test_household(self):
        n = lambda y, t, x=0.08: L(x, y, t)
        names = [n(0.20, "Anders Persson"), n(0.23, "H. Maja Jonsdotter"), n(0.26, "S. Johan"),
                 n(0.29, "D. Stina"), n(0.32, "D:o Lisa"), n(0.36, "Dr. Per Nilsson"), n(0.39, "Enk. Brita Olsdotter"),
                 n(0.60, "Nils Svensson"), n(0.63, "S. Carl")]
        h = rows.household(names, names[5])
        self.assertEqual((h["role"], h["size"], h["servants"]), ("dräng", 7, 1))
        self.assertEqual(h["elders"], [("widow", "Enk. Brita Olsdotter")])
        self.assertEqual(rows.household(names, names[4])["role"], "daughter")      # d:o after a daughter
        self.assertEqual(rows.household(names, names[8])["size"], 2)               # the gap ends the first
        # a widow followed by her children heads the household
        w = [n(0.20, "Enk. Kajsa Persdotter"), n(0.23, "S. Olof"), n(0.26, "D. Anna")]
        self.assertEqual(rows.household(w, w[0])["role"], "head, widow")
        self.assertEqual(rows.household(w, w[1])["elders"], [])


class TestCitationCheck(unittest.TestCase):
    def test_farm_read(self):
        lines = [L(0.05, 0.10, "Stret."), L(0.05, 0.30, "Anna")]
        self.assertEqual(rows.farm_read(lines, "Stret"), "Stret.")
        self.assertEqual(rows.farm_read([L(0.05, 0.1, "1811 2/2 Källerrö")], "Källerö T. Stenshult"), "1811 2/2 Källerrö")
        self.assertEqual(rows.farm_read(lines, "Backen"), "")
        self.assertEqual(rows.farm_read(lines, ""), "")

    def test_verdicts(self):
        r = dict(volume="Socken A I/5", page="12", farm="Byn")
        checks = {("p1", "V", "12"): dict(r=r, images=[3], guess=False, why=""),
                  ("p2", "V", "12"): dict(r=r, images=[3], guess=False, why=""),
                  ("p3", "V", "40"): dict(r=dict(r, page="40"), images=[20, 21, 22], guess=True, why=""),
                  ("p4", "V", "99"): dict(r=dict(r, page="99"), images=[], guess=True, why="past the last label"),
                  ("p5", "V", "13"): dict(r=r, images=[4], guess=False, why="")}
        seen = {("p1", "V", 3): (1.2, "Anna", ""), ("p2", "V", 3): (0.6, "Per", "Byn"),
                ("p3", "V", 20): (0.5, "x", ""), ("p3", "V", 21): (1.1, "Olof", "")}
        got = {c["mh_id"]: (c["verdict"], c["image"]) for c in rows.verdicts(checks, seen)}
        self.assertEqual(got, {"p1": ("row found", 3), "p2": ("farm read", 3),
                               "p3": ("page not labelled, guessed 20-22: row found", 21),
                               "p4": ("past the last label", ""), "p5": ("no text", "")})
