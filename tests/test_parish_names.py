"""Parishes the family's citations never name, read from a full parish list
(a small hand-made list here, in the shape of gazetteer/parish_names.tsv).
Parish, town and county names are public; no people."""
import unittest

import parish_names as P
import volumes as v


def item(qid, kind, label, county="", succ="", pred="", aliases=""):
    return dict(qid=qid, kind=kind, label=label, aliases=aliases, archive="", county=county,
                lat="", lon="", succ=succ, pred=pred)


ROWS = [
    item("Q1", "socken", "Östra Eneby socken", "", succ="Q2"),
    item("Q2", "församling", "Norrköpings Östra Eneby församling", "Östergötlands län", pred="Q1"),
    item("Q3", "församling", "Maria Magdalena församling", "Stockholms län"),
    item("Q4", "församling", "Helsingborgs Maria församling", "Skåne län"),
    item("Q5", "församling", "Sofia församling", "Stockholms län"),
    item("Q6", "församling", "Jönköpings Sofia församling", "Jönköpings län"),
    item("Q7", "församling", "Haurida församling", "Jönköpings län"),
    item("Q8", "församling", "Aneby församling", "Jönköpings län"),
    item("Q9", "församling", "Tåstarps församling", "Skåne län"),
    item("Q10", "församling", "Högalids församling", "Stockholms län"),
    item("Q11", "församling", "Ystads stadsförsamling", "Skåne län"),
    item("Q12", "församling", "Bräkne-Hoby församling", "Blekinge län"),
    item("Q13", "församling", "Norra Sandby församling", "Skåne län"),
    item("Q14", "församling", "Stora Malms församling", "Södermanlands län"),
    item("Q15", "församling", "Katrineholm-Stora Malms församling", "Södermanlands län", pred="Q14"),
    item("Q16", "församling", "Riseberga församling", "Skåne län"),
    dict(item("Q17", "församling", "Burlövs församling", "Skåne län"), lat="55.6", lon="13.1"),
]
KOMMUNER = ["Klippans kommun", "Burlövs kommun", "Aneby kommun", "Tranemo kommun", "Ödeshögs kommun", "Ystads kommun"]


def names():
    return P.Names(rows=ROWS, kommuner=KOMMUNER)


def read(places, family=(), cited=()):
    """Parish read from each place; `family` are parishes the family's
    setup names, `cited` parishes its citations name."""
    rows = [dict(tier="mh-record", parish=p) for p in cited]
    rows += [dict(tier="plac-only", event_place=p) for p in places]
    v.normalise(rows, extra_parishes=family, reference=names())
    return [r["parish"] for r in rows[len(cited):]]


class List(unittest.TestCase):
    def test_forms(self):
        n = names()
        label = lambda name, **kw: sorted(n.label(g) for g in n.candidates(name, **kw))
        self.assertEqual(label("Östra Eneby"), ["Norrköpings Östra Eneby"])     # town dropped
        self.assertEqual(label("Ö. Eneby"), ["Norrköpings Östra Eneby"])        # abbreviation
        self.assertEqual(label("N. Sandby"), ["Norra Sandby"])
        self.assertEqual(label("Maria", counties=["Stockholm"]), [])            # "Maria" is no name of Q3
        self.assertEqual(label("Sofia", counties=["Stockholms län"]), ["Sofia"])
        self.assertEqual(label("Brakne-Hoby"), ["Bräkne-Hoby"])                 # letters lost
        self.assertEqual(label("Stora Malm"), ["Stora Malm"])                   # not the merger

    def test_regions(self):
        self.assertEqual(P.counties_of("Malmöhus"), P.counties_of("Skåne län"))
        self.assertEqual(P.counties_of("Alvsborg"), P.counties_of("Västra Götalands län"))
        self.assertTrue(P.counties_of("Småland"))
        self.assertEqual(P.counties_of("Sverige"), set())

    def test_town_and_kommun(self):
        n = names()
        self.assertTrue(n.is_town("Ystad"))
        self.assertFalse(n.is_town("Ystads stadsförsamling"))
        self.assertTrue(n.is_kommun("Aneby"))


class Read(unittest.TestCase):
    def test_town_genitive_and_abbreviation(self):
        self.assertEqual(read(["Gården, Östra Eneby, Norrköping, Östergötlands län, Sverige",
                               "Ö. Eneby, Östergötland"]),
                         ["Norrköpings Östra Eneby"] * 2)
        # a family spelling of the same parish is kept
        self.assertEqual(read(["Östra Eneby, Norrköping"], cited=["Norrköpings Östra Eneby"]),
                         ["Norrköpings Östra Eneby"])

    def test_moves_are_destinations_not_parishes(self):
        got = read(["till Sofia Församling, Stockholm", "Från Byn Till Sofia församling, Stockholm",
                    "till Okänd Församling, Staden"])
        self.assertEqual(got[:2], ["Sofia", "Sofia"])
        self.assertFalse(got[2].lower().startswith("till"))

    def test_kommun_after_parish(self):
        self.assertEqual(read(["Haurida, Aneby, Jönköpings län, Sverige"]), ["Haurida"])
        # a kommun the family's citations name as a parish keeps its place
        self.assertEqual(read(["Åryd, Ödeshög, Östergötlands län"], cited=["Ödeshög", "Åryd"]),
                         ["Ödeshög"])

    def test_written_county_rules_out_namesakes(self):
        self.assertEqual(read(["Tåstarp, Tranemo, Älvsborgs, Västergötland"], cited=["Tranemo"]),
                         ["Tranemo"])

    def test_lone_names_and_towns(self):
        self.assertEqual(read(["Högalid", "Högalid, Stockholm", "Ystad",
                               "Ystads stadsförsamling, Malmöhus, Sverige"]),
                         ["", "Högalid", "", "Ystad"])

    def test_bracket_style(self):
        """MyHeritage's places without commas (plac_parts splits them)."""
        self.assertEqual(read(["Riseberga (Klippans Kommun) (Skåne Län) Skåne Sverige",
                               "Byn (Gatan 1) (Burlöv Kommun) (Skåne Län) Skåne Sverige (Kyrkobokförd Burlöv)"]),
                         ["Riseberga", "Burlöv"])

    def test_explicit_parishes_count_for_every_row(self):
        self.assertEqual(read(["Gården, Okändhem", "Kyrkby, Okändhems socken"]),
                         ["Okändhem", "Okändhem"])


if __name__ == "__main__":
    unittest.main()
