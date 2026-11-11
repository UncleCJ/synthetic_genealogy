"""
Read a GEDCOM 5.5.1 tree (as exported by Gramps or MyHeritage) into a
pedigree graph, and address people from the testers' point of view.

The tree file stays private in `data/`; `family.toml` names it:

    [gedcom]
    file = "tree.ged"
    proband = "MH:I1"        # xref ("@I0001@") or a FACT value; a tester

A person's *lineage code* is the path from the proband up to them, F and M
by the sex of each parent on the way: "FM" is the father's mother, "FMF"
her father. It is the DNA Painter convention used throughout, and the same
information as an Ahnentafel number (F -> 2n, M -> 2n+1). Like Ahnentafel
numbers, codes address paths, not people: under pedigree collapse one
person has several.

Only biological links (PEDI "birth" or unset) are followed for genetics.
Adopted and foster links are kept, flagged, and left out of paths.

Sketch status: run on a Gramps 5.1 export (2,105 people) and on a raw
MyHeritage export (3,170 people; MyHeritage IDs as RIN, married surnames
as _MARNM, CONC splits inside UTF-8 characters, all handled). Dates are kept
as written; `year` is the first four-digit number in them. Not handled:
name variants beyond the first NAME, sources and citations, places as
entities, GEDCOM 7.

Unlinked people are dropped by default. A tree can hold islands with no
family link (parent, child or spouse, adopted included) to the proband:
MyHeritage users build hypotheses there before attaching them. They have
no lineage code, so they add nothing to the analysis, and their names
would only collide with matches' names. `parse` keeps the connected part
that holds the proband (the largest part when none is given);
`[gedcom] keep_unlinked = true` keeps everyone.
"""
import re
import sys
from collections import deque
from pathlib import Path

import identity
import lineage as lin
import textfix

LINE = re.compile(r"^\s*(\d+)\s+(@[^@]+@\s+)?(\S+)(?:\s(.*))?$")
YEAR = re.compile(r"\b(\d{4})\b")
BIOLOGICAL = {None, "", "birth"}


def options(cfg):
    """parse/Tree keyword arguments from family.toml's [gedcom] table."""
    g = (cfg or {}).get("gedcom") or {}
    return dict(keep_unlinked=bool(g.get("keep_unlinked", False)), root=g.get("proband"))


def linked(records, root=None):
    """Keep the people (and families) connected to `root` through any
    family link; root is an xref or a FACT/RIN value such as "MH:I1".
    Without a root, or one not in the tree, the largest connected part is
    kept. Records other than INDI and FAM (sources, notes, media) stay.
    Returns (kept records, xrefs of the dropped people)."""
    indi = {r["xref"]: r for r in records if r["tag"] == "INDI" and r["xref"]}
    fams = [r for r in records if r["tag"] == "FAM"]
    adj = {i: set() for i in indi}
    for f in fams:
        members = [s["value"] for s in f["sub"] if s["tag"] in ("HUSB", "WIFE", "CHIL")
                   and s["value"] in indi]
        for a in members:
            adj[a].update(members)
    seen, parts = set(), []
    for start in indi:
        if start in seen:
            continue
        part, todo = {start}, [start]
        while todo:
            for y in adj[todo.pop()] - part:
                part.add(y)
                todo.append(y)
        seen |= part
        parts.append(part)
    if not parts:
        return records, []
    keep = None
    if root:
        xref = next((x for x in (root, f"@{root}@") if x in indi), None) or next(
            (x for x, r in indi.items() for s in r["sub"]
             if s["tag"] in ("FACT", "RIN") and s["value"] == root), None)
        if xref:
            keep = next(p for p in parts if xref in p)
        else:
            print(f"gedcom_io: proband {root} not in the tree; keeping its largest "
                  "connected part", file=sys.stderr)
    keep = keep or max(parts, key=len)

    def kept(r):
        if r["tag"] == "INDI":
            return r["xref"] in keep
        if r["tag"] == "FAM":
            return any(s["value"] in keep for s in r["sub"] if s["tag"] in ("HUSB", "WIFE", "CHIL"))
        return True
    return [r for r in records if kept(r)], sorted(set(indi) - keep)


