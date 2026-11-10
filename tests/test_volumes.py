"""MyHeritage household-examination labels in their written variants, and
a town between farm and parish in a place (synthetic text, no people)."""
import unittest

import volumes as v


def bok(text):
    m = v.MH_BOK.search(v._squash(text))
    return m and (m["town"], m["parish"].replace("_", " ").strip(), m["series"], m["vol"])


class Labels(unittest.TestCase):
    def test_variants(self):
        cases = {
            "Bok: LandSwedenBokAnderstorp AIIa2, 1911 - 1921 ProvinsSmåland":
                (None, "Anderstorp", "AIIa", "2"),
            "Bok: Land:SwedenBok:Källeryd_AIIa3-296, 1921 - 1941 Provins:":
                (None, "Källeryd", "AIIa", "3"),
            "BokStora Åby AI 20, 1891 - 1895": (None, "Stora Åby", "AI ", "20"),
            "Bok: Land Sweden, Bok Anderstorp AI14, 1891 - 1899": (None, "Anderstorp", "AI", "14"),
            "Bok: \tLandSwedenBokSigtuna, Sankt Olof och Sankt Per AI16, 1876 - 1880\tProvins":
                ("Sigtuna", "Sankt Olof och Sankt Per", "AI", "16"),
            "Bok: LandSwedenBokRisinge,_Finspångs_kyrkobokföringsdistrikt_AIIa4-2229, 1926 - 1939":
                ("Risinge", "Finspångs kyrkobokföringsdistrikt", "AIIa", "4"),
        }
        for text, want in cases.items():
            self.assertEqual(bok(text), want, text)

    def test_town_skipped_in_place(self):
        rows = [dict(tier="mh-record", parish="Sankt Olof och Sankt Per", town="Sigtuna"),
                dict(tier="plac-only", event_place="Gården, Sigtuna, Sankt Olof och Sankt Per, "
                                                   "Stockholms, Uppland, Sweden"),
                dict(tier="plac-only", event_place="Gården, Byn, Sankt Olof och Sankt Per")]
        v.normalise(rows)
        self.assertEqual((rows[1]["parish"], rows[1]["farm"]), ("Sankt Olof och Sankt Per", "Gården"))
        self.assertEqual(rows[2]["farm"], "Byn")        # no town: the village, as before


if __name__ == "__main__":
    unittest.main()
