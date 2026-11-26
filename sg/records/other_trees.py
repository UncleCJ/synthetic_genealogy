"""Other people's trees that hold our people, read as pointers to people who
research the family, not as evidence (docs/records.md, "Other trees").

- MyHeritage sites: a Smart Match cites "<Name> Web Site", but the title is
  not the tree (MyHeritage often writes the matching site's name, or ours).
  The tree is the site token in the cited URL,
  `/person-<n>_<SITE>_<TREE>/<name>`. Its coverage (which of our people it
  holds) places its keeper: people put in their own children and
  grandchildren, so the youngest people a tree holds point to whoever keeps it.
- WikiTree: profiles linked to ours by walking parents from a seed profile
  (family.toml `[wikitree] profile`, the proband's own), then by searching
  WikiTree for the direct ancestors still unlinked (name and birth date) and
  walking up from each hit. A profile's managers are its genealogists.
- Shared world trees (Geni, FamilySearch): everyone edits them, so they point
  to no one; one row each, counted only.

Unvalidated: the keeper guess is a hint; a tree's activity is unknown (MyHeritage
dates few of these citations). Run with --wikitree to ask WikiTree (public API,
answers cached in data/cache/wikitree.json); without it, the cache is read only.
"""
import csv
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from datetime import date

API = "https://api.wikitree.com/api.php"
APP_ID = "synthetic_genealogy"
UA = "synthetic-genealogy/0.1 (other_trees.py; research sketch)"
FIELDS = ("Id,Name,FirstName,MiddleName,LastNameAtBirth,BirthDate,DeathDate,"
          "Gender,Father,Mother,Managers")
SITE = re.compile(r"/person-\d+_([A-Z0-9]+)_")
SHARED = {"Geni": re.compile(r"\bGeni\b", re.I), "FamilySearch": re.compile(r"FamilySearch", re.I)}
MONTHS = {m: i for i, m in enumerate(
    "JAN FEB MAR APR MAY JUN JUL AUG SEP OCT NOV DEC".split(), 1)}
OLD = date.today().year - 100              # born before this: searched on WikiTree


def iso(gedcom_date):
    """'23 MAR 1827' -> '1827-03-23'; a year alone, or a qualified date
    ('ABT 1827', 'BET ...'), gives the year only; '' when none."""
    d = (gedcom_date or "").upper().split()
    if len(d) == 3 and d[0].isdigit() and d[1] in MONTHS and d[2].isdigit():
        return f"{d[2]}-{MONTHS[d[1]]:02d}-{int(d[0]):02d}"
    y = re.search(r"\b(\d{4})\b", " ".join(d))
    return y[1] if y else ""


def _year(s):
    m = re.match(r"(\d{4})", s or "")
    return int(m[1]) if m and m[1] != "0000" else None


# --- MyHeritage sites and shared trees, from volume_refs.csv ---------------

def site_key(url):
    m = SITE.search(url or "")
    return m[1] if m else ""


def _coverage(rows, tree):
    """Columns shared by every kind: people, ancestors, branches, youngest, living."""
    people = {r["person"]: r for r in rows}
    born = {p: (tree.people.get(p, {}).get("birth") or {}).get("year") for p in people}
    youngest = max(people, key=lambda p: born[p] or 0)
    living = [p for p in people if born[p] and born[p] >= OLD
              and not tree.people.get(p, {}).get("death")]
    return dict(people=len(people),
                ancestors=sum(1 for r in people.values() if r.get("kin") == "ancestor"),
                branches=" ".join(b for b, _ in Counter(
                    r.get("branch") or "?" for r in people.values()).most_common()),
                youngest=people[youngest].get("label", youngest), living=len(living))


def myheritage_trees(refs, tree):
    """One row per MyHeritage site among the tree-tier citations."""
    by = defaultdict(list)
    for r in refs:
        if r.get("tier") == "tree" and site_key(r.get("url")):
            by[site_key(r["url"])].append(r)
    out = []
    for key, rs in by.items():
        row = dict(kind="myheritage", key=key, **_coverage(rs, tree))
        youngest = max(rs, key=lambda r: (tree.people.get(r["person"], {}).get("birth") or {})
                       .get("year") or 0)
        titles = Counter(r.get("source_title", "") for r in rs)
        dates = sorted({r["cite_date"] for r in rs if r.get("cite_date")}, key=_year)
        row.update(title=" / ".join(t for t, _ in titles.most_common()), link=youngest["url"],
                   note=f"cited {dates[0]}" if dates else "")
        out.append(row)
    return out


def shared_trees(refs, tree):
    out = []
    for name, rx in SHARED.items():
        rs = [r for r in refs if r.get("tier") == "tree" and rx.search(r.get("source_title", ""))]
        if rs:
            out.append(dict(kind="shared", key=name, title=rs[0]["source_title"], link="",
                            note="edited by everyone: points to no one", **_coverage(rs, tree)))
    return out


# --- WikiTree --------------------------------------------------------------

