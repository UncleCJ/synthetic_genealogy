"""
One graph of matches from several testers' shared-match runs, with
observability, for analysis and for Gephi.

Merging AutoCluster runs naively mixes thresholds: each run only includes
matches in its tester's cM window, and only reports shared matches above
its own minimum. An edge missing from a run means "not shared" only if
both matches were inside that run; otherwise it means "not looked at".
So every match pair carries two counts:

    observable  runs in which both matches were included (clustered, or
                listed in the run's footer as without shared matches or
                as singletons)
    reported    runs that report the pair as sharing

and support = reported / observable. Single-run edges are weak; an edge
seen in every run that could see it is strong; a pair observable in
three runs and reported in none is evidence against.

Layers (bipartite, tester -> match): each tester node links to the
matches it shares DNA with (cM from the segment exports, or the run).
The projection onto matches is the shared-match graph above; onto testers
it is how many matches two siblings share.

Node attributes come from the placement (pooled over siblings: a
grandparent, or a side when both of that side's grandparents carry DNA),
and from the tree (deepest lineage code). Edges between differently
placed matches are listed: pile-ups, double relationships or placement
errors.

Sketch. MyHeritage only (stable match IDs); FTDNA runs key matches by
name and are left out.
"""
import csv
import io
import re
from collections import defaultdict
from itertools import combinations
from pathlib import Path

import pandas as pd

import icw_io

GP = ("FF", "FM", "MF", "MM")


def run_members(path, name_to_key):
    """(keys included in the run, set of reported pairs)."""
    nodes, edges = icw_io.autocluster_matrix(path, "?", "MyHeritage")
    ids, names, lo, hi = icw_io.autocluster_window(path)
    members = set(ids) | {name_to_key[n] for n in names if n in name_to_key}
    pairs = {tuple(sorted(p)) for p in zip(edges.a_key, edges.b_key)}
    cm = dict(zip(nodes.match_key, nodes.cM))      # clustered rows carry total cM
    return members, pairs, (lo, hi), cm


def pooled_label(placed, couple_share=0.25, couple_cm=100.0):
    """match_key -> (label, cM by grandparent) pooled over testers."""
    g = placed.groupby("match_key")[list(GP)].sum()
    out = {}
    for k, r in g.iterrows():
        tot = r.sum()
        if tot <= 0:
            continue
        label = r.idxmax()
        for side in "FM":
            a, b = r[side + "F"], r[side + "M"]
            if a + b >= couple_cm and min(a, b) / (a + b) >= couple_share:
                label = side
        out[k] = (label, r.to_dict())
    return out


