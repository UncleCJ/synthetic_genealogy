"""gedcom_io on a made-up tree: unlinked people are left out by default."""
import tempfile
import unittest
from pathlib import Path

import gedcom_io

# Main tree: I1 child of I2 + I3, I1 married to I4 (married in), I5 adopted
# by I2 + I3. Island (a hypothesis): I6 child of I7, plus I8 with no family.
TREE = """0 HEAD
0 @I1@ INDI
1 NAME Anna /Test/
1 RIN MH:I1
1 FAMC @F1@
1 FAMS @F2@
0 @I2@ INDI
1 NAME Bo /Test/
1 FAMS @F1@
0 @I3@ INDI
1 NAME Cia /Prov/
1 SEX F
1 FAMS @F1@
0 @I4@ INDI
1 NAME Dag /Gift/
1 FAMS @F2@
0 @I5@ INDI
1 NAME Eva /Adopt/
1 FAMC @F1@
2 PEDI adopted
0 @I6@ INDI
1 NAME Fia /Ö/
1 FAMC @F3@
0 @I7@ INDI
1 NAME Gun /Ö/
1 FAMS @F3@
0 @I8@ INDI
1 NAME Hans /Ensam/
0 @F1@ FAM
1 HUSB @I2@
1 WIFE @I3@
1 CHIL @I1@
1 CHIL @I5@
0 @F2@ FAM
1 HUSB @I4@
1 WIFE @I1@
0 @F3@ FAM
1 WIFE @I7@
1 CHIL @I6@
0 @S1@ SOUR
1 TITL A source
0 TRLR
"""


class Unlinked(unittest.TestCase):
    def setUp(self):
        self.path = Path(tempfile.mkdtemp()) / "tree.ged"
        self.path.write_text(TREE, encoding="utf-8")

    def test_default_drops_islands(self):
        recs = gedcom_io.parse(self.path, root="MH:I1")
        xrefs = {r["xref"] for r in recs}
        self.assertEqual(xrefs & {"@I6@", "@I7@", "@I8@", "@F3@"}, set())
        self.assertLessEqual({"@I1@", "@I2@", "@I3@", "@I4@", "@I5@", "@F1@", "@F2@", "@S1@"}, xrefs)
        self.assertIn(None, xrefs)                     # HEAD and TRLR stay

    def test_keep_unlinked(self):
        recs = gedcom_io.parse(self.path, keep_unlinked=True)
        self.assertEqual(sum(r["tag"] == "INDI" for r in recs), 8)

    def test_root_picks_the_part(self):
        recs = gedcom_io.parse(self.path, root="@I6@")
        self.assertEqual({r["xref"] for r in recs if r["tag"] == "INDI"}, {"@I6@", "@I7@"})

    def test_largest_part_without_root(self):
        tree = gedcom_io.Tree(self.path)
        self.assertEqual(set(tree.people), {"@I1@", "@I2@", "@I3@", "@I4@", "@I5@"})
        self.assertEqual(tree.unlinked, ["@I6@", "@I7@", "@I8@"])
        self.assertEqual(tree.lineage("MH:I1", "@I3@"), ["M"])

    def test_options(self):
        self.assertEqual(gedcom_io.options({"gedcom": {"proband": "MH:I1"}}),
                         dict(keep_unlinked=False, root="MH:I1"))
        self.assertTrue(gedcom_io.options({"gedcom": {"keep_unlinked": True}})["keep_unlinked"])


if __name__ == "__main__":
    unittest.main()