class WikiTree:
    """The public API, cached by query; `fetch` False reads the cache only."""

    def __init__(self, cache_path, fetch=False):
        self.path, self.fetch = cache_path, fetch
        self.cache = json.loads(cache_path.read_text(encoding="utf-8")) if cache_path.exists() else {}
        self.calls = 0

    def save(self):
        if self.calls:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(self.cache, ensure_ascii=False, indent=0), encoding="utf-8")

    def get(self, **params):
        q = urllib.parse.urlencode(sorted(params.items()))
        if q not in self.cache and self.fetch:
            self.cache[q] = self._ask(q)
            self.calls += 1
        return self.cache.get(q)

    def _ask(self, q):
        url = f"{API}?{q}&appId={APP_ID}"
        for attempt in range(4):
            time.sleep(1)
            try:
                req = urllib.request.Request(url, headers={"User-Agent": UA})
                ans = json.load(urllib.request.urlopen(req, timeout=60))
            except OSError:
                time.sleep(5 * (attempt + 1))
                continue
            if isinstance(ans, list) and ans and ans[0].get("status") == "Limit exceeded.":
                time.sleep(30 * (attempt + 1))
                continue
            return ans
        raise SystemExit(f"WikiTree did not answer: {url}")

    def family(self, key, depth=10):
        """Profile `key` and its ancestors: {numeric id: profile}, and key's id."""
        ans = self.get(action="getPeople", keys=key, ancestors=depth, fields=FIELDS)
        if not ans:
            return {}, None
        people = ans[0].get("people") or {}
        top = (ans[0].get("resultByKey") or {}).get(key, {}).get("Id")
        return {int(k): v for k, v in people.items() if int(k) > 0}, top

    def search(self, first, last, year):
        ans = self.get(action="searchPerson", FirstName=first, LastName=last,
                       BirthDate=str(year), fields=FIELDS, limit=50)
        return (ans[0].get("matches") or []) if ans else []


SPELLING = (("th", "t"), ("ph", "f"), ("w", "v"), ("c", "k"), ("q", "k"), ("z", "s"))


def _names(text):
    """Given names as spelling-free stems: Mathilda and Matilda, Jacob and
    Jakob, Mattis and Mats meet (lower case, old spellings, doubled letters
    folded, the first three letters kept)."""
    out = set()
    for w in re.split(r"[\s\-()]+", (text or "").lower()):
        for a, b in SPELLING:
            w = w.replace(a, b)
        w = re.sub(r"(.)\1", r"\1", w)
        if w:
            out.add(w[:3])
    return out


def agrees(ours, wt):
    """Same person by name and birth: a given name in common (when WikiTree
    shows one) and birth years within 2 (10 before 1700, where births are
    estimated) when both are known."""
    wt_given = _names(f"{wt.get('FirstName', '')} {wt.get('MiddleName', '')}")
    our_given = _names(ours.get("given"))
    if wt_given and our_given and not (wt_given & our_given):
        return False
    a, b = (ours.get("birth") or {}).get("year"), _year(wt.get("BirthDate"))
    return not (a and b and abs(a - b) > (10 if min(a, b) < 1700 else 2))


def walk(tree, people, ours, wt_id, links, how):
    """Link ours to WikiTree profile wt_id and up through both trees' parents
    while they agree; a disagreeing parent is noted, not linked."""
    q = [(ours, wt_id, how)]
    while q:
        o, w, h = q.pop()
        wp = people.get(w)
        if not wp or o in links:
            continue
        links[o] = dict(wt=wp, how=h)
        for par in tree.parents(o):
            pid = wp.get("Father" if tree.people[par]["sex"] == "M" else "Mother") or 0
            if pid > 0 and par not in links and pid in people:
                if agrees(tree.people[par], people[pid]):
                    q.append((par, pid, "walk"))
                else:
                    links.setdefault(("conflict", par), dict(wt=people[pid], how="conflict"))


def search_one(tree, wt, ours):
    """The one WikiTree profile for an ancestor of ours: same given name and
    birth date (or year, when ours has only a year), else None and the count."""
    p = tree.people[ours]
    born = iso((p.get("birth") or {}).get("date"))
    first = p.get("call") or (p.get("given") or "").split(" ")[0]
    if not (first and p.get("surname") and born):
        return None, 0
    hits = [m for m in wt.search(first, p["surname"], born[:4]) if agrees(p, m)
            and ((m.get("BirthDate") or "").startswith(born) if len(born) == 10
                 else _year(m.get("BirthDate")) == int(born[:4]))]
    return (hits[0], 1) if len(hits) == 1 else (None, len(hits))


def _searchable(tree, i):
    p = tree.people[i]
    y = (p.get("birth") or {}).get("year")
    return bool(p.get("death")) or (y is not None and y < OLD)


