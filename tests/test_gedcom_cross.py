"""gedcom_audit cross on two made-up trees: a shared grandfather written
two ways, a shared parish and a shared surname. Parish names are public
(gazetteer/parish_names.tsv); no people."""
import tempfile
import unittest
from pathlib import Path

import gedcom_audit

OURS = """0 HEAD
0 @I1@ INDI
1 NAME Anna /Prov/
1 FAMC @F1@
0 @I2@ INDI
1 NAME Bo /Prov/
1 SEX M
1 FAMS @F1@
1 FAMC @F2@
0 @I3@ INDI
1 NAME Carl Johan /Svensson/
1 SEX M
1 BIRT
2 DATE 1870
2 PLAC Haurida, Jönköpings län
1 FAMS @F2@
0 @I4@ INDI
1 NAME Dora /Lind/
1 SEX F
1 BIRT
2 DATE 1875
2 PLAC Aneby
1 FAMS @F2@
0 @F1@ FAM
1 HUSB @I2@
1 CHIL @I1@
0 @F2@ FAM
1 HUSB @I3@
1 WIFE @I4@
1 CHIL @I2@
0 TRLR
"""

THEIRS = """0 HEAD
0 @T1@ INDI
1 NAME Tora /Test/
1 FAMC @G1@
0 @T2@ INDI
1 NAME Ulla /Test/
1 SEX F
1 FAMS @G1@
1 FAMC @G2@
0 @T3@ INDI
1 NAME Karl /Svenson/
1 SEX M
1 BIRT
2 DATE abt 1872
2 PLAC Haurida
1 FAMS @G2@
0 @T4@ INDI
1 NAME Vera /Lind/
1 SEX F
1 BIRT
2 DATE 1801
2 PLAC Stockholm
1 FAMC @G3@
0 @G1@ FAM
1 WIFE @T2@
1 CHIL @T1@
0 @G2@ FAM
1 HUSB @T3@
1 CHIL @T2@
0 @G3@ FAM
1 CHIL @T4@
0 @G4@ FAM
1 WIFE @T4@
1 CHIL @T3@
0 TRLR
"""


class Cross(unittest.TestCase):
    def setUp(self):
        d = Path(tempfile.mkdtemp())
        self.ours, self.theirs = d / "ours.ged", d / "theirs.ged"
        self.ours.write_text(OURS, encoding="utf-8")
        self.theirs.write_text(THEIRS, encoding="utf-8")
        self.r = gedcom_audit.cross(str(self.theirs), "Tora", str(self.ours), "@I1@")

    def test_same_person(self):
        s = self.r["same"]
        self.assertEqual(len(s), 1)
        self.assertEqual((s[0]["our_codes"], s[0]["their_codes"]), (["FF"], ["MF"]))
        self.assertEqual((s[0]["gap"], s[0]["relationship"]), (2, "1C"))
        self.assertTrue(s[0]["parish"].startswith("Haurida"))

    def test_parish_and_surname(self):
        self.assertEqual([p[0] for p in self.r["parishes"]][:1], [self.r["same"][0]["parish"]])
        self.assertEqual([s[0] for s in self.r["surnames"]], ["lind"])

    def test_patronymic_surname_left_out(self):
        # folded keys drop double letters (persdotter -> persdoter)
        self.ours.write_text(OURS.replace("/Lind/", "/Persdotter/"), encoding="utf-8")
        self.theirs.write_text(THEIRS.replace("/Lind/", "/Persdotter/"), encoding="utf-8")
        r = gedcom_audit.cross(str(self.theirs), "Tora", str(self.ours), "@I1@")
        self.assertEqual(r["surnames"], [])


if __name__ == "__main__":
    unittest.main()
