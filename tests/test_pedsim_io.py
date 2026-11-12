"""Ped-sim def writer and output reader, on hand-made files (no Ped-sim
binary needed)."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import simulate as sm  # noqa: E402


class PedsimDef(unittest.TestCase):
    def test_ancestry_with_half_sibling(self):
        ped, via = sm.ancestry(depth=3, relatives_per_couple=1)
        ped.add("hs_dad", "M")
        ped.add("halfsib", "F", father="hs_dad", mother="M")
        text, ids = sm.pedsim_def(ped, name="t", copies=2)
        lines = text.splitlines()
        self.assertEqual(lines[0], "def t 2 4")
        self.assertEqual(len(lines), 5)
        self.assertNotIn("hs_dad", ids)              # a founder spouse, Ped-sim's to make
        last = lines[-1].split()
        b_sib, b_hs = ids["sib1"].split("-b")[1].split("-")[0], ids["halfsib"].split("-b")[1].split("-")[0]
        b_m = ids["M"].split("-b")[1].split("-")[0]
        self.assertIn(f"{b_hs}:{b_m}", last)           # the mother with a new spouse
        self.assertTrue(any(t.startswith(f"{b_sib}:") and "_" in t for t in last))

    def test_parent_two_generations_up_is_refused(self):
        ped = sm.Pedigree()
        ped.add("a", "M"); ped.add("b", "F"); ped.add("c", "M", father="a", mother="b")
        ped.add("d", "F"); ped.add("e", "F", father="c", mother="d")
        ped.add("f", "M", father="a", mother="e")      # a is two generations above f
        with self.assertRaises(ValueError):
            sm.pedsim_def(ped)


class FromPedsim(unittest.TestCase):
    def test_reads_mosaics_under_our_names(self):
        ped = sm.Pedigree()
        ped.add("dad", "M"); ped.add("mum", "F"); ped.add("kid", "F", father="dad", mother="mum")
        _, ids = sm.pedsim_def(ped, name="p")
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / "map.simmap").write_text("#chr\tpos\tmale_cM\tfemale_cM\n"
                                          "22\t1000000\t0\t0\n22\t51000000\t40\t60\n")
            fam = {n: "p1" + ids[n] for n in ids}
            (d / "o-everyone.fam").write_text(
                f"p1 {fam['dad']} 0 0 1 -9\np1 {fam['mum']} 0 0 2 -9\n"
                f"p1 {fam['kid']} {fam['dad']} {fam['mum']} 2 -9\n")
            (d / "o.bp").write_text(
                f"{fam['dad']} s0 h0 22|1000000 0:51000000\n{fam['dad']} s0 h1 22|1000000 1:51000000\n"
                f"{fam['mum']} s1 h0 22|1000000 2:51000000\n{fam['mum']} s1 h1 22|1000000 3:51000000\n"
                f"{fam['kid']} s1 h0 22|1000000 0:21000000 1:51000000\n"
                f"{fam['kid']} s1 h1 22|1000000 3:51000000\n")
            sim, = sm.from_pedsim(d / "o", d / "map.simmap", ids, name="p")
        self.assertEqual(sim.ped.people["kid"].father, "dad")
        self.assertEqual(sim.lengths["22"], 50.0)        # average of 40 and 60
        self.assertEqual(sim.lineage("kid", "22", 10e6), ("F", "M"))
        gm = sim.maps["average"]                         # h0 = paternal, and its crossover at 21 Mb
        self.assertEqual(sim.copy_at("kid", "F", "22", float(gm.cm("22", 10e6))), "dad:F")
        self.assertEqual(sim.copy_at("kid", "F", "22", float(gm.cm("22", 40e6))), "dad:M")
        self.assertEqual(sim.copy_at("kid", "M", "22", float(gm.cm("22", 40e6))), "mum:M")
        ibd = sm.true_ibd(sim, "kid", "dad")
        self.assertAlmostEqual(ibd.cM.sum(), 50.0)
        self.assertEqual(set(ibd.copy_a), {"F"})


if __name__ == "__main__":
    unittest.main()
