"""ftdna_io on FTDNA web-page tables pasted into a spreadsheet: made-up
people, the page's own column names and cell formats. They must come out
like the exports, and join with them by key."""
import tempfile
import unittest
from pathlib import Path

import ftdna_io
import icw_io

ICW = '''Name,Ancestral Surnames,Relationship Range,Shared DNA,Longest Block,X Match,Y Haplog,mt Haplog
Mr. Bo Test,"Andersson, Prov
View Details","3rd Cousin - 5th Cousin
Link on Family Tree",21,21,0,—,—
Anna Prov,—,4th Cousin - Remote  Link on Family Tree,14,9,0,I-M253,H1
'''

SEGS = '''Match Name,Chromosome,Start Location,End Location,Centimorgans(cM),Matching SNPs
Mr. Bo Test,10,"118,952,100","129,027,867",21.31,"5,071"
Anna Prov,X,"51,091,477","69,453,731",6.17,"1,412"
'''

EXPORT = '''Full Name,First Name,Middle Name,Last Name,Match Date,Relationship Range,Shared DNA,Longest Block,Linked Relationship,Ancestral Surnames,Y-DNA Haplogroup,mtDNA Haplogroup,Notes,Matching Bucket,X-Match
Mrs. Bo Test,Mrs.,,Bo Test,4/13/2021,3rd Cousin - 5th Cousin,21,21,,,,,,Paternal,No Match
'''


class Web(unittest.TestCase):
    def setUp(self):
        d = Path(tempfile.mkdtemp())
        for name, text in (("icw.csv", ICW), ("segs.csv", SEGS), ("export.csv", EXPORT)):
            (d / name).write_text(text, encoding="utf-8")
        self.d = d

    def test_match_list(self):
        m = ftdna_io.read_matches(self.d / "icw.csv", "x")
        self.assertEqual(list(m.match_key), ["bo test", "anna prov"])
        self.assertEqual(list(m.shared_cM), [21, 14])
        self.assertEqual(list(m["Relationship Range"]), ["3rd Cousin - 5th Cousin", "4th Cousin - Remote"])
        self.assertEqual(m["Ancestral Surnames"].iloc[0], "Andersson, Prov")
        self.assertIsNone(m["Y-DNA Haplogroup"].iloc[0])

    def test_segments(self):
        s = ftdna_io.read_segments(self.d / "segs.csv", "x")
        self.assertEqual(list(s.match_key), ["bo test", "anna prov"])
        self.assertEqual((s.start.iloc[0], s.end.iloc[0], s.snps.iloc[0]), (118952100, 129027867, 5071))
        self.assertEqual(s.cM.iloc[1], 6.17)

    def test_titles_join_with_export(self):
        e = ftdna_io.read_matches(self.d / "export.csv", "x")
        self.assertEqual(e.match_key.iloc[0], "bo test")

    def test_icw_edges(self):
        nodes, e = icw_io.ftdna_icw_list(self.d / "icw.csv", "x", "Mr. Focal Person")
        self.assertEqual(list(e.a_key.unique()), ["focal person"])
        self.assertEqual(list(e.b_key), ["bo test", "anna prov"])


if __name__ == "__main__":
    unittest.main()
