"""Other trees: MyHeritage sites keyed by the URL's site token, and WikiTree
profiles linked by walking parents and by search (synthetic people, a fake
API answer table, no network)."""
import unittest

from sg.records import other_trees as ot


class FakeTree:
    """Child @C@ with father @F@ and mother @M@; @F@'s father @G@."""
    def __init__(self):
        P = lambda i, given, sex, y, d=None: dict(  # noqa: E731
            id=i, given=given, surname="Exempel", call="", sex=sex,
            birth=dict(date=d or str(y), year=y), death=None if y > 1950 else {"date": ""})
        self.people = {"@C@": P("@C@", "Kim", "M", 1970), "@F@": P("@F@", "Per", "M", 1940),
                       "@M@": P("@M@", "Eva", "F", 1942), "@G@": P("@G@", "Olof", "M", 1900, "1 MAR 1900")}
        self._par = {"@C@": ["@F@", "@M@"], "@F@": ["@G@"]}

    def id(self, x):
        return x

    def parents(self, i):
        return self._par.get(i, [])

    def ancestors(self, i):
        out, q = [], [i]
        while q:
            for p in self.parents(q.pop()):
                out.append((p, ""))
                q.append(p)
        return out

    def label(self, i):
        return self.people[i]["given"]


class FakeWikiTree(ot.WikiTree):
    def __init__(self, answers):
        self.cache, self.fetch, self.calls, self.answers = {}, False, 0, answers

    def get(self, **params):
        return self.answers.get((params["action"], params.get("keys") or params.get("FirstName")))


def profile(i, name, first, born, father=0, mother=0, manager="Keeper-1"):
    return dict(Id=i, Name=name, FirstName=first, BirthDate=born, Father=father, Mother=mother,
                Managers=[dict(Name=manager)])


class OtherTrees(unittest.TestCase):
    def test_iso_dates(self):
        self.assertEqual(ot.iso("1 MAR 1900"), "1900-03-01")
        self.assertEqual(ot.iso("ABT 1900"), "1900")
        self.assertEqual(ot.iso(""), "")

    def test_names_agree_across_spellings(self):
        ours = dict(given="Mathilda Sofia", birth=dict(year=1871))
        self.assertTrue(ot.agrees(ours, dict(FirstName="Matilda", BirthDate="1871-07-10")))
        self.assertTrue(ot.agrees(dict(given="Mattis", birth=dict(year=1663)),
                                  dict(FirstName="Mats", BirthDate="1655-00-00")))
        self.assertFalse(ot.agrees(ours, dict(FirstName="Eva", BirthDate="1871-00-00")))
        self.assertFalse(ot.agrees(ours, dict(FirstName="Matilda", BirthDate="1875-00-00")))

    def test_namesake_far_away(self):
        ours = dict(birth=dict(place=""), death=dict(place="Ryd, Exempel län, Sverige"))
        self.assertFalse(ot.same_place(ours, dict(BirthLocation="By, Norrsocken, Nordlän")))
        self.assertTrue(ot.same_place(ours, dict(DeathLocation="Ryd, Exempel, Sverige")))
        self.assertTrue(ot.same_place(ours, {}))                  # no places: not refused

    def test_dna_keeper_by_tree_link(self):
        entries = [dict(match="A", subject="x", shared_cM="40", tree_url="https://x/pedigree-tree-SITEA-1500001/a"),
                   dict(match="B", subject="y", shared_cM="90", tree_url="https://x/pedigree-tree-SITEA-1500002/b"),
                   dict(match="C", subject="x", shared_cM="nan", tree_url="nan")]
        self.assertEqual(ot.dna_keepers(entries), {"SITEA": "B (y, 90 cM)"})

    def test_month_must_agree(self):
        self.assertFalse(ot.same_month("BET 7 OCT 1799 AND 11 OCT 1799", "1799-04-03"))
        self.assertTrue(ot.same_month("1799", "1799-04-03"))
        self.assertTrue(ot.same_month("OCT 1799", "1799-00-00"))

    def test_site_token_not_title(self):
        url = "https://www.myheritage.se/person-1000054_SITEAAA_SITEAAA/kim-exempel"
        refs = [dict(person="@C@", tier="tree", url=url, source_title="Ours Web Site", kin="relative",
                     branch="FF", label="Kim"),
                dict(person="@F@", tier="tree", url=url.replace("1000054", "1000055"),
                     source_title="Theirs Web Site", kin="ancestor", branch="FF", label="Per")]
        (row,) = ot.myheritage_trees(refs, FakeTree())
        self.assertEqual((row["key"], row["people"], row["ancestors"]), ("SITEAAA", 2, 1))
        self.assertEqual(row["youngest"], "Kim")       # the keeper hint
        self.assertEqual(row["living"], 1)

    def test_walk_and_search(self):
        tree = FakeTree()
        seed = {"people": {"1": profile(1, "Exempel-1", "", "", father=2, mother=3, manager="Me-1"),
                           "2": profile(2, "Exempel-2", "Per", "1940-01-01", manager="Me-1"),
                           "3": profile(3, "Exempel-3", "Anna", "1942-01-01", manager="Me-1")},
                "resultByKey": {"Exempel-1": {"Id": 1}}}
        hit = profile(9, "Exempel-9", "Olof", "1900-03-01")
        wt = FakeWikiTree({("getPeople", "Exempel-1"): [seed],
                           ("searchPerson", "Olof"): [{"matches": [hit]}],
                           ("getPeople", "Exempel-9"): [{"people": {"9": hit},
                                                         "resultByKey": {"Exempel-9": {"Id": 9}}}]})
        links, ambiguous = ot.link_wikitree(tree, "@C@", "Exempel-1", wt)
        self.assertEqual(links["@F@"]["how"], "walk")
        self.assertEqual(links[("conflict", "@M@")]["how"], "conflict")   # Eva is not Anna
        self.assertEqual(links["@G@"]["wt"]["Name"], "Exempel-9")
        self.assertEqual(links["@G@"]["how"], "search")
        rows = ot.wikitree_trees(links, {}, tree, "Me-1")
        people = {9: dict(Father=8), 8: dict(FirstName="Nils", BirthDate="1870-00-00")}
        tree._par["@G@"] = ["@F@"]                        # a father that is not Nils
        self.assertTrue(ot.parents_disagree(tree, "@G@", people, 9))
        self.assertEqual({r["key"]: r["people"] for r in rows}, {"Me-1": 2, "Keeper-1": 1})


if __name__ == "__main__":
    unittest.main()
