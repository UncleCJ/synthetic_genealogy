import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sg.store import tree_store


class EditCommandsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.s = tree_store.Store(Path(self.tmp.name) / "tree.sqlite")
        self.s.db.execute("insert into person (id, given, surname, origin) values ('P1','Anna','Exempel','import:t')")
        self.s.db.execute("insert into event (owner, tag, date, place, origin) "
                          "values ('P1','BIRT','1 JAN 1900','Socken','import:t')")
        self.s.db.commit()

    def tearDown(self):
        self.s.db.close()
        self.tmp.cleanup()

    def run_(self, *argv):
        return tree_store.edit_main(self.s, ["--who", "T", *argv, "--why", "test"])

    def test_add_cite_drop(self):
        self.assertEqual(self.run_("add-source", "SRC:a", "A letter"), "SRC:a")
        n = self.run_("add-event", "P1", "even", "--type", "Letter", "--source", "SRC:a", "--page", "p. 1")
        self.assertEqual(self.s.db.execute("select tag from event where n=?", (n,)).fetchone()[0], "EVEN")
        self.run_("cite", "SRC:a", "--person", "P1")
        self.assertEqual(self.s.db.execute("select count(*) from citation").fetchone()[0], 2)
        self.run_("drop", "event", str(n))
        self.assertEqual(self.s.db.execute("select count(*) from citation").fetchone()[0], 1)
        edits = json.loads((Path(self.tmp.name) / "tree_edits.json").read_text())
        self.assertNotIn("event", edits)

    def test_imported_rows_are_refused(self):
        with self.assertRaises(SystemExit):
            self.run_("set-event", "1", "--date", "1901")
        with self.assertRaises(SystemExit):
            self.run_("drop", "event", "1")
        with self.assertRaises(SystemExit):
            self.run_("cite", "SRC:missing", "--event", "1")

    def test_citation_of_imported_event_survives_renumbering(self):
        self.run_("add-source", "SRC:a", "A letter")
        self.run_("cite", "SRC:a", "--event", "1", "--page", "p. 2")
        # a re-import: tree rows cleared, the event comes back with another number
        for t in tree_store.Store.TREE_TABLES:
            self.s.db.execute(f"delete from {t}")
        self.s.db.execute("insert into event (n, owner, tag, date, place, origin) "
                          "values (9, 'P1','BIRT','1 JAN 1900','Socken','import:t2')")
        self.s.load_edits()
        self.assertEqual(self.s.db.execute("select event from citation").fetchone()[0], 9)

    def test_citation_survives_rewritten_place(self):
        self.run_("add-source", "SRC:a", "A letter")
        self.run_("cite", "SRC:a", "--event", "1", "--page", "p. 2")
        for t in tree_store.Store.TREE_TABLES:
            self.s.db.execute(f"delete from {t}")
        # the new export writes the place differently; one event still fits
        self.s.db.execute("insert into event (n, owner, tag, date, place, origin) "
                          "values (7, 'P1','BIRT','1 JAN 1900','Socken, Land','import:t2')")
        self.s.load_edits()
        self.assertEqual(self.s.db.execute("select event from citation").fetchone()[0], 7)


if __name__ == "__main__":
    unittest.main()


class ExportTest(unittest.TestCase):
    """export_gedcom keeps to GEDCOM 5.5.1's line rules and comes back whole."""

    def test_long_values_round_trip(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        d = Path(tmp.name)
        s = tree_store.Store(d / "a.sqlite")
        self.addCleanup(s.db.close)
        occu = "Bonde i Byn, nämndeman i häradet, kyrkvärd, sexman. Riksdagsman 1634, se noter, och mer därtill"
        two = "Snickare\nsedan målare"
        text = ("Ett långt ord " * 30 + "Åsa Ödmark ") * 3 + "slut "
        s.db.execute("insert into person (id, given, surname, origin) values ('P1','Anna','Exempel','import:t')")
        for tag, v in (("OCCU", occu), ("OCCU", two), ("EVEN", text), ("OCCU", "Bonde")):
            s.db.execute("insert into event (owner, tag, value, origin) values ('P1',?,?,'import:t')", (tag, v))
        s.db.commit()
        out = d / "out.ged"
        s.export_gedcom(out)
        lines = out.read_text(encoding="utf-8").splitlines()
        self.assertTrue(all(len(ln.encode()) <= 255 for ln in lines))
        conc = [ln for ln in lines if " CONC " in ln]
        self.assertTrue(conc)
        self.assertFalse([ln for ln in conc if ln.split(" CONC ", 1)[1].startswith(" ")])
        occus = [ln[7:] for ln in lines if ln.startswith("1 OCCU ")]
        self.assertTrue(all(len(v) <= 90 for v in occus))
        self.assertIn("Snickare…", occus)
        self.assertIn("1 SUBM @U1@", lines)
        self.assertIn("0 @U1@ SUBM", lines)
        b = tree_store.Store(d / "b.sqlite")
        self.addCleanup(b.db.close)
        b.import_gedcom(out, "t", keep_unlinked=True)
        got = sorted(v for _, v in b.db.execute("select tag, value from event"))
        self.assertEqual(got, sorted([occu, two, text, "Bonde"]))
        self.assertEqual(b.db.execute("select extra from event where value=?", (occu,)).fetchone()[0], "[]")
