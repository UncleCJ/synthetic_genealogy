"""
A match-centred chromosome browser and research report, as one HTML file.

    python3 match_view.py --entry q-some-question            # focus = entry's people
    python3 match_view.py --focus "Erik Example" --focus "Anna Example" --title "..."
    python3 match_view.py --focus "Erik Example" --md      # also report_<title>.md, facts only
    python3 match_view.py --like '\\bExample\\b'           # every match of that name, as a group
    python3 match_view.py --report erik --focus "Erik Example"   # keep it: data/notes/reports/erik.md
    python3 match_view.py --report erik                   # regenerate it, with the summary written there
    python3 match_view.py --all-reports                   # regenerate every kept report

For the focus matches it shows, per sibling, both parental copies painted
by grandparent (the phased painting), with:

- the focus matches' segments on the copy they lie on; a segment whose
  parent is unknown is drawn dashed on both copies, labelled with the
  grandparent each reading would give;
- the other matches that share the same stretch with the same sibling
  (overlap ≥ half of the shorter segment, ≥ 7 cM): triangulation
  candidates, coloured by where they were placed;
- totals per tester, shared-match neighbours (merged AutoCluster graph,
  with support), tree persons linked to these matches, and the research
  entry's own text.

With a confirmed identity (`[[identity]]`, optionally `down = n` and
`line` for a path below the tree person) it adds a relation section: each
tester's relationship, expected and observed cM, WATO-style odds
(relationship_check.odds), path variants, and whether the placed segments
sit on the grandparent the path predicts. Without one, the indications:
odds per tester, where the segments were placed, the shared-match
neighbours, tree persons of the same name, research entries naming the
match. Both end with the ancestors involved as an Ahnentafel list, with
each one's unique record references (volume_refs.csv). `--md` writes the
same facts as compact Markdown, for writing the narrative.

A kept report (`--report NAME`) lives in data/notes/reports/NAME.md: a
TOML header (title, focus, like, written) and below it a summary for an
outside reader, written once by hand or by a session from the Markdown
facts. It is shown at the top and kept when the facts are regenerated,
with its date beside the regeneration date.

Click a chromosome to enlarge it; hover a segment for details. Everything
is inside the file (no network); it names matches and positions, so it
stays in data/ (private) unless you decide otherwise.
"""
import argparse
import html
import json
import re
from pathlib import Path

import numpy as np
import pandas as pd

import config
import icw_io
import lineage
import match_placement as mp
import outputs

GRCH37 = [249250621, 243199373, 198022430, 191154276, 180915260, 171115067, 159138663, 146364022,
          141213431, 135534747, 135006516, 133851895, 115169878, 107349540, 102531392, 90354753,
          81195210, 78077248, 59128983, 63025520, 48129895, 51304566]
MIN_CM, MIN_OVERLAP, MAX_NEIGHBOURS = 7.0, 0.5, 12
MAX_SET = 20      # matches kept in the neighbour set (largest totals), the segment table and the browser


def md_to_html(text):
    """Enough Markdown for research entries: headings, lists, tables, emphasis, code."""
    out, in_list, table = [], False, []

    def inline(s):
        s = html.escape(s)
        s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
        s = re.sub(r"`(.+?)`", r"<code>\1</code>", s)
        return s

    def flush_table():
        if table:
            rows = [r for r in table if not re.match(r"^\|\s*-", r)]
            cells = [[c.strip() for c in r.strip("|").split("|")] for r in rows]
            out.append("<table><thead><tr>" + "".join(f"<th>{inline(c)}</th>" for c in cells[0]) + "</tr></thead><tbody>"
                       + "".join("<tr>" + "".join(f"<td>{inline(c)}</td>" for c in r) + "</tr>" for r in cells[1:])
                       + "</tbody></table>")
            table.clear()

    lines = []                      # wrapped lines joined first, so emphasis may span them
    for line in text.splitlines():
        block = re.match(r"\s*([-|#]|\d+\.)\s", line + " ") and not line.startswith("  ")
        if lines and lines[-1].strip() and line.strip() and not block and not lines[-1].lstrip().startswith(("|", "#")):
            lines[-1] = lines[-1].rstrip() + " " + line.strip()
        else:
            lines.append(line)
    for line in lines:
        if line.startswith("|"):
            table.append(line)
            continue
        flush_table()
        if line.startswith("- "):
            if not in_list:
                out.append("<ul>"); in_list = True
            out.append(f"<li>{inline(line[2:])}</li>")
            continue
        if in_list:
            out.append("</ul>"); in_list = False
        if line.startswith("#"):
            n = len(line) - len(line.lstrip("#"))
            out.append(f"<h{n + 2}>{inline(line.lstrip('#').strip())}</h{n + 2}>")
        elif line.strip():
            out.append(f"<p>{inline(line)}</p>")
    flush_table()
    if in_list:
        out.append("</ul>")
    return "\n".join(out)


def read_entry(path):
    text = Path(path).read_text(encoding="utf-8")
    import tomllib
    _, head, body = text.split("+++", 2)
    return tomllib.loads(head), body


