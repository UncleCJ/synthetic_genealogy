"""Keys and lineage codes."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import identity as idn  # noqa: E402
import lineage as lin  # noqa: E402

PAIR = "D-00000000-0000-0000-0000-00000000000A-D-0000000B-0000-0000-0000-00000000000C"


class Keys(unittest.TestCase):
    def test_name_keys(self):
        self.assertEqual(idn.name_key("  Eva* Anna-Karin  Example, Jr. "), "eva anna karin example jr")
        self.assertEqual(idn.ftdna_key("Ancelet- Jr."), "ancelet jr.")

    def test_myheritage(self):
        self.assertEqual(idn.mh_pair(PAIR)[1], "D-0000000B-0000-0000-0000-00000000000C")
        self.assertEqual(idn.mh_pair("nonsense"), (None, None))
        self.assertEqual(idn.mh_match_in("https://x/?id=" + PAIR.lower() + "&a=1"),
                         "D-0000000B-0000-0000-0000-00000000000C")
        self.assertEqual(idn.mh_match_id(" 0000000b-0000-0000-0000-00000000000c"),
                         "D-0000000B-0000-0000-0000-00000000000C")
        self.assertEqual(idn.key_strength("D-0000000B-0000-0000-0000-00000000000C"), "strong")
        self.assertEqual(idn.key_strength("name:erik example"), "weak")
        self.assertEqual(idn.mh_id(["X", "MH:I7"]), "MH:I7")


    def test_common_surname(self):
        self.assertTrue(idn.common_surname("Anna Andersson"))
        self.assertTrue(idn.common_surname("Kari Olsen"))
        self.assertTrue(idn.common_surname("Brita Persdotter"))
        self.assertFalse(idn.common_surname("Anna Lindqvist"))
        self.assertFalse(idn.common_surname(""))


class Lineage(unittest.TestCase):
    def test_ahnentafel_round_trip(self):
        self.assertEqual(lin.ahnentafel("FMMF"), 22)
        self.assertEqual(lin.ahnentafel(""), 1)
        for n in range(1, 200):
            self.assertEqual(lin.ahnentafel(lin.from_ahnentafel(n)), n)

    def test_prefix_and_couples(self):
        self.assertEqual(lin.via(["FMF", "FMM"]), "FM")
        self.assertEqual(lin.common_prefix(["MF"]), "MF")
        self.assertEqual(lin.common_prefix([]), "")
        self.assertEqual(lin.split(" FMF  FMM "), ["FMF", "FMM"])
        self.assertTrue(lin.is_couple_split(80, 40))
        self.assertFalse(lin.is_couple_split(200, 10))
        self.assertEqual(lin.grandparent("MFM"), "MF")


if __name__ == "__main__":
    unittest.main()
