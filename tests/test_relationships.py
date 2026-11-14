"""Relationship paths, names and WATO-style odds, on a made-up tree and
small simulations."""
import tempfile
import unittest
from pathlib import Path

import numpy as np

import gedcom_io
import relationship_check as rc
import simulate

# G1 + G2 -> P1, P2; G1 + W -> P3 (half); P1 -> A, P2 -> B, P3 -> C
TREE = """0 HEAD
0 @G1@ INDI
1 NAME Gustav /Test/
1 SEX M
1 BIRT
2 DATE 1850
2 PLAC Ryd
1 FAMS @F1@
1 FAMS @F2@
0 @G2@ INDI
1 NAME Greta /Test/
1 SEX F
1 FAMS @F1@
0 @W@ INDI
1 NAME Wilma /Annan/
1 SEX F
1 FAMS @F2@
0 @P1@ INDI
1 NAME Per /Test/
1 SEX M
1 FAMC @F1@
1 FAMS @F3@
0 @P2@ INDI
1 NAME Pia /Test/
1 SEX F
1 FAMC @F1@
1 FAMS @F4@
0 @P3@ INDI
1 NAME Pål /Test/
1 SEX M
1 FAMC @F2@
1 FAMS @F5@
0 @A@ INDI
1 NAME Anna /Test/
1 SEX F
1 FAMC @F3@
0 @B@ INDI
1 NAME Bo /Kusin/
1 SEX M
1 FAMC @F4@
0 @C@ INDI
1 NAME Cia /Halv/
1 SEX F
1 FAMC @F5@
0 @F1@ FAM
1 HUSB @G1@
1 WIFE @G2@
1 CHIL @P1@
1 CHIL @P2@
0 @F2@ FAM
1 HUSB @G1@
1 WIFE @W@
1 CHIL @P3@
0 @F3@ FAM
1 HUSB @P1@
1 CHIL @A@
0 @F4@ FAM
1 WIFE @P2@
1 CHIL @B@
0 @F5@ FAM
1 HUSB @P3@
1 CHIL @C@
0 TRLR
"""


class Paths(unittest.TestCase):
    def setUp(self):
        p = Path(tempfile.mkdtemp()) / "t.ged"
        p.write_text(TREE, encoding="utf-8")
        self.t = gedcom_io.Tree(p)

    def test_names(self):
        n = gedcom_io.relationship_name
        self.assertEqual(n(1, 0), "parent/child")
        self.assertEqual(n(1, 1, True), "half sibling")
        self.assertEqual(n(2, 3), n(3, 2))
        self.assertEqual(n(3, 2), "1C1R")
        self.assertEqual(n(4, 4, True), "half 3C")
        self.assertEqual(n(5, 0), "3x great-grandparent")

    def test_relation_in_tree(self):
        r = self.t.relation("A", "B")
        self.assertEqual((r["name"], r["code"], r["half"]), ("1C", "FF", False))
        self.assertEqual(set(r["ancestors"]), {"@G1@", "@G2@"})
        self.assertEqual(self.t.relation("A", "C")["name"], "half 1C")
        self.assertEqual(self.t.relation("A", "G1")["name"], "grandparent")
        self.assertEqual(self.t.relation("A", "B")["paths"], 1)

    def test_relation_below_the_tree(self):
        # someone two generations below P2: P2's grandchild is A's 1C1R
        self.assertEqual(self.t.relation("A", "P2", down=1)["name"], "1C")
        self.assertEqual(self.t.relation("A", "P2", down=2)["name"], "1C1R")
        self.assertEqual(self.t.relation("A", "P3", down=2)["name"], "half 1C1R")
        # below a shared ancestor: through the spouse who is also A's ancestor,
        # unless the identity says half; P1's partner is not in the tree
        self.assertEqual(self.t.relation("A", "G1", down=2)["name"], "1C")
        self.assertEqual(self.t.relation("A", "G1", down=2, half=True)["name"], "half 1C")
        self.assertEqual(self.t.relation("A", "P1", down=1)["name"], "half sibling")
        self.assertEqual(self.t.relation("A", "P1", down=1, half=False)["name"], "sibling")

    def test_facts(self):
        f = self.t.facts("@G1@")
        self.assertEqual((f["name"], f["birth"], f["parents"]), ("Gustav Test", "1850 Ryd", []))
        self.assertEqual(len(self.t.facts("@A@")["parents"]), 1)


