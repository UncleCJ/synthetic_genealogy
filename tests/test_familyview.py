"""The family lens on a synthetic store: lineage codes and counts."""
import sqlite3
import unittest

import familyview as fv


def store():
    db = sqlite3.connect(":memory:")
    db.executescript("""
    create table person(id, given, surname, sex);
    create table event(owner, tag, date);
    create table family(id, husb, wife);
    create table child(family, child);
    create table citation(owner);
    create table dna_match(person);
    create table out_assertions_tree(lineage, match_key);
    insert into person values ('me','A','X','M'),('f','B','X','M'),('m','C','Y','F'),
                              ('ff','D','X','M'),('sib','E','X','F'),('kid','G','X','M');
    insert into event values ('me','BIRT','1980'),('f','BIRT','ABT 1950'),('f','DEAT','2010');
    insert into family values ('F1','f','m'),('F2','ff',null),('F3','me',null);
    insert into child values ('F1','me'),('F1','sib'),('F2','f'),('F3','kid');
    insert into citation values ('f'),('f');
    insert into out_assertions_tree values ('FF','a'),('FF','a'),('FF','b'),('M','c');
    """)
    return db


class FamilyLens(unittest.TestCase):
    def test_lineage_codes_collapse(self):
        # one person reached by two paths keeps both codes
        par = {"me": ("f", "m"), "f": ("x", None), "m": ("x", None)}
        self.assertEqual(fv.lineage_codes(par, "me")["x"], ["FF", "MF"])

    def test_collect(self):
        d = fv.collect(store(), "me")
        p = {r[0]: r for r in d["people"]}
        self.assertEqual(p["f"][5], ["F"])
        self.assertEqual((p["f"][3], p["f"][4]), (1950, 2010))
        self.assertEqual(p["f"][7], 2)          # citations
        self.assertEqual(p["ff"][8], 2)         # matches a, b counted once each
        self.assertEqual(p["sib"][5], [])       # not an ancestor
        self.assertIn(["F1", "f", "m", ["me", "sib"]], d["fams"])


if __name__ == "__main__":
    unittest.main()