def parse(path, keep_unlinked=False, root=None):
    """GEDCOM lines -> list of top-level records, each a nested dict
    {tag, xref, value, sub}. CONT/CONC are folded into the value. People
    not linked to `root` are left out unless keep_unlinked (see `linked`)."""
    records = _parse(path)
    return records if keep_unlinked else linked(records, root)[0]


def _parse(path):
    root = {"tag": None, "xref": None, "value": "", "sub": []}
    stack = [root]
    # MyHeritage splits long values with CONC in the middle of a multi-byte
    # UTF-8 character, so single lines may not decode. Read with
    # surrogateescape, fold, then decode the joined bytes.
    # MyHeritage's raw export also writes bare line breaks inside a value
    # ("Bok: <newline><tab>LandSwedenBokDand" then "4 CONC eryd AIIa1"): a
    # line without a level number, or with a level deeper than one below
    # the current node, continues the value written last.
    last = root
    with open(path, encoding="utf-8-sig", errors="surrogateescape") as f:
        for raw in f:
            line = raw.rstrip("\r\n")
            m = LINE.match(line)
            if not m or int(m[1]) > len(stack) - 1:
                if line.strip() and last is not root:
                    last["value"] += "\n" + line
                continue
            level, xref, tag, value = int(m[1]), (m[2] or "").strip() or None, m[3], m[4] or ""
            parent = stack[min(level, len(stack) - 1)]
            if tag == "CONC":
                parent["value"] += value
                last = parent
                continue
            if tag == "CONT":
                parent["value"] += "\n" + value
                last = parent
                continue
            node = {"tag": tag, "xref": xref, "value": value, "sub": []}
            stack[level]["sub"].append(node)
            del stack[level + 1:]
            stack.append(node)
            last = node
    # repair å/ä/ö after folding: a CONC can split "Ka" from "¨lleryd"
    todo = list(root["sub"])
    while todo:
        n = todo.pop()
        v = n["value"]
        if any("\udc80" <= ch <= "\udcff" for ch in v):
            v = v.encode("utf-8", "surrogateescape").decode("utf-8", "replace")
        n["value"] = textfix.fix(v)
        todo.extend(n["sub"])
    return root["sub"]


def _first(node, tag):
    return next((s for s in node["sub"] if s["tag"] == tag), None)


def _event(node, tag):
    e = _first(node, tag)
    if e is None:
        return None
    d, p = _first(e, "DATE"), _first(e, "PLAC")
    date = d["value"] if d else ""
    y = YEAR.search(date)
    return {"date": date, "year": int(y[1]) if y else None,
            "place": p["value"] if p else ""}


def _name(node):
    n = _first(node, "NAME")
    if n is None:
        return "", "", ""
    given, _, rest = n["value"].partition("/")
    surname = rest.split("/")[0]
    call = next((w.rstrip("*") for w in given.split() if w.endswith("*")), "")
    return given.replace("*", "").strip(), surname.strip(), call


