"""
Ingest every segment export listed in family.toml, place matches on
grandparents (match_placement), cross-check, and write a report.

  python3 revelations.py            -> <data_dir>/output/revelations.md + CSVs
"""

import pandas as pd

from sg.common import outputs

from sg.common import config
from sg.common import identity
from sg.common import kits
from sg.genetics import match_placement as mp

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
    v = v[v.assertion_id.str.startswith("tree:") & v.verdict.isin(["agrees", "dissents"])]
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


GRANDPARENTS = ("FF", "FM", "MF", "MM")
SEG_COLS = ["platform", "subject", "match_key", "match", "chrom", "start", "end", "cM",
            "parent", "parent_reason", "grandparent", "purity", "straddles_crossover",
            "if_paternal", "if_maternal", "relative_gp", "painting_grandparent", "painting_purity",
            "reason", "source"]


def main():
    platforms = load()
    paint, models = _place(platforms)
    kit_list = [(plat, k) for plat, p in platforms.items() for k in _kits_of(p)]
    all_segs, all_placed = _collect(kit_list)
    outputs.write(D, "placed_segments.csv", all_segs.reindex(columns=SEG_COLS))
    outputs.write(D, "placed_matches.csv", all_placed)

    dp = check_dnapainter(all_segs)
    sib = check_siblings(platforms)
    out = [_intro(paint, models),
           _kits_section(kit_list),
           _trust_section(platforms, sib, dp),
           tree_anchor_report(),
           _closest_relatives(all_placed),
           _new_leads(all_placed),
           _multi_grandparent(all_placed),
           _mother_only(platforms),
           _straddling(all_segs),
           _pileup_section(kit_list)]
    (D / "revelations.md").write_text("".join(out), encoding="utf-8")
    print("".join(out)[:200], "...\n->", D / "revelations.md")


def _read_if(name, default, **kw):
    """An output file if it exists, else the default."""
    return outputs.read(D, name, **kw) if outputs.has(D, name) else default


def _kits_of(p):
    """A platform's kits: the children, then the mother if she has one."""
    return [k for k in p["children"] + [p["mother"]] if k is not None]


def _place(platforms):
    """Place every kit's segments on grandparents, in place; returns the
    painting and the copy models (empty unless the method is copy_model)."""
    paint = mp.load_painting(D)
    models = {}
    if config.placement_method(CFG) == "copy_model":
        from sg.genetics import copy_model
        models = copy_model.fit_models(CFG)[0]
    labels = _read_if("phasing_copy_labels.csv", None, dtype={"chrom": str})
    relatives = mp.relative_paths(CFG, platforms)
    for p in platforms.values():
        mp.run_platform(p["children"], p["mother"], paint, models, labels, relatives)
    return paint, models


def _collect(kit_list):
    """All kits' placed segments and placed matches in two tables, the
    matches marked when DNA Painter already has them."""
    all_segs = pd.concat([k["segs"].assign(platform=plat) for plat, k in kit_list], ignore_index=True)
    all_placed = pd.concat([k["placed"].assign(platform=plat, subject=k["subject"])
                            for plat, k in kit_list], ignore_index=True)
    keys = _painted_keys()
    all_placed["in_dnapainter"] = all_placed.match.map(_name_key).isin(keys) | \
        all_placed.match_key.isin(keys)
    return all_segs, all_placed


def _painted_keys():
    """Name keys and MyHeritage IDs of the matches DNA Painter has painted."""
    painted = _read_if("assertions_dnapainter.csv", pd.DataFrame(columns=["match", "evidence"]))
    mh_ids = painted.evidence.fillna("").str.extract(identity.MH_PAIR_IN)[0].dropna().str.upper()
    return set(painted.match.map(_name_key)) | set(mh_ids)