def build(cfg, focus, title, entry_body=""):
    D = cfg["data_dir"]
    children = cfg["children"]
    names = {k: v["short"] for k, v in testers_named(cfg).items()}
    segs = outputs.read(D, "placed_segments.csv", dtype={"chrom": str})
    segs = segs[segs.chrom.isin([str(c) for c in range(1, 23)])]
    paint = mp.load_painting(D)
    fkeys = {icw_io.name_key(f) for f in focus}
    segs["nk"] = segs.match.map(icw_io.name_key)
    fseg = segs[segs.nk.isin(fkeys)]
    others = segs[~segs.nk.isin(fkeys) & (segs.cM >= MIN_CM)]

    def gp(r):
        return r.grandparent if isinstance(r.grandparent, str) else ""

    focus_rows, neigh_rows = [], []
    for r in fseg.itertuples():
        focus_rows.append(dict(t=r.subject, m=r.match, c=r.chrom, s=int(r.start), e=int(r.end), cm=round(r.cM, 1),
                               p=r.parent if isinstance(r.parent, str) else "", g=gp(r),
                               ip=r.if_paternal if isinstance(r.if_paternal, str) else "",
                               im=r.if_maternal if isinstance(r.if_maternal, str) else "",
                               why=r.parent_reason if isinstance(r.parent_reason, str) else "", src=r.platform))
        o = others[(others.subject == r.subject) & (others.chrom == r.chrom)]
        ov = (o.end.clip(upper=r.end) - o.start.clip(lower=r.start)).clip(lower=0)
        short = pd.concat([(o.end - o.start), pd.Series(r.end - r.start, index=o.index)], axis=1).min(axis=1)
        o = o[ov / short >= MIN_OVERLAP].assign(ov=ov).sort_values("cM", ascending=False).head(MAX_NEIGHBOURS)
        for q in o.itertuples():
            neigh_rows.append(dict(t=q.subject, m=q.match, c=q.chrom, s=int(q.start), e=int(q.end), cm=round(q.cM, 1),
                                   p=q.parent if isinstance(q.parent, str) else "", g=gp(q), src=q.platform,
                                   near=r.match, fp=r.parent if isinstance(r.parent, str) else ""))
    neigh = pd.DataFrame(neigh_rows).drop_duplicates(["t", "m", "c", "s"]) if neigh_rows else pd.DataFrame()
    # totals
    placed = outputs.read(D, "placed_matches.csv")
    placed["nk"] = placed.match.map(icw_io.name_key)
    tot = placed[placed.nk.isin(fkeys)].groupby(["match", "subject"]).shared_cM.max().unstack()
    seg_tot = fseg.groupby(["match", "subject"]).cM.sum().unstack()
    totals = (seg_tot.combine_first(tot) if tot is not None else seg_tot).round(1)
    # who in the family appears at all: a sibling with no row has no listed segment
    # shared-match neighbours from the merged graph
    graph_rows = []
    try:
        import match_graph
        G, *_ = match_graph.build(cfg)
        for k, d in G.nodes(data=True):
            if d.get("kind") == "match" and icw_io.name_key(d["label"]) in fkeys:
                for v, e in G[k].items():
                    if e.get("kind") == "shared match":
                        graph_rows.append(dict(focus=d["label"], match=G.nodes[v]["label"],
                                               placement=G.nodes[v]["placement"], support=e["support"],
                                               runs=f'{e["reported"]}/{e["observable"]}'))
    except Exception as ex:   # the graph needs AutoCluster runs; the report works without
        graph_rows.append(dict(focus="", match=f"(no shared-match graph: {ex})", placement="", support="", runs=""))
    # tree links
    links = [x for x in cfg.get("identity", []) if icw_io.name_key(x["match"]) in fkeys]
    data = dict(
        title=title, chroms=GRCH37, testers=children, names=names,
        paint=[dict(t=r.subject, c=str(r.chrom), p=r.parent, s=int(r.start), e=int(r.end), g=r.lineage)
               for r in paint.itertuples() if r.subject in children],
        focus=focus_rows, neigh=neigh.to_dict("records") if len(neigh) else [],
        grandparents={k: v for k, v in cfg.get("grandparents", {}).items()})
    return data, totals, pd.DataFrame(graph_rows), links, fseg


# -- who the testers are, for readers who don't know the family's short names --
WORDS = {"sibling": ("brother", "sister"), "half sibling": ("half-brother", "half-sister"),
         "aunt/uncle": ("uncle", "aunt"), "great-aunt/uncle": ("great-uncle", "great-aunt")}


_NAMED = {}


def testers_named(cfg):
    """{tester key: dict(short, full, rel)}: the given (call) name, the full
    name and the relationship to the proband, from the tree where it can;
    otherwise the name in family.toml."""
    if id(cfg) not in _NAMED:
        _NAMED[id(cfg)] = _named(cfg)
    return _NAMED[id(cfg)]


def _named(cfg):
    out = {k: dict(short=config.display_name(cfg, k), full=config.display_name(cfg, k), rel="")
           for k in cfg["people"]}
    try:
        import gedcom_io
        tree, proband = gedcom_io.load(cfg)
        pid = tree.id(proband)
    except Exception:
        return out
    for k, p in cfg["people"].items():
        try:
            i = tree.id(p["mh"])
        except (KeyError, TypeError):
            continue
        q = tree.people[i]
        short = q["call"] or (q["given"].split() or [out[k]["short"]])[0]
        r = tree.relation(pid, i)
        if i == pid:
            rel = "proband"
        elif r and r["up_b"] == 0:             # the tester is the proband's ancestor
            rel = {1: ("father", "mother"), 2: ("grandfather", "grandmother")}.get(r["up_a"], (r["name"],) * 2)[q["sex"] == "F"]
        elif r:
            rel = WORDS.get(r["name"], (r["name"],) * 2)[q["sex"] == "F"]
        else:
            rel = "not related in the tree"
        out[k] = dict(short=short, full=f"{q['given']} {q['surname']}".strip(), rel=rel, sex=q["sex"])
    return out


def headline(cfg):
    """One sentence placing the testers in relation to the proband (empty
    when the proband is the only tester)."""
    tn = testers_named(cfg)
    pro = next((v for v in tn.values() if v["rel"] == "proband"), None)
    others = [v for v in tn.values() if v["rel"] != "proband"]
    if not pro or not others:
        return ""
    his = {"M": "his", "F": "her"}.get(pro.get("sex"), "their")
    nick = lambda v: "" if v["short"] in v["full"].split() else f" ({v['short']})"
    rest = [f"{his} {v['rel']} {v['full']}{nick(v)}" for v in others]
    rest = ", ".join(rest[:-1]) + (" and " if len(rest) > 1 else "") + rest[-1]
    return f"From the point of view of {pro['full']}{nick(pro)}; also tested: {rest}."


