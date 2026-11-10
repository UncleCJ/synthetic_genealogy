"""The copy model on simulated families: one tester, relatives through
every ancestral couple, vendor-style segments (noise, false segments)."""
import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import copy_model as cm  # noqa: E402
import simulate as sm  # noqa: E402


class Pieces(unittest.TestCase):
    def test_transition_rows_and_structure(self):
        T = cm.transition(3, 0.01)
        np.testing.assert_allclose(T.sum(1), 1)
        S = cm.states("F", 3)
        self.assertEqual(S, ["FFF", "FFM", "FMF", "FMM"])
        # changing the grandparent (2nd letter) redraws the 3rd: FFF -> FMF = FFF -> FMM
        self.assertAlmostEqual(T[0, 2], T[0, 3])
        # FFF -> FFM: one crossover (r); FFF -> FMF: one crossover (r) times a redraw (1/2)
        self.assertGreater(T[0, 1], T[0, 2])

    def test_real_probability(self):
        self.assertAlmostEqual(float(cm.real_probability(cm.FALSE_AT)), 0.5)
        self.assertGreater(float(cm.real_probability(20)), 0.99)


class Simulated(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.runs = []
        for seed in (2, 4):
            ped, via = sm.ancestry(depth=4, relatives_per_couple=2)
            sim = sm.simulate(ped, seed=seed)
            segs = sm.detect(sim, ["sib1"], seed=seed, matches=list(via))
            claims = cm.claims_from_segments(segs, via)
            model = cm.CopyModel(depth=3).fit(claims, lengths_cm=sm.CHROM_CM)
            cls.runs.append((sim, segs, claims, model))

    def test_confident_calls_are_right(self):
        for sim, _, _, model in self.runs:
            a = cm.accuracy(model, sim, "sib1", level=2, n=600, seed=1)
            for side in "FM":
                self.assertGreater(a[side]["called_share"], 0.1)
                self.assertGreater(a[side]["accuracy_when_called"], 0.9, a)

    def test_conflicts_flag_false_segments(self):
        n_false_conf = n_conf = n_false = n = 0
        for _, segs, claims, model in self.runs:
            v = model.verdicts().merge(claims[["claim_id", "match", "start", "end"]], on="claim_id")
            real = segs[segs.real]
            v["real"] = [bool(((real.match == r.match) & (real.chrom == r.chrom) & (real.start < r.end)
                               & (real.end > r.start)).any()) for r in v.itertuples()]
            n += len(v)
            n_false += (~v.real).sum()
            n_conf += (v.verdict == "conflicts").sum()
            n_false_conf += ((v.verdict == "conflicts") & ~v.real).sum()
        # false segments are over-represented among the conflicts
        self.assertGreater(n_false_conf / n_conf, 1.5 * n_false / n)

    def test_blocks(self):
        b = self.runs[0][3].blocks(level=2, min_post=0.9)
        self.assertTrue(len(b))
        self.assertTrue(b.lineage.str.len().eq(2).all())
        self.assertTrue((b.posterior >= 0.9).all())


if __name__ == "__main__":
    unittest.main()