# Unions with an unrecorded partner: M alone in U1 (X1, X2) and in U2 (X3);
# M with H in U3 (Y) and again in U4, a duplicate of the couple (Z); X1 -> K1,
# X2 -> K2
UNIONS = """0 HEAD
0 @M@ INDI
1 NAME Maja /Test/
1 SEX F
0 @H@ INDI
1 NAME Hans /Test/
1 SEX M
""" + "".join(f"0 @{x}@ INDI\n1 NAME {x} /Test/\n1 SEX M\n" for x in ("X1", "X2", "X3", "Y", "Z", "K1", "K2")) + """0 @U1@ FAM
1 WIFE @M@
1 CHIL @X1@
1 CHIL @X2@
0 @U2@ FAM
1 WIFE @M@
1 CHIL @X3@
0 @U3@ FAM
1 HUSB @H@
1 WIFE @M@
1 CHIL @Y@
0 @U4@ FAM
1 HUSB @H@
1 WIFE @M@
1 CHIL @Z@
0 @U5@ FAM
1 HUSB @X1@
1 CHIL @K1@
0 @U6@ FAM
1 HUSB @X2@
1 CHIL @K2@
0 TRLR
"""


class SiblingKind(unittest.TestCase):
    def setUp(self):
        p = Path(tempfile.mkdtemp()) / "u.ged"
        p.write_text(UNIONS, encoding="utf-8")
        self.t = gedcom_io.Tree(p, keep_unlinked=True)

    def test_one_union_with_an_unrecorded_partner_is_full(self):
        r = self.t.relation("X1", "X2")
        self.assertEqual((r["name"], r["half"], r["open"]), ("sibling", False, False))
        self.assertEqual(self.t.relation("K1", "K2")["name"], "1C")
        self.assertAlmostEqual(gedcom_io.kinship(self.t, "X1", "X2"), 0.25)
        self.assertAlmostEqual(gedcom_io.kinship(self.t, "K1", "K2"), 0.0625)

    def test_another_union_is_half_or_open(self):
        self.assertEqual(self.t.relation("X1", "X3")["name"], "at least half sibling")
        self.assertEqual(self.t.relation("X1", "Y")["name"], "at least half sibling")
        self.assertEqual(self.t.relation("X1", "X3", half=False)["name"], "sibling")
        self.assertAlmostEqual(gedcom_io.kinship(self.t, "X1", "X3"), 0.125)

    def test_same_couple_twice_is_full(self):
        self.assertEqual(self.t.sibship("@Y@", "@Z@", "@M@"), "full")
        self.assertEqual(self.t.relation("Y", "Z")["name"], "sibling")
        self.assertAlmostEqual(gedcom_io.kinship(self.t, "Y", "Z"), 0.25)


class Odds(unittest.TestCase):
    def test_simulated_means(self):
        sib = simulate.relationship_cm(1, 1, n=40, seed=1)
        half = simulate.relationship_cm(1, 1, True, n=40, seed=1)
        cous = simulate.relationship_cm(2, 2, n=40, seed=1)
        self.assertTrue(2300 < sib.mean() < 2900, sib.mean())   # union of HIR and FIR, ~75% of the genome
        self.assertTrue(1500 < half.mean() < 2000, half.mean())
        self.assertTrue(650 < cous.mean() < 1100, cous.mean())

    def test_odds_pick_the_nearest(self):
        rng = np.random.default_rng(0)
        dist = {(2, 2, False): (rng.lognormal(np.log(850), 0.2, 300), 300),
                (3, 3, False): (rng.lognormal(np.log(220), 0.4, 300), 300),
                (4, 4, False): (rng.lognormal(np.log(75), 0.5, 200), 300)}
        self.assertEqual(rc.odds(dist, 800).rel.iloc[0], "1C")
        self.assertEqual(rc.odds(dist, 200).rel.iloc[0], "2C")
        self.assertAlmostEqual(rc.odds(dist, 60).p.sum(), 1.0)
        self.assertIsNone(rc.likelihood(dist, 2, 3, False, 400))


if __name__ == "__main__":
    unittest.main()
