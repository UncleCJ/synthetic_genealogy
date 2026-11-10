"""config.load(): the setup in family.toml, hand-kept claims merged in
from data/notes/assertions.toml."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import config  # noqa: E402


class HandKept(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        (self.tmp / "data" / "notes").mkdir(parents=True)
        self.fam = self.tmp / "family.toml"
        self.fam.write_text('data_dir = "data"\n[[identity]]\nmatch = "Old Setup"\ntree = "MH:I1"\n')

    def test_merge(self):
        (self.tmp / "data/notes/assertions.toml").write_text(
            '[[identity]]\nmatch = "Erik Example"\ntree = "MH:I42"\n'
            '[[mz_twins]]\na = "MH:I4"\nb = "MH:I5"\n')
        cfg = config.load(self.fam)
        self.assertEqual([x["match"] for x in cfg["identity"]], ["Old Setup", "Erik Example"])
        self.assertEqual(cfg["mz_twins"][0]["b"], "MH:I5")
        self.assertEqual(cfg["anchors"], [])
        self.assertEqual(cfg["assertions_file"].name, "assertions.toml")

    def test_without_notes_file(self):
        cfg = config.load(self.fam)
        self.assertIsNone(cfg["assertions_file"])
        self.assertEqual(len(cfg["identity"]), 1)

    def test_unknown_section(self):
        (self.tmp / "data/notes/assertions.toml").write_text("[gedcom]\nfile = 'x.ged'\n")
        with self.assertRaises(SystemExit):
            config.load(self.fam)

    def test_examples_parse(self):
        root = Path(__file__).resolve().parents[1] / "examples"
        cfg = config.load(root / "family.example.toml")
        self.assertIn("segment_exports", cfg)
        import tomllib
        hand = tomllib.loads((root / "assertions.example.toml").read_text())
        self.assertEqual(set(hand), set(config.HAND_KEPT))


if __name__ == "__main__":
    unittest.main()
