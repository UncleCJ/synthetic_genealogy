"""The copy model on simulated families: one tester, relatives through
every ancestral couple, vendor-style segments (noise, false segments)."""
import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

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

    def test_per_letter_rates(self):
        T = cm.transition(3, [0.0, 0.2])        # only the 3rd letter can change
        self.assertAlmostEqual(T[0, 1], 0.2)    # FFF -> FFM
        self.assertAlmostEqual(T[0, 2], 0.0)    # FFF -> FMF

    def test_segment_end_raises_crossover_odds_there(self):
        import pandas as pd
        claims = pd.DataFrame(dict(claim_id=["x"], chrom=["1"], start=[50e6], end=[80e6],
                                   lineage=["FMF"], w=[0.9], cM=[30.0]))
        m = cm.CopyModel(depth=3).fit(claims, lengths_cm={"1": 150})
        cc = m.claims
        Tt = m._end_transitions(m.grid["1"], cc)
        near = [t for t in Tt if abs(m.grid["1"][t] - 50) < 1.5]
        self.assertTrue(near)
        switch = max(1 - Tt[t][0, 0] for t in near)
        self.assertGreater(switch, 2 * (1 - m.T[0, 0]))
        self.assertFalse(cm.CopyModel(depth=3, ends=False).fit(claims, lengths_cm={"1": 150})
                         ._end_transitions(m.grid["1"], cc))

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

    def test_calibrated(self):
        """The posteriors mean what they say: low calibration error, and
        better than counting each segment once (which is underconfident)."""
        for sim, _, claims, model in self.runs:
            _, now = cm.calibration(model, sim, "sib1", level=2, n=1500, seed=1)
            once = cm.CopyModel(depth=3, evidence=1.0).fit(claims, lengths_cm=sm.CHROM_CM)
            _, before = cm.calibration(once, sim, "sib1", level=2, n=1500, seed=1)
            self.assertLess(now["ece"], 0.07, now)
            self.assertLess(now["ece"], before["ece"])
            self.assertLess(now["log_loss"], before["log_loss"])

    def test_blocks(self):
        b = self.runs[0][3].blocks(level=2, min_post=0.9)
        self.assertTrue(len(b))
        self.assertTrue(b.lineage.str.len().eq(2).all())
        self.assertTrue((b.posterior >= 0.9).all())



class Siblings(unittest.TestCase):
    """Three phased siblings: the joint model names the parents' copies
    from every sibling's claims at once."""

    @classmethod
    def setUpClass(cls):
        ped, via = sm.ancestry(depth=4, siblings=3, relatives_per_couple=2)
        cls.sim = sm.simulate(ped, seed=2)
        cls.sibs = ["sib1", "sib2", "sib3"]
        segs = sm.detect(cls.sim, cls.sibs, seed=2, matches=list(via))
        cls.claims = cm.claims_from_segments(segs, via)
        labels = sm.copy_labels(cls.sim, cls.sibs, seed=2)
        cls.J = cm.SiblingCopyModel(labels, depth=3).fit(cls.claims, lengths_cm=sm.CHROM_CM)

    def test_labels_from_truth(self):
        labels = sm.copy_labels(self.sim, ["sib1"], seed=1)
        self.assertEqual(set(labels.label), {0, 1})
        self.assertEqual(set(labels.parent), {"F", "M"})

    def test_joint_beats_single(self):
        s = "sib2"
        single = cm.CopyModel(depth=3).fit(self.claims[self.claims.subject == s], lengths_cm=sm.CHROM_CM)
        a1 = cm.accuracy(single, self.sim, s, 2, n=400, seed=3)
        a2 = cm.accuracy(self.J.for_sibling(s), self.sim, s, 2, n=400, seed=3)
        for side in "FM":
            self.assertGreater(a2[side]["accuracy"], a1[side]["accuracy"])
            self.assertGreater(a2[side]["called_share"], 0.7)
            self.assertGreater(a2[side]["accuracy_when_called"], 0.95)

    def test_calibrated(self):
        _, d = cm.calibration(self.J.for_sibling("sib2"), self.sim, "sib2", level=2, n=1000, seed=3)
        self.assertLess(d["ece"], 0.05, d)

    def test_label_error_caps_confidence(self):
        P = self.J.for_sibling("sib1").post[("1", "F")]
        S = cm.states("F", 3)
        gp = P[:, [s.startswith("FF") for s in S]].sum(1)
        self.assertLessEqual(gp.max(), 1 - self.J.label_error + 1e-9)

    def test_verdicts_cover_every_sibling(self):
        v = self.J.verdicts()
        self.assertEqual(set(v.subject), set(self.sibs))
        self.assertGreater((v.verdict == "agrees").mean(), 0.5)


class Placement(unittest.TestCase):
    """Matches the model was not fitted on, placed through it: half the
    relatives give the claims, the other half's segments are placed."""

    @staticmethod
    def _score(placed, sim):
        real = placed[placed.real & placed.parent.isin(["F", "M"])]
        truth = [sim.lineage(r.subject, r.chrom, (r.start + r.end) / 2)["FM".index(r.parent)][:2]
                 for r in real.itertuples()]
        called = real.cm_grandparent != ""
        right = (real.cm_grandparent == pd.Series(truth, index=real.index))[called]
        return called.mean(), right.mean()

    def _run(self, siblings):
        ped, via = sm.ancestry(depth=4, siblings=siblings, relatives_per_couple=2)
        sim = sm.simulate(ped, seed=4)
        sibs = [f"sib{i}" for i in range(1, siblings + 1)]
        segs = sm.detect(sim, sibs, seed=4, matches=list(via))
        known = {m: c for m, c in via.items() if m.endswith("_1")}
        claims = cm.claims_from_segments(segs, known)
        if siblings > 1:
            J = cm.SiblingCopyModel(sm.copy_labels(sim, sibs, seed=4), depth=3).fit(claims, lengths_cm=sm.CHROM_CM)
            models = {s: J.for_sibling(s) for s in sibs}
        else:
            models = {"sib1": cm.CopyModel(depth=3).fit(claims, lengths_cm=sm.CHROM_CM)}
        new = segs[~segs.match.isin(known)].assign(parent=lambda d: d.true_copy)
        return self._score(cm.place(new, models), sim)

    def test_single_donor(self):
        share, acc = self._run(1)
        self.assertGreater(share, 0.1)
        self.assertGreater(acc, 0.9)

    def test_phased_siblings(self):
        share, acc = self._run(3)
        self.assertGreater(share, 0.6)
        self.assertGreater(acc, 0.97)

    def test_unknown_side_gives_both_readings(self):
        ped, via = sm.ancestry(depth=3, relatives_per_couple=1)
        sim = sm.simulate(ped, seed=1)
        segs = sm.detect(sim, ["sib1"], seed=1, matches=list(via))
        m = cm.CopyModel(depth=3).fit(cm.claims_from_segments(segs, via), lengths_cm=sm.CHROM_CM)
        out = cm.place(segs.assign(parent=""), {"sib1": m})
        self.assertTrue((out.cm_grandparent == "").all())
        self.assertTrue(out.cm_if_paternal.isin(["", "FF", "FM"]).all())
        self.assertTrue((out.cm_if_maternal != "").any())


if __name__ == "__main__":
    unittest.main()