def link_wikitree(tree, proband, seed, wt):
    """{our xref: {wt, how}} (and ("conflict", xref) keys for disagreements)."""
    links = {}
    people, top = wt.family(seed)
    if top:
        walk(tree, people, tree.id(proband), top, links, "seed")
    ambiguous = {}
    for i, _ in tree.ancestors(tree.id(proband)):
        if i in links or i in ambiguous or not _searchable(tree, i):
            continue
        hit, n = search_one(tree, wt, i)
        if hit:
            people, top = wt.family(hit["Name"])
            walk(tree, people, i, top or hit.get("Id"), links, "search")
        elif n:
            ambiguous[i] = n
    return links, ambiguous


def wikitree_trees(links, refs_by_person, tree, seed):
    """One row per WikiTree manager: the profiles of ours they manage."""
    by = defaultdict(list)
    for o, link in links.items():
        if isinstance(o, tuple):
            continue
        for m in link["wt"].get("Managers") or []:
            by[m["Name"]].append(refs_by_person.get(o) or dict(person=o, label=tree.label(o)))
    return [dict(kind="wikitree", key=name, title="WikiTree", link=f"https://www.wikitree.com/wiki/{name}",
                 note="your own profile" if name == seed else "", **_coverage(rs, tree))
            for name, rs in by.items()]


def _person(x, refs_by_person, tree, kin):
    """mh_id, label, kin, branch: from the person's citation row, else the tree."""
    from sg.common import identity
    r = refs_by_person.get(x) or {}
    k = kin.get(x, ("", "", ""))
    return dict(mh_id=r.get("mh_id") or identity.mh_id(tree.people[x]["facts"]) or "",
                label=r.get("label") or tree.label(x), kin=r.get("kin") or k[0],
                branch=r.get("branch") or k[1])


def link_rows(links, ambiguous, refs_by_person, tree, kin):
    out = []
    for o, link in links.items():
        conflict = isinstance(o, tuple)
        x = o[1] if conflict else o
        wp = link["wt"]
        out.append(dict(**_person(x, refs_by_person, tree, kin), wikitree=wp.get("Name", ""),
                        how=link["how"], wt_birth=wp.get("BirthDate", ""),
                        managers=" ".join(m["Name"] for m in wp.get("Managers") or [])))
    for x, n in ambiguous.items():
        out.append(dict(**_person(x, refs_by_person, tree, kin), wikitree="",
                        how=f"ambiguous ({n} profiles)", wt_birth="", managers=""))
    return out


# --- run -------------------------------------------------------------------

TREE_COLS = ["kind", "key", "title", "people", "ancestors", "branches", "living", "youngest", "link", "note"]
LINK_COLS = ["mh_id", "label", "kin", "branch", "wikitree", "how", "wt_birth", "managers"]


def write_csv(rows, cols, path):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def run(cfg, fetch=False):
    """(tree rows, WikiTree link rows) for the configured family."""
    from sg.common import config
    from sg.readers import gedcom_io
    g = cfg.get("gedcom") or {}
    tree = gedcom_io.Tree(config.path(cfg, g["file"]), **gedcom_io.options(cfg))
    with open(config.path(cfg, "volume_refs.csv"), encoding="utf-8") as f:
        refs = list(csv.DictReader(f))
    by_person = {r["person"]: r for r in refs}
    trees = sorted(myheritage_trees(refs, tree), key=lambda t: -t["people"]) + shared_trees(refs, tree)
    seed = (cfg.get("wikitree") or {}).get("profile")
    links_out = []
    if seed:
        wt = WikiTree(cfg["data_dir"] / "cache/wikitree.json", fetch)
        try:
            links, ambiguous = link_wikitree(tree, g.get("proband"), seed, wt)
        finally:
            wt.save()
        trees += sorted(wikitree_trees(links, by_person, tree, seed), key=lambda t: -t["people"])
        from sg.common import lineage
        links_out = link_rows(links, ambiguous, by_person, tree, lineage.kinship(tree, g.get("proband")))
    return trees, links_out


def _main(argv):
    from sg.common import config
    bad = [a for a in argv if a not in ("--wikitree",)]
    if bad:
        raise SystemExit(f"unknown argument {' '.join(bad)}; known: --wikitree")
    cfg = config.load()
    trees, links = run(cfg, fetch="--wikitree" in argv)
    write_csv(trees, TREE_COLS, config.path(cfg, "other_trees.csv"))
    kinds = Counter(t["kind"] for t in trees)
    print("other trees: " + ", ".join(f"{k} {n}" for k, n in kinds.items()))
    if links:
        write_csv(links, LINK_COLS, config.path(cfg, "wikitree_links.csv"))
        how = Counter(r["how"].split(" (")[0] for r in links)
        print("WikiTree links: " + ", ".join(f"{k} {n}" for k, n in how.items()))
    elif (cfg.get("wikitree") or {}).get("profile") and "--wikitree" not in argv:
        print("no WikiTree answers cached: run with --wikitree")
    print("wrote other_trees.csv" + (" and wikitree_links.csv" if links else ""))


if __name__ == "__main__":
    _main(sys.argv[1:])
