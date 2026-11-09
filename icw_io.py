"""
Read in-common-with (ICW) evidence into one edge table: for a tester,
"match A and match B also match each other" (a shared match).

Sources:

- Genetic Affairs AutoCluster CSV (the one in each run's zip): one row per
  match with `Identifier` (MyHeritage: the match's kit, without "D-"),
  `Name`, `total shared cM`, `Cluster`, then one column per match
  ("12_Name"); a non-empty cell means the row and column matches share.
- Genetic Affairs node/edge CSVs (FTDNA runs, also used for Gephi): nodes
  with `index`, `name`, `cM`, `group`; edges `source,value,target` by index.
- FTDNA "in common with" match lists: the Family Finder match list
  filtered to one focal match; every row shares with the focal match.

Columns out: subject, platform, a_key, b_key, a, b, source. Keys follow
the segment readers (`match_key`): MyHeritage "D-<kit>", FTDNA the
normalised name. Nodes: subject, platform, match_key, match, cM, cluster.

What an edge means: both matches share DNA with the tester and with each
other. Usually that is one ancestral line, but pile-up regions, endogamy
and people related on two lines make edges across lines too. Treat as
weak, symmetric evidence.
"""
import re
from pathlib import Path

import pandas as pd

import ftdna_io


def autocluster_matrix(path, subject, platform="MyHeritage"):
    import io
    # the table ends at the first blank line; a footer lists matches left
    # out (no shared match within the run's limits), as comma-separated names
    lines = Path(path).read_text(encoding="utf-8-sig").splitlines()
    end = next((k for k, l in enumerate(lines) if k and (not l.strip() or l.startswith("#"))), len(lines))
    d = pd.read_csv(io.StringIO("\n".join(lines[:end])), dtype=str)
    cols = [c for c in d.columns if re.match(r"^\d+_", c)]
    if platform == "MyHeritage":
        keys = ("D-" + d["Identifier"].str.strip().str.upper()).tolist()
    else:
        keys = d["Name"].map(ftdna_io._key).tolist()
    nodes = pd.DataFrame(dict(subject=subject, platform=platform, match_key=keys,
                              match=d["Name"].str.strip(),
                              cM=pd.to_numeric(d["total shared cM"], errors="coerce"),
                              cluster=d["Cluster"]))
    pos = {int(c.split("_", 1)[0]): i for i, c in enumerate(cols)}   # column number -> row
    rows = []
    for i, r in d.iterrows():
        for c in cols:
            if pd.notna(r[c]) and str(r[c]).strip():
                j = pos[int(c.split("_", 1)[0])]
                if j != i:
                    a, b = sorted((i, j))
                    rows.append((a, b))
    e = pd.DataFrame(sorted(set(rows)), columns=["i", "j"])
    return nodes, _edges(nodes, e, Path(path).name)


def ga_nodes_edges(nodes_path, edges_path, subject, platform="FTDNA", exclude_values=()):
    """`value` is an edge code from Genetic Affairs whose meaning is not
    documented here; on one FTDNA run, edges with value 231 joined matches
    placed on different parents' sides far more often than 232 or 250, so
    callers can leave codes out."""
    n = pd.read_csv(nodes_path, encoding="utf-8-sig", dtype=str)
    e = pd.read_csv(edges_path, encoding="utf-8-sig", dtype=str).dropna(subset=["source", "target"])
    if exclude_values:
        e = e[~e["value"].astype(int).isin([int(v) for v in exclude_values])]
    n["index"] = n["index"].astype(int)
    n = n.sort_values("index").set_index("index")
    nodes = pd.DataFrame(dict(subject=subject, platform=platform,
                              match_key=n["name"].map(ftdna_io._key), match=n["name"].str.strip(),
                              cM=pd.to_numeric(n["cM"], errors="coerce"),
                              cluster=n["group"])).reset_index(drop=False).rename(columns={"index": "i"})
    ij = pd.DataFrame(dict(i=e.source.astype(int), j=e.target.astype(int)))
    pos = {idx: k for k, idx in enumerate(nodes["i"])}
    ij = ij[ij.i.isin(pos) & ij.j.isin(pos)]
    ij = pd.DataFrame(dict(i=ij.i.map(pos), j=ij.j.map(pos)))
    return nodes.drop(columns="i"), _edges(nodes.drop(columns="i"), ij,
                                            f"{Path(nodes_path).name} + {Path(edges_path).name}")


def ftdna_icw_list(path, subject, focal):
    """`focal`: the match the list was filtered on, as written in the match list."""
    m = pd.read_csv(path, encoding="utf-8-sig", dtype=str)
    parts = m[["First Name", "Middle Name", "Last Name"]].fillna("")
    keys = (parts["First Name"] + " " + parts["Middle Name"] + " " + parts["Last Name"]).map(ftdna_io._key)
    fk = ftdna_io._key(focal)
    nodes = pd.DataFrame(dict(subject=subject, platform="FTDNA", match_key=keys,
                              match=m["Full Name"].str.strip(),
                              cM=pd.to_numeric(m["Shared cM"] if "Shared cM" in m else m["Shared DNA"], errors="coerce"),
                              cluster=""))
    e = pd.DataFrame(dict(subject=subject, platform="FTDNA", a_key=fk, b_key=keys, a=focal,
                          b=nodes.match, source=Path(path).name))
    return nodes, e[e.b_key != fk]


def _edges(nodes, ij, source):
    a, b = nodes.iloc[ij.i.to_numpy()], nodes.iloc[ij.j.to_numpy()]
    return pd.DataFrame(dict(subject=nodes.subject.iloc[0], platform=nodes.platform.iloc[0],
                             a_key=a.match_key.to_numpy(), b_key=b.match_key.to_numpy(),
                             a=a.match.to_numpy(), b=b.match.to_numpy(), source=source))


def load(cfg):
    """[[icw]] entries in family.toml:
         kind = "autocluster" | "ga_nodes_edges" | "ftdna_icw"
         subject, platform, file (or nodes + edges), focal (ftdna_icw)."""
    import config
    N, E = [], []
    for x in cfg.get("icw", []):
        if x["kind"] == "autocluster":
            n, e = autocluster_matrix(config.path(cfg, x["file"]), x["subject"], x.get("platform", "MyHeritage"))
        elif x["kind"] == "ga_nodes_edges":
            n, e = ga_nodes_edges(config.path(cfg, x["nodes"]), config.path(cfg, x["edges"]),
                                  x["subject"], x.get("platform", "FTDNA"), x.get("exclude_values", ()))
        elif x["kind"] == "ftdna_icw":
            n, e = ftdna_icw_list(config.path(cfg, x["file"]), x["subject"], x["focal"])
        else:
            raise ValueError(x["kind"])
        N.append(n); E.append(e)
    if not N:
        return pd.DataFrame(), pd.DataFrame()
    return pd.concat(N, ignore_index=True), pd.concat(E, ignore_index=True)
