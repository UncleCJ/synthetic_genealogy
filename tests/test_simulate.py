"""The pedigree simulator: its truth must be right before anything is
tested against it."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import simulate as sm  # noqa: E402

GENOME = sum(sm.CHROM_CM.values())


class Truth(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ped = sm.family(twin_fathers=True)
        cls.sim = sm.simulate(cls.ped, seed=3)

    def test_parent_child_share_one_copy_everywhere(self):
        ibd = sm.true_ibd(self.sim, "sib1", "M")
        self.assertTrue((ibd.copy_a == "M").all())
        self.assertAlmostEqual(ibd.cM.sum(), GENOME, delta=1e-6)

    def test_full_siblings_share_about_half(self):
        tot = sm.true_ibd(self.sim, "sib1", "sib2").cM.sum()
        # half-identical over both copy pairs: expected about GENOME (2 x 50%)
        self.assertTrue(0.6 * GENOME < tot < 1.4 * GENOME, tot)

    def test_twins_and_twin_cousin(self):
        self.assertIs(self.sim.genomes["uncle_twin"], self.sim.genomes["F"])
        ibd = sm.true_ibd(self.sim, "sib1", "twin_cousin")
        self.assertTrue((ibd.copy_a == "F").all())       # only through the fathers
        self.assertTrue(0.3 * GENOME < ibd.cM.sum() < 0.7 * GENOME)

    def test_lineage_codes(self):
        f, m = self.sim.lineage("sib1", "1", 100e6)
        self.assertRegex(f, r"^F[FM]{2}$")
        self.assertRegex(m, r"^M[FM]{2}$")
        # the second cousin through FF shares only on the FF branch
        ibd = sm.true_ibd(self.sim, "sib1", "c2_FF")
        for r in ibd.itertuples():
            self.assertTrue(self.sim.founder_of(r.founder_copy) in ("FFF", "FFM"))

    def test_stranger_shares_nothing(self):
        self.assertEqual(len(sm.true_ibd(self.sim, "sib1", "stranger")), 0)


class Detection(unittest.TestCase):
    def test_threshold_noise_and_false_segments(self):
        sim, segs = sm.scenario("unrelated kit", seed=5)
        s = segs[segs.match == "stranger"]
        self.assertFalse(s.real.any())                     # only false segments
        sim, segs = sm.scenario("donor + parent", seed=5, false_per_pair=0)
        self.assertTrue((segs.cM >= 7).all())
        mum = segs[(segs.subject == "sib1") & (segs.match == "M")]
        self.assertTrue((mum.true_copy == "M").all())
        self.assertGreater(mum.cM.sum(), 0.9 * GENOME)

    def test_scenarios_run(self):
        for name in sm.SCENARIOS:
            sim, segs = sm.scenario(name, seed=1)
            self.assertGreater(len(segs), 0, name)


if __name__ == "__main__":
    unittest.main()
