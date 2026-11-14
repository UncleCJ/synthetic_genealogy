"""The family lens on a synthetic store: lineage codes and counts."""
import json
import shutil
import sqlite3
import subprocess
import unittest

import familyview as fv
import volumes
from geoview import FOLD_JS, name_fold


def store():
    db = sqlite3.connect(":memory:")
    db.executescript("""
    create table person(id, given, surname, sex);
    create table event(owner, tag, date, place, value, n, place_id);
    create table place(id, name, parish);
    create table family(id, husb, wife);
    create table child(family, child);
    create table citation(owner);
    create table dna_match(person);
    create table out_assertions_tree(lineage, match_key);
    insert into person values ('me','A','X','M'),('f','B','X','M'),('m','C','Y','F'),
                              ('ff','D','X','M'),('sib','E','X','F'),('kid','G','X','M');
    insert into event(owner, tag, date) values ('me','BIRT','1980'),('f','BIRT','ABT 1950'),('f','DEAT','2010');
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

    def test_death_erratum(self):
        fix = [dict(key="person:sib", field="death", was="", now="ABT OCT 2026", source="CJ")]
        d = fv.collect(store(), "me", fixes=fix)
        p = {r[0]: r for r in d["people"]}
        self.assertEqual((p["sib"][4], p["sib"][11]), (2026, "ABT OCT 2026"))
        self.assertEqual(d["life"]["sib"][-1][:2], ["DEAT", "ABT OCT 2026"])
        # the store now says something else: the erratum does not apply
        fix[0]["was"] = "1990"
        self.assertIsNone({r[0]: r for r in fv.collect(store(), "me", fixes=fix)["people"]}["sib"][4])

    def test_unknown_names(self):
        # the tree's markers for an unknown name read as absent; a doubt is a name
        db = store()
        db.executescript("insert into person values ('u1','okänd','','F'),('u2','','Svensson','M'),"
                         "('u3','Anders','NN','M'),('u4','Peter?','','M');")
        p = {r[0]: r for r in fv.collect(db, "me")["people"]}
        self.assertEqual([p[x][1] for x in ("u1", "u2", "u3", "u4")], ["", "Svensson", "Anders", "Peter?"])
        self.assertEqual([p[x][13] for x in ("u1", "u2", "u3", "u4", "me")], ["gs", "g", "s", "s", ""])

    def test_collect(self):
        d = fv.collect(store(), "me")
        p = {r[0]: r for r in d["people"]}
        self.assertEqual(p["f"][5], ["F"])
        self.assertEqual((p["f"][3], p["f"][4]), (1950, 2010))
        self.assertEqual(p["f"][7], 2)          # citations
        self.assertEqual(p["ff"][8], 2)         # matches a, b counted once each
        self.assertEqual(p["sib"][5], [])       # not an ancestor
        self.assertIn(["F1", "f", "m", ["me", "sib"], None, "", None], d["fams"])


if __name__ == "__main__":
    unittest.main()


class ReferenceOrder(unittest.TestCase):
    VARIANTS = [("Oscar", "Oskar"), ("Carl", "Karl"), ("Gustaf", "Gustav"),
                ("Christina", "Kristina"), ("Eric", "Erik"), ("Fredric", "Fredrik"),
                ("Johan", "Johann"), ("Margareta", "Margaretha"), ("Svenning", "Svening"),
                ("Josephina", "Josefina"), ("Wilhelm", "Vilhelm"), ("Alexander", "Aleksander"),
                ("Gustafsson", "Gustavson"), ("Söderström", "Soderstrom")]

    def test_name_fold_variants(self):
        for a, b in self.VARIANTS:
            self.assertEqual(name_fold(a), name_fold(b), (a, b))
        self.assertNotEqual(name_fold("Anna"), name_fold("Hanna"))
        # a partial query still finds the longer name
        self.assertIn(name_fold("Gustaf"), name_fold("Gustafsson"))
        self.assertIn(name_fold("Osc"), name_fold("Oskar"))
        # archive volume codes stay apart: doubled letters fold only inside a word
        self.assertNotIn(name_fold("A I/3"), name_fold("A II/3"))
        self.assertEqual(name_fold("Qvarnby"), name_fold("Kvarnby"))

    @unittest.skipUnless(shutil.which("node"), "node not installed")
    def test_page_fold_matches_python(self):
        for page in (fv.HTML, volumes.HTML):
            self.assertIn("__FOLDJS__", page)
        names = [n for pair in self.VARIANTS for n in pair] + ["Ann-Mari (Lind)*", "A II/3"]
        prog = f"{FOLD_JS}\nconsole.log(JSON.stringify({json.dumps(names)}.map(fold)))"
        out = subprocess.run(["node", "-e", prog], capture_output=True, text=True, check=True).stdout
        self.assertEqual(json.loads(out), [name_fold(n) for n in names])

    def test_order_key(self):
        import references as r
        refs = [("1830-1835", "B", "A I", "10"), ("1830-1835", "B", "A I", "9"),
                ("1830-1835", "A", "C I", "1"), ("1820-1830", "Z", "F I", "1"),
                ("1830-1835", "B", "A IX", "1"), ("1830-1835", "B", "A V", "1"), ("", "A", "A I", "1")]
        got = sorted(refs, key=lambda x: r.order_key(*x))
        self.assertEqual(got, [("1820-1830", "Z", "F I", "1"), ("1830-1835", "A", "C I", "1"),
                               ("1830-1835", "B", "A I", "9"), ("1830-1835", "B", "A I", "10"),
                               ("1830-1835", "B", "A V", "1"), ("1830-1835", "B", "A IX", "1"),
                               ("", "A", "A I", "1")])

    def test_references_split(self):
        rows = [dict(mh_id="x", tier="tree"), dict(mh_id="x", tier="mh-record", years="1850-1855",
                parish="P", series="A I", vol="3", volume="P A I/3", page="12", event="person"),
                dict(mh_id="x", tier="plac-only")]
        refs, trees = fv.references(rows)
        self.assertEqual(trees, {"x": 1})
        self.assertEqual(refs["x"][0][2:5], ["P A I/3", "1850-1855", "12"])
        self.assertEqual(refs["x"][0][7:], ["P", 1])

    def test_page_data_round_trip(self):
        import geoview
        data = dict(people=[["MH:I1", "Å </script> ö", 1850]])
        page = fv.HTML.replace("__NAV__", "").replace("__DATEJS__", "")
        out = geoview.embed(page, data)
        self.assertNotIn("__DATA__", out)
        self.assertNotIn("</script> ö", out)
        head, back, tail = geoview.embedded(out)
        self.assertEqual(back, data)
        self.assertEqual(head + geoview.pack_data(back) + tail, out)
