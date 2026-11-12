"""
Where things change along a chromosome, as terse text: for reading segment
edges and reasoning about paths and unknown crossovers without opening the
HTML views.

    python3 edges.py --at 15:60-102          # events on chr15, 60-102 Mb
    python3 edges.py --at 1                  # the whole of chr1
    python3 edges.py --summary --top 30      # unexplained end clusters, genome-wide

Events, in cM order (one line each): X, a sibling's crossover (from the
phasing's copy labels); B, a change of the copy model's most likely code;
E, a cluster of segment ends (within --tol cM) across matches, with who ends
there, where they are placed, how many segments cover the spot, and what
explains it ("-" when nothing does).

Reads the pipeline's tables (copy labels, copy-model blocks, placed
segments, lineage assertions); writes nothing. Private output: it names
matches.

How it works: docs/genetics.md, "Deep labels and edges".
Sketch: the tolerance and the "explained" radius are judgement calls.
"""
import argparse
from collections import Counter

import numpy as np
import pandas as pd

import config
import identity
import intervals as iv
import outputs

TOL_CM = 0.75          # ends this close (cM) form one cluster
NEAR_CM = 1.5          # a crossover or model change this close explains a cluster
MIN_CM = 10.0          # segments shorter than this are left out (false ones end at random)
MIN_POST = 0.6         # model changes between codes less sure than this are not shown
BACKGROUND_CM = 10.0   # an end cluster is compared with the ends within this distance
# A crossover on a shared copy makes segments both end and start there; a
# cluster of ends running one way only (all starts or all ends) is a
# coverage edge: chip SNPs run out (centromere gap, chromosome tip).
ONE_WAY = 0.15         # the smaller direction under this share of a cluster -> one-way


def _range(spec):
    """'15', '15:60-102' -> (chrom, lo_bp, hi_bp)."""
    c, _, r = spec.partition(":")
    if not r:
        return c, 0, 3e8
    a, _, b = r.partition("-")
    return c, float(a) * 1e6, float(b or a) * 1e6


class Edges:
    def __init__(self, cfg, min_cm=MIN_CM):
        D = cfg["data_dir"]
        self.gm = iv.GeneticMap.load(cfg, quiet=True)
        self.labels = (outputs.read(D, "phasing_copy_labels.csv", dtype={"chrom": str})
                       if outputs.has(D, "phasing_copy_labels.csv") else None)
        b = (outputs.read(D, "copy_model_blocks.csv", dtype={"chrom": str})
             if outputs.has(D, "copy_model_blocks.csv") else pd.DataFrame())
        if len(b):
            b = b[(b.level == 3) & (b.model == ("siblings" if (b.model == "siblings").any() else "single"))]
        self.blocks = b
        s = outputs.read(D, "placed_segments.csv", dtype={"chrom": str})
        s = s[(s.cM >= min_cm) & (s.chrom != "X")].copy()
        s["parent"] = s.parent.fillna("")
        s["grandparent"] = s.grandparent.fillna("")
        s["nk"] = s.match.map(identity.name_key)
        self.segs = s
        import assertions
        a = assertions.read(D, list(assertions.ANCHOR_SOURCES), kinds={"lineage"})
        a = a[a.lineage.astype(str).str.len() > 0]
        self.deep = (a.assign(nk=a.match.map(identity.name_key), L=a.lineage.astype(str))
                     .sort_values("L", key=lambda x: x.str.len())
                     .groupby("nk").L.last().to_dict())

    def cm(self, chrom, bp):
        return np.asarray(self.gm.cm(chrom, np.asarray(bp, float)), float)

    # ------------------------------------------------------------ events
    def crossovers(self, chrom):
        out = []
        if self.labels is None:
            return out
        L = self.labels[self.labels.chrom == chrom].sort_values("start")
        for (sib, par), g in L.groupby(["sibling", "parent"]):
            g = g.reset_index(drop=True)
            for i in range(1, len(g)):
                if g.label[i] != g.label[i - 1]:
                    a, b = g.end[i - 1], g.start[i]
                    out.append(dict(kind="X", bp=(a + b) / 2, lo=a, hi=b,
                                    text=f"{sib} {par} crossover (label {g.label[i - 1]}->{g.label[i]})",
                                    who=f"{sib}:{par}"))
        return out

    def model_changes(self, chrom, min_post=MIN_POST):
        out = []
        b = self.blocks
        if not len(b):
            return out
        b = b[b.chrom == chrom].sort_values("start")
        for (subj, side), g in b.groupby(["subject", "side"]):
            g = g.reset_index(drop=True)
            for i in range(1, len(g)):
                x, y = g.lineage[i - 1], g.lineage[i]
                if x == y or max(g.posterior[i - 1], g.posterior[i]) < min_post:
                    continue
                what = (f"crossover in {x[0]}'s meiosis" if x[:2] != y[:2]
                        else f"ancestral edge: crossover in {x[:2]}'s meiosis")
                out.append(dict(kind="B", bp=g.start[i], lo=g.end[i - 1], hi=g.start[i],
                                text=f"{subj} {x}->{y} ({what}; post {g.posterior[i - 1]:.2f}/{g.posterior[i]:.2f})",
                                who=f"{subj}:{side}"))
        return out

    def end_clusters(self, chrom, tol=TOL_CM):
        s = self.segs[self.segs.chrom == chrom]
        if not len(s):
            return []
        top = float(self.cm(chrom, s.end.max()))
        rows = []
        for which in ("start", "end"):
            rows.append(s.assign(edge=which, at=s[which], at_cm=self.cm(chrom, s[which])))
        e = pd.concat(rows).sort_values("at_cm")
        bot = float(self.cm(chrom, s.start.min()))
        e = e[(e.at_cm > bot + 3) & (e.at_cm < top - 3)]      # coverage tips: cut, not recombined
        out, cur = [], []
        for r in e.itertuples():           # a cluster is at most 2 * tol wide
            if cur and (r.at_cm - cur[-1].at_cm > tol or r.at_cm - cur[0].at_cm > 2 * tol):
                out.append(cur)
                cur = []
            cur.append(r)
        if cur:
            out.append(cur)
        res = []
        starts, ends = s.start.to_numpy(), s.end.to_numpy()
        at_all = np.sort(e.at_cm.to_numpy())
        for c in out:
            matches = {r.nk for r in c}
            if len(matches) < 2:
                continue
            bp = float(np.median([r.at for r in c]))
            per = {}                              # one row per match: its placement
            for r in c:
                per.setdefault(r.nk, set()).add(r.grandparent or (r.parent + "?" if r.parent else "?"))
            gp = Counter(sorted(v)[0] if len(v) == 1 else "mixed" for v in per.values())
            deep = Counter(self.deep[m] for m in matches if m in self.deep)
            side_of_end = Counter(f"{r.edge[0]}" for r in c)
            # enrichment: ends here per cM against the ends around it
            mid = float(np.median([r.at_cm for r in c]))
            width = max(c[-1].at_cm - c[0].at_cm, tol)
            around = (np.searchsorted(at_all, mid + BACKGROUND_CM) - np.searchsorted(at_all, mid - BACKGROUND_CM)
                      - len(c))
            enrich = (len(c) / width) / max(around / (2 * BACKGROUND_CM), 1 / (2 * BACKGROUND_CM))
            ns, ne = side_of_end.get("s", 0), side_of_end.get("e", 0)
            one_way = min(ns, ne) < ONE_WAY * (ns + ne)
            res.append(dict(kind="E", bp=bp, lo=min(r.at for r in c), hi=max(r.at for r in c),
                            n_matches=len(matches), testers=len({r.subject for r in c}), enrich=enrich,
                            one_way=one_way,
                            cover=int(((starts < bp) & (ends > bp)).sum()),
                            text=(f"ends of {len(matches)} matches ({len({r.subject for r in c})} testers; "
                                  f"{ns} starts {ne} ends{' ONE-WAY' if one_way else ''}; x{enrich:.1f} the ends around; "
                                  + " ".join(f"{k}{v}" for k, v in gp.most_common())
                                  + (("; tree " + " ".join(f"{k}x{v}" if v > 1 else k for k, v in deep.most_common()))
                                     if deep else "")),
                            names=sorted({r.match for r in c})))
        return res

    def events(self, chrom, lo=0, hi=3e8, tol=TOL_CM):
        X, B = self.crossovers(chrom), self.model_changes(chrom)
        E = self.end_clusters(chrom, tol)
        near_cm = lambda bp: float(self.cm(chrom, bp))
        for e in E:
            c = near_cm(e["bp"])
            why = [x["who"] for x in X + B if abs(near_cm(x["bp"]) - c) <= NEAR_CM]
            e["explained"] = ", ".join(sorted(set(why))) or "-"
        ev = [x for x in X + B + E if lo <= x["bp"] <= hi]
        for x in ev:
            x["cm"] = near_cm(x["bp"])
        return sorted(ev, key=lambda x: x["cm"])


