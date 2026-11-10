"""outputs.py: tables through the store read back exactly as their CSV
would; the assertion table matches the assertion files."""
import sys
import tempfile
import unittest
from pathlib import Path

import pandas as pd
from pandas.testing import assert_frame_equal

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import assertions  # noqa: E402
import config  # noqa: E402
import outputs  # noqa: E402


def frame():
    return pd.DataFrame(dict(
        subject=["a", "b", "c"], chrom=["1", "X", "22"], start=[10, 20, 30],
        cM=[7.5, float("nan"), 12.0], lineage=["FM", "", None], ok=[True, False, True]))


class Store(unittest.TestCase):
    def setUp(self):
        self.D = config.DataDir(tempfile.mkdtemp())

    def test_same_as_csv(self):
        outputs.write(self.D, "t.csv", frame(), step="test")
        csv = self.D.layer("output") / "t.csv"
        for dt in (None, {"chrom": str}):
            assert_frame_equal(pd.read_csv(csv, dtype=dt), outputs.read(self.D, "t.csv", dtype=dt))
        self.assertTrue(outputs.has(self.D, "t.csv"))
        self.assertEqual(outputs.artifacts(self.D).step.tolist(), ["test"])
        self.assertEqual(list(outputs.read(self.D, "t.csv", usecols=["cM"]).columns), ["cM"])

    def test_falls_back_to_csv(self):
        out = self.D.layer("output")
        out.mkdir(parents=True)
        frame().to_csv(out / "old.csv", index=False)
        self.assertTrue(outputs.has(self.D, "old.csv"))
        assert_frame_equal(pd.read_csv(out / "old.csv"), outputs.read(self.D, "old.csv"))
        self.assertFalse(outputs.has(self.D, "missing.csv"))

    def test_assertion_table(self):
        doc = pd.DataFrame(dict(subject=["a"], chrom=["3"], start=[1], end=[9], lineage=["MFM"],
                                rule=["child shares it"], match=["erik example"], kind=["lineage"],
                                weight=[10], evidence=["x"], asserted_by=["t"], source=["s"],
                                assertion_id=["anchor:1"]))
        icw = pd.DataFrame(dict(subject=["a"], platform=["P"], match_key=["k"], match=["K"],
                                lineage=["F"], kind=["icw_candidate"], share=[0.8], why=["w"]))
        outputs.write(self.D, assertions.FILES["documented"], doc)
        self.assertIsNone(outputs.read_assertions(self.D, ["documented", "icw"]))   # icw not there yet
        outputs.write(self.D, assertions.FILES["icw"], icw)
        got = assertions.read(self.D, ["documented", "icw"])
        self.assertEqual(got.source_kind.tolist(), ["documented", "icw"])
        self.assertEqual(got.kind.tolist(), ["lineage", "descent"])
        self.assertEqual(got.loc[0, "rule"], "child shares it")              # own columns kept
        self.assertTrue(pd.isna(got.loc[1, "start"]))                        # no interval
        # rewriting one source replaces only its rows
        outputs.write(self.D, assertions.FILES["icw"], icw.iloc[:0])
        self.assertEqual(assertions.read(self.D, ["documented", "icw"]).source_kind.tolist(), ["documented"])


if __name__ == "__main__":
    unittest.main()