# -- relation, indications, ancestors -----------------------------------
BRANCH_SHARE = 0.3        # a grandparent branch with this share of the placed cM is "indicated"


def _short(cfg, t):
    return testers_named(cfg).get(t, {}).get("short", t)


def _testers(cfg):
    return {k: p["mh"] for k, p in cfg["people"].items() if p.get("mh")}


def _placed_cm(fseg, match_keys, mother=None):
    """cM per tester by where the segments were placed: grandparent, or side
    only. The mother's segments are maternal from the children's view."""
    s = fseg[fseg.nk.isin(match_keys)]
    side = s.parent.where(s.subject != mother, "M") if mother else s.parent
    where = s.grandparent.where(s.grandparent.notna() & (s.grandparent != ""), side).fillna("?")
    return s.assign(where=where).groupby(["subject", "where"]).cM.sum().unstack(fill_value=0).round(1)


def references(cfg, ids):
    """Unique record references per tree person, from volume_refs.csv:
    {xref: [text, ...]} (volume and page, else source title)."""
    f = config.path(cfg, "volume_refs.csv")
    if not f.exists():
        return {}
    d = pd.read_csv(f, dtype=str).fillna("")
    d = d[d.person.isin(ids) & (d.tier != "plac-only")]
    out = {}
    for r in d.itertuples():
        if r.volume:
            t = f"{r.volume}" + (f" ({r.years})" if r.years else "") + (f" p. {r.page}" if r.page else "") \
                + (f" · {r.archive_code}" if r.archive_code else "")
        elif r.source_title:
            t = r.source_title + (f": {r.ref_text}" if r.ref_text else "")
        else:
            continue
        out.setdefault(r.person, [])
        if t not in out[r.person]:
            out[r.person].append(t)
    return out


def ancestors(cfg, tree, proband, codes):
    """Ahnentafel rows for the direct ancestors at these lineage codes."""
    by_code = {}
    for x, c in tree.ancestors(tree.id(proband)):
        by_code.setdefault(c, x)
    rows = []
    for c in sorted(set(codes), key=lambda c: (lineage.ahnentafel(c))):
        if c in by_code:
            rows.append(dict(n=lineage.ahnentafel(c), code=c, **tree.facts(by_code[c])))
    refs = references(cfg, [r["id"] for r in rows])
    for r in rows:
        r["refs"] = sorted(refs.get(r["id"], []))
    return rows


def relations(cfg, focus, totals, fseg):
    """For focus matches with a confirmed identity ([[identity]], optionally
    `down`/`line`): each tester's relationship, expected and observed cM,
    WATO-style odds of the stated relationship, path variants, and whether
    the placed segments sit on the grandparent the path predicts."""
    import gedcom_io
    import relationship_check as rc
    tree, proband = gedcom_io.load(cfg)
    twins = {x["a"]: x["b"] for x in cfg.get("mz_twins", [])}
    dist = rc.distributions(cfg)
    fkeys = {icw_io.name_key(f) for f in focus}
    out = []
    for x in cfg.get("identity", []):
        if icw_io.name_key(x["match"]) not in fkeys:
            continue
        down = int(x.get("down", 0))
        rel = tree.relation(proband, x["tree"], down, x.get("half"))
        if not rel:
            out.append(dict(ident=x, error="not related in the tree"))
            continue
        obs = {}
        if totals is not None and len(totals):
            row = totals[[icw_io.name_key(m) == icw_io.name_key(x["match"]) for m in totals.index]]
            obs = {t: float(v) for t, v in row.max().items() if pd.notna(v)}
        donors = []
        variants = {"as stated": (0, None), "one generation further down": (1, None),
                    "one generation further up": (-1, None), "half instead of full" if not rel["half"]
                    else "full instead of half": (0, "flip")}
        joint = {k: 0.0 for k in variants}
        for t, mh in _testers(cfg).items():
            r = tree.relation(mh, x["tree"], down, x.get("half"))
            e = 2 * gedcom_io.kinship(tree, mh, x["tree"], twins=twins) * rc.GENOME_CM * 0.5 ** down
            o = obs.get(t)
            if not r and not o:
                continue
            d = dict(tester=_short(cfg, t), relationship=r["name"] if r else "", expected=round(e),
                     observed=round(o) if o else None)
            if r and o:
                od = rc.odds(dist, o)
                same = (od.up_a.combine(od.up_b, min) == min(r["up_a"], r["up_b"])) & \
                       ((od.up_a - od.up_b).abs() == abs(r["up_a"] - r["up_b"])) & (od.half == r["half"])
                d["p stated"] = round(float(od[same].p.sum()), 3) if same.any() else None
                best = od[~same].iloc[0]
                d["best other"] = f"{best.rel} ({best.p:.2f})"
                d["range stated"] = od[same].range.iloc[0] if same.any() else ""
                for k, (dd, flip) in variants.items():
                    ub = r["up_b"] + dd
                    h = (not r["half"]) if flip else r["half"]
                    lk = rc.likelihood(dist, r["up_a"], ub, h, o) if ub >= 0 else None
                    joint[k] += np.log(lk) if lk else -np.inf
            donors.append(d)
        base = joint["as stated"]
        var = [dict(hypothesis=k, **{"log10 LR vs stated": round((v - base) / np.log(10), 1)
                                     if np.isfinite(v) and np.isfinite(base) else None}) for k, v in joint.items()]
        couple = rel["up_a"] and len(rel["ancestors"]) > 1
        pred = (rel["code"][:-1] if couple else rel["code"])[:2]      # the via node, to grandparent depth
        pc = _placed_cm(fseg, {icw_io.name_key(x["match"])}, cfg.get("mother")) if len(fseg) else pd.DataFrame()
        check = []
        for t, row in pc.iterrows():
            fits = lambda w: w.startswith(pred) or pred.startswith(w)     # side-only placements fit their side
            agree = sum(v for w, v in row.items() if w not in ("?", "") and fits(w))
            other = sum(v for w, v in row.items() if w not in ("?", "") and not fits(w))
            check.append(dict(tester=_short(cfg, t), predicted=pred,
                              **{"cM agree": round(agree, 1), "cM elsewhere": round(other, 1),
                                 "cM unplaced": round(float(row.get("?", 0)), 1)},
                              placed=", ".join(f"{w} {v:g}" for w, v in row.items() if v)))
        codes = [rel["code"][:k] for k in range(1, len(rel["code"]) + 1)]
        if rel["up_a"] and len(rel["ancestors"]) > 1:
            codes.append(rel["code"][:-1] + ("M" if rel["code"].endswith("F") else "F"))
        out.append(dict(ident=x, rel=rel, mrca=[tree.label(a) for a in rel["ancestors"]], donors=donors,
                        variants=var, check=check, ancestors=ancestors(cfg, tree, proband, codes)))
    return out


