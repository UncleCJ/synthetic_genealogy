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

    @unittest.skipUnless(shutil.which("node"), "node not installed")
    def test_page_script_parses(self):
        page = gv.HTML
        js = page[page.index('id="view-js">') + 13:page.index("</script>__DATA__")]
        r = subprocess.run(["node", "--check", "-"], input="const DATA={};" + js, text=True, capture_output=True)
        self.assertEqual(r.returncode, 0, r.stderr)


if __name__ == "__main__":
    unittest.main()
