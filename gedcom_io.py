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

Sketch status: run on one Gramps 5.1 export (2,105 people). Dates are kept
as written; `year` is the first four-digit number in them. Not handled:
name variants beyond the first NAME, sources and citations, places as
entities, GEDCOM 7.
"""
import re
import sys
from collections import deque
from pathlib import Path

import textfix

LINE = re.compile(r"^\s*(\d+)\s+(@[^@]+@\s+)?(\S+)(?:\s(.*))?$")
YEAR = re.compile(r"\b(\d{4})\b")
BIOLOGICAL = {None, "", "birth"}


def parse(path):
    """GEDCOM lines -> list of top-level records, each a nested dict
    {tag, xref, value, sub}. CONT/CONC are folded into the value."""
    root = {"tag": None, "xref": None, "value": "", "sub": []}
    stack = [root]
    with open(path, encoding="utf-8-sig") as f:
        for raw in f:
            m = LINE.match(raw.rstrip("\r\n"))
            if not m:
                continue
            level, xref, tag, value = int(m[1]), (m[2] or "").strip() or None, m[3], m[4] or ""
            parent = stack[min(level, len(stack) - 1)]
            if tag == "CONC":
                parent["value"] += value
                continue
            if tag == "CONT":
                parent["value"] += "\n" + value
                continue
            node = {"tag": tag, "xref": xref, "value": value, "sub": []}
            stack[level]["sub"].append(node)
            del stack[level + 1:]
            stack.append(node)
    # repair å/ä/ö after folding: a CONC can split "Ka" from "¨lleryd"
    todo = list(root["sub"])
    while todo:
        n = todo.pop()
        n["value"] = textfix.fix(n["value"])
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
    def __init__(self, path):
        self.people, self.families, self.alias = {}, {}, {}
        famc_pedi = {}
        for r in parse(path):
            if r["tag"] == "INDI":
                given, surname, call = _name(r)
                facts = [s["value"] for s in r["sub"] if s["tag"] == "FACT"]
                sex = _first(r, "SEX")
                for s in r["sub"]:          # GEDCOM 5.5.1: PEDI under FAMC
                    pedi = _first(s, "PEDI") if s["tag"] == "FAMC" else None
                    if pedi:
                        famc_pedi[(r["xref"], s["value"])] = pedi["value"].lower()
                self.people[r["xref"]] = dict(
                    id=r["xref"], given=given, surname=surname, call=call,
                    sex=sex["value"] if sex else "U",
                    birth=_event(r, "BIRT"), death=_event(r, "DEAT"),
                    facts=facts,
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


def _norm(s):
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", str(s).lower())).strip()


def matches_in_tree(tree, proband, placed):
    """Join the tree to placed matches (data/placed_matches.csv) by full name.

    Name matching is weak: a hit is a candidate to confirm, not an identity.
    For each hit: the closest shared ancestors with the proband, the lineage
    code that predicts (the code of the MRCA couple minus its last letter,
    i.e. the `via` node, at grandparent depth), and where the DNA placed it."""
    import pandas as pd
    names = {}
    for i, p in tree.people.items():
        for variant in {f"{p['given']} {p['surname']}", f"{p['given'].split()[0] if p['given'] else ''} {p['surname']}"}:
            names.setdefault(_norm(variant), []).append(i)
    rows = []
    for _, m in placed.iterrows():
        key = _norm(str(m["match"]))
        if len(key.split()) < 2:        # a first name alone is no identity
            continue
        for i in names.get(key, []):
            rel = tree.relationship(proband, i)
            codes = sorted({c for _, c, _ in rel})
            rows.append(dict(match=m["match"], platform=m.get("platform"),
                             subject=m.get("subject"), shared_cM=m.get("shared_cM"),
                             placement=m.get("placement"), person=tree.label(i),
                             mrca=" & ".join(tree.label(x) for x, _, _ in rel),
                             tree_side=" ".join(sorted({c[:2] for c in codes if len(c) >= 2})),
                             mrca_code=" ".join(codes)))
    return pd.DataFrame(rows)


def ahnentafel(code):
    n = 1
    for c in code:
        n = 2 * n + (c == "M")
    return n


def load(cfg=None):
    import config
    cfg = cfg or config.load()
    g = cfg.get("gedcom") or {}
    if "file" not in g:
        raise KeyError("family.toml has no [gedcom] file")
    return Tree(config.path(cfg, g["file"])), g.get("proband")


def _main(argv):
    tree, proband = load()
    cmd, args = (argv[0], argv[1:]) if argv else ("summary", [])
    if cmd == "summary":
        print(f"{len(tree.people)} people, {len(tree.families)} families, "
              f"{len(tree.nonbio)} non-biological child links")
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
        df = matches_in_tree(tree, proband, placed)
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
