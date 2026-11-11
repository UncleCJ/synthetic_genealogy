import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import store_query
import tree_store


class StoreQueryTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        path = Path(self.tmp.name) / "tree.sqlite"
        s = tree_store.Store(path)
        rows = [("P1", "Anders", "Exempel", "M", "[]"), ("P2", "Åsa", "Prov", "F", '["Exempel"]'),
                ("P3", "Lisa", "Exempel", "F", "[]"), ("P4", "Lisa", "Annan", "F", "[]")]
        s.db.executemany("insert into person (id, given, surname, sex, married) values (?,?,?,?,?)", rows)
        s.db.execute("insert into family (id, husb, wife) values ('F1','P1','P2')")
        s.db.execute("insert into child (family, child, pedi) values ('F1','P3','')")
        s.db.execute("insert into event (owner, tag, date) values ('P3','BIRT','1 JAN 1950')")
        s.db.commit()
        s.db.close()
        self.db = store_query.connect(path)

    def tearDown(self):
        self.db.close()
        self.tmp.cleanup()

    def test_find_folds_case_accents_and_married_names(self):
        self.assertEqual(store_query.find(self.db, "asa exempel"), ["P2"])
        self.assertEqual(store_query.find(self.db, "lisa"), ["P3", "P4"])
        self.assertEqual(store_query.find(self.db, "lisa exxempel"), ["P3"])

    def test_parents_and_children(self):
        rel = store_query.relatives(self.db, "P3")
        self.assertEqual((rel["parents"][0]["father"], rel["parents"][0]["mother"]), ("P1", "P2"))
        self.assertEqual(store_query.relatives(self.db, "P1")["unions"][0]["children"], ["P3"])
        text = store_query.describe(self.db, "P3")
        self.assertIn("b. 1950", text)
        self.assertIn("mother: Åsa Prov (married Exempel)", text)

    def test_read_only(self):
        with self.assertRaises(Exception):
            self.db.execute("delete from person")


if __name__ == "__main__":
    unittest.main()
