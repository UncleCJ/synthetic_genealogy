"""A relative at a known path names the side (and grandparent) of the
segments it shares with the same match (match_placement.sides_from_relatives).
Synthetic rows only."""

import sys
import unittest
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import match_placement as mp  # noqa: E402


def segs(rows):
    return pd.DataFrame(rows, columns=["match_key", "chrom", "start", "end", "cM"])


class RelativeSide(unittest.TestCase):
    def setUp(self):
        t = segs([("a", "1", 10e6, 30e6, 20), ("b", "2", 10e6, 30e6, 20),
                  ("c", "3", 10e6, 30e6, 20), ("d", "4", 10e6, 30e6, 20)])
        t = t.assign(parent=["", "", "", "F"], parent_reason="")
        self.kit = dict(subject="t", platform="P", segs=t)
        grand = segs([("a", "1", 12e6, 31e6, 18),     # shares a: maternal grandmother
                      ("b", "2", 40e6, 60e6, 18)])    # b elsewhere only
        half = segs([("c", "3", 11e6, 29e6, 18),      # shares c: paternal half-sibling
                     ("d", "4", 10e6, 30e6, 20)])
        by = lambda d: dict(tuple(d.groupby("match_key")))
        self.rels = [("g", "MM", "P", by(grand)), ("h", "F", "P", by(half))]

    def test_sharing_names_side_and_grandparent(self):
        mp.sides_from_relatives(self.kit, self.rels)
        o = self.kit["segs"].set_index("match_key")
        self.assertEqual((o.loc["a", "parent"], o.loc["a", "relative_gp"]), ("M", "MM"))
        self.assertEqual(o.loc["b", "parent"], "")          # absence says nothing
        self.assertEqual((o.loc["c", "parent"], o.loc["c", "relative_gp"]), ("F", ""))
        self.assertEqual(o.loc["d", "parent_reason"], "")   # side already given

    def test_other_platform_ignored(self):
        self.kit["platform"] = "Q"
        mp.sides_from_relatives(self.kit, self.rels)
        self.assertTrue((self.kit["segs"].parent.iloc[:3] == "").all())


if __name__ == "__main__":
    unittest.main()
