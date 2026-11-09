"""
Close matches the family tree doesn't explain yet: a shortlist to research.

From the AutoCluster runs (every match in each run's cM window, with the
match's own tree URL and size), keep matches that

- share at least `MIN_SIB_CM` with a sibling (roughly second to third
  cousins: common ancestors three to four generations back), or at least
  `MIN_MOTHER_CM` with the mother (one generation closer to the same
  ancestors), and
- are not in the GEDCOM by full name (gedcom_io.matches_in_tree; weak, so
  a hit there may still be a namesake, and a miss may be a spelling).

For each: cM per tester, the side and grandparent from the segments
(pooled over siblings) or, failing that, the shared-match candidate
(icw_phasing), and branch hints: shared matches that ARE in the tree, with
their lineage codes. A match sharing strongly with tree-linked relatives
on one branch most likely descends from that branch.

Expected relationships are rough (Shared cM Project averages); ranges
overlap widely.

Output: `<data_dir>/prospects.md`.
"""
import re
from collections import Counter, defaultdict
from pathlib import Path

import pandas as pd

import icw_io

MIN_SIB_CM, MIN_MOTHER_CM = 60.0, 90.0
GP = ("FF", "FM", "MF", "MM")


def guess(cm):
    """Rough relationship for a sibling's cM (one generation below the mother)."""
    if cm >= 300:
        return "1C1R / 2C / half-1C1R"
    if cm >= 150:
        return "2C / 2C1R"
    if cm >= 90:
        return "2C1R / 3C"
    return "3C / 3C1R"


def _norm(w):
    w = re.sub(r"[^a-zåäöæøéü]", "", w.lower())
    return re.sub(r"(.)\1", r"\1", w)          # Svenningsson ~ Sveningson


def loose_tree_hits(tree, proband, name):
    """Tree people whose surname matches the match's last name and whose
    given names include its first name (call names, doubled letters and
    married surnames in parentheses tolerated). Returns [(label, code)]."""
    parts = [p for p in re.split(r"[\s()]+", name) if p]
    if len(parts) < 2:
        return []
    first, last = _norm(parts[0]), _norm(parts[-1])
    out = []
    for i, p in tree.people.items():
        surnames = {_norm(x) for x in re.split(r"[\s()/]+", p["surname"]) if x}
        given = {_norm(x) for x in p["given"].split()}
        if last in surnames and first in given:
            rel = tree.relationship(proband, i)
            code = sorted({c for _, c, _ in rel})[0] if rel else "?"
            out.append((tree.label(i), code))
    return out


def tree_info(path):
    lines = Path(path).read_text(encoding="utf-8-sig").splitlines()
    end = next((k for k, l in enumerate(lines) if k and (not l.strip() or l.startswith("#"))), len(lines))
    import io
    d = pd.read_csv(io.StringIO("\n".join(lines[:end])), dtype=str)
    return {("D-" + r.Identifier.strip().upper()): (r.Tree if isinstance(r.Tree, str) else "",
                                                   r._5 if isinstance(r._5, str) else "")
            for r in d.itertuples()}


