"""Recursive deduction (grandparent_copies.py) on the simulator only."""
import os
import sys
import unittest

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import grandparent_copies as gc  # noqa: E402
import simulate as sm  # noqa: E402


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


if __name__ == "__main__":
    unittest.main()