def build(cfg):
    import networkx as nx
    D = cfg["data_dir"]
    placed = pd.read_csv(D / "placed_matches.csv", low_memory=False)
    placed = placed[placed.platform == "MyHeritage"]
    segs = pd.read_csv(D / "placed_segments.csv", low_memory=False,
                       usecols=["platform", "subject", "match_key", "match", "cM"])
    segs = segs[segs.platform == "MyHeritage"]
    names = segs.drop_duplicates("match_key")[["match_key", "match"]]
    nk = names.assign(n=names.match.map(icw_io.name_key)).groupby("n").match_key.agg(list)
    name_to_key = {n: ks[0] for n, ks in nk.items() if len(ks) == 1}   # unambiguous names only
    runs = [x for x in cfg.get("icw", []) if x["kind"] == "autocluster" and x.get("platform", "MyHeritage") == "MyHeritage"]
    observable, reported, tester_cm = defaultdict(int), defaultdict(int), defaultdict(dict)
    run_info = []
    for x in runs:
        members, pairs, win, run_cm = run_members(D / x["file"], name_to_key)
        run_info.append((x["subject"], Path(x["file"]).name, len(members), len(pairs), win))
        for p in combinations(sorted(members), 2):
            observable[p] += 1
        for p in pairs:
            reported[p] += 1
        for k in members:
            v = run_cm.get(k)
            old = tester_cm[k].get(x["subject"])
            # in the run: its total cM if clustered, else "in window" (lower bound)
            tester_cm[k][x["subject"]] = max(v or 0, old or 0) or win[0]
    cm = segs.groupby(["match_key", "subject"]).cM.sum()
    for (k, s), v in cm.items():
        if k in tester_cm and s in tester_cm[k]:
            tester_cm[k][s] = round(max(v, tester_cm[k][s] or 0), 1)
        elif k in tester_cm:
            tester_cm[k][s] = round(v, 1)
    labels = pooled_label(placed)
    deep = {}
    if cfg.get("gedcom"):
        import dnapainter_export
        import gedcom_io
        tree, proband = gedcom_io.load(cfg)
        deep = dnapainter_export.deep_codes(tree, proband, placed)
    G = nx.Graph()
    key_name = dict(zip(names.match_key, names.match))
    for x in runs:                                   # matches known only from the runs
        n_, _ = icw_io.autocluster_matrix(D / x["file"], "?", "MyHeritage")
        for k, m in zip(n_.match_key, n_.match):
            key_name.setdefault(k, m)
    for k, t in tester_cm.items():
        lab, by = labels.get(k, ("", {}))
        G.add_node(k, label=key_name.get(k, k), kind="match", placement=lab or "unplaced",
                   deep=deep.get(k, ""), testers=len(t),
                   max_cM=float(max([v for v in t.values() if v] or [0])),
                   **{f"cM_{s}": float(v or 0) for s, v in t.items()},
                   **{f"gp_{g}": float(round(by.get(g, 0), 1)) for g in GP})
    for p, r in reported.items():
        if p[0] in G and p[1] in G:
            o = max(observable[p], r)
            G.add_edge(*p, kind="shared match", reported=r, observable=o, support=float(round(r / o, 2)), weight=float(r / o))
    for s in {x["subject"] for x in runs}:
        G.add_node(f"tester:{s}", label=s, kind="tester", placement="tester", deep="", testers=0, max_cM=0.0)
    for k, t in tester_cm.items():
        for s, v in t.items():
            G.add_edge(f"tester:{s}", k, kind="shares", cM=float(v or 0), weight=0.0)   # bipartite layer
    return G, run_info, observable, reported


def summary(G):
    import networkx as nx
    M = G.subgraph([n for n, d in G.nodes(data=True) if d["kind"] == "match"])
    E = [(u, v, d) for u, v, d in M.edges(data=True) if d.get("kind") == "shared match"]
    lab = nx.get_node_attributes(M, "placement")
    out = {"matches": M.number_of_nodes(), "shared-match edges": len(E)}
    out["edges seen in every run that could see them"] = sum(d["support"] == 1 and d["observable"] > 1 for *_, d in E)
    out["edges seen in only some runs that could see them"] = sum(d["support"] < 1 for *_, d in E)
    # agreement of the graph with the placement (both ends at grandparent level)
    gp = [(lab[u], lab[v]) for u, v, _ in E if lab[u] in GP and lab[v] in GP]
    same = sum(a == b for a, b in gp)
    side = sum(a[0] == b[0] for a, b in gp)
    out["edges between placed matches"] = len(gp)
    out["... same grandparent"] = same
    out["... same parent's side"] = side
    from collections import Counter
    c = Counter(l for l in lab.values() if l in GP)
    n = sum(c.values())
    exp = sum((v / n) ** 2 for v in c.values()) if n else 0
    out["... same grandparent expected by chance"] = round(exp * len(gp))
    try:
        sub = M.subgraph([x for x in M if lab[x] in GP])
        out["assortativity by grandparent"] = round(nx.attribute_assortativity_coefficient(sub, "placement"), 2)
    except Exception:
        pass
    return out


