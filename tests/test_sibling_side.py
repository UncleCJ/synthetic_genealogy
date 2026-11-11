"""The side of a match segment from which siblings share it (phased copy
labels), on simulated families."""
import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import match_placement as mp  # noqa: E402
import simulate as sm  # noqa: E402


class SideFromSiblings(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        ped, via = sm.ancestry(depth=4, siblings=3, relatives_per_couple=3)
        sim = sm.simulate(ped, seed=2)
        sibs = ["sib1", "sib2", "sib3"]
        segs = sm.detect(sim, sibs, seed=2, matches=list(via))
        labels = sm.copy_labels(sim, sibs, seed=2)
        rng = np.random.default_rng(2)
        cls.kids = []
        for s in sibs:
            g = segs[segs.subject == s].reset_index(drop=True)
            known = rng.random(len(g)) < 0.5           # what the mother's list would give
            par = np.where(known, np.where(g.real, g.true_copy, "F"), "")
            cls.kids.append(dict(subject=s, date=pd.Timestamp("2023-01-01"), keys=set(g.match_key),
                                 segs=g.assign(parent=par, parent_reason="", hidden=~known)))
        cls.rates = mp.sides_from_siblings(cls.kids, labels)
        out = pd.concat([k["segs"] for k in cls.kids])
        cls.all_hidden = out[out.hidden]
        cls.hidden = out[out.hidden & (out.cM >= mp.SIDE_BANDS[0])]

    def test_sides_are_right(self):
        real = self.hidden[self.hidden.real]
        sided = real[real.parent != ""]
        self.assertGreater(len(sided) / len(real), 0.3)
        self.assertGreater((sided.parent == sided.true_copy).mean(), 0.97)

    def test_false_segments_rarely_get_a_side(self):
        false = self.all_hidden[~self.all_hidden.real]
        self.assertTrue(len(false))
        self.assertLess((false.parent != "").mean(), 0.1)

    def test_rates_learnt(self):
        for band in (1, 2):
            self.assertGreater(self.rates[(band, True)]["has"], self.rates[(band, False)]["has"])

    def test_known_sides_untouched(self):
        for k in self.kids:
            s = k["segs"]
            known = s[~s.hidden]
            self.assertFalse(known.parent_reason.str.startswith("siblings").any())


if __name__ == "__main__":
    unittest.main()