def main():
    import config
    import gedcom_io
    import match_graph
    import networkx as nx
    cfg = config.load()
    D = cfg["data_dir"]
    mother, children = cfg["mother"], cfg["children"]
    G, *_ = match_graph.build(cfg)
    runs = [x for x in cfg.get("icw", []) if x["kind"] == "autocluster"]
    trees = {}
    for x in runs:
        trees.update(tree_info(D / x["file"]))
    placed = pd.read_csv(D / "placed_matches.csv", low_memory=False)
    mh = placed[placed.platform == "MyHeritage"]
    tree, proband = gedcom_io.load(cfg)
    names = pd.DataFrame([(n, d["label"]) for n, d in G.nodes(data=True) if d["kind"] == "match"],
                         columns=["match_key", "match"])
    linked = gedcom_io.matches_in_tree(tree, proband, identities=gedcom_io.load_identities(cfg), placed=names.assign(platform="MyHeritage", subject="",
                                                                    shared_cM=0, placement=""))
    in_tree = {}
    for r in linked.itertuples():
        k = names.loc[names.match == r.match, "match_key"]
        for kk in k:
            in_tree[kk] = r.mrca_code.split()[0] if r.mrca_code else "?"
    icw = pd.read_csv(D / "assertions_icw.csv") if (D / "assertions_icw.csv").exists() else pd.DataFrame()
    icw_label = {}
    if len(icw):
        for k, g in icw[icw.kind == "icw_candidate"].groupby("match_key"):
            icw_label[k] = Counter(g.lineage).most_common(1)[0][0]
    seen_before = set(placed.match_key)   # in a segment export (2020-2023 MyHeritage)
    rows = []
    for k, d in G.nodes(data=True):
        if d["kind"] != "match" or k in in_tree:
            continue
        loose = loose_tree_hits(tree, proband, d["label"])
        sib = max([d.get(f"cM_{s}", 0) or 0 for s in children])
        mum = d.get(f"cM_{mother}", 0) or 0
        if sib < MIN_SIB_CM and mum < MIN_MOTHER_CM:
            continue
        side = d["placement"] if d["placement"] != "unplaced" else (icw_label.get(k, "") + " (ICW)" if k in icw_label else "?")
        nbrs = [(v, e["support"]) for v, e in G[k].items() if e.get("kind") == "shared match"]
        hints = Counter()
        for v, s in nbrs:
            if v in in_tree and s >= 0.5:
                hints[f"{G.nodes[v]['label']} [{in_tree[v]}]"] += 1
        nb_place = Counter(G.nodes[v]["placement"] for v, s in nbrs if s >= 0.5 and G.nodes[v]["placement"] in GP)
        url, size = trees.get(k, ("", ""))
        rows.append(dict(match=d["label"], **{s: round(d.get(f"cM_{s}", 0) or 0) for s in children + [mother]},
                         best=max(sib, mum / 2 if mum else 0), side=side,
                         neighbours=" ".join(f"{g}:{n}" for g, n in nb_place.most_common()),
                         in_tree_neighbours="; ".join(list(hints)[:4]),
                         guess=guess(sib) if sib >= MIN_SIB_CM else "via mother: 1C1R / 2C",
                         tree_persons=size, tree=url, new=("new since 2023" if k not in seen_before else ""),
                         maybe_in_tree="; ".join(f"{l} [{c}]" for l, c in loose[:2])))
    df = pd.DataFrame(rows).sort_values("best", ascending=False)
    md = ["# Close matches not in the tree",
          "", f"Generated by `prospects.py`: matches sharing ≥ {MIN_SIB_CM:g} cM with a sibling or ≥ {MIN_MOTHER_CM:g} cM "
          "with the mother (MyHeritage AutoCluster runs), whose name is not in the GEDCOM. "
          "Side: from segments pooled over siblings, else the shared-match candidate. "
          "Branch hint: shared matches (support ≥ 0.5) that are in the tree, with their lineage code.", "",
          "| match | " + " | ".join(children + [mother]) + " | side | placed shared matches | in-tree shared matches | guess | tree size | new |",
          "|---|" + "---|" * (len(children) + 1) + "---|---|---|---|---|---|"]
    maybe = df[df.maybe_in_tree != ""]
    df = df[df.maybe_in_tree == ""]
    for r in df.itertuples():
        t = f"[{r.tree_persons}]({r.tree})" if r.tree else ""
        md.append(f"| {r.match} | " + " | ".join(str(getattr(r, s)) or "" for s in children + [mother])
                  + f" | {r.side} | {r.neighbours} | {r.in_tree_neighbours} | {r.guess} | {t} | {r.new} |")
    md += ["", "## Probably in the tree under a fuller or variant name", "",
           "| match | tree person [lineage code] | best cM |", "|---|---|---|"]
    md += [f"| {r.match} | {r.maybe_in_tree} | {r.best:.0f} |" for r in maybe.itertuples()]
    (D / "prospects.md").write_text("\n".join(md), encoding="utf-8")
    df.to_csv(D / "prospects.csv", index=False)
    print(f"{len(df)} close matches not in the tree, {len(maybe)} probably in it under another name -> prospects.md")
    print(df.drop(columns=["tree", "maybe_in_tree"]).head(30).to_string(index=False))
    print(maybe[["match", "maybe_in_tree", "best"]].to_string(index=False))


if __name__ == "__main__":
    main()
