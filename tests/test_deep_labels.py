import unittest

import pandas as pd

import deep_labels as dl


def blocks():
    rows = [
        # subject, level, chrom, side, start, end, start_cm, end_cm, lineage, posterior
        ("a", 2, "1", "F", 0, 50e6, 0, 60, "FF", 0.99),
        ("a", 3, "1", "F", 0, 30e6, 0, 40, "FFF", 0.95),
        ("a", 3, "1", "F", 30e6, 50e6, 40, 60, "FFM", 0.6),
        ("a", 2, "1", "M", 0, 50e6, 0, 60, "MF", 0.99),
        ("a", 3, "1", "M", 0, 50e6, 0, 60, "MFM", 0.8),
    ]
    b = pd.DataFrame(rows, columns=["subject", "level", "chrom", "side", "start", "end",
                                    "start_cm", "end_cm", "lineage", "posterior"])
    return b.assign(model="siblings")


def claims():
    rows = [
        ("c1", "a", "1", "FFFM", "agrees", 0.9, 20.0, "x", 1e6, 9e6, "name join"),
        ("c2", "a", "1", "MMFF", "conflicts", 0.01, 15.0, "y", 10e6, 20e6, "name join"),
        ("c3", "a", "1", "FF", "agrees", 0.99, 30.0, "z", 1e6, 9e6, "documented"),
    ]
    return pd.DataFrame(rows, columns=["claim_id", "subject", "chrom", "lineage", "verdict", "support",
                                       "cM", "match", "start", "end", "join"])


class DeepLabels(unittest.TestCase):
    def test_coverage_bands(self):
        cov = dl.coverage(blocks(), "a")
        self.assertEqual(cov.loc["FFF", "sure"], 40)
        self.assertEqual(cov.loc["FFM", "leaning"], 20)
        self.assertEqual(cov.loc["MFM", "likely"], 60)

    def test_claims_only_deep(self):
        t = dl.claim_table(claims(), "a")
        self.assertEqual(set(t.index), {"FFF", "MMF"})        # the two-letter claim names no great-grandparent
        self.assertEqual(t.loc["MMF", "conflicts"], 1)
        self.assertEqual(t.loc["FFF", "name_join"], 1)

    def test_conflict_read_at_grandparent(self):
        k = dl.conflicts(blocks(), claims(), "a")
        self.assertEqual(len(k), 1)
        self.assertEqual(k.model_reads.iloc[0], "MFM")
        self.assertEqual(k.differs_at.iloc[0], "grandparent")

    def test_confirm_next_name_joins_only(self):
        k = dl.confirm_next(claims())
        self.assertTrue((k.lineage.str.len() >= 3).all())
        self.assertNotIn("z", set(k.match))                    # documented, not a name join
        self.assertEqual(k.conflicts.sum(), 1)


if __name__ == "__main__":
    unittest.main()