def _intro(paint, models):
    """The title, what the placement was made from, and the copy model's part."""
    s = ("# Match placement on grandparents\n"
         "Generated by `revelations.py` from FTDNA and MyHeritage segment exports, "
         + ("the visual-phasing grandparent painting (three siblings' raw kits plus the "
            "mother's), " if len(paint) else "no painting (no phased sibling set: copy models only), ")
         + "with grandparents named by "
         + ", ".join(config.anchor_sources(CFG)) + " anchors. Every placement is an "
         "inference with its reason in `placed_segments.csv`.\n")
    if models:
        from sg.genetics import copy_model
        s += ("\nGrandparents come from the copy model (`[placement] method`), for "
              + ", ".join(sorted(models)) + f": a segment is placed where the model is at least "
              f"{copy_model.MIN_P} sure over it; the painting's reading is kept beside it "
              "(`painting_grandparent`), and `copy_model_placement.md` compares the two. "
              "Donors without a copy model are placed through the painting.\n")
    return s


def _kits_section(kit_list):
    """Per kit: export date, segments, matches, segments placed on a grandparent."""
    kt = pd.DataFrame([dict(platform=plat, subject=k["subject"], export=k["date"],
                            segments=len(k["segs"]), matches=len(k["keys"]),
                            placed_segments=int(k["segs"].grandparent.isin(GRANDPARENTS).sum()))
                       for plat, k in kit_list])
    return "## Kits\n" + md(kt)


def _trust_section(platforms, sib, dp):
    """How far to trust the placement: FTDNA's buckets, siblings, DNA Painter."""
    return ("\n## How far to trust it\n"
            + _bucket_tables(platforms)
            + "\nFor the mother, FTDNA's *Paternal* bucket is her father's side, i.e. MF; *Maternal* is MM.\n"
            + "\n**Siblings placing the same match**\n\n" + md(sib, floatfmt="{:.3f}")
            + _dnapainter_section(dp))


def _bucket_tables(platforms):
    """Per FTDNA kit: FTDNA's own maternal/paternal bucket against the placement."""
    s = ""
    for plat, p in platforms.items():
        for k in _kits_of(p):
            if "Matching Bucket" in k["placed"]:
                ct = pd.crosstab(k["placed"]["Matching Bucket"].fillna("—"), k["placed"].placement)
                s += f"\n**{plat} {k['subject']}: FTDNA's own bucket (rows) vs placement (columns)**\n\n"
                s += md(ct.reset_index())
    return s


def _ok_ratio(s):
    """'right/judged' for a column of True, False and None."""
    return f"{(s == True).sum()}/{s.notna().sum()}"


def _dnapainter_section(dp):
    """DNA Painter's assertions against the placement, and the ones that disagree."""
    if not len(dp):
        return ""
    g = dp.groupby("subject").agg(compared=("assertion_id", "size"),
                                  parent_ok=("parent_ok", _ok_ratio),
                                  grandparent_ok=("gp_ok", _ok_ratio))
    held_out = "dnapainter" not in config.anchor_sources(CFG)
    s = ("\n**DNA Painter assertions vs placement** (same match, ≥50% overlap"
         + ("; held out: the paintings did not anchor the phasing" if held_out else "") + ")\n\n"
         + md(g.reset_index()))
    bad = dp[(dp.parent_ok == False) | (dp.gp_ok == False)]
    if len(bad):
        s += "\nDisagreeing DNA Painter segments:\n\n" + md(
            bad, ["subject", "platform", "chrom", "match", "painted", "parent_found", "grandparent_found"], n=40)
    return s


def _closest_relatives(all_placed):
    """Matches sharing 150 cM or more, with how they spread over the grandparents."""
    near = all_placed[all_placed.shared_cM >= 150].sort_values("shared_cM", ascending=False)
    return ("\n## Closest relatives outside the nuclear family\n\n"
            + md(near, ["platform", "subject", "match", "shared_cM", "placement", "agreement",
                        *GRANDPARENTS], n=30)
            + "\nA relative sharing on **both** grandparents of one side (e.g. FF and FM) "
            "descends from both, like a full aunt/uncle or first cousin; one grandparent only "
            "points to a half-relationship or a more distant line.\n")


