"""showcase.family_page on a synthetic lens: who is kept, named or blanked."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import familyview  # noqa: E402
import geoview  # noqa: E402
import showcase  # noqa: E402


def person(pid, name, sex, b, d, codes):
    return [pid, name, sex, b, d, codes, 3, 2, 1, 0, str(b or ""), str(d or "")]


class FamilyPage(unittest.TestCase):
    def test_pseudonyms(self):
        data = dict(root="I1", people=[
            person("I1", "Anna Test", "F", 1980, None, [""]),             # proband: bare slot
            person("I2", "Bo Test", "M", 1950, None, ["F"]),               # father: bare slot
            person("I8", "Carl Old", "M", 1850, 1920, ["FFF"]),            # kept ancestor
            person("I9", "Dora Old", "F", 1852, 1930, ["FFM"]),
            person("I20", "Eva Old", "F", 1880, 1890, []),                 # a daughter of No. 8
            person("I21", "Frans Young", "M", 1905, None, []),             # too young: dropped
        ], life={"I8": [["OCCU", "1880", "Gyllenfors", "Torpare", None, ""],
                        ["EVEN", "1881", "", "a note naming Carl Old", None, ""]],
                 "I1": [["BIRT", "1980", "Somewhere", "", None, ""]]},
            refs={"I8": [["birth", "", "Vol 1", "1850", "3", "https://www.myheritage.se/x", "mh-record", "P", 1]]},
            trees={}, fams=[["F1", "I8", "I9", ["I4", "I20", "I21"], 1875, "1875", None],
                            ["F2", "I2", None, ["I1"], 1970, "1970", None]])
        data["people"].append(person("I4", "Gun Test", "M", 1920, 1990, ["FF"]))
        with tempfile.TemporaryDirectory() as t:
            src, dst = Path(t) / "family.html", Path(t) / "out.html"
            familyview.write(src, data)
            showcase.family_page(src, dst)
            _, d, _ = geoview.embedded(dst.read_text(encoding="utf-8"))
        names = {p[0]: p[1] for p in d["people"]}
        self.assertEqual(names, {"A1": "No. 1", "A2": "No. 2", "A4": "No. 4", "A8": "No. 8",
                                 "A9": "No. 9", "A8c1": "Daughter 1 of No. 8"})
        P = {p[0]: p for p in d["people"]}
        self.assertIsNone(P["A2"][3])                          # slots carry no years
        self.assertEqual(P["A8"][3], 1850)
        self.assertEqual(set(d["life"]), {"A8"})
        self.assertEqual([e[3] for e in d["life"]["A8"]], ["Torpare", ""])
        self.assertEqual(d["refs"]["A8"][0][5], "")            # MyHeritage link gone
        self.assertEqual(d["root"], "A1")
        fams = {tuple(f[1:3]): f for f in d["fams"]}
        self.assertEqual(fams[("A8", "A9")][3], ["A4", "A8c1"])
        self.assertIsNone(fams[("A2", None)][4])               # a slot's marriage is undated
        self.assertNotIn("Old", str(d))


if __name__ == "__main__":
    unittest.main()
