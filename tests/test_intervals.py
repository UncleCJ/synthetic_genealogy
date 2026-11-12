"""Intervals and the genetic map, on synthetic numbers only."""
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import intervals as iv  # noqa: E402


class Genome(unittest.TestCase):
    def test_overlap_and_jaccard(self):
        self.assertEqual(iv.overlap(0, 10, 5, 20), 5)
        self.assertEqual(iv.overlap(0, 10, 10, 20), 0)
        np.testing.assert_array_equal(iv.overlap(0, 10, np.array([2, 12]), np.array([4, 14])), [2, 0])
        self.assertAlmostEqual(float(iv.jaccard(0, 10, 5, 15)), 5 / 15)
        self.assertEqual(float(iv.jaccard(0, 1, 2, 3)), 0.0)

    def test_merge_and_covered(self):
        self.assertEqual(iv.merge([(5, 8), (0, 3), (2, 4)]), [[0, 4], [5, 8]])
        self.assertEqual(iv.merge([(0, 3), (4, 6)], gap=1), [[0, 6]])
        # overlapping others are counted once
        self.assertEqual(iv.covered(0, 10, [(2, 6), (4, 8), (20, 30)]), 6)

    def test_interval_set(self):
        a = iv.IntervalSet.of("3", [(30, 40), (0, 10), (5, 15), (50, 50)])
        b = iv.IntervalSet.of("3", [(12, 35), (38, 60)])
        self.assertEqual(a.spans, ((0, 15), (30, 40)))          # merged, empty dropped
        self.assertEqual((a | b).spans, ((0, 60),))
        self.assertEqual((a & b).spans, ((12, 15), (30, 35), (38, 40)))
        self.assertEqual((a - b).spans, ((0, 12), (35, 38)))
        self.assertEqual((b - a).spans, ((15, 30), (40, 60)))
        self.assertEqual(a.bp, 25)
        self.assertEqual((a & b).bp + (a - b).bp, a.bp)
        self.assertEqual(a.longest(), 15)
        gm = iv.GeneticMap.flat(rate=2.0)                        # 2 cM per Mb
        big = iv.IntervalSet.of("3", [(0, 1e6), (2e6, 4e6)])
        self.assertAlmostEqual(big.cm(gm), 6.0)
        self.assertAlmostEqual(big.longest(gm), 4.0)
        empty = iv.IntervalSet.of("3")
        self.assertFalse(empty)
        self.assertEqual(empty.longest(), 0.0)
        self.assertEqual((a & empty).bp, 0)
        with self.assertRaises(ValueError):
            a | iv.IntervalSet.of("4", [(0, 1)])

    def test_bins(self):
        np.testing.assert_array_equal(iv.bins([0, 1.5e6], [1e6, 2.5e6], 1e6), [0, 2])


class Map(unittest.TestCase):
    def test_flat(self):
        gm = iv.GeneticMap.flat()
        self.assertTrue(gm.is_flat)
        self.assertAlmostEqual(float(gm.length("1", 1e6, 3e6)), 2.0)
        self.assertAlmostEqual(float(gm.bp("1", 2.0)), 2e6)

    def test_interpolation_and_files(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            # HapMap / Bherer style: chrom, bp, rate, cM (with a header)
            (d / "a.txt").write_text("Chromosome Position(bp) Rate(cM/Mb) Map(cM)\n"
                                     "chr1 1000000 1.0 0.0\nchr1 2000000 3.0 1.0\n"
                                     "chr1 3000000 0.0 4.0\n")
            # one file per chromosome, 3 columns
            (d / "genetic_map_chr2.txt").write_text("position rate cM\n0 1 0\n1000000 1 2\n")
            gm = iv.GeneticMap.read(d)
            self.assertEqual(sorted(gm.points), ["1", "2"])
            self.assertAlmostEqual(float(gm.cm("1", 1.5e6)), 0.5)
            self.assertAlmostEqual(float(gm.length("1", 1.5e6, 2.5e6)), 2.0)
            self.assertAlmostEqual(float(gm.cm("1", 9e6)), 4.0)      # flat beyond the end
            self.assertAlmostEqual(float(gm.bp("1", 2.5)), 2.5e6)
            self.assertAlmostEqual(float(gm.cm("2", 5e5)), 1.0)
            # PLINK
            (d / "p.map").write_text("3 rs1 0.0 100\n3 rs2 1.5 200\n")
            self.assertAlmostEqual(float(iv.GeneticMap.read(d / "p.map").cm("3", 150)), 0.75)

    def test_load_without_config_is_flat(self):
        gm = iv.GeneticMap.load({"data_dir": Path(".")}, quiet=True)
        self.assertTrue(gm.is_flat)


class Years(unittest.TestCase):
    def test_year_runs(self):
        # closed year spans: touching years join with gap=1, ints stay ints
        r = iv.runs([("b", 1856, 1860), ("a", 1850, 1855), ("c", 1862, 1863)],
                    lambda t: (t[1], t[2]), gap=1)
        self.assertEqual([(a, b, [t[0] for t in its]) for a, b, its in r],
                         [(1850, 1860, ["a", "b"]), (1862, 1863, ["c"])])
        self.assertIsInstance(r[0][0], int)
        # 1850-1859 covered by 1848-1852 and 1855-1855: 3 + 1 years
        self.assertEqual(iv.year_count(1850, 1859, [(1848, 1852), (1855, 1855)]), 4)

    def test_parse(self):
        P = iv.YearSpan.parse
        self.assertEqual(P("12 MAR 1850"), iv.YearSpan(1850, 1850, "day"))
        self.assertEqual(P("ABT 1850").as_tuple(), (1850, 1850))
        self.assertTrue(P("ABT 1850").approx)
        self.assertEqual(P("BEF 1850").as_tuple(), (None, 1850))
        self.assertEqual(P("TO 1856").as_tuple(), (None, 1856))
        self.assertEqual(P("AFT 1850").as_tuple(), (1850, None))
        self.assertEqual(P("FROM 1850").as_tuple(), (1850, None))
        self.assertEqual(P("FROM 1850 TO 1856").as_tuple(), (1850, 1856))
        self.assertEqual(P("BET 1850 AND 1855").as_tuple(), (1850, 1855))
        self.assertEqual(P("").precision, "none")
        self.assertEqual(P(None).as_tuple(), (None, None))

    def test_overlaps(self):
        P = iv.YearSpan.parse
        self.assertTrue(P("FROM 1850 TO 1856").overlaps(P("1855")))
        self.assertTrue(P("AFT 1850").overlaps(P("1900")))
        self.assertFalse(P("BEF 1850").overlaps(P("1851")))
        self.assertFalse(P("").overlaps(P("1851")))


if __name__ == "__main__":
    unittest.main()
