"""Match-list entries: the MyHeritage list reader (a generated xlsx) and
the FTDNA mapping onto the same fields (kits.ENTRY)."""
import tempfile
import unittest
import zipfile
from pathlib import Path

import pandas as pd

import ftdna_io
import kits
import myheritage_io as mh

DONOR = "D-" + "A" * 8 + "-" + "B" * 4 + "-" + "C" * 4 + "-" + "D" * 4 + "-" + "E" * 12
MATCH = "D-" + "1" * 8 + "-" + "2" * 4 + "-" + "3" * 4 + "-" + "4" * 4 + "-" + "5" * 12


def xlsx(path, rows):
    """A minimal xlsx: strings shared, numbers as values."""
    ss, sheet = [], []
    for i, row in enumerate(rows, 1):
        cells = []
        for j, v in enumerate(row):
            ref = chr(65 + j) + str(i)
            if isinstance(v, str):
                ss.append(v)
                cells.append(f'<c r="{ref}" t="s"><v>{len(ss) - 1}</v></c>')
            else:
                cells.append(f'<c r="{ref}"><v>{v}</v></c>')
        sheet.append(f'<row r="{i}">{"".join(cells)}</row>')
    ns = 'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("xl/sharedStrings.xml", f'<sst {ns}>' + "".join(f"<si><t>{s}</t></si>" for s in ss) + "</sst>")
        z.writestr("xl/worksheets/sheet1.xml", f'<worksheet {ns}><sheetData>{"".join(sheet)}</sheetData></worksheet>')


class MatchEntries(unittest.TestCase):
    def test_myheritage_list(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "list.xlsx"
            xlsx(p, [["Kit", "DNA-matchnings-ID", "Full Name", "Ålder", "Shared cM", "Andel gemensamt DNA",
                      "Antal gemensamma segment", "Har släktträd", "Antal individer i trädet", "Visa släktträd", "Status"],
                     ["Donor", f"{DONOR}-{MATCH}", "Anna Ek", "60-årsåldern", "1 031,5", "1,4", 12.0, "Ja", 65.0,
                      "https://example.org/tree", ""],
                     ["Donor", "", "No Id", "", "1", "", "", "", "", "", ""]])
            e = mh.read_match_list(p, "a")
        self.assertEqual(len(e), 1)                       # no pair ID: dropped
        r = e.iloc[0]
        self.assertEqual(r.match_key, MATCH)
        self.assertEqual((r.match, r.age, r.shared_cM, r.shared_pct, r.n_segments), ("Anna Ek", "60-årsåldern", 1031.5, 1.4, 12))
        self.assertTrue(r.has_tree)
        self.assertEqual((r.tree_size, r.tree_url, r.source), (65, "https://example.org/tree", "list.xlsx"))

    def test_not_a_match_list(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "x.xlsx"
            xlsx(p, [["Name", "cM"], ["Anna", 1.0]])
            with self.assertRaises(ValueError):
                mh.read_match_list(p, "a")

    def test_ftdna_entries(self):
        m = pd.DataFrame(dict(subject=["a"], match_key=["anna ek"], **{"Full Name": ["Anna Ek"]},
                              match_date=[pd.Timestamp("2024-01-01")], shared_cM=[30.0], longest_cM=[12.0],
                              x_cM=[None], source=["f.csv"], Email=["a@example.org"],
                              **{"Matching Bucket": ["Paternal"], "Ancestral Surnames": ["Ek"]}))
        e = ftdna_io.entries(m)
        self.assertEqual(e.iloc[0].match, "Anna Ek")
        self.assertEqual((e.iloc[0].email, e.iloc[0].bucket, e.iloc[0].ancestral_surnames), ("a@example.org", "Paternal", "Ek"))
        fields = {f for f, *_ in kits.ENTRY}
        self.assertTrue(set(e.columns) - {"subject", "match_key", "match", "source"} <= fields)

    def test_entry_fields_cover_the_readers(self):
        fields = {f for f, *_ in kits.ENTRY}
        self.assertEqual(set(mh.LIST_COLS.values()) - fields, {"pair_id", "match"})
        self.assertEqual(set(ftdna_io.ENTRY_COLS.values()) - fields, {"match"})


if __name__ == "__main__":
    unittest.main()
