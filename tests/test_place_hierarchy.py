"""Place strings completed with their whole hierarchy from the tree's
other strings (a small hand-made parish list; public place names, no
people; farms are made up)."""
import unittest

import parish_names as P
import place_hierarchy as H


def item(qid, label, county):
    return dict(qid=qid, kind="församling", label=label, aliases="", archive="", county=county,
                lat="", lon="", succ="", pred="")


ROWS = [item("Q1", "Dädesjö församling", "Kronobergs län"),
        item("Q2", "Källeryds församling", "Jönköpings län"),
        item("Q3", "Ödeshögs församling", "Östergötlands län"),
        item("Q4", "Skogs församling", "Gävleborgs län"),
        item("Q5", "Skogs församling", "Västernorrlands län")]
KOMMUNER = ["Uppvidinge kommun", "Växjö kommun", "Gnosjö kommun", "Jönköpings kommun",
            "Ödeshögs kommun", "Bengtsfors kommun"]


def hier(places):
    return H.Hierarchy(places, names=P.Names(rows=ROWS, kommuner=KOMMUNER))


class Complete(unittest.TestCase):
    TREE = ["Dädesjö, Uppvidinge, Kronobergs län", "Uppvidinge, Kronobergs län, Småland",
            "Dädesjö, Uppvidinge", "Dädesjö, Växjö, Kronobergs län, Sverige"]

    def test_levels_from_other_strings(self):
        h = hier(self.TREE)
        self.assertEqual(h.label("Dädesjö, Uppvidinge"), "Dädesjö, Uppvidinge, Småland, Kronobergs län")
        # two of three strings that give Dädesjö a town say Uppvidinge
        self.assertEqual(h.label("Gården, Dädesjö"), "Gården, Dädesjö, Uppvidinge, Småland, Kronobergs län")
        # what is written is kept
        self.assertEqual(h.label("Dädesjö, Växjö"), "Dädesjö, Växjö, Småland, Kronobergs län")

    def test_split_votes_fill_nothing(self):
        h = hier(self.TREE + ["Gården, Dädesjö, Växjö"])
        self.assertEqual(h.label("Gården, Dädesjö"), "Gården, Dädesjö, Småland, Kronobergs län")

    def test_known_parish(self):
        h = hier([])
        self.assertEqual(h.label("Dädesjö prästgård, Uppvidinge", parish="Dädesjö"),
                         "Dädesjö prästgård, Dädesjö, Uppvidinge, Småland, Kronobergs län")
        self.assertEqual(h.label("Gården", parish="Skog (Gävleborgs län)"), "Gården, Skog")

    def test_written_forms(self):
        h = hier([])
        for written, shown in {
            "Gården, Källeryd (F), Sverige": "Gården, Källeryd, Småland, Jönköpings län",
            "Gården, Källeryd, Jönköping, Sverige": "Gården, Källeryd, Småland, Jönköpings län",
            "Gården, Källeryds socken, Gnosjö kommun": "Gården, Källeryd, Gnosjö, Småland, Jönköpings län",
            "Gården, Ödeshög, Östergötlands län": "Gården, Ödeshög, Östergötland, Östergötlands län",
            "Dädesjö Kronobergs Len": "Dädesjö, Småland, Kronobergs län",
            "Gården, Bengtsfors kommun, Sweden": "Gården, Bengtsfors",
            "Gården, Skog": "Gården, Skog",                       # two parishes named Skog
            "Gården, Skog, Hälsingland": "Gården, Skog, Hälsingland, Gävleborgs län",
            "Chicago, Cook, Illinois, USA": "Chicago, Cook, Illinois, USA",
        }.items():
            self.assertEqual(h.label(written), shown, written)


if __name__ == "__main__":
    unittest.main()
