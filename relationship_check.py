"""Expected versus observed shared DNA for matches whose place in the tree is
confirmed (`[[identity]]` in data/notes/assertions.toml).

Expected is 2 x kinship x 6800 cM (gedcom_io.kinship, identical twins
`[[mz_twins]]` as one person); observed is the largest total per tester from
the segment exports or AutoCluster runs. An identity can sit below the tree
(`down = n`). `odds()` gives WATO-style odds per relationship from simulated
distributions (`simulate.relationship_cm`, cached in
`<data_dir>/cache/relationship_cm.csv`); unvalidated.

Output: `<data_dir>/output/relationship_check.md`.

How it works: docs/genetics.md, "Relationships".
"""
import numpy as np
import pandas as pd

import outputs

import config
import gedcom_io
import match_graph

GENOME_CM = 6800.0
SIMS = 500
# (up_a, up_b, half): direct line to 2x great-grandparent, aunt-type to 2x
# great-aunt, cousins to 5C3R; full and half
CANDIDATES = ([(r, 0, False) for r in range(1, 5)]
              + [(1 + r, 1, h) for r in range(5) for h in (False, True)]
              + [(g + r, g, h) for g in range(2, 7) for r in range(4) for h in (False, True)])


def distributions(cfg, n=SIMS):
    """{(up_a, up_b, half): (simulated totals of listed matches, n simulated)},
    from the cache, simulated on first use (a few minutes)."""
    import simulate
    f = config.path(cfg, "relationship_cm.csv")
    if f.exists():
        df = pd.read_csv(f)
        if int(df.n.iloc[0]) == n and len(df.groupby(["up_a", "up_b", "half"])) == len(CANDIDATES):
            return {(int(a), int(b), bool(h)): (g.cM.dropna().to_numpy(), n)
                    for (a, b, h), g in df.groupby(["up_a", "up_b", "half"])}
    rows = []
    for i, (a, b, h) in enumerate(CANDIDATES):
        x = simulate.relationship_cm(a, b, h, n=n, seed=i + 1)
        rows += [dict(up_a=a, up_b=b, half=h, n=n, cM=round(v, 1)) for v in x] or [
            dict(up_a=a, up_b=b, half=h, n=n, cM=None)]
    pd.DataFrame(rows).to_csv(f, index=False)
    return distributions(cfg, n)


def _density(x, v):
    """Kernel density of log cM at v (Silverman bandwidth)."""
    if len(x) < 5:
        return 0.0
    lx = np.log(x)
    bw = max(1.06 * lx.std() * len(lx) ** -0.2, 0.05)
    z = (np.log(v) - lx) / bw
    return float(np.exp(-0.5 * z * z).sum() / (len(lx) * bw * np.sqrt(2 * np.pi)) / v)


def odds(dist, cm):
    """DataFrame of relationships by probability for a total of cm, as WATO
    does: likelihood = P(listed) x density(cm | listed), equal priors."""
    rows = []
    for (a, b, h), (x, n) in dist.items():
        rows.append(dict(rel=gedcom_io.relationship_name(a, b, h), up_a=a, up_b=b, half=h,
                         like=len(x) / n * _density(x, cm),
                         range=f"{np.percentile(x, 1):.0f}–{np.percentile(x, 99):.0f}" if len(x) >= 5 else ""))
    df = pd.DataFrame(rows)
    df["p"] = df.like / df.like.sum() if df.like.sum() else 0.0
    return df.sort_values("p", ascending=False).reset_index(drop=True)


def likelihood(dist, up_a, up_b, half, cm):
    """Likelihood of one relationship (up_a and up_b swapped is the same)."""
    g, r = min(up_a, up_b), abs(up_a - up_b)
    key = (g + r, g, bool(half and g > 0))
    if key not in dist:
        return None
    x, n = dist[key]
    return len(x) / n * _density(x, cm)


def main():
    cfg = config.load()
    D = cfg["data_dir"]
    tree, proband = gedcom_io.load(cfg)
    twins = {x["a"]: x["b"] for x in cfg.get("mz_twins", [])}
    testers = {k: p["mh"] for k, p in cfg["people"].items() if p.get("mh")}
    G, *_ = match_graph.build(cfg)
    placed = outputs.read(D, "placed_matches.csv")
    seg_total = placed.groupby([placed.match.map(gedcom_io._norm), "subject"]).shared_cM.max()
    # a match with no segment placed is missing from placed_matches: its
    # observed total is then the sum of its segments (largest per export)
    segs = outputs.read(D, "placed_segments.csv", usecols=["platform", "subject", "match", "cM"])
    seg_sum = (segs.groupby([segs.match.map(gedcom_io._norm), "subject", "platform"]).cM.sum()
               .groupby(level=[0, 1]).max())
    seg_total = seg_total.combine_first(seg_sum)
    by_name = {}
    for k, d in G.nodes(data=True):
        if d["kind"] == "match":
            by_name.setdefault(gedcom_io._norm(d["label"]), d)
    rows = []
    for x in cfg.get("identity", []):
        d = by_name.get(gedcom_io._norm(x["match"]), {})
        down = int(x.get("down", 0))
        row = dict(match=x["match"], tree=tree.label(tree.id(x["tree"])) + (f" ↓{down}" if down else ""))
        exp, obs = [], []
        for t, mh in testers.items():
            e = 2 * gedcom_io.kinship(tree, mh, x["tree"], twins=twins) * GENOME_CM * 0.5 ** down
            o = d.get(f"cM_{t}") or seg_total.get((gedcom_io._norm(x["match"]), t)) or None
            row[f"{t} exp"], row[f"{t} obs"] = round(e), (round(o) if o else "")
            if o and e:
                exp.append(e); obs.append(o)
        row["ratio"] = round(sum(obs) / sum(exp), 2) if exp else ""
        rel = tree.relation(proband, x["tree"], down, x.get("half"))
        row["relationship"] = rel["name"] if rel else ""
        row["via"] = " & ".join(tree.label(a) for a in rel["ancestors"]) if rel else ""
        rows.append(row)
    df = pd.DataFrame(rows)
    md = ["# Confirmed relatives: expected vs observed shared DNA", "",
          "Expected = 2 × kinship × 6800 cM over all tree paths (identical twins as one person); "
          "observed = largest total per tester. Ratio = sum observed / sum expected over testers with data.", "",
          df.to_markdown(index=False)]
    (D / "relationship_check.md").write_text("\n".join(md), encoding="utf-8")
    print(df.to_string(index=False))


if __name__ == "__main__":
    main()
