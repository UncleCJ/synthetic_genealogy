"""The genome lens on synthetic copy-model tables."""
import json
import shutil
import subprocess
import unittest

import pandas as pd

import genomeview as gv
from test_familyview import store

BLOCKS = pd.DataFrame([
    # chrom, side, start_cm, end_cm, start, end, lineage, posterior, subject, level, model
    ["1", "F", 0.0, 60.0, 1e5, 5e7, "FF", 0.95, "a", 2, "siblings"],
    ["1", "F", 60.5, 100.0, 5.1e7, 9e7, "FM", 0.6, "a", 2, "siblings"],
    ["1", "M", 0.0, 100.0, 1e5, 9e7, "MF", 0.99, "a", 2, "siblings"],
    ["2", "F", 0.0, 80.0, 1e5, 7e7, "FFM", 0.5, "a", 3, "siblings"],
], columns="chrom side start_cm end_cm start end lineage posterior subject level model".split())
VERDICTS = pd.DataFrame([
    ["tree:x: y:a:1:20000000:FF", "a", "1", "FF", "FF", 0.97, 0.5, "agrees", "siblings", "tree", 12.0],
    ["anchor:z:a:1:60000000:FFM", "a", "1", "FF", "FFM", 0.1, 0.25, "dissents", "siblings", "documented", 8.5],
], columns="claim_id subject chrom lineage code support prior verdict model source_kind cM".split())


