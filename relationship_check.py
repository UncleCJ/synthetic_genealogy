"""
Expected versus observed shared DNA for matches whose place in the tree is
confirmed (`[[identity]]` in family.toml).

Expected: 2 x kinship x 6800 cM, kinship over all paths in the tree
(gedcom_io.kinship), with identical twins (`[[mz_twins]]`) counted as one
person. Observed: the largest total per tester from the segment exports
or AutoCluster runs. A ratio far from 1 says the tree is missing a path
(an extra relationship, often through a parent the tree doesn't trace) or
has a wrong one. Single values vary a lot (a second cousin ranges about
0.2-2.5 x the average), so look at all testers together.

Output: `<data_dir>/output/relationship_check.md`.
"""
import pandas as pd

import config
import gedcom_io
import match_graph

GENOME_CM = 6800.0


def main():
    cfg = config.load()
    D = cfg["data_dir"]
    tree, proband = gedcom_io.load(cfg)
    twins = {x["a"]: x["b"] for x in cfg.get("mz_twins", [])}
    testers = {k: p["mh"] for k, p in cfg["people"].items() if p.get("mh")}
    G, *_ = match_graph.build(cfg)
    placed = pd.read_csv(D / "placed_matches.csv", low_memory=False)
    seg_total = placed.groupby([placed.match.map(gedcom_io._norm), "subject"]).shared_cM.max()
    by_name = {}
    for k, d in G.nodes(data=True):
        if d["kind"] == "match":
            by_name.setdefault(gedcom_io._norm(d["label"]), d)
    rows = []
    for x in cfg.get("identity", []):
        d = by_name.get(gedcom_io._norm(x["match"]), {})
        row = dict(match=x["match"], tree=tree.label(tree.id(x["tree"])))
        exp, obs = [], []
        for t, mh in testers.items():
            e = 2 * gedcom_io.kinship(tree, mh, x["tree"], twins=twins) * GENOME_CM
            o = d.get(f"cM_{t}") or seg_total.get((gedcom_io._norm(x["match"]), t)) or None
            row[f"{t} exp"], row[f"{t} obs"] = round(e), (round(o) if o else "")
            if o and e:
                exp.append(e); obs.append(o)
        row["ratio"] = round(sum(obs) / sum(exp), 2) if exp else ""
        rel = tree.relationship(proband, x["tree"])
        row["via"] = " & ".join(tree.label(a) for a, _, _ in rel)
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