def show(ev, names=False):
    for x in ev:
        tail = ""
        if x["kind"] == "E":
            tail = f"; cover {x['cover']}; near: {x['explained']}"
            if names:
                tail += "\n" + " " * 22 + ", ".join(x["names"][:12]) + (" ..." if len(x["names"]) > 12 else "")
        print(f"{x['cm']:7.1f} cM {x['bp'] / 1e6:7.2f} Mb  {x['kind']}  {x['text']}{tail}")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--at", help="chrom or chrom:lo-hi (Mb)")
    ap.add_argument("--summary", action="store_true", help="unexplained end clusters, genome-wide")
    ap.add_argument("--top", type=int, default=25)
    ap.add_argument("--min-matches", type=int, default=3)
    ap.add_argument("--tol", type=float, default=TOL_CM)
    ap.add_argument("--min-cm", type=float, default=MIN_CM)
    ap.add_argument("--names", action="store_true", help="list the matches of each end cluster")
    ap.add_argument("--only", default="XBE", help="event kinds to show, e.g. E or XB")
    ap.add_argument("--one-way", action="store_true", help="include one-way clusters (coverage edges) in --summary")
    a = ap.parse_args()
    E = Edges(config.load(), a.min_cm)
    if a.summary:
        rows = []
        for c in iv.AUTOSOMES:
            rows += [dict(x, chrom=c) for x in E.events(c, tol=a.tol)
                     if x["kind"] == "E" and x["explained"] == "-" and x["n_matches"] >= a.min_matches
                     and (a.one_way or not x["one_way"])]
        rows.sort(key=lambda x: -x["enrich"])
        for x in rows[: a.top]:
            print(f"chr{x['chrom']:>2}", end=" ")
            show([x], a.names)
        print(f"({len(rows)} unexplained clusters of >= {a.min_matches} matches; cover = segments across the spot)")
        return
    if not a.at:
        ap.error("--at or --summary")
    chrom, lo, hi = _range(a.at)
    show([x for x in E.events(chrom, lo, hi, a.tol) if x["kind"] in a.only], a.names)


if __name__ == "__main__":
    main()