class GenomeLens(unittest.TestCase):
    def test_claim_id_keeps_colons_in_names(self):
        self.assertEqual(gv._claim("tree:x: y:a:1:20000000:FF"), ("tree", "x: y", 20000000))

    def test_collect(self):
        anc = gv.ancestors(store(), "me")
        self.assertEqual(anc["F"][0], "f")
        self.assertEqual(anc["FF"][0], "ff")
        self.assertEqual(anc["F"][2], 1950)
        d = gv.collect(BLOCKS, VERDICTS, anc, {"a": "Donor A"})
        self.assertEqual(sorted(d["blocks"]["a"]["siblings"]), ["2", "3"])
        self.assertEqual(len(d["blocks"]["a"]["siblings"]["2"]), 3)
        self.assertEqual(d["lengths"], {"1": 100.0, "2": 80.0})
        self.assertEqual(d["names"], {"a": "Donor A"})
        self.assertEqual([v[3] for v in d["verdicts"]], ["x: y", "z"])
        self.assertIn("FFM", d["col"])
        self.assertIsNone(gv.collect(BLOCKS, None, anc)["verdicts"] or None)

    def test_fit_keeps_proband_and_full_siblings(self):
        par = {"me": ("f", "m"), "sib": ("f", "m"), "half": ("f", "x"), "m": ("mf", "mm")}
        why = gv.fit(par, "me", {"me": "me", "sib": "sib", "half": "half", "gm": "mm", "none": None})
        self.assertIsNone(why["me"])
        self.assertIsNone(why["sib"])
        self.assertIn("half-sibling", why["half"])
        self.assertIn("MM", why["gm"])
        self.assertIn("not placed", why["none"])

    def test_match_list(self):
        segs = pd.DataFrame([
            ["FTDNA", "a", "k1", "Anna Ek", "1", 1e6, 2e7, 19.0, "F", "", "FF"],
            ["FTDNA", "a", "k1", "Anna Ek", "2", 5e6, 9e6, 4.0, None, "below 10 cM", None],
            ["FTDNA", "b", "k1", "Anna Ek", "1", 1e6, 2e7, 19.0, None, "no mother export", None],
            ["MyHeritage", "a", "D-1", "Bo Berg", "3", 1e6, 3e6, 2.0, None, "", None],
            # a selection repeats a match the full export has: folded away
            ["MyHeritage (selection)", "a", "name:bo berg", "Bo Berg", "3", 1e6, 3e6, 2.0, None, "", None],
        ], columns="platform subject match_key match chrom start end cM parent parent_reason grandparent".split())
        placed = pd.DataFrame([["FTDNA", "a", "k1", "Anna Ek", 25.5, 19.0, "FF", 1.0, "Paternal"]],
                              columns="platform subject match_key match shared_cM longest_cM placement agreement".split()
                              + ["Matching Bucket"])
        # the copy model's reading: one sided segment, one with both readings
        cm_segs = pd.DataFrame([["a", "FTDNA", "k1", "1", 1e6, 2e7, "FM", 0.97, "", ""],
                                ["a", "FTDNA", "k1", "2", 5e6, 9e6, "", None, "FF", ""]],
                               columns="subject platform match_key chrom start end cm_grandparent cm_p "
                                       "cm_if_paternal cm_if_maternal".split())
        cm_matches = pd.DataFrame([["a", "FTDNA", "k1", "FM", 1.0]],
                                  columns="subject platform match_key placement agreement".split())
        ml = gv.match_list(segs, placed, links={("FTDNA", "k1"): ("confirmed", ["@I1@"])},
                           relate=lambda d, i: ("1C", "FF") if d == "a" else ("", ""),
                           people={"@I1@": ["MH:I1", "Anna Ek", 1950, None]},
                           cm_segs=cm_segs, cm_matches=cm_matches)
        self.assertEqual(ml["P"], ["FTDNA", "MyHeritage"])
        self.assertEqual([m[2] for m in ml["M"]], ["Anna Ek", "Bo Berg"])
        a = {ml["M"][r[0]][2]: r for r in ml["S"]["a"]}
        self.assertEqual(a["Anna Ek"][1:5], [25.5, 19.0, 2, "FF"])       # the vendor's total, not the sum
        self.assertEqual(a["Anna Ek"][9:14], [["b"], "1C", "FF", "FM", 1.0])  # b matches them too; the painting says FM
        self.assertEqual(a["Bo Berg"][1:4], [2.0, 2.0, 1])                # no placed row: from the segments
        self.assertEqual(ml["S"]["b"][0][10:], ["", "", "", None, None])
        self.assertEqual(ml["tp"], {"@I1@": ["MH:I1", "Anna Ek", 1950, None]})
        self.assertEqual(len(ml["G"]["a"]), 3)
        g = ml["G"]["a"][0]
        self.assertEqual(g[1:4], ["1", 1.0, 20.0])                        # flat map: 1 cM per Mb
        self.assertEqual(ml["R"][ml["G"]["a"][1][9]], "below 10 cM")
        self.assertEqual(g[10:], ["FM", 0.97, "", ""])
        self.assertEqual(ml["G"]["a"][1][10:], ["", None, "FF", ""])       # no side: both readings
        self.assertEqual(ml["G"]["a"][2][10:], ["", None, "", ""])         # the model has not read it
        self.assertEqual(ml["ends"]["1"], [20.0, 20])

    def test_match_list_entries(self):
        """A match may have a list entry, segments, or both; the entry's
        values win over the placed table's, the segments fill the rest."""
        segs = pd.DataFrame([["FTDNA", "a", "k1", "Anna Ek", "1", 1e6, 2e7, 19.0, "F", "", "FF"],
                             ["FTDNA", "a", "k3", "Cai Dal", "2", 1e6, 9e6, 8.0, None, "", None]],
                            columns="platform subject match_key match chrom start end cM parent parent_reason grandparent".split())
        entries = pd.DataFrame([["a", "FTDNA", "k1", "Anna Ek", 30.0, "Paternal", "ek, berg", None],
                                ["a", "FTDNA", "k2", "Bo Berg", 12.0, None, None, pd.Timestamp("2024-02-03")]],
                               columns="subject platform match_key match shared_cM bucket ancestral_surnames match_date".split())
        ml = gv.match_list(segs, entries=entries)
        rows = {ml["M"][r[0]][2]: r for r in ml["S"]["a"]}
        self.assertEqual(rows["Anna Ek"][1], 30.0)                             # the list's total
        self.assertEqual(rows["Anna Ek"][6], "Paternal")
        self.assertEqual(ml["M"][rows["Anna Ek"][0]][3], "ek, berg")           # surnames once, per match
        self.assertEqual(rows["Anna Ek"][14], {"shared_cM": 30.0, "bucket": "Paternal"})
        self.assertEqual(rows["Bo Berg"][1:4], [12.0, None, 0])               # a list entry, no segments
        self.assertEqual(rows["Bo Berg"][14]["match_date"], "2024-02-03")
        self.assertEqual(rows["Cai Dal"][1:4], [8.0, 8.0, 1])                 # segments, no entry
        self.assertIsNone(rows["Cai Dal"][14])

    def test_match_list_with_entries_only(self):
        segs = pd.DataFrame(columns="platform subject match_key match chrom start end cM parent parent_reason grandparent".split())
        entries = pd.DataFrame([["a", "FTDNA", "k2", "Bo Berg", 12.0]], columns="subject platform match_key match shared_cM".split())
        ml = gv.match_list(segs, entries=entries)
        self.assertEqual(len(ml["S"]["a"]), 1)
        self.assertEqual(ml["G"], {})

    @unittest.skipUnless(shutil.which("node"), "node not installed")
    def test_page_script_parses(self):
        page = gv.HTML
        js = page[page.index('id="view-js">') + 13:page.index("</script>__DATA__")]
        r = subprocess.run(["node", "--check", "-"], input="const DATA={};" + js, text=True, capture_output=True)
        self.assertEqual(r.returncode, 0, r.stderr)


if __name__ == "__main__":
    unittest.main()
