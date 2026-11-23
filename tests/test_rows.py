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