def indications(cfg, focus, totals, fseg, graph_rows):
    """For focus matches without a confirmed identity: odds per tester from
    the totals, where the segments were placed, the shared-match
    neighbours' placements, tree persons of the same name who could have
    tested, and research entries naming the match."""
    import relationship_check as rc
    dist = rc.distributions(cfg)
    out = dict(odds=[], placed=None, neighbours=None, candidates=[], entries=[], ancestors=[], why="")
    if totals is not None and len(totals):
        for m, row in totals.iterrows():
            for t, v in row.items():
                if pd.notna(v) and v > 0:
                    od = rc.odds(dist, float(v)).head(5)
                    out["odds"].append(dict(match=m, tester=_short(cfg, t), cM=float(v),
                                            top=", ".join(f"{r.rel} {r.p:.2f}" for r in od.itertuples())))
    fkeys = {icw_io.name_key(f) for f in focus}
    if len(fseg):
        out["placed"] = _placed_cm(fseg, fkeys, cfg.get("mother"))
    nb = [g for g in graph_rows if g.get("placement")]
    if nb:
        out["neighbours"] = pd.Series([g["placement"] for g in nb]).value_counts().to_dict()
    try:
        import gedcom_io
        tree, proband = gedcom_io.load(cfg)
    except Exception:
        return out
    for i, p in tree.people.items():
        k = icw_io.name_key(f"{p['given']} {p['surname']}")
        first = icw_io.name_key(f"{(p['given'] or '').split(' ')[0]} {p['surname']}")
        if (k in fkeys or first in fkeys) and gedcom_io.could_have_tested(p):
            r = tree.relation(proband, i)
            out["candidates"].append(dict(person=tree.label(i), relationship=r["name"] if r else "unrelated",
                                          code=r["code"] if r else ""))
    try:
        import research_log
        for f in sorted(research_log.DIR.glob("*.md")):
            text = f.read_text(encoding="utf-8").lower()
            if f.name != "INDEX.md" and any(n.lower() in text for n in focus):
                out["entries"].append(f.stem)
    except Exception:
        pass
    # ancestors on the indicated branches, to great-grandparent depth
    codes, why = [], []
    if out["placed"] is not None and len(out["placed"]):
        tot = out["placed"].sum()
        gps = [g for g, v in tot.items() if len(g) == 2 and v >= BRANCH_SHARE * tot.sum()]
        codes = [g + s for g in gps for s in ("", "F", "M")]
        why += [f"branch {g} holds {tot[g]:.0f} of the {tot.sum():.0f} placed cM (at least "
                f"{BRANCH_SHARE:.0%}): its grandparent and great-grandparents" for g in gps]
    codes += [c["code"][:k] for c in out["candidates"] for k in range(1, len(c["code"]) + 1)]
    why += [f"the path to the namesake {c['person']}" for c in out["candidates"] if c["code"]]
    out["ancestors"] = ancestors(cfg, tree, proband, codes)
    out["why"] = "; ".join(why)
    return out


def short_cols(cfg, df):
    """Tester keys as short names, in columns and index."""
    m = {k: v["short"] for k, v in testers_named(cfg).items()}
    return df.rename(columns=m, index=m)


def match_set(data, placed, top=MAX_SET):
    """The other matches on the focus matches' stretches (not those placed on
    the other parent's copy), once each, with the largest overlapping
    segment, the largest total with any tester and the focus matches they lie
    near: the `top` with the largest totals, and how many there were."""
    nb = pd.DataFrame(data["neigh"])
    if not len(nb):
        return nb, 0
    tot = placed.assign(nk=placed.match.map(icw_io.name_key)).groupby("nk").shared_cM.max()
    nb = nb[~((nb.p != "") & (nb.fp != "") & (nb.p != nb.fp))]      # the other parent's copy: no neighbour
    rows = [{"match": m, "total cM": round(float(tot.get(icw_io.name_key(m), float("nan"))), 1),
             "largest segment cM": g.cm.max(), "near": ", ".join(sorted(set(g.near)))}
            for m, g in nb.groupby("m")]
    df = pd.DataFrame(rows, columns=["match", "total cM", "largest segment cM", "near"])
    return df.sort_values("total cM", ascending=False, na_position="last").head(top), len(df)


def _md_table(rows):
    df = pd.DataFrame(rows)
    return df.to_markdown(index=False) if len(df) else "none"


def ancestors_why(rels, ind):
    """Why these ancestors are listed: the confirmed paths, or the rule that
    picked them without one (not a hypothesis)."""
    why = [f"on the confirmed path to {r['ident']['match']}" for r in rels if r.get("ancestors")]
    if ind and ind.get("why"):
        why.append("no confirmed path, so by rule: " + ind["why"])
    return "Listed because: " + "; ".join(why) + "." if why else ""