class Tree:
    def __init__(self, path, keep_unlinked=False, root=None):
        self.people, self.families, self.alias = {}, {}, {}
        famc_pedi = {}
        records = _parse(path)
        self.unlinked = []           # xrefs of the people left out
        if not keep_unlinked:
            records, self.unlinked = linked(records, root)
        for r in records:
            if r["tag"] == "INDI":
                given, surname, call = _name(r)
                # MyHeritage IDs: Gramps exports carry them as FACT, MyHeritage's own as RIN
                facts = [s["value"] for s in r["sub"] if s["tag"] in ("FACT", "RIN")]
                married = [m["value"] for n in r["sub"] if n["tag"] == "NAME"
                           for m in n["sub"] if m["tag"] == "_MARNM"]
                sex = _first(r, "SEX")
                for s in r["sub"]:          # GEDCOM 5.5.1: PEDI under FAMC
                    pedi = _first(s, "PEDI") if s["tag"] == "FAMC" else None
                    if pedi:
                        famc_pedi[(r["xref"], s["value"])] = pedi["value"].lower()
                self.people[r["xref"]] = dict(
                    id=r["xref"], given=given, surname=surname, call=call,
                    sex=sex["value"] if sex else "U",
                    birth=_event(r, "BIRT"), death=_event(r, "DEAT"),
                    facts=facts, married=married,
                    famc=[s["value"] for s in r["sub"] if s["tag"] == "FAMC"],
                    fams=[s["value"] for s in r["sub"] if s["tag"] == "FAMS"])
                for fct in facts:
                    self.alias.setdefault(fct, r["xref"])
            elif r["tag"] == "FAM":
                kids = []
                for s in r["sub"]:
                    if s["tag"] == "CHIL":
                        pedi = _first(s, "PEDI")   # some exporters put it here
                        kids.append((s["value"], pedi["value"].lower() if pedi else None))
                husb, wife = _first(r, "HUSB"), _first(r, "WIFE")
                self.families[r["xref"]] = dict(
                    id=r["xref"], husb=husb["value"] if husb else None,
                    wife=wife["value"] if wife else None, children=kids,
                    marriage=_event(r, "MARR"))
        self._parents, self._children, self.nonbio = {}, {}, []
        for f in self.families.values():
            for c, pedi in f["children"]:
                pedi = pedi or famc_pedi.get((c, f["id"]))
                for par in (f["husb"], f["wife"]):
                    if not par:
                        continue
                    if pedi in BIOLOGICAL:
                        self._parents.setdefault(c, []).append(par)
                        self._children.setdefault(par, []).append(c)
                    else:
                        self.nonbio.append((c, par, pedi))

    # -- lookup ---------------------------------------------------------
    def id(self, ref):
        """xref, "@I1@"-less xref, or a FACT value such as "MH:I1"."""
        if ref in self.people:
            return ref
        if f"@{ref}@" in self.people:
            return f"@{ref}@"
        if ref in self.alias:
            return self.alias[ref]
        raise KeyError(ref)

    def label(self, i):
        p = self.people[i]
        life = "–".join(str((p[e] or {}).get("year") or "") for e in ("birth", "death"))
        mh = next((f for f in p["facts"] if f.startswith("MH:")), "")
        return f"{p['given']} {p['surname']} ({life}) {mh or i}".replace("  ", " ")

    def find(self, pattern):
        rx = re.compile(pattern, re.I)
        return [i for i, p in self.people.items()
                if rx.search(f"{p['given']} {p['surname']}")]

    # -- graph ----------------------------------------------------------
    def parents(self, i):
        return self._parents.get(i, [])

    def children(self, i):
        return self._children.get(i, [])

    def ancestors(self, i, max_depth=12):
        """(person, lineage code) for every biological path upward; a person
        reached by several paths (pedigree collapse) appears once per path."""
        out, q = [], deque([(i, "")])
        while q:
            x, code = q.popleft()
            if len(code) >= max_depth:
                continue
            for par in self.parents(x):
                step = {"M": "F", "F": "M"}.get(self.people[par]["sex"], "?")
                out.append((par, code + step))
                q.append((par, code + step))
        return out

    def descendants(self, i, max_depth=6):
        """(person, generations below i, path of xrefs) by biological links,
        depth first, so each line of descent stays together."""
        out, stack = [], [(i, 0, (i,))]
        while stack:
            x, g, path = stack.pop()
            if x != i:
                out.append((x, g, path))
            if g < max_depth:
                kids = sorted(self.children(x), key=self._born)
                stack.extend((c, g + 1, path + (c,)) for c in reversed(kids))
        return out

    def _born(self, i):
        return (self.people[i]["birth"] or {}).get("year") or 9999

    def lineage(self, proband, person):
        """All lineage codes from proband up to person ('' if the same)."""
        proband, person = self.id(proband), self.id(person)
        if proband == person:
            return [""]
        return [code for x, code in self.ancestors(proband) if x == person]

    def relationship(self, a, b):
        """Closest shared ancestors of a and b: list of (ancestor, code from a,
        generations from b). Spouses of one couple both appear; the `via`
        node of a couple MRCA (lineage codes ending F and M) is the code
        without its last letter."""
        a, b = self.id(a), self.id(b)
        up_a = {}
        for x, code in [(a, "")] + self.ancestors(a):
            up_a.setdefault(x, []).append(code)
        best, out = None, []
        for x, gb in [(b, 0)] + [(x, len(c)) for x, c in self.ancestors(b)]:
            for code in up_a.get(x, []):
                d = len(code) + gb
                if best is None or d < best:
                    best, out = d, []
                if d == best and (x, code, gb) not in out:
                    out.append((x, code, gb))
        return out


