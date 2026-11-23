"""gedcom_audit.successors on two made-up exports of one tree: a family
deleted and entered again under new ids, with names respelled, plus a
stranger who only shares a first name. And the successors.tsv helpers."""
import tempfile
import unittest
from pathlib import Path

from sg.readers import gedcom_audit
from sg.common import identity


def indi(x, mh, name, sex, birth=None, death=None):
    s = f"0 @{x}@ INDI\n1 NAME {name}\n1 SEX {sex}\n1 RIN {mh}\n"
    for tag, d in (("BIRT", birth), ("DEAT", death)):
        if d:
            s += f"1 {tag}\n2 DATE {d}\n"
    return s


def fam(x, h, w, kids):
    return (f"0 @{x}@ FAM\n" + (f"1 HUSB @{h}@\n" if h else "") + (f"1 WIFE @{w}@\n" if w else "")
            + "".join(f"1 CHIL @{c}@\n" for c in kids))


# Father P (kept, MH:I1) and mother M with children Gustaf and Malkom; in
# the new export M, Gustaf and Malkom are entered again (I20-I22) as
# Johanna Fredrika, Gustav, Malkolm, the mother's birth year read 7 years
# later. Stranger S shares Gustaf's first name and nothing else.
OLD = ("0 HEAD\n" + indi("P", "MH:I1", "Per /Test/", "M", "1785")
       + indi("M", "MH:I2", "Johanna Frederica /Johansdotter/", "F", "1784")
       + indi("C1", "MH:I3", "Gustaf /Persson/", "M", "3 MAR 1810")
       + indi("C2", "MH:I4", "Malkom //", "M", "1812", "1813")
       + indi("S", "MH:I5", "Anna /Other/", "F", "1700")
       + fam("F1", "P", "M", ["C1", "C2"]) + "0 TRLR\n")
NEW = ("0 HEAD\n" + indi("P", "MH:I1", "Per /Test/", "M", "1785")
       + indi("M", "MH:I20", "Johanna Fredrika /Johansdotter/", "F", "1791")
       + indi("C1", "MH:I21", "Gustav //", "M", "3 MAR 1810")
       + indi("C2", "MH:I22", "Malkolm //", "M", "1812", "1813")
       + indi("S", "MH:I23", "Gustaf /Stranger/", "M", "1811")
       + fam("F1", "P", "M", ["C1", "C2"]) + "0 TRLR\n")


class Successors(unittest.TestCase):
    def setUp(self):
        d = Path(tempfile.mkdtemp())
        (d / "old.ged").write_text(OLD, encoding="utf-8")
        (d / "new.ged").write_text(NEW, encoding="utf-8")
        self.a, self.b, added, removed, _ = gedcom_audit.diff(d / "old.ged", d / "new.ged")
        self.pairs, self.misses = gedcom_audit.successors(self.a, self.b, removed, added)

    def test_family_found_again(self):
        found = {k: m for k, m, *_ in self.pairs}
        self.assertEqual(found, {"MH:I2": "MH:I20", "MH:I3": "MH:I21", "MH:I4": "MH:I22"})

    def test_mother_found_through_her_children(self):
        why = next(w for k, m, s, w in self.pairs if k == "MH:I2")
        self.assertEqual(set(why[0].removeprefix("same ").split(", ")), {"partner", "children"})

    def test_stranger_left_alone(self):
        self.assertNotIn("MH:I23", {m for _, m, *_ in self.pairs})


class Table(unittest.TestCase):
    def test_chain_and_rejection(self):
        rows = [dict(was="MH:I1", now="MH:I2", status="auto"), dict(was="MH:I2", now="MH:I3", status="yes"),
                dict(was="MH:I7", now="MH:I8", status="no")]
        m = identity.successor_map(rows)
        self.assertEqual(m, {"MH:I1": "MH:I3", "MH:I2": "MH:I3"})
        self.assertEqual(identity.repoint('["MH:I1", "BIRT"] MH:I10 MH:I7', m), '["MH:I3", "BIRT"] MH:I10 MH:I7')

    def test_file_round_trip(self):
        p = Path(tempfile.mkdtemp()) / "successors.tsv"
        p.write_text("# comment\n" + "\t".join(identity.SUCCESSOR_COLS) + "\n"
                     "MH:I1\tMH:I2\tauto\t4.0\tsame parents\ta → b\t2026-01-01\n", encoding="utf-8")
        self.assertEqual(identity.successors_for(p.parent), {"MH:I1": "MH:I2"})


if __name__ == "__main__":
    unittest.main()
