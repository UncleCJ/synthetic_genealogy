"""gedcom_audit.misplaced on a made-up tree: a widower's two wives and a
widow's two husbands, with children listed under the wrong union."""
import tempfile
import unittest
from pathlib import Path

import gedcom_audit
import gedcom_io


def indi(x, sex, birth=None, death=None):
    s = f"0 @{x}@ INDI\n1 NAME {x} /Test/\n1 SEX {sex}\n"
    for tag, d in (("BIRT", birth), ("DEAT", death)):
        if d:
            s += f"1 {tag}\n2 DATE {d}\n"
    return s


def fam(x, h, w, kids, marr=None):
    s = f"0 @{x}@ FAM\n" + (f"1 HUSB @{h}@\n" if h else "") + (f"1 WIFE @{w}@\n" if w else "")
    s += f"1 MARR\n2 DATE {marr}\n" if marr else ""
    return s + "".join(f"1 CHIL @{c}@\n" for c in kids)


# H marries W1 (1840; she dies 12 MAR 1850), then W2 (1851). A is W1's,
# D was born the day W1 died; B (1852) is listed with W1, C (1846) with W2.
# V marries H3 (he dies 1 JAN 1860), then H4; E (5 months later) is fine,
# F (1862) is listed with H3. G's mother would be 55.
TREE = ("0 HEAD\n" + indi("H", "M", "1815") + indi("W1", "F", "1818", "12 MAR 1850")
        + indi("W2", "F", "1825") + indi("V", "F", "1830") + indi("H3", "M", "1825", "1 JAN 1860")
        + indi("H4", "M", "1828") + indi("A", "M", "1845") + indi("B", "F", "3 MAY 1852")
        + indi("C", "M", "1846") + indi("D", "F", "12 MAR 1850") + indi("E", "M", "1 JUN 1860")
        + indi("F", "F", "1862") + indi("G", "M", "1874")
        + fam("U1", "H", "W1", ["A", "B", "D", "G"], "1840") + fam("U2", "H", "W2", ["C"], "1851")
        + fam("U3", "H3", "V", ["E", "F"], "1850") + fam("U4", "H4", "V", [], "1861") + "0 TRLR\n")


class Misplaced(unittest.TestCase):
    def setUp(self):
        p = Path(tempfile.mkdtemp()) / "m.ged"
        p.write_text(TREE, encoding="utf-8")
        rows = gedcom_audit.misplaced(gedcom_io.Tree(p, keep_unlinked=True))
        self.by = {(r["child"].split()[0], r["why"]): r["candidates"] for r in rows}

    def test_after_the_mothers_death(self):
        self.assertEqual([c.split()[0] for c in self.by[("B", "born after the mother's death")]], ["@U2@"])
        self.assertNotIn("D", {k for k, _ in self.by})       # born the day she died
        self.assertNotIn("A", {k for k, _ in self.by})

    def test_after_the_fathers_death(self):
        self.assertIn(("F", "born over ten months after the father's death"), self.by)
        self.assertNotIn("E", {k for k, _ in self.by})       # five months after

    def test_before_the_second_marriage(self):
        why = "born before this marriage, while the parent's earlier partner lived"
        self.assertEqual([c.split()[0] for c in self.by[("C", why)]], ["@U1@"])

    def test_mothers_age(self):
        self.assertEqual([c.split()[0] for c in self.by[("G", "the mother over 50 at the birth")]], ["@U2@"])


if __name__ == "__main__":
    unittest.main()