_norm = identity.name_key


def load_identities(cfg):
    """Confirmed match -> tree person links from data/notes/assertions.toml:

        [[identity]]
        match = "Erik Example"        # the match's display name at the vendor
        tree = "MH:I42"               # xref or MyHeritage ID
        by = "A. Researcher"          # who confirmed it
        date = 2026-01-31

    Returns {normalised match name: tree ref}. These are assertions (who
    said so, when) and take precedence over the name join."""
    return {_norm(x["match"]): x["tree"] for x in cfg.get("identity", [])}


def kinship(tree, a, b, _memo=None, twins=None):
    """Kinship coefficient over all paths (Malécot), by recursion on the
    parents of whichever of the two is not an ancestor of the other.
    Expected shared autosomal DNA is about 2 * kinship * 6800 cM. Pedigree
    collapse (cousin or uncle-niece marriages) adds up automatically.
    `twins` maps one identical twin to the other: they count as one person."""
    memo = {} if _memo is None else _memo
    anc = {}
    tw = {tree.id(k): tree.id(v) for k, v in (twins or {}).items()}

    def ancestors(x):
        if x not in anc:
            s = set()
            for q in tree.parents(x):
                s |= {q, tw.get(q, q)} | ancestors(q)
            anc[x] = s
        return anc[x]

    def phi(x, y):
        if x is None or y is None:
            return 0.0
        x, y = tw.get(x, x), tw.get(y, y)      # identical twins: one genome
        k = (x, y) if x <= y else (y, x)
        if k in memo:
            return memo[k]
        if x == y:
            ps = tree.parents(x)
            r = 0.5 * (1 + (phi(ps[0], ps[1]) if len(ps) == 2 else 0.0))
        else:
            if x in ancestors(y):        # expand the descendant
                x, y = y, x
            ps = tree.parents(x)
            r = 0.5 * sum(phi(q, y) for q in ps) if ps else 0.0
        memo[k] = r
        return r

    import sys as _sys
    _sys.setrecursionlimit(max(_sys.getrecursionlimit(), 20000))
    return phi(tree.id(a), tree.id(b))


# A match is a person who gave a DNA sample. Consumer autosomal tests began
# in 2007, so a tree person who died before then, or who would have been
# older than MAX_TESTER_AGE by then, cannot be the match of that name.
DNA_TESTS_FROM = 2007
MAX_TESTER_AGE = 95     # a judgement call: older testers are rare, and a
                        # tree often lacks the death of someone born ~1905


def could_have_tested(person, until=None):
    """False when a tree person's dates rule them out as a DNA tester: died
    before DNA_TESTS_FROM, born too early to be alive then (MAX_TESTER_AGE),
    or born after `until` (the export's year, if known). Missing dates
    rule nothing out. A sample taken before death still counts, so a
    death after 2007 is no objection."""
    born = (person.get("birth") or {}).get("year")
    died = (person.get("death") or {}).get("year")
    if died is not None and died < DNA_TESTS_FROM:
        return False
    if born is not None and born < DNA_TESTS_FROM - MAX_TESTER_AGE:
        return False
    if born is not None and until is not None and born > until:
        return False
    return True