def summary_html(summary, written):
    if not summary:
        return ""
    return (f"<h2>Summary</h2><div class='notes'>{md_to_html(summary)}</div>"
            f"<p class='sub'>Summary written {written or '?'}; the sections below are regenerated "
            f"{pd.Timestamp.today().date()} and may have moved since.</p>")


def render_md(cfg, title, totals, rels, ind, mset=None, n_set=0, summary="", written=None):
    """The report as compact Markdown: what a session reads to write the summary."""
    md = [f"# {title}", "", headline(cfg), ""]
    if summary:
        md += ["## Summary", "", summary, "", f"_summary written {written or '?'}_", ""]
    md += [f"_facts generated {pd.Timestamp.today().date()}_", "",
          "## Totals per tester (cM)", "", short_cols(cfg, totals).reset_index().to_markdown(index=False) if len(totals) else "none"]
    for r in rels:
        x = r["ident"]
        md += ["", f"## Relation: {x['match']}", ""]
        if "error" in r:
            md.append(f"{x['tree']}: {r['error']}")
            continue
        down = int(x.get("down", 0))
        md += [f"- path: tree {x['tree']}" + (f" ↓{down} ({x['line']})" if down and x.get("line") else
                                               (f" ↓{down}" if down else "")),
               f"- to proband: {r['rel']['name']} via {' & '.join(r['mrca'])} (code {r['rel']['code']})",
               f"- confirmed by {x.get('by', '?')} {x.get('date', '')}" + (f"; source: {x['source']}" if x.get("source") else ""),
               "", "### Testers: expected and observed (p stated = WATO-style share of the stated relationship"
               + ("; odds for one path, expected over all" if r["rel"].get("paths", 1) > 1 else "") + ")", "",
               _md_table(r["donors"]), "", "### Path variants (sum over testers; siblings' totals are correlated, so this overstates)",
               "", _md_table(r["variants"]), "", "### Placement against the path's grandparent", "", _md_table(r["check"])]
    if ind:
        md += ["", "## Indications (no confirmed relation)", "", "### Odds per tester (top 5)", "", _md_table(ind["odds"])]
        if ind["placed"] is not None:
            md += ["", "### Where the segments were placed (cM)", "", short_cols(cfg, ind["placed"]).reset_index().to_markdown(index=False)]
        if ind["neighbours"]:
            md += ["", "Shared-match neighbours by placement: " + ", ".join(f"{k} {v}" for k, v in ind["neighbours"].items())]
        md += ["", "### Tree persons of the same name who could have tested", "", _md_table(ind["candidates"]),
               "", "Research entries naming the match: " + (", ".join(ind["entries"]) or "none")]
    if mset is not None and len(mset):
        md += ["", f"## Other matches on the same stretches (top {len(mset)} of {n_set} by total cM)", "",
               mset.to_markdown(index=False)]
    anc = [a for r in rels for a in r.get("ancestors", [])] + (ind["ancestors"] if ind else [])
    if anc:
        md += ["", "## Ancestors (Ahnentafel)", "", ancestors_why(rels, ind), ""]
        seen = set()
        for a in sorted(anc, key=lambda a: a["n"]):
            if a["n"] in seen:
                continue
            seen.add(a["n"])
            md.append(f"- **{a['n']} · {a['code']}** {a['name']}; b. {a['birth'] or '?'}; d. {a['death'] or '?'}")
            md += [f"  - {t}" for t in a["refs"]]
    return "\n".join(md) + "\n"


def render_html(cfg, rels, ind):
    """The same sections as HTML fragments: (overview, ahnentafel)."""
    h = []
    for r in rels:
        x = r["ident"]
        h.append(f"<h2>Relation: {html.escape(x['match'])}</h2>")
        if "error" in r:
            h.append(f"<p>{html.escape(x['tree'])}: {r['error']}</p>")
            continue
        down = int(x.get("down", 0))
        path = html.escape(x["tree"]) + (f" ↓{down}" if down else "") + (f" ({html.escape(x['line'])})" if x.get("line") else "")
        h.append(f"<p><b>{html.escape(r['rel']['name'])}</b> to the proband, via {html.escape(' & '.join(r['mrca']))} "
                 f"(code {r['rel']['code']}). Path: {path}. Confirmed by {html.escape(str(x.get('by', '?')))} "
                 f"{x.get('date', '')}{(' · ' + html.escape(x['source'])) if x.get('source') else ''}.</p>")
        h.append("<h3>Testers: expected and observed</h3><p class='sub'>p stated: the stated relationship's share "
                 "among all candidates, as WATO computes it (simulated distributions, equal priors)"
                 + ("; the odds are for one path, the expected cM over all of them" if r["rel"].get("paths", 1) > 1 else "") + ".</p>"
                 + table(pd.DataFrame(r["donors"])))
        h.append("<h3>Path variants</h3><p class='sub'>Summed over testers; siblings' totals are correlated, "
                 "so this overstates. Negative favours the stated path.</p>" + table(pd.DataFrame(r["variants"])))
        h.append("<h3>Placement against the path</h3>" + table(pd.DataFrame(r["check"])))
    if ind:
        h.append("<h2>Indications (no confirmed relation)</h2><h3>Odds per tester (top 5)</h3>" + table(pd.DataFrame(ind["odds"])))
        if ind["placed"] is not None:
            h.append("<h3>Where the segments were placed (cM)</h3>" + table(short_cols(cfg, ind["placed"]).reset_index()))
        if ind["neighbours"]:
            h.append("<p>Shared-match neighbours by placement: "
                     + html.escape(", ".join(f"{k} {v}" for k, v in ind["neighbours"].items())) + "</p>")
        h.append("<h3>Tree persons of the same name who could have tested</h3>" + table(pd.DataFrame(ind["candidates"])))
        h.append("<p>Research entries naming the match: " + html.escape(", ".join(ind["entries"]) or "none") + "</p>")
    anc = [a for r in rels for a in r.get("ancestors", [])] + (ind["ancestors"] if ind else [])
    rows, seen = [], set()
    for a in sorted(anc, key=lambda a: a["n"]):
        if a["n"] not in seen:
            seen.add(a["n"])
            refs = "".join(f"<li>{html.escape(t)}</li>" for t in a["refs"])
            rows.append(f"<li><b>{a['n']} · {a['code']}</b> {html.escape(a['name'])}; b. {html.escape(a['birth'] or '?')}; "
                        f"d. {html.escape(a['death'] or '?')}" + (f"<ul class='sub'>{refs}</ul>" if refs else "") + "</li>")
    ahn = (f"<h2>Ancestors (Ahnentafel)</h2><p class='sub'>{html.escape(ancestors_why(rels, ind))}</p>"
           f"<ul>{''.join(rows)}</ul>") if rows else ""
    return "".join(h), ahn


