"""Recursive deduction (grandparent_copies.py) on the simulator only."""
import os
import sys
import unittest

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import grandparent_copies as gc  # noqa: E402
import simulate as sm  # noqa: E402

import numpy as np  # noqa: E402


def _seg(line, a, b, chrom="1", subject="sib1", group="child"):
    return dict(line=line, match=line, subject=subject, group=group, chrom=chrom, start_cm=a, end_cm=b, cM=b - a)


class TestJoint(unittest.TestCase):
    """posterior_joint on hand-made segments along one 100 cM chromosome."""
    vis = staticmethod(lambda c, x: {"sib1": np.ones(len(x), bool)})
    bounds = {"1": (0.0, 100.0)}

    def run_(self, rows):
        s = pd.DataFrame(rows)
        child, nc = s[s.group == "child"], s[s.group != "child"]
        return gc.posterior_joint(child, nc, s[s.group == "M"], self.bounds, self.vis)

    def test_two_lines_changing_together_are_her_crossover(self):
        g = self.run_([_seg("a", 5, 50), _seg("b", 50, 95), _seg("m", 60, 90, group="M")])
        e = gc.joint_edges(g)
        self.assertTrue(((e.cm - 50).abs() < 2).any())
        self.assertGreater(g[(g.cm > 60) & (g.cm < 90)].p_M.mean(), 0.9)
        self.assertLess(g[(g.cm > 10) & (g.cm < 45)].p_M.mean(), 0.3)   # across her crossover

    def test_one_line_ending_alone_is_not(self):
        g = self.run_([_seg("a", 20, 50), _seg("b", 5, 95), _seg("m", 60, 90, group="M")])
        e = gc.joint_edges(g)
        self.assertFalse(((e.cm - 50).abs() < 5).any())
        self.assertGreater(g[(g.cm > 25) & (g.cm < 45)].p_M.mean(), 0.9)


class TestJoin(unittest.TestCase):
    def test_join_merges_ibd_through_a_deeper_ancestor(self):
        ped, groups = sm.grandmother(children=2)
        sim = sm.simulate(ped, seed=3)
        cut = sm.true_ibd(sim, "sib1", "gline1")
        joined = sm.true_ibd(sim, "sib1", "gline1", join=True)
        self.assertLessEqual(len(joined), len(cut))
        self.assertAlmostEqual(joined.cM.sum(), cut.cM.sum(), places=6)


class TestEdges(unittest.TestCase):
    def seg(self, rows):
        return pd.DataFrame(rows, columns=["chrom", "start_cm", "end_cm", "line"])

    def test_two_lines_ending_together_make_an_edge(self):
        s = self.seg([("1", 10, 50, "a"), ("1", 50.3, 90, "b"), ("1", 20, 70, "c")])
        E = gc.edges(s, bounds={"1": (0, 100)}, min_lines=2, spans=s)
        self.assertEqual(len(E), 0)                    # c spans 50: the copy is unbroken
        E = gc.edges(s[s.line != "c"], bounds={"1": (0, 100)}, min_lines=2)
        self.assertEqual(list(E.lines), [2])

    def test_sibling_crossover_explains_an_end_cluster(self):
        s = self.seg([("1", 10, 50, "a"), ("1", 50.3, 90, "b")])
        xo = pd.DataFrame([("1", 50.5)], columns=["chrom", "cm"])
        self.assertEqual(len(gc.edges(s, xo, {"1": (0, 100)})), 0)


class TestEvaluate(unittest.TestCase):
    def test_simulated_family(self):
        r = gc.evaluate(1, children=6, mother_side=6, father_side=4)
        self.assertGreater(r["recall"], 0.5)
        self.assertGreater(r["naming_acc"], 0.75)
        self.assertLess(r["pM_P"], r["pM_M_loo"])      # the copy test reads right
        self.assertGreater(r["copy_diff"], 0)          # per relative, held out
        self.assertTrue(0 < r["copy_p"] <= 1)


if __name__ == "__main__":
    unittest.main()
