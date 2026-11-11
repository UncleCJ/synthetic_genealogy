"""
Ingest every segment export listed in family.toml, place matches on
grandparents (match_placement), cross-check, and write a report.

  python3 revelations.py            -> <data_dir>/output/revelations.md + CSVs
"""

import pandas as pd

import outputs

import config
import identity
import kits
import match_placement as mp

CFG = config.load()
D = CFG["data_dir"]


def load():
    return kits.load(CFG)


# ---------------------------------------------------------------- checks
_name_key = identity.name_key


def check_dnapainter(all_segs):
    """Compare each DNA Painter lineage assertion with the placed segment of
    the same subject, chromosome and match (MyHeritage ID from the
    evidence URL, else the name), overlapping >= 50%."""
    if not outputs.has(D, "assertions_dnapainter.csv"):
        return pd.DataFrame()
    a = outputs.read(D, "assertions_dnapainter.csv", dtype={"chrom": str})
    a = a[(a.kind == "lineage")]
    a["mh_key"] = a.evidence.fillna("").str.extract(identity.MH_PAIR_IN)[0].str.upper()
    a["nkey"] = a.match.map(_name_key)
    s = all_segs.assign(nkey=all_segs.match.map(_name_key))
    rows = []
    for x in a.itertuples():
        cand = s[(s.subject == x.subject) & (s.chrom == x.chrom)]
        cand = cand[(cand.match_key == x.mh_key) | (cand.nkey == x.nkey)]
        if not len(cand):
            continue
        ov = mp._overlap(x.start, x.end, cand.start.to_numpy(), cand.end.to_numpy()) / (x.end - x.start)
        if ov.max() < 0.5:
            continue
        c = cand.iloc[ov.argmax()]
        rows.append(dict(assertion_id=x.assertion_id, subject=x.subject, chrom=x.chrom,
                         match=x.match, painted=x.lineage, platform=c.platform,
                         parent_found=c.parent, grandparent_found=c.grandparent,
                         parent_ok=(c.parent == x.lineage[0]) if c.parent else None,
                         gp_ok=(c.grandparent == x.lineage[:2])
                         if len(x.lineage) >= 2 and c.grandparent else None))
    return pd.DataFrame(rows)


def check_siblings(platforms):
    rows = []
    for plat, p in platforms.items():
        kids = p["children"]
        for i in range(len(kids)):
            for j in range(i + 1, len(kids)):
                a = kids[i]["placed"].set_index("match_key")
                b = kids[j]["placed"].set_index("match_key")
                both = a.index.intersection(b.index)
                agree = (a.loc[both, "placement"] == b.loc[both, "placement"])
                rows.append(dict(platform=plat, pair=f"{kids[i]['subject']}–{kids[j]['subject']}",
                                 shared_matches=len(both), same_grandparent=int(agree.sum()),
                                 share=round(agree.mean(), 3) if len(both) else None))
    return pd.DataFrame(rows)


def tree_anchor_report():
    """Tree links as anchors, judged leave-one-out by the rest of the
    evidence in their block (phasing_verdicts.csv): the matches whose tree
    path the painting mostly contradicts are the links to re-examine."""
    if not outputs.has(D, "phasing_verdicts.csv"):
        return ""
    v = outputs.read(D, "phasing_verdicts.csv", dtype={"chrom": str})
    v = v[v.assertion_id.str.startswith("tree:") & v.verdict.isin(["agrees", "conflicts"])]
    if not len(v):
        return ""
    g = v.assign(ok=v.snps_used.where(v.verdict == "agrees", 0)).groupby(["match", "lineage"]) \
         .agg(claims=("assertion_id", "size"), snps=("snps_used", "sum"), agree_snps=("ok", "sum"))
    g["agree"] = (g.agree_snps / g.snps).round(2)
    g = g.reset_index().sort_values(["agree", "snps"], ascending=[True, False])
    bad = g[g.agree < 0.5]
    return ("\n## Tree links as anchors\n\n"
            f"{len(g)} tree-linked matches voted on the grandparent labels; "
            f"{(g.agree >= 0.5).sum()} mostly agree with the rest of the evidence, "
            f"{len(bad)} mostly conflict (links or names to re-examine; weight "
            "3 for confirmed identities and distinctive names, 1 for patronymic name joins):\n\n"
            + (md(bad, ["match", "lineage", "claims", "snps", "agree"], n=40, floatfmt="{:.2f}")
               if len(bad) else "none\n"))