PAGE = r"""<!doctype html><html lang="sv"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>__TITLE__</title>
<style>
:root{--bg:#fbfaf7;--fg:#1d1d1b;--muted:#6b6a64;--line:#d9d6cc;--panel:#ffffff;
--FF:#2b6cb0;--FM:#2f855a;--MF:#c05621;--MM:#805ad5;--F:#7fb3d5;--M:#e0a37a;--none:#b8b5ab}
@media (prefers-color-scheme:dark){:root{--bg:#161614;--fg:#ecebe6;--muted:#a3a198;--line:#3a3934;--panel:#1f1f1c;
--FF:#63a4e8;--FM:#5fbf8a;--MF:#ef8a4f;--MM:#a98af0;--F:#8fc0e0;--M:#e8b48c;--none:#5b5a54}}
body{margin:0;background:var(--bg);color:var(--fg);font:14px/1.45 system-ui,-apple-system,Segoe UI,sans-serif}
main{max-width:1180px;margin:0 auto;padding:20px 16px 60px}
h1{font-size:22px;margin:0 0 4px}h2{font-size:17px;margin:28px 0 8px}h3,h4{font-size:15px;margin:18px 0 6px}
.sub{color:var(--muted)}table{border-collapse:collapse;margin:6px 0;font-size:13px}
th,td{border-bottom:1px solid var(--line);padding:3px 8px;text-align:left;vertical-align:top}th{color:var(--muted);font-weight:600}
.legend span{display:inline-flex;align-items:center;margin-right:14px;font-size:12px;color:var(--muted)}
.legend i{display:inline-block;width:14px;height:10px;margin-right:5px;border-radius:2px}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(270px,1fr));gap:10px}
.chr{background:var(--panel);border:1px solid var(--line);border-radius:6px;padding:6px 8px;cursor:zoom-in}
.chr.focus{border-color:var(--fg)}.chr h5{margin:0 0 4px;font-size:12px;color:var(--muted);font-weight:600}
#big{background:var(--panel);border:1px solid var(--line);border-radius:6px;padding:10px;margin:8px 0;display:none}
#tip{position:fixed;pointer-events:none;background:var(--panel);border:1px solid var(--line);border-radius:5px;
padding:6px 8px;font-size:12px;box-shadow:0 2px 8px rgba(0,0,0,.15);display:none;max-width:340px;z-index:9}
label{font-size:13px;color:var(--muted);margin-right:14px}svg text{fill:var(--muted);font-size:10px}
.notes{background:var(--panel);border:1px solid var(--line);border-radius:6px;padding:4px 16px}
code{font-size:12px}
</style></head><body><main>
<h1>__TITLE__</h1><p>__HEAD__</p><div class="sub">__SUB__</div>
__SUMMARY__
<h2>Totals per tester (cM)</h2>__TOTALS__
__LINKS__
<h2>Chromosome browser</h2>
<div class="legend" id="legend"></div>
<div><label><input type="checkbox" id="showN" checked> other matches on the same stretch</label>
<label><input type="checkbox" id="onlyFocus" checked> only chromosomes with a focus segment</label></div>
<div id="big"></div><div class="grid" id="grid"></div>
__MSET__
<details><summary><h2 style="display:inline">Focus segments and neighbours, per tester</h2></summary>__SEGTABLE__</details>
<h2>Shared matches (merged AutoCluster runs)</h2>__GRAPH__
<h2>Research notes</h2><div class="notes">__NOTES__</div>
__AHNENTAFEL__
</main><div id="tip"></div>
<script>
const D=__DATA__;
const css=k=>getComputedStyle(document.documentElement).getPropertyValue('--'+(k||'none')).trim()||'#999';
const GP=["FF","FM","MF","MM"];
const leg=document.getElementById('legend');
for(const g of GP){const n=D.grandparents[g]||g;leg.innerHTML+=`<span><i style="background:${css(g)}"></i>${g} ${n}</span>`}
leg.innerHTML+=`<span><i style="border:2px solid var(--fg);background:transparent"></i>focus match</span><span><i style="border:2px dashed var(--fg);background:transparent"></i>side unknown (both readings)</span>`;
const tip=document.getElementById('tip');
function showTip(ev,h){tip.innerHTML=h;tip.style.display='block';tip.style.left=Math.min(ev.clientX+12,innerWidth-350)+'px';tip.style.top=(ev.clientY+12)+'px'}
function hideTip(){tip.style.display='none'}
const focusChroms=new Set(D.focus.map(f=>f.c));
function draw(c,W,big){
  const len=D.chroms[+c-1],X=v=>40+(W-50)*v/len,laneH=big?16:9,gap=big?6:3,rowH=2*laneH+gap+ (big?28:14);
  const showN=document.getElementById('showN').checked;
  const H=D.testers.length*rowH+(big?24:6);
  let s=`<svg width="${W}" height="${H}" viewBox="0 0 ${W} ${H}" role="img">`;
  D.testers.forEach((t,i)=>{
    const y0=i*rowH+4;
    s+=`<text x="0" y="${y0+laneH}">${D.names[t]||t}</text>`;
    ["F","M"].forEach((p,k)=>{const y=y0+k*(laneH+1);
      s+=`<rect x="40" y="${y}" width="${W-50}" height="${laneH}" fill="var(--line)" opacity=".35"/>`;
      for(const b of D.paint.filter(b=>b.t===t&&b.c===c&&b.p===p))
        s+=`<rect x="${X(b.s)}" y="${y}" width="${Math.max(1,X(b.e)-X(b.s))}" height="${laneH}" fill="${css(b.g)}" opacity=".28"/>`;
    });
    if(showN) for(const n of D.neigh.filter(n=>n.t===t&&n.c===c)){
      const y=y0+2*laneH+3+((n.s/1e3|0)%3)*(big?6:3);
      s+=`<rect x="${X(n.s)}" y="${y}" width="${Math.max(1,X(n.e)-X(n.s))}" height="${big?5:2.5}" fill="${css(n.g||'none')}" data-tip="${encodeURIComponent(`<b>${n.m}</b><br>${n.cm} cM · ${(n.s/1e6).toFixed(1)}–${(n.e/1e6).toFixed(1)} Mb<br>placed ${n.g||'–'} (${n.p||'side unknown'}) · ${n.src}<br>near ${n.near}`)}"/>`;
    }
    for(const f of D.focus.filter(f=>f.t===t&&f.c===c)){
      const lanes=f.p? [f.p] : ["F","M"];
      for(const p of lanes){const k=p==="F"?0:1,y=y0+k*(laneH+1),g=f.p?f.g:(p==="F"?f.ip:f.im);
        s+=`<rect x="${X(f.s)}" y="${y-1}" width="${Math.max(2,X(f.e)-X(f.s))}" height="${laneH+2}" fill="${css(g||'none')}" fill-opacity=".9" stroke="var(--fg)" stroke-width="${big?2:1.4}" ${f.p?'':'stroke-dasharray="3 2"'} data-tip="${encodeURIComponent(`<b>${f.m}</b> · ${D.names[t]}<br>chr ${c}: ${(f.s/1e6).toFixed(2)}–${(f.e/1e6).toFixed(2)} Mb · ${f.cm} cM · ${f.src}<br>${f.p?`parent ${f.p} → ${f.g||'?'}`:`side unknown: if paternal ${f.ip||'?'}, if maternal ${f.im||'?'}`}<br><span style="color:var(--muted)">${f.why}</span>`)}"/>`;
        if(big) s+=`<text x="${X(f.s)}" y="${y-3}">${f.m.split(' ')[0]} ${f.cm}</text>`;
      }
    }
  });
  if(big){for(let mb=0;mb<=len/1e6;mb+=20){s+=`<text x="${X(mb*1e6)}" y="${H-6}">${mb}</text>`}}
  return s+"</svg>";
}
function render(){
  const grid=document.getElementById('grid'),only=document.getElementById('onlyFocus').checked;grid.innerHTML='';
  for(let c=1;c<=22;c++){const cs=String(c);if(only&&!focusChroms.has(cs))continue;
    const d=document.createElement('div');d.className='chr'+(focusChroms.has(cs)?' focus':'');
    d.innerHTML=`<h5>chr ${c}</h5>`+draw(cs,250,false);d.onclick=()=>{const b=document.getElementById('big');
      b.style.display='block';b.innerHTML=`<h5>chr ${c} (click to close)</h5>`+draw(cs,Math.min(1140,innerWidth-40),true);b.onclick=()=>b.style.display='none';b.scrollIntoView({behavior:'smooth'})};
    grid.appendChild(d)}
}
document.addEventListener('mousemove',e=>{const t=e.target.closest&&e.target.closest('[data-tip]');t?showTip(e,decodeURIComponent(t.dataset.tip)):hideTip()});
document.getElementById('showN').onchange=render;document.getElementById('onlyFocus').onchange=render;render();
</script></body></html>"""