def matches_in_tree(tree, proband, placed, identities=None, until=None):
    """Join the tree to placed matches (data/output/placed_matches.csv) by full name.

    Name matching is weak: a hit is a candidate to confirm, not an identity.
    Tree people whose dates rule them out as testers (`could_have_tested`)
    are not candidates, so a living match is not joined to a namesake who
    died in 1874. Confirmed identities are taken as given.
    For each hit: the closest shared ancestors with the proband, the lineage
    code that predicts (the code of the MRCA couple minus its last letter,
    i.e. the `via` node, at grandparent depth), and where the DNA placed it."""
    import pandas as pd
    names = {}
    for i, p in tree.people.items():
        first = p['given'].split()[0] if p['given'] else ''
        variants = {f"{p['given']} {p['surname']}", f"{first} {p['surname']}"}
        for m in p.get("married", []):              # married surnames (MyHeritage _MARNM)
            variants |= {f"{p['given']} {m}", f"{first} {m}"}
        for variant in variants:
            names.setdefault(_norm(variant), []).append(i)
    identities = identities or {}
    rows = []
    for _, m in placed.iterrows():
        key = _norm(str(m["match"]))
        if key in identities:              # confirmed: no name guessing
            cands = [tree.id(identities[key])]
        elif len(key.split()) < 2:         # a first name alone is no identity
            continue
        else:
            cands = [i for i in names.get(key, []) if could_have_tested(tree.people[i], until)]
        for i in cands:
            rel = tree.relationship(proband, i)
            codes = sorted({c for _, c, _ in rel})
            rows.append(dict(match=m["match"], platform=m.get("platform"),
                             subject=m.get("subject"), shared_cM=m.get("shared_cM"),
                             placement=m.get("placement"), person=tree.label(i),
                             mrca=" & ".join(tree.label(x) for x, _, _ in rel),
                             tree_side=" ".join(sorted({c[:2] for c in codes if len(c) >= 2})),
                             mrca_code=" ".join(codes)))
    return pd.DataFrame(rows)


ahnentafel = lin.ahnentafel


def load(cfg=None):
    import config
    cfg = cfg or config.load()
    g = cfg.get("gedcom") or {}
    if "file" not in g:
        raise KeyError("family.toml has no [gedcom] file")
    return Tree(config.path(cfg, g["file"]), **options(cfg)), g.get("proband")


def _main(argv):
    tree, proband = load()
    cmd, args = (argv[0], argv[1:]) if argv else ("summary", [])
    if cmd == "summary":
        print(f"{len(tree.people)} people, {len(tree.families)} families, "
              f"{len(tree.nonbio)} non-biological child links, "
              f"{len(tree.unlinked)} unlinked people left out")
        for c, par, pedi in tree.nonbio:
            print(f"  {pedi}: {tree.label(c)} <- {tree.label(par)}")
    elif cmd == "find":
        for i in tree.find(args[0]):
            codes = tree.lineage(proband, i) if proband else []
            print(tree.label(i), " ".join(f"{c} ({ahnentafel(c)})" for c in codes))
    elif cmd == "lineage":
        for c in tree.lineage(proband, args[0]):
            print(c, ahnentafel(c))
    elif cmd == "descendants":
        depth = int(args[1]) if len(args) > 1 else 6
        root = tree.id(args[0])
        print(tree.label(root))
        for x, g, _ in tree.descendants(root, depth):
            print("  " * g + tree.label(x))
    elif cmd == "matches":
        import config
        import pandas as pd
        cfg = config.load()
        placed = pd.read_csv(config.path(cfg, "placed_matches.csv"))
        df = matches_in_tree(tree, proband, placed, load_identities(config.load()))
        if df.empty:
            print("no tree person matches a placed match by name")
        else:
            df["agrees"] = [(t and p and p[:2] in t.split()) for t, p in
                            zip(df.tree_side, df.placement.fillna(""))]
            cols = ["match", "platform", "subject", "shared_cM", "placement",
                    "tree_side", "agrees", "mrca_code"]
            print(df.sort_values("shared_cM", ascending=False)[cols].to_string(index=False))
    elif cmd == "rel":
        for x, code, gb in tree.relationship(args[0], args[1]):
            print(f"{tree.label(x)}: {code or 'self'} from {args[0]}, {gb} generations above {args[1]}")
    else:
        sys.exit("usage: gedcom_io.py [summary | find <regex> | lineage <ref> | "
                 "descendants <ref> [depth] | rel <ref> <ref> | matches]")


if __name__ == "__main__":
    _main(sys.argv[1:])