# ---------------------------------------------------------------- report
def md(df, cols=None, n=None, floatfmt="{:.0f}"):
    df = df if cols is None else df[cols]
    df = df if n is None else df.head(n)
    def f(v):
        if isinstance(v, float):
            return "" if pd.isna(v) else floatfmt.format(v)
        if isinstance(v, pd.Timestamp):
            return v.strftime("%Y-%m-%d")
        return str(v).replace("|", "/")[:70] if v is not None else ""
    head = "| " + " | ".join(df.columns) + " |\n|" + "---|" * len(df.columns) + "\n"
    return head + "".join("| " + " | ".join(f(v) for v in r) + " |\n"
                          for r in df.itertuples(index=False))


def main():
    platforms = load()
    paint = mp.load_painting(D)
    method = config.placement_method(CFG)
    models = {}
    if method == "copy_model":
        import copy_model
        models = copy_model.fit_models(CFG)[0]
    labels = (outputs.read(D, "phasing_copy_labels.csv", dtype={"chrom": str})
              if outputs.has(D, "phasing_copy_labels.csv") else None)
    relatives = mp.relative_paths(CFG, platforms)
    for p in platforms.values():
        mp.run_platform(p["children"], p["mother"], paint, models, labels, relatives)

    kits = [(plat, k) for plat, p in platforms.items() for k in p["children"] + [p["mother"]] if k is not None]
    all_segs = pd.concat([k["segs"].assign(platform=plat) for plat, k in kits], ignore_index=True)
    all_placed = pd.concat([k["placed"].assign(platform=plat, subject=k["subject"])
                            for plat, k in kits], ignore_index=True)
    painted = (outputs.read(D, "assertions_dnapainter.csv")
               if outputs.has(D, "assertions_dnapainter.csv") else
               pd.DataFrame(columns=["match", "evidence"]))
    painted_keys = set(painted.match.map(_name_key)) | set(
        painted.evidence.fillna("").str.extract(identity.MH_PAIR_IN)[0]
        .dropna().str.upper())
    all_placed["in_dnapainter"] = all_placed.match.map(_name_key).isin(painted_keys) | \
        all_placed.match_key.isin(painted_keys)

    cols = ["platform", "subject", "match_key", "match", "chrom", "start", "end", "cM",
            "parent", "parent_reason", "grandparent", "purity", "straddles_crossover",
            "if_paternal", "if_maternal", "relative_gp", "painting_grandparent", "painting_purity", "reason", "source"]
    outputs.write(D, "placed_segments.csv", all_segs.reindex(columns=cols))
    outputs.write(D, "placed_matches.csv", all_placed)

    dp = check_dnapainter(all_segs)
    sib = check_siblings(platforms)
    out = []
    w = out.append
    w("# Match placement on grandparents\n")
    w("Generated by `revelations.py` from FTDNA and MyHeritage segment exports, "
      + ("the visual-phasing grandparent painting (three siblings' raw kits plus the "
         "mother's), " if len(paint) else "no painting (no phased sibling set: copy models only), ")
      + "with grandparents named by "
      + ", ".join(config.anchor_sources(CFG)) + " anchors. Every placement is an "
      "inference with its reason in `placed_segments.csv`.\n")
    if models:
        w("\nGrandparents come from the copy model (`[placement] method`), for "
          + ", ".join(sorted(models)) + f": a segment is placed where the model is at least "
          f"{copy_model.MIN_P} sure over it; the painting's reading is kept beside it "
          "(`painting_grandparent`), and `copy_model_placement.md` compares the two. "
          "Testers without a copy model are placed through the painting.\n")

    w("## Kits\n")
    kt = pd.DataFrame([dict(platform=plat, subject=k["subject"], export=k["date"],
                            segments=len(k["segs"]), matches=len(k["keys"]),
                            placed_segments=int(k["segs"].grandparent.isin(["FF", "FM", "MF", "MM"]).sum()))
                       for plat, k in kits])
    w(md(kt))

    w("\n## How far to trust it\n")
    for plat, p in platforms.items():
        for k in [x for x in p["children"] + [p["mother"]] if x is not None]:
            if "Matching Bucket" in k["placed"]:
                ct = pd.crosstab(k["placed"]["Matching Bucket"].fillna("—"), k["placed"].placement)
                w(f"\n**{plat} {k['subject']}: FTDNA's own bucket (rows) vs placement (columns)**\n\n")
                w(md(ct.reset_index()))
    w("\nFor the mother, FTDNA's *Paternal* bucket is her father's side, i.e. MF; *Maternal* is MM.\n")
    w("\n**Siblings placing the same match**\n\n" + md(sib, floatfmt="{:.3f}"))
    if len(dp):
        g = dp.groupby("subject").agg(compared=("assertion_id", "size"),
                                      parent_ok=("parent_ok", lambda s: f"{(s == True).sum()}/{s.notna().sum()}"),
                                      grandparent_ok=("gp_ok", lambda s: f"{(s == True).sum()}/{s.notna().sum()}"))
        held_out = "dnapainter" not in config.anchor_sources(CFG)
        w("\n**DNA Painter assertions vs placement** (same match, ≥50% overlap"
          + ("; held out: the paintings did not anchor the phasing" if held_out else "") + ")\n\n"
          + md(g.reset_index()))
        bad = dp[(dp.parent_ok == False) | (dp.gp_ok == False)]
        if len(bad):
            w("\nDisagreeing DNA Painter segments:\n\n" + md(bad, ["subject", "platform", "chrom", "match", "painted",
                                                                    "parent_found", "grandparent_found"], n=40))

    w(tree_anchor_report())
    w("\n## Closest relatives outside the nuclear family\n\n")
    near = all_placed[all_placed.shared_cM >= 150].sort_values("shared_cM", ascending=False)
    w(md(near, ["platform", "subject", "match", "shared_cM", "placement", "agreement",
                "FF", "FM", "MF", "MM"], n=30))
    w("\nA relative sharing on **both** grandparents of one side (e.g. FF and FM) "
      "descends from both, like a full aunt/uncle or first cousin; one grandparent only "
      "points to a half-relationship or a more distant line.\n")

    w("\n## New leads per grandparent (not in DNA Painter)\n")
    leads = all_placed[(~all_placed.in_dnapainter) & (all_placed.agreement >= 0.8)
                       & (all_placed.placed_cM >= 15)]
    for gp in ("FF", "FM", "MF", "MM"):
        name = config.grandparent_label(CFG, gp)
        l = leads[leads.placement == gp].sort_values("shared_cM", ascending=False)
        w(f"\n### {name} ({len(l)} matches)\n\n")
        w(md(l, ["platform", "subject", "match", "shared_cM", "placed_cM", "agreement",
                 "Ancestral Surnames"] if "Ancestral Surnames" in l else None, n=12))

    w("\n## Matches landing on more than one grandparent\n\n")
    multi = all_placed[(all_placed.agreement < 0.6) & (all_placed.placed_cM >= 30)] \
        .sort_values("placed_cM", ascending=False)
    w(f"{len(multi)} matches with ≥30 cM placed and no grandparent holding 60%. "
      "Candidates for relatedness through two lines (pedigree collapse), or false segments.\n\n")
    w(md(multi, ["platform", "subject", "match", "shared_cM", "FF", "FM", "MF", "MM"], n=20))

    w("\n## Mother's matches none of the tested children carry\n\n")
    mo = pd.concat([p["mother"]["segs"].assign(platform=plat) for plat, p in platforms.items()
                    if p["mother"] is not None]
                   + [pd.DataFrame(columns=["platform", "match", "chrom", "start", "end", "cM",
                                            "grandparent", "reason"])])
    other = mo[mo.reason.str.contains("lacks", na=False) & ~mo.reason.str.contains("shares", na=False)]
    w(f"{len(other)} segments placed by the 'other copy' rule: the mother has them, a child "
      "with a full match list does not, so they sit on the copy that child did not get. "
      "These are leads only the mother (or an untested sibling) can follow.\n\n")
    w(md(other.sort_values("cM", ascending=False),
         ["platform", "match", "chrom", "start", "end", "cM", "grandparent", "reason"], n=20))

    w("\n## Segments straddling a child's crossover\n\n")
    st = all_segs[all_segs.straddles_crossover == True]
    w(f"{len(st)} child segments lie across a crossover in that child's painting. "
      "A real IBD segment sits on one grandparent's copy, so either the segment is partly "
      "false or the crossover is misplaced.\n\n")
    w(md(st.sort_values("cM", ascending=False),
         ["platform", "subject", "match", "chrom", "start", "end", "cM", "purity"], n=15, floatfmt="{:.2f}"))

    w("\n## Pile-up regions (2 Mb bins, robust z ≥ 3)\n\n")
    for plat, k in kits:
        pu = mp.pileups(k["segs"])
        w(f"\n**{plat} {k['subject']}**: " + ", ".join(
            f"chr{r.chrom} {r.start_Mb}–{r.end_Mb} Mb ({r['count']})" for _, r in pu.head(8).iterrows()) + "\n")
    w("\nchr6 ~28–34 Mb is the HLA region; bins near centromeres (chr2 ~90 Mb, chr9 ~40–70 Mb) "
      "are typical too. Small segments there deserve little weight.\n")

    (D / "revelations.md").write_text("".join(out), encoding="utf-8")
    print("".join(out)[:200], "...\n->", D / "revelations.md")


if __name__ == "__main__":
    main()