def draw(G, path, names=False, strong_only=False):
    import matplotlib.pyplot as plt
    import networkx as nx
    from matplotlib.patches import Patch
    M = G.subgraph([n for n, d in G.nodes(data=True) if d["kind"] == "match" and G.degree(n) > 0])
    keep = [(u, v) for u, v, d in M.edges(data=True) if d.get("kind") == "shared match"
            and (not strong_only or (d["support"] == 1 and d["observable"] >= 2))]
    M = M.edge_subgraph(keep).copy()
    colors = {"FF": "#2b6cb0", "FM": "#2f855a", "MF": "#c05621", "MM": "#805ad5",
              "F": "#7fb3d5", "M": "#e0a37a", "unplaced": "#bbbbbb"}
    pos = nx.spring_layout(M, weight="weight", seed=7, k=0.35, iterations=200)
    fig, ax = plt.subplots(figsize=(13, 11))
    w = [0.3 + 2.5 * d["support"] for *_, d in M.edges(data=True)]
    al = [0.15 + 0.6 * d["support"] for *_, d in M.edges(data=True)]
    for (u, v, d), lw, a in zip(M.edges(data=True), w, al):
        ax.plot(*zip(pos[u], pos[v]), color="#666", lw=lw, alpha=a, zorder=1)
    nodes = list(M)
    ax.scatter([pos[n][0] for n in nodes], [pos[n][1] for n in nodes],
               s=[15 + 1.2 * min(M.nodes[n]["max_cM"], 400) for n in nodes],
               c=[colors.get(M.nodes[n]["placement"], "#bbb") for n in nodes],
               edgecolors=["k" if M.nodes[n]["testers"] >= 3 else "none" for n in nodes],
               linewidths=0.6, zorder=2)
    if names:
        for n in nodes:
            d = M.nodes[n]
            if d["max_cM"] >= 90 or d["deep"]:
                ax.annotate(d["label"] + (f" [{d['deep']}]" if d["deep"] else ""), pos[n], fontsize=6,
                            xytext=(3, 3), textcoords="offset points")
    ax.legend(handles=[Patch(color=c, label=l) for l, c in colors.items()], loc="lower left",
              fontsize=8, frameon=False, title="placement (pooled over siblings)")
    ax.set_title("MyHeritage shared-match graph, all testers' AutoCluster runs merged"
                 + (" (only edges seen in every run, 2+, that could see them)" if strong_only else "")
                 + "\nedge width = support (runs reporting / runs that could see the pair); "
                 "node size = largest cM; black ring = shared by three or more of the family", fontsize=9)
    ax.axis("off")
    fig.tight_layout()
    fig.savefig(path, dpi=140)
    plt.close(fig)


def main():
    import networkx as nx
    import config
    cfg = config.load()
    D = cfg["data_dir"]
    G, run_info, _, _ = build(cfg)
    for r in run_info:
        print(f"run {r[0]:10s} {r[2]:4d} matches in window {r[4][0]:g}-{r[4][1]:g} cM, {r[3]:4d} pairs  ({r[1]})")
    for k, v in summary(G).items():
        print(f"{k}: {v}")
    nx.write_gexf(G, D / "match_graph.gexf")
    draw(G, D / "match_graph.png", names=True)
    draw(G, D / "match_graph_strong.png", names=True, strong_only=True)
    M = G.subgraph([n for n, d in G.nodes(data=True) if d["kind"] == "match"])
    lab = nx.get_node_attributes(M, "placement")
    rows = [dict(a=M.nodes[u]["label"], a_place=lab[u], b=M.nodes[v]["label"], b_place=lab[v],
                 support=d["support"], reported=d["reported"], observable=d["observable"])
            for u, v, d in M.edges(data=True) if lab[u] in GP and lab[v] in GP and lab[u][0] != lab[v][0]]
    pd.DataFrame(rows).sort_values("support", ascending=False).to_csv(D / "match_graph_cross_side.csv", index=False)
    print(f"-> match_graph.gexf (Gephi), match_graph.png, match_graph_strong.png, match_graph_cross_side.csv ({len(rows)} cross-side edges)")


if __name__ == "__main__":
    main()