def _new_leads(all_placed):
    """Per grandparent: well-placed matches of 15 cM and up that DNA Painter lacks."""
    s = "\n## New leads per grandparent (not in DNA Painter)\n"
    leads = all_placed[(~all_placed.in_dnapainter) & (all_placed.agreement >= 0.8)
                       & (all_placed.placed_cM >= 15)]
    for gp in GRANDPARENTS:
        name = config.grandparent_label(CFG, gp)
        l = leads[leads.placement == gp].sort_values("shared_cM", ascending=False)
        cols = (["platform", "subject", "match", "shared_cM", "placed_cM", "agreement", "Ancestral Surnames"]
                if "Ancestral Surnames" in l else None)
        s += f"\n### {name} ({len(l)} matches)\n\n" + md(l, cols, n=12)
    return s


def _multi_grandparent(all_placed):
    """Matches of 30 cM and up placed with no grandparent holding 60%."""
    multi = all_placed[(all_placed.agreement < 0.6) & (all_placed.placed_cM >= 30)] \
        .sort_values("placed_cM", ascending=False)
    return ("\n## Matches landing on more than one grandparent\n\n"
            f"{len(multi)} matches with ≥30 cM placed and no grandparent holding 60%. "
            "Candidates for relatedness through two lines (pedigree collapse), or false segments.\n\n"
            + md(multi, ["platform", "subject", "match", "shared_cM", *GRANDPARENTS], n=20))


def _mother_only(platforms):
    """The mother's segments placed by the 'other copy' rule: no donor child carries them."""
    mo = pd.concat([p["mother"]["segs"].assign(platform=plat) for plat, p in platforms.items()
                    if p["mother"] is not None]
                   + [pd.DataFrame(columns=["platform", "match", "chrom", "start", "end", "cM",
                                            "grandparent", "reason"])])
    other = mo[mo.reason.str.contains("lacks", na=False) & ~mo.reason.str.contains("shares", na=False)]
    return ("\n## Mother's matches none of the donor children carry\n\n"
            f"{len(other)} segments placed by the 'other copy' rule: the mother has them, a child "
            "with a full match list does not, so they sit on the copy that child did not get. "
            "These are leads only the mother (or an non-donor sibling) can follow.\n\n"
            + md(other.sort_values("cM", ascending=False),
                 ["platform", "match", "chrom", "start", "end", "cM", "grandparent", "reason"], n=20))


def _straddling(all_segs):
    """Child segments lying across a crossover in that child's painting."""
    st = all_segs[all_segs.straddles_crossover == True]
    return ("\n## Segments straddling a child's crossover\n\n"
            f"{len(st)} child segments lie across a crossover in that child's painting. "
            "A real IBD segment sits on one grandparent's copy, so either the segment is partly "
            "false or the crossover is misplaced.\n\n"
            + md(st.sort_values("cM", ascending=False),
                 ["platform", "subject", "match", "chrom", "start", "end", "cM", "purity"],
                 n=15, floatfmt="{:.2f}"))


def _pileup_section(kit_list):
    """Per kit: the 2 Mb bins where unusually many segments pile up."""
    s = "\n## Pile-up regions (2 Mb bins, robust z ≥ 3)\n\n"
    for plat, k in kit_list:
        pu = mp.pileups(k["segs"])
        bins = ", ".join(f"chr{r.chrom} {r.start_Mb}–{r.end_Mb} Mb ({r['count']})"
                         for _, r in pu.head(8).iterrows())
        s += f"\n**{plat} {k['subject']}**: " + bins + "\n"
    return (s + "\nchr6 ~28–34 Mb is the HLA region; bins near centromeres "
            "(chr2 ~90 Mb, chr9 ~40–70 Mb) are typical too. Small segments there deserve little weight.\n")


if __name__ == "__main__":
    main()