def table(df):
    return df.to_html(index=False, border=0, na_rep="", escape=True) if len(df) else "<p class='sub'>none</p>"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--entry")
    ap.add_argument("--focus", action="append", default=[])
    ap.add_argument("--title")
    ap.add_argument("--out")
    ap.add_argument("--like", help="focus on every match whose name matches this regex, as a group "
                    "(e.g. '\\bExample\\b'; case-insensitive)")
    ap.add_argument("--md", action="store_true", help="also write the facts as compact Markdown")
    ap.add_argument("--report", metavar="NAME", help="a report kept in data/notes/reports/NAME.md: its "
                    "header says what to focus on, its text is the summary; created from --focus/--like "
                    "if missing")
    ap.add_argument("--all-reports", action="store_true", help="regenerate every kept report")
    a = ap.parse_args()
    cfg = config.load()
    if a.all_reports:
        for p in sorted(reports_dir(cfg).glob("*.md")):
            run(cfg, argparse.Namespace(**{**vars(a), "report": p.stem}))
    else:
        run(cfg, a)


def reports_dir(cfg):
    return cfg["data_dir"].layer("notes") / "reports"


def kept_report(cfg, a):
    """The kept report NAME: (header, summary), created from the command line
    if missing. The header holds what the report is about (focus, like,
    title); the text below it is the summary for an outside reader, written
    once by hand or by a session, and kept across regenerations."""
    import tomllib
    p = reports_dir(cfg) / f"{a.report}.md"
    if not p.exists():
        if not (a.focus or a.like):
            raise SystemExit(f"{p} not found: give --focus or --like to create it")
        p.parent.mkdir(parents=True, exist_ok=True)
        head = [f"title = {json.dumps(a.title or a.report, ensure_ascii=False)}", f"focus = {json.dumps(a.focus, ensure_ascii=False)}"]
        if a.like:
            head.append(f"like = {json.dumps(a.like, ensure_ascii=False)}")
        head.append("# written = YYYY-MM-DD   # the date of the summary below the header, for the reader")
        p.write_text("+++\n" + "\n".join(head) + "\n+++\n\n", encoding="utf-8")
        print(f"created {p}: write the summary there")
    _, head, body = p.read_text(encoding="utf-8").split("+++", 2)
    return tomllib.loads(head), body.strip()


def run(cfg, a):
    D = cfg["data_dir"]
    body, meta = "", {}
    summary, written = "", None
    if a.report:
        note, summary = kept_report(cfg, a)
        a.focus = a.focus or note.get("focus", [])
        a.like = a.like or note.get("like")
        a.title = a.title or note.get("title")
        a.md = True
        written = note.get("written")
        if not a.out:
            a.out = str(D / "output" / f"report_{a.report}.html")
    if a.entry:
        import research_log
        meta, body = read_entry(research_log.DIR / f"{a.entry}.md")
    focus = a.focus or [p for p in meta.get("people", [])]
    if a.like:
        names = set(outputs.read(D, "placed_segments.csv", usecols=["match"]).match.dropna())
        focus += sorted(n for n in names if re.search(a.like, n, re.I) and n not in focus)
    title = a.title or meta.get("title") or (f"Matches like {a.like.replace(chr(92) + 'b', '')}" if a.like and not a.focus else ", ".join(focus))
    data, totals, graph, links, fseg = build(cfg, focus, title, body)
    rels, ind = [], None
    try:
        rels = relations(cfg, focus, totals, fseg)
        known = {icw_io.name_key(r["ident"]["match"]) for r in rels}
        rest = [f for f in focus if icw_io.name_key(f) not in known]
        if rest:     # focus matches without a confirmed identity
            keep = [m for m in totals.index if icw_io.name_key(m) not in known] if len(totals) else []
            gr = graph[[icw_io.name_key(str(f)) not in known for f in graph.focus]] if len(graph) and "focus" in graph else graph
            ind = indications(cfg, rest, totals.loc[keep] if len(totals) else totals, fseg, gr.to_dict("records"))
    except (KeyError, FileNotFoundError) as ex:     # no tree: the report works without
        print(f"no relation section ({ex})")
    rel_html, ahn_html = render_html(cfg, rels, ind)
    placed = outputs.read(D, "placed_matches.csv", usecols=["match", "shared_cM"])
    mset, n_set = match_set(data, placed)
    keep = set(mset.match) if len(mset) else set()
    data["neigh"] = [n for n in data["neigh"] if n["m"] in keep]     # the browser and the table follow the set
    found = sorted({f["m"] for f in data["focus"]})
    sub = (f"Focus: {', '.join(found) or '(no segments found)'} · generated from placed_segments.csv, the phased "
           f"painting and the AutoCluster runs · {pd.Timestamp.today().date()}")
    seg = pd.DataFrame(data["focus"] + [dict(n, near=n["near"]) for n in data["neigh"]])
    if len(seg):
        seg = seg.assign(Mb=lambda d: (d.s / 1e6).round(1).astype(str) + "–" + (d.e / 1e6).round(1).astype(str))
        seg["t"] = seg.t.map(lambda t: _short(cfg, t))
        seg = seg.rename(columns=dict(t="tester", m="match", c="chr", cm="cM", p="parent", g="grandparent",
                                      ip="if paternal", im="if maternal", src="platform"))
        cols = [c for c in ["tester", "match", "chr", "Mb", "cM", "parent", "grandparent", "if paternal",
                            "if maternal", "platform", "near"] if c in seg]
        seg = seg[cols].sort_values(["chr", "Mb"], key=lambda s: s.map(lambda v: (len(str(v)), str(v))))
    links_html = ""
    if links:
        links_html = "<h2>Linked tree persons</h2><ul>" + "".join(
            f"<li>{html.escape(x['match'])} = {html.escape(x['tree'])} (confirmed by {html.escape(str(x.get('by','')))}, {x.get('date','')})</li>"
            for x in links) + "</ul>"
    page = (PAGE.replace("__TITLE__", html.escape(title)).replace("__SUB__", html.escape(sub))
            .replace("__HEAD__", html.escape(headline(cfg)))
            .replace("__SUMMARY__", summary_html(summary, written))
            .replace("__MSET__", f"<h2>Other matches on the same stretches (top {len(mset)} of {n_set} by total cM)</h2>"
                     "<p class='sub'>Each once, whichever tester shares it: a set to compare with the focus "
                     "matches' own lists.</p>" + table(mset))
            .replace("__TOTALS__", table(short_cols(cfg, totals).reset_index()))
            .replace("__LINKS__", links_html + rel_html).replace("__AHNENTAFEL__", ahn_html).replace("__SEGTABLE__", table(seg))
            .replace("__GRAPH__", table(graph.sort_values("support", ascending=False) if len(graph) and "support" in graph and graph.support.astype(str).str.len().gt(0).all() else graph))
            .replace("__NOTES__", md_to_html(body) if body else "<p class='sub'>no entry given</p>")
            .replace("__DATA__", json.dumps(data, ensure_ascii=False)))
    out = Path(a.out) if a.out else D / f"report_{re.sub(r'\W+', '_', title.lower())[:40]}.html"
    out.write_text(page, encoding="utf-8")
    if a.md:
        out.with_suffix(".md").write_text(render_md(cfg, title, totals, rels, ind, mset, n_set, summary, written), encoding="utf-8")
        print(f"-> {out.with_suffix('.md')}")
    print(f"{len(data['focus'])} focus segments, {len(data['neigh'])} neighbours -> {out}")


if __name__ == "__main__":
    main()
