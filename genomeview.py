"""
The genome page, donor focus (docs/lenses.md): one donor's matches on
every platform, and their segments on the donor's two copies of each
chromosome, painted with the copy model's blocks where the model applies.

    python3 genomeview.py       # writes data/output/genome.html (private: names)

From the top: the match list, each match with the tree's link to them
(a hand link, or a join by name that is a candidate only), where
placement put them, where the copy model's painting puts them (flagged
where the tree's path disagrees), and the model's verdicts on their
segments; a match may come from a match list, from segments, or both,
and a card under the list shows its match-list entry (kits.ENTRY: contact,
their tree, surnames) for each selected match. A segment carries the
painting's reading under it (both
readings where its side is unknown) and any assertions on it; the segment
list is the one table for both.
Filters sit in the column heads, as in a spreadsheet: words to find
(-word excludes), a range, values to tick. The chromosomes draw the
segments of the matches the list shows (or of the selected ones) under
the copy they come through, and the segment list lists the same; its
filters narrow the drawing too. Last, the painting's key: per code its
share of its copy against the expected, how much is sure, and the
verdicts under it. Column heads explain themselves on hover.

Blocks are painted for the proband and full siblings only (the codes run
from the proband); other donors get their matches and segments on bare
copies, with the reason.

Link scheme (after #): d=<donor>&c=<code>&l=<2|3>&m=<siblings|single>
&s=<selected matches>&f=<filters>&o=<sorts> (f and o JSON, per table).
A donor or a code adds a history step; the rest replace it.

Sketch: reads placed_matches.csv and placed_segments.csv (the list),
the match lists in family.toml (kits.match_entries),
copy_model_blocks.csv and copy_model_verdicts.csv (the painting),
copy_model_placed_segments.csv and copy_model_placed_matches.csv (its
reading of the segments), the
store (ancestors, hand links of matches) and the GEDCOM (name joins,
gedcom_io.matches_in_tree). Positions in cM from the genetic map
([genetic_map], else flat 1 cM/Mb), as the copy model places its blocks;
a verdict is tied to the segment of its match that holds its start.
"""
import re
import sys

import pandas as pd

import lineage

SURE = 0.9


def parents(db):
    """person -> (father, mother) from the store (the first family a child is in)."""
    par = {}
    fams = {fid: (h, w) for fid, h, w in db.execute("select id, husb, wife from family")}
    for fid, child in db.execute("select family, child from child order by rowid"):
        par.setdefault(child, fams.get(fid, (None, None)))
    return par


def fit(par, root, donors):
    """donor -> why the page leaves them out, or None: the codes run from
    the proband, so only the proband and full siblings (both parents
    recorded and shared) can be painted. donors: donor -> store id."""
    import familyview
    codes = familyview.lineage_codes(par, root, 12)
    mine = par.get(root, (None, None))
    out = {}
    for d, pid in donors.items():
        theirs = par.get(pid, (None, None))
        if not pid:
            out[d] = "not placed in the tree (no mh for them in family.toml)"
        elif pid == root or (all(mine) and theirs == mine):
            out[d] = None
        elif any(a and a == b for a, b in zip(theirs, mine)):
            out[d] = "a half-sibling: only the copy from the shared parent runs through the proband's codes"
        elif codes.get(pid):
            out[d] = f"the proband's {codes[pid][0]}: their own codes do not run from the proband"
        else:
            out[d] = "neither the proband nor a full sibling"
    return out


def ancestors(db, root, depth=3):
    """code -> [store id, name, birth, death] for root's ancestors to depth
    (pedigree collapse: one person under several codes)."""
    import familyview
    import tree_store
    from intervals import years
    codes = familyview.lineage_codes(parents(db), root, depth)
    life = {}
    for pid, tag, date in db.execute("select owner, tag, date from event where tag in ('BIRT','DEAT')"):
        life.setdefault(pid, {})[tag] = years(date)[0]
    out = {}
    for pid, g, s in db.execute("select id, given, surname from person"):
        for c in codes.get(pid, []):
            if c and c not in out:
                lf = life.get(pid, {})
                out[c] = [pid, " ".join(tree_store.name_parts(g, s)).replace("*", "").strip(), lf.get("BIRT"), lf.get("DEAT")]
    return out


def _claim(cid):
    """(source, match, start bp) from a claim id source:match:subject:chrom:start:code
    (a match name may hold colons)."""
    p = str(cid).split(":")
    try:
        return p[0], ":".join(p[1:-4]), int(float(p[-2]))
    except (ValueError, IndexError):
        return p[0], "", None


def collect(blocks, verdicts, anc, names=None, matches=None, left=()):
    """The lens's data from the copy model's tables (DataFrames; verdicts may
    be None), the ancestors (ancestors()), the donors' display names and
    match key -> match name (keys in claim ids are vendor ids); left: (name,
    reason) for subjects with blocks the page does not paint (fit())."""
    lengths = blocks.groupby(blocks.chrom.astype(str)).end_cm.max().round(1).to_dict()
    mb = (blocks.groupby(blocks.chrom.astype(str)).end.max() / 1e6).round(0).to_dict()
    B = {}
    for (subj, model, level), g in blocks.groupby(["subject", "model", "level"]):
        B.setdefault(subj, {}).setdefault(model, {})[str(level)] = [
            [str(r.chrom), r.side, round(r.start_cm, 1), round(r.end_cm, 1), int(r.start), int(r.end),
             r.lineage, round(float(r.posterior), 3)] for r in g.itertuples()]
    V = []
    for r in (verdicts.itertuples() if verdicts is not None else ()):
        src, match, bp = _claim(r.claim_id)
        if bp is None:
            continue
        V.append([r.subject, r.model, getattr(r, "source_kind", None) or src, (matches or {}).get(match, match), str(r.chrom), bp, r.code, float(r.support),
                  r.verdict, None if r.cM != r.cM else round(float(r.cM), 1), match])
    codes = {c for c in blocks.lineage.unique()} | {c[:k] for c in anc for k in range(1, len(c) + 1)}
    col = {c: [lineage.color(c), lineage.color(c, dark=True)] for c in sorted(codes)}
    return dict(left=[list(x) for x in left], mb=mb, blocks=B, names={d: (names or {}).get(d, d) for d in B}, verdicts=V, lengths=lengths, anc=anc, col=col, sure=SURE)


def _s(x):
    return x if isinstance(x, str) else ""


def _f(x, nd=1):
    try:
        x = float(x)
    except (TypeError, ValueError):
        return None
    return None if x != x else round(x, nd)


def tree_links(cfg, tree, proband, keys, db=None):
    """(platform, match_key) -> (kind, [tree ids]): "confirmed" for a hand
    link ([[identity]] in assertions.toml, or tree_store.py link-match in
    the store db), else "name" for a join by full name (a candidate, not an
    identity; several ids when the name is ambiguous). keys: DataFrame
    with platform, match_key, match."""
    import gedcom_io
    ids = gedcom_io.load_identities(cfg)
    if db is not None:
        for name, person in db.execute("select name, person from dna_match where person is not null and person != ''"):
            ids.setdefault(gedcom_io._norm(name), person)
    ids = {k: v for k, v in ids.items() if _in_tree(tree, v)}
    hits = gedcom_io.matches_in_tree(tree, proband, keys.assign(subject=""), ids)
    out = {}
    for (p, k), h in (hits.groupby(["platform", "match_key"]) if len(hits) else ()):
        out[(p, k)] = ("confirmed" if gedcom_io._norm(h.match.iloc[0]) in ids else "name",
                       list(dict.fromkeys(h.pid)))
    return out


def _in_tree(tree, ref):
    try:
        tree.id(ref)
        return True
    except KeyError:
        print(f"hand link to {ref}: not in the tree")
        return False


def tree_person(tree, i):
    """[ref for the family page, name, birth, death] of a tree person."""
    p = tree.people[i]
    b, d = ((p[e] or {}).get("year") for e in ("birth", "death"))
    return [next((f for f in p["facts"] if f.startswith("MH:")), i), f"{p['given']} {p['surname']}".strip(), b, d]


def relater(tree, donors):
    """relate(donor, tree id) -> (relationship from the donor, path code
    to the shared ancestors: where a couple's two lines part).
    donors: donor -> tree ref (mh)."""
    at = {}
    for d, ref in donors.items():
        try:
            at[d] = tree.id(ref)
        except (KeyError, TypeError):
            pass
    memo = {}

    def relate(d, i):
        if d not in at:
            return "", ""
        if (d, i) not in memo:
            r = tree.relation(at[d], i)
            codes = [c for _, c, _ in tree.relationship(at[d], i)]
            memo[(d, i)] = (r["name"] if r else "not related in the tree",
                            lineage.common_prefix(codes) if codes else "")
        return memo[(d, i)]
    return relate


def _base(platform):
    """A selection export's platform without its selection mark:
    "MyHeritage (selection 2026-11-09) jenny" -> "MyHeritage jenny"."""
    return re.sub(r" \(selection[^)]*\)", "", str(platform))


def _fold_selections(segs, placed=None):
    """Drop a selection export's rows where the full export of the same
    platform has the match for that donor (by name: selections key matches
    by name, full exports by the vendor's id): the same match again."""
    import identity
    rows = [x for x in (segs, placed) if x is not None]
    full = {(d, str(p), identity.name_key(m)) for x in rows
            for d, p, m in zip(x.subject, x.platform, x.match) if "(selection" not in str(p)}

    def keep(x):
        return x[pd.Series([not ("(selection" in str(p) and (d, _base(p), identity.name_key(m)) in full)
                            for d, p, m in zip(x.subject, x.platform, x.match)], index=x.index, dtype=bool)]
    return tuple(keep(x) if x is not None else None for x in (segs, placed))


def match_list(segs, placed=None, gm=None, links=None, relate=None, people=None, cm_segs=None, cm_matches=None, entries=None):
    """The match list and the segments behind it, per donor (subject), from
    placed_segments.csv and placed_matches.csv (DataFrames; placed may be
    None). Returns P platforms; M per match [platform, key, name, surnames,
    link (kind, tree ids) or None]; S donor -> rows [match, shared cM,
    longest cM, segments, placement, agreement, bucket, range, vendor's
    tree link, other donors, relationship, path, painting's placement,
    its agreement]; G donor -> segments [match, chrom, start cM, end cM,
    start Mb, end Mb, cM, parent, grandparent, reason, painting's
    grandparent, its probability, if paternal, if maternal]; R the reasons; tp tree id -> tree_person; ends
    chrom -> [cM, Mb] reached. links: (platform, key) -> (kind, [tree ids]);
    relate(donor, tree id) -> (relationship, path); people: tree id ->
    tree_person; cm_segs, cm_matches: copy_model_placed_segments.csv and
    copy_model_placed_matches.csv (the copy model's reading of the same
    segments: the grandparent its painting has under each, both readings
    where the side is unknown, summed per match); entries: match-list
    entries (kits.match_entries), each S row ending in its entry (the
    fields it has) or None. A match may have an entry, segments, or both."""
    import intervals as iv
    gm = gm or iv.GeneticMap.flat()
    links, people = links or {}, people or {}
    cols = ["subject", "platform", "match_key", "match"]
    segs, placed = _fold_selections(segs, placed)
    if entries is None:
        entries = pd.DataFrame(columns=cols)
    seen = pd.concat([segs[cols]] + ([placed[cols]] if placed is not None else []) + [entries[cols]])
    seen = seen.dropna(subset=["subject", "match_key"]).astype(str).drop_duplicates(["subject", "platform", "match_key"])
    P = sorted(seen.platform.unique())
    surn, pl = {}, {}
    for r in (placed.to_dict("records") if placed is not None else ()):
        pl.setdefault((str(r["subject"]), str(r["platform"]), str(r["match_key"])), r)
        if _s(r.get("Ancestral Surnames")):
            surn.setdefault((str(r["platform"]), str(r["match_key"])), r["Ancestral Surnames"])
    ent = {}
    for r in entries.to_dict("records"):
        d = {k: _jsonable(v) for k, v in r.items() if k not in cols and _jsonable(v) is not None}
        if d.get("ancestral_surnames"):            # kept once per match (M), not per donor
            surn.setdefault((str(r["platform"]), str(r["match_key"])), d.pop("ancestral_surnames"))
        d.pop("ancestral_surnames", None)
        for u in ("manager_contact_url", "tree_contact_url"):    # the same link again says nothing new
            if d.get(u) in (d.get("contact_url"), d.get("manager_contact_url") if u != "manager_contact_url" else None):
                d.pop(u, None)
        ent[(str(r["subject"]), str(r["platform"]), str(r["match_key"]))] = d
    idx, M, tp = {}, [], {}
    for p, k, name in seen.drop_duplicates(["platform", "match_key"])[["platform", "match_key", "match"]].itertuples(index=False):
        idx[(p, k)] = len(M)
        lk = links.get((p, k))
        for i in (lk[1] if lk else ()):
            tp[i] = people.get(i, [i, i, None, None])
        M.append([P.index(p), k, _s(name) or k, surn.get((p, k), ""), [lk[0], list(lk[1])] if lk else None])
    who = seen.groupby(["platform", "match_key"]).subject.agg(lambda s: sorted(set(s))).to_dict()
    sk = segs.assign(subject=segs.subject.astype(str), platform=segs.platform.astype(str), match_key=segs.match_key.astype(str))
    n = sk.groupby(["subject", "platform", "match_key"]).size().to_dict()
    auto = sk[sk.chrom.astype(str) != "X"].groupby(["subject", "platform", "match_key"]).cM.agg(["sum", "max"])
    auto = {k: (round(a, 1), round(b, 1)) for k, a, b in zip(auto.index, auto["sum"], auto["max"])}
    cmm = {} if cm_matches is None else {
        (str(d), str(p), str(k)): (_s(c), _f(a, 2)) for d, p, k, c, a in
        cm_matches[["subject", "platform", "match_key", "placement", "agreement"]].itertuples(index=False)}
    cms = {} if cm_segs is None else {
        (str(d), str(p), str(k), str(c), int(a), int(b)): [_s(g), _f(q, 2), _s(f), _s(m)] for d, p, k, c, a, b, g, q, f, m in
        cm_segs[["subject", "platform", "match_key", "chrom", "start", "end", "cm_grandparent", "cm_p",
                 "cm_if_paternal", "cm_if_maternal"]].itertuples(index=False)}
    S = {}
    for d, p, k, _ in seen.itertuples(index=False):
        r, a, lk, e = pl.get((d, p, k), {}), auto.get((d, p, k), (None, None)), links.get((p, k)), ent.get((d, p, k))
        r = {**r, **{c: e[f] for c, f in (("shared_cM", "shared_cM"), ("longest_cM", "longest_cM"),
                                          ("Matching Bucket", "bucket"), ("Relationship Range", "relationship_range"),
                                          ("Linked Relationship", "linked_relationship")) if e and f in e}}
        shared, longest = _f(r.get("shared_cM")), _f(r.get("longest_cM"))
        rel, path = relate(d, lk[1][0]) if lk and relate and len(lk[1]) == 1 else ("", "")
        S.setdefault(d, []).append([idx[(p, k)], shared if shared is not None else a[0],
                                    longest if longest is not None else a[1], n.get((d, p, k), 0),
                                    _s(r.get("placement")), _f(r.get("agreement"), 2), _s(r.get("Matching Bucket")),
                                    _s(r.get("Relationship Range")), _s(r.get("Linked Relationship")),
                                    [x for x in who[(p, k)] if x != d], rel, path, *cmm.get((d, p, k), ("", None)), e])
    R, ri, G, ends = [""], {"": 0}, {}, {}
    for chrom, g in sk.groupby(sk.chrom.astype(str)):
        try:
            a, b = gm.cm(chrom, g.start.values), gm.cm(chrom, g.end.values)
        except KeyError:                                   # no map for it (X): flat
            a, b = g.start.values / 1e6, g.end.values / 1e6
        ends[chrom] = [round(float(b.max()), 1), round(float(g.end.max()) / 1e6)]
        for r, x, y in zip(g.itertuples(index=False), a, b):
            why = _s(r.parent_reason)
            if why not in ri:
                ri[why] = len(R)
                R.append(why)
            G.setdefault(r.subject, []).append([idx[(r.platform, r.match_key)], chrom, round(float(x), 2), round(float(y), 2),
                                                round(r.start / 1e6, 2), round(r.end / 1e6, 2), round(float(r.cM), 1),
                                                _s(r.parent), _s(r.grandparent), ri[why],
                                                *cms.get((r.subject, r.platform, r.match_key, chrom, int(r.start), int(r.end)), ["", None, "", ""])])
    return dict(P=P, M=M, S=S, G=G, R=R, tp=tp, ends=ends)


def _jsonable(v):
    """A match-list value for the page: dates as days, floats rounded, None
    for missing."""
    if v is None or (isinstance(v, float) and v != v) or v is pd.NaT:
        return None
    if isinstance(v, pd.Timestamp):
        return v.strftime("%Y-%m-%d")
    if hasattr(v, "item"):                     # numpy scalars
        v = v.item()
    if isinstance(v, float):
        return round(v, 2)
    return v


def write(path, data):
    import geoview
    path.write_text(geoview.embed(HTML.replace("__NAV__", geoview.nav("genome.html")), data), encoding="utf-8")


HTML = r"""<!doctype html>
<html lang="sv"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Genome</title>
<style>
:root{--bg:#fbfaf7;--fg:#1d1c1a;--mut:#6b6760;--line:#e2ded6;--card:#fff;--sel:#fff1bf;--acc:#2f6db5;--bad:#c0392b}
@media (prefers-color-scheme:dark){:root{--bg:#171614;--fg:#ece9e2;--mut:#9b968c;--line:#34312c;--card:#201f1c;--sel:#4a4220;--acc:#6ea4e6;--bad:#e8705f}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:13px/1.4 system-ui,-apple-system,sans-serif}
header{display:flex;gap:10px;align-items:center;padding:8px 12px;border-bottom:1px solid var(--line);flex-wrap:wrap}
h1{font-size:16px;margin:0 8px 0 0}h2{font-size:13px;margin:0 0 6px;color:var(--mut);font-weight:600}
.seg{display:inline-flex;border:1px solid var(--line);border-radius:6px;overflow:hidden;vertical-align:middle}.seg:empty{display:none}
.seg button{font:inherit;font-weight:400;color:var(--fg);background:var(--card);border:0;border-left:1px solid var(--line);padding:3px 9px;cursor:pointer}
.seg button:first-child{border-left:0}.seg button.on{background:var(--sel);font-weight:600}.seg button:disabled{color:var(--mut);cursor:not-allowed;opacity:.5;text-decoration:line-through}
main{padding:12px 16px;display:grid;gap:16px;max-width:1400px}main>section+section{border-top:1px solid var(--line);padding-top:12px}main>section{min-width:0}
table{border-collapse:collapse}td,th{padding:2px 12px 2px 0;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}
th{color:var(--mut);font-weight:600;font-size:12px}[title].help{cursor:help;text-decoration:underline dotted;text-underline-offset:3px}
.n{text-align:right;font-variant-numeric:tabular-nums}
.chip{display:inline-block;width:12px;height:12px;border-radius:2px;vertical-align:-2px;margin-right:6px}
.code{font-family:ui-monospace,monospace;font-size:11px}.meta{color:var(--mut);font-size:11px;font-weight:400}
a{color:var(--acc);cursor:pointer}.bad{color:var(--bad)}tr.on td{background:var(--sel)}
#focus{display:flex;gap:4px;align-items:center}#focus a{cursor:pointer;margin-left:6px}
/* the counts: a bar for the share of the copy, a tick where the expected share falls */
.share{position:relative;width:120px;height:10px;background:var(--line);border-radius:2px}.share i{position:absolute;top:0;bottom:0;left:0;border-radius:2px}
.share b{position:absolute;top:-2px;bottom:-2px;width:2px;background:var(--fg)}
/* tables with filters in the column heads */
.tw{overflow-x:auto;max-height:70vh;overflow-y:auto;border-bottom:1px solid var(--line)}
table.ft td{white-space:nowrap}table.ft th{position:sticky;top:0;background:var(--bg);white-space:nowrap;z-index:1}
.st{cursor:pointer}th.fon .st{color:var(--acc)}
.fb{font:inherit;border:0;background:none;color:var(--mut);cursor:pointer;padding:0 0 0 3px;font-size:11px}.fb.on{color:var(--acc);font-weight:700}
.bar{display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin:0 0 6px}
.fchip{border:1px solid var(--acc);border-radius:10px;padding:0 8px;font-size:12px}.fchip a{text-decoration:none;margin-left:4px}
.tog{font:inherit;font-size:12px;border:1px solid var(--line);background:var(--card);color:var(--fg);border-radius:10px;padding:0 9px;cursor:pointer}.tog.on{background:var(--sel);border-color:var(--acc)}
tr[data-m]{cursor:pointer}tr[data-m]:hover td{background:var(--line)}tr.lk td:first-child{box-shadow:inset 3px 0 var(--acc);padding-left:6px}
.trunc{display:inline-block;max-width:220px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;vertical-align:bottom}
.k{display:inline-block;width:8px;height:8px;border-radius:50%;border:1.5px solid var(--acc);margin-right:5px;vertical-align:0}.k.confirmed{background:var(--acc)}.k.vendor{border-style:dotted;border-color:var(--mut)}
#pop{position:fixed;display:none;z-index:4;background:var(--card);border:1px solid var(--line);border-radius:6px;padding:8px;width:300px;box-shadow:0 2px 10px #0003}
#pop .pr{display:flex;justify-content:space-between;align-items:center;gap:6px;margin-bottom:6px}#pop input[type=search],#pop input[type=number]{font:inherit;width:100%;padding:2px 4px}
#pop button{font:inherit;font-size:12px;cursor:pointer}.opts{max-height:240px;overflow:auto;border:1px solid var(--line);padding:2px 4px;margin-bottom:6px}
.opts label{display:block;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
/* chromosomes: a row each, the paternal copy and its segments above the maternal and its, then segments with no side;
   width by cM */
.cr{display:grid;grid-template-columns:28px 1fr;align-items:center;gap:6px;margin-bottom:6px}.cr>span{color:var(--mut);text-align:right;font-variant-numeric:tabular-nums}
.tr{position:relative;height:10px;background:var(--line);border-radius:2px;margin-top:1px}.tr i{position:absolute;top:0;bottom:0;cursor:pointer}
.tr i:hover{outline:1.5px solid var(--fg);z-index:1}
.ln{position:relative;margin:1px 0 2px}.ln b{position:absolute;height:4px;border-radius:1px;cursor:pointer;min-width:2px}
.ln.unk{border-top:1px dashed var(--line)}.ln b.dis{outline:1.5px solid var(--bad);z-index:1}.ln b:hover,.ln b.hl{outline:2px solid var(--fg);z-index:2}
.cards{display:flex;gap:12px;flex-wrap:wrap;margin-top:10px}.card{border:1px solid var(--line);border-radius:6px;background:var(--card);padding:8px 10px;flex:1 1 320px;max-width:520px}
.card h3{font-size:13px;margin:0 0 4px}.card dl{display:grid;grid-template-columns:max-content 1fr;gap:1px 10px;margin:4px 0 0}.card dt{color:var(--mut);font-size:12px}.card dd{margin:0;overflow-wrap:anywhere}
.card .g{grid-column:1/-1;color:var(--mut);font-size:11px;text-transform:uppercase;letter-spacing:.04em;margin-top:5px}
.legend{display:flex;gap:16px;flex-wrap:wrap;align-items:center;color:var(--mut);font-size:12px}
#tip{position:fixed;pointer-events:none;background:var(--card);border:1px solid var(--line);border-radius:6px;padding:6px 8px;max-width:340px;font-size:12px;display:none;z-index:5;box-shadow:0 2px 8px #0002}
</style></head><body>
<header>__NAV__<h1>Genome</h1><span class="seg" id="donors"></span><span class="seg" id="levels"></span><span class="seg" id="models"></span><span id="focus"></span></header>
<main><section id="matches"></section><section id="chroms"></section><section id="segs"></section><section id="counts"></section></main><div id="tip"></div><div id="pop"></div>
<script type="text/plain" id="view-js">
const D=DATA;const DARK=matchMedia('(prefers-color-scheme:dark)').matches;
const esc=s=>String(s??'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const col=c=>(D.col[c]||['#8f8a80','#8f8a80'])[DARK?1:0];
const pct=x=>(100*x).toFixed(x<0.1?1:0)+'%';
const num=x=>x==null?'':Number(x).toLocaleString('en');
// a life as ✻ born and † died, as on the family page
const yrs=a=>a?[a[2]&&'✻ '+a[2],a[3]&&'† '+a[3]].filter(Boolean).join(' '):'';
const who=c=>{const a=D.anc[c];return a?(esc(a[1])||'<i>unnamed</i>'):'<i>no one in the tree</i>'};
const chipc=c=>c?`<span class="chip" style="background:${col(c.slice(0,2))}"></span><span class="code">${esc(c)}</span>`:'';
const fold=s=>String(s??'').normalize('NFD').replace(/[̀-ͯ]/g,'').toLowerCase();
const PL=D.P||[],MT=D.M||[],TP=D.tp||{},RS=D.R||[],SIDE={F:'paternal',M:'maternal'};
const VER={dissents:'dissent',unclear:'unclear',agrees:'agree'},VR={dissents:0,unclear:1,agrees:2};
const KIND={confirmed:'confirmed','name join':'name join','name join, ambiguous':'name join, ambiguous','vendor tree only':'vendor tree only'},KR={confirmed:0,'name join':1,'name join, ambiguous':2,'vendor tree only':3};
const SRC={documented:'a relative documented by hand (assertions.toml, [[anchors]]): the path is researched, the segment read against a parent\'s or the siblings\' matches',
 tree:'a match linked to a person in the tree (a confirmed identity, or a name join): the path is the tree\'s'};
const TH={code:'Lineage code: the path from the proband up to an ancestor, F for father and M for mother, read left to right (FM is the father\'s mother). Its first letter names the copy. Click one to hold that ancestor out.',
 anc:'The person the tree has at that code; the name opens the family page.',
 bar:'How much of this copy (in cM) the model paints with this code; the tick marks the average share inheritance gives.',
 share:'Share of the copy, in cM, painted with this code.',
 sure:'Share of the copy in blocks the model is at least 90% sure of (posterior ≥ 0.9).',
 agree:'Assertions under this code (match segments said to come down from this ancestor) that the model, judged without each one, places under it.',
 conf:'Assertions under this code that the model, judged without each one, places under another code. The rest are unclear.',
 match:'The DNA match, as the vendor names them. Click a row to draw only their segments (cmd- or shift-click adds more); click again to let go.',
 tree:'Who the match is in the tree. ● confirmed: a hand link ([[identity]] in assertions.toml, or tree_store.py link-match). ○ name join: their full name is a tree person who could be a donor; a candidate, not an identity (ambiguous: several people have the name). Vendor tree only: the vendor\'s own tree links them (FTDNA\'s linked relationship), ours does not. The relationship is to the donor in focus.',
 path:'The tree\'s path from the donor in focus up to the shared ancestors (F father, M mother), down to where a couple\'s two lines part. Filters by its first two letters.',
 place:'Where placement puts the match: the parent (F, M) or grandparent (FF, FM, MF, MM) they share through, read from the mother\'s match list, relatives sharing the segments, or the painting; the percent is the share of the placed cM that agrees, when not all. Blank: nothing could tell.',
 paint:'Where the copy model\'s painting puts the match: per segment with a known side, the grandparent the painting has under it (when at least 90% sure), summed over the match; the percent is the share of those cM that agree, when not all. ≠ tree: the tree\'s path names another grandparent (tick it to list just those). Blank: no painting for this donor, or no sided segment it is sure about.',
 ver:'The copy model\'s leave-one-out verdicts on the assertions this match makes (tree-linked and documented matches only): ✗ dissents, ? unclear, ✓ agrees. Filters by the worst one.',
 shared:'Shared cM: the vendor\'s total where its match list gives one, else the sum of the autosomal segments.',
 longest:'The longest shared segment, in cM.',
 nseg:'Segments in the export (all chromosomes, the X included).',
 also:'The other donors here who match them on the same platform: a sibling suggests a shared ancestor, the mother the maternal side.',
 plat:'The vendor and export the match comes from.',
 vendor:'The vendor\'s own reading: FTDNA\'s bucket (paternal, maternal, both) and relationship range, and its tree link where someone made one. Filters by the bucket.',
 surn:'Surnames from their match-list entry: those in both trees first (MyHeritage), then the ancestral surnames they list.',
 from:'What we have on the match: an entry in a match list (the vendor\'s details on them), exported segments, or both. A match with no segments has nothing to draw; one with no entry has only what the segments say.',
 tsize:'People in their tree at the vendor, from a match list or an AutoCluster run; the arrow opens it.',
 seen:'When the vendor first listed them (match lists give it; FTDNA always, MyHeritage rarely).',
 src:'Where the assertion\'s path comes from. documented: '+SRC.documented+'. tree: '+SRC.tree+'.',
 chr:(()=>{const c=Object.keys(D.lengths).sort((a,b)=>D.lengths[a]-D.lengths[b]),f=k=>`${k} (${D.mb[k]} Mb, ${Math.round(D.lengths[k])} cM)`;
  return c.length?`Chromosome. Numbered roughly by decreasing size (21, not 22, is in fact the smallest); here from ${f(c[0])} to ${f(c[c.length-1])}, as far as the genetic map reaches.`:'Chromosome.'})(),
 mb:'Where the segment starts and ends, in megabases (million base pairs): physical positions along the chromosome\'s DNA sequence.',
 cm:'Length in centimorgans: genetic distance, measured by how often crossovers fall in a stretch (1 cM is about a 1% chance of one per generation). It measures the same stretch as Mb, but by recombination rather than by letters of DNA, which is what says how much a shared segment means for relationship. On average about 1 Mb per cM, varying along the chromosome.',
 side:'The parent the segment comes through, as placement reads it; blank where it cannot tell (the next column says why).',
 gp:'The grandparent placement puts the segment under, where it can.',
 why:'Why placement gives the segment no side.',
 as:'The code an assertion on this segment names (tree-linked and documented matches); it can go deeper than the level shown.',
 spaint:'The grandparent the copy model\'s painting has under the segment, with its probability, where the side is known and it is at least 90% sure. With no side, both readings: what the segment would be on the paternal copy, and on the maternal (? where the painting is unsure there). This is how a match nobody has placed gets an ancestor: from where their segments fall.',
 sver:'The copy model\'s verdict on that assertion, judged without it.',
 sup:'The model\'s belief, computed without this assertion, that the segment\'s copy is under its code. Against the prior (a coin toss between the codes): well above it agrees, well below it dissents.'};
const th=(k,t,n)=>`<th class="help${n?' n':''}" title="${esc(TH[k])}">${t}</th>`;
const DONORS=[...new Set([...Object.keys(D.blocks||{}),...Object.keys(D.S||{}),...Object.keys(D.G||{})])].sort((a,b)=>(b===D.first)-(a===D.first)||(!D.blocks[a])-(!D.blocks[b])||a.localeCompare(b));
const dn=d=>(D.names||{})[d]||d;
// ---- state in the hash
const H=()=>new URLSearchParams(location.hash.slice(1));
const J=(h,k)=>{try{return JSON.parse(h.get(k)||'{}')||{}}catch(e){return {}}};
function state(){const h=H();let d=h.get('d');if(!DONORS.includes(d))d=DONORS[0];const P=D.blocks[d];
 const ms=P?Object.keys(P).sort((a,b)=>(b==='siblings')-(a==='siblings')):[];let m=h.get('m');if(!ms.includes(m))m=ms[0]||'';
 const c=(h.get('c')||'').replace(/[^FM]/g,'');let l=h.get('l')||String(Math.max(2,Math.min(3,c.length)));if(!P||!P[m]||!P[m][l])l='2';
 const sel=(h.get('s')||'').split(',').filter(x=>x!=='').map(Number);return {d,m,l,ms,c,sel,f:J(h,'f'),o:J(h,'o')}}
function setH(ch,push){const h=H();for(const [k,v] of Object.entries(ch)){if(v==null||v===''||(typeof v==='object'&&!Object.keys(v).length))h.delete(k);else h.set(k,typeof v==='object'?JSON.stringify(v):v)}
 if(push)location.hash='#'+h;else{history.replaceState(null,'','#'+h);render()}}
function link(k,v){const h=H();if(v==null)h.delete(k);else h.set(k,v);return '#'+h}
function seg(id,opts,cur,k,push,title){document.getElementById(id).innerHTML=opts.map(([v,t,dis])=>
 `<button data-v="${esc(v)}" class="${v===cur?'on':''}"${dis?' disabled':''} title="${esc(title||'')}">${esc(t)}</button>`).join('');
 document.getElementById(id).onclick=e=>{const b=e.target.closest('button');if(b&&!b.disabled)setH(k==='d'?{d:b.dataset.v,s:null}:{[k]:b.dataset.v},push)}}
// ---- tables with filters in the column heads, as in a spreadsheet: words (-word excludes, "a phrase"), a range, ticked values
function terms(q){const o=[];for(const m of String(q).matchAll(/(-?)"([^"]*)"|(\S+)/g)){if(m[3]!=null){const n=m[3].length>1&&m[3][0]==='-';o.push([n,fold(n?m[3].slice(1):m[3])])}else o.push([!!m[1],fold(m[2])])}return o.filter(t=>t[1])}
const colOf=(T,k)=>T.cols.find(c=>c.k===k);
const blank=x=>x==null||x==='';
function catOf(c,r){let v=c.cat(r);v=(Array.isArray(v)?v:[v]).filter(x=>!blank(x)).map(String);return v.length?v:['(none)']}
function txtOf(c,r){const k='_t'+c.k;return r[k]??=fold(c.txt?c.txt(r):c.v(r))}
const active=f=>f&&(f.q||f.lo!=null||f.hi!=null||f.i||f.x);
function passes(T,F,r,skip){for(const c of T.cols){const f=F[c.k];if(c.k===skip||!active(f))continue;
 if(f.q){const h=txtOf(c,r);for(const [neg,t] of (f._t??=terms(f.q)))if(h.includes(t)===neg)return false}
 if(f.lo!=null||f.hi!=null){const v=c.v(r);if(blank(v)||(f.lo!=null&&v<f.lo)||(f.hi!=null&&v>f.hi))return false}
 if(f.i||f.x){const v=catOf(c,r);if(f.i&&!v.some(x=>f.i.includes(x)))return false;if(f.x&&v.some(x=>f.x.includes(x)))return false}}return true}
const cmp=(a,b)=>typeof a==='number'&&typeof b==='number'?a-b:String(a).localeCompare(String(b),'sv',{numeric:true});
function compute(T,s){const F=JSON.parse(JSON.stringify(s.f[T.key]||{})),o=s.o[T.key]||T.sort0,desc=o[0]==='-',c=colOf(T,o.replace(/^-/,''))||T.cols[0];
 T.F=F;T.sort=desc?'-'+c.k:c.k;T.view=T.rows.filter(r=>passes(T,F,r));
 // rows with no value stay last in either direction
 T.view.sort((a,b)=>{const x=c.v(a),y=c.v(b),e=blank(x),g=blank(y);return e||g?e-g:desc?cmp(y,x):cmp(x,y)})}
function describe(f){const p=[];if(f.q)p.push(`“${esc(f.q)}”`);if(f.lo!=null||f.hi!=null)p.push(f.lo!=null&&f.hi!=null?`${f.lo}–${f.hi}`:f.lo!=null?`≥ ${f.lo}`:`≤ ${f.hi}`);
 if(f.i)p.push('only '+(f.i.length?f.i.map(esc).join(', '):'nothing'));if(f.x)p.push('not '+f.x.map(esc).join(', '));return p.join('; ')}
function setFilter(T,k,f){const s=state(),F={...(s.f[T.key]||{})};delete f._t;for(const x in f)if(f[x]==null||f[x]==='')delete f[x];
 if(active(f))F[k]=f;else delete F[k];for(const x in F)delete F[x]._t;T.limit=T.page;setH({f:{...s.f,[T.key]:F}})}
function setSort(T,o){const s=state();setH({o:{...s.o,[T.key]:o}})}
function drawTable(T,extra){const el=document.getElementById(T.id),sk=T.sort.replace(/^-/,''),desc=T.sort[0]==='-';
 const head=T.cols.map(c=>{const on=active(T.F[c.k]);return `<th class="${c.num?'n':''}${on?' fon':''}"><span class="help st" data-k="${c.k}" title="${esc(c.help||'')}">${c.t}${sk===c.k?(desc?' ▼':' ▲'):''}</span><button class="fb${on?' on':''}" data-k="${c.k}" title="Filter and sort">▾</button></th>`}).join('');
 const rows=T.view.slice(0,T.limit).map(r=>`<tr${T.attr?T.attr(r):''}>${T.cols.map(c=>`<td class="${c.num?'n':''}">${c.html?c.html(r):esc(c.num?num(c.v(r)):c.v(r))}</td>`).join('')}</tr>`).join('');
 const on=T.cols.filter(c=>active(T.F[c.k]));
 const chips=on.map(c=>`<span class="fchip"><b>${c.t}</b> ${describe(T.F[c.k])}<a data-clear="${c.k}" title="Clear this filter">✕</a></span>`).join('')+(on.length>1?'<a data-clear="*">clear all</a>':'');
 const left=T.view.length-T.limit;
 el.innerHTML=(extra||'')+(chips?`<div class="bar">${chips}</div>`:'')+(T.view.length?`<div class="tw"><table class="ft"><thead><tr>${head}</tr></thead><tbody>${rows}</tbody></table></div>`+
  (left>0?`<p class="meta">Showing ${num(T.limit)} of ${num(T.view.length)}. <a data-more="${T.page}">${num(Math.min(T.page,left))} more</a>${T.view.length<=5000?' · <a data-more="all">all</a>':''}</p>`:''):`<table class="ft"><thead><tr>${head}</tr></thead></table><p class="meta">No rows pass the filters.</p>`);
 el.onclick=e=>{const t=e.target;
  if(t.classList.contains('fb'))return openPop(T,t.dataset.k,t);
  if(t.classList.contains('st')){const c=colOf(T,t.dataset.k);return setSort(T,sk===c.k?(desc?c.k:'-'+c.k):(c.num?'-':'')+c.k)}
  if(t.dataset.more){T.limit=t.dataset.more==='all'?1e9:T.limit+(+t.dataset.more);return render()}
  if(t.dataset.clear){if(t.dataset.clear==='*'){const s=state();T.limit=T.page;return setH({f:{...s.f,[T.key]:{}}})}return setFilter(T,t.dataset.clear,{})}
  if(t.dataset.tog)return T.toggle(t.dataset.tog);
  const tr=t.closest('tr[data-m]');if(tr&&!t.closest('a')&&T.row)T.row(+tr.dataset.m,e)};
 if(T.hover){el.onmouseover=e=>{const tr=e.target.closest('tr[data-m]');T.hover(tr?+tr.dataset.m:null)};el.onmouseleave=()=>T.hover(null)}}
// the popover under a column head: sort, words or a range, the values to tick (counted over the rows the other filters let through)
const POP=document.getElementById('pop');let popAt=null,popT=null;
function openPop(T,k,btn){popAt={T,k};const r=btn.getBoundingClientRect();POP.style.display='block';
 POP.style.left=Math.max(8,Math.min(r.left-10,innerWidth-310))+'px';POP.style.top=Math.min(r.bottom+4,innerHeight-380)+'px';drawPop(true)}
function closePop(){popAt=null;POP.style.display='none'}
const curF=()=>({...((state().f[popAt.T.key]||{})[popAt.k]||{})});
function drawPop(first){const {T,k}=popAt,c=colOf(T,k),f=curF();
 let h=`<div class="pr"><b>${c.t}</b><span><button data-s="${c.k}">${c.num?'1→9':'A→Z'}</button> <button data-s="-${c.k}">${c.num?'9→1':'Z→A'}</button></span></div>`;
 h+=c.num?`<div class="pr"><input data-n="lo" type="number" step="any" placeholder="min" value="${f.lo??''}"> – <input data-n="hi" type="number" step="any" placeholder="max" value="${f.hi??''}"></div>`
  :`<div class="pr"><input data-q type="search" placeholder="words… (-word excludes)" value="${esc(f.q||'')}"></div>`;
 if(c.cat)h+=`<div class="pr"><span class="meta">Values</span><span><a data-all>all</a> · <a data-none>none</a> · <a data-inv>invert</a></span></div><div class="opts"></div>`;
 h+=`<div class="pr"><span class="meta">${c.num?'Blank rows drop out under a range.':'All words must appear; -word must not; "two words" as one.'}</span><button data-clr>Clear</button></div>`;
 POP.innerHTML=h;if(c.cat)drawOpts();const i=POP.querySelector('input');if(i&&first)i.focus()}
function optsOf(){const {T,k}=popAt,c=colOf(T,k),n=new Map();for(const r of T.rows)if(passes(T,T.F,r,k))for(const v of catOf(c,r))n.set(v,(n.get(v)||0)+1);
 const f=curF();for(const v of [...(f.i||[]),...(f.x||[])])if(!n.has(v))n.set(v,0);return [...n.entries()].sort((a,b)=>(a[0]==='(none)')-(b[0]==='(none)')||(c.order?c.order(a[0],b[0]):b[1]-a[1])||cmp(a[0],b[0]))}
function drawOpts(){const {T,k}=popAt,c=colOf(T,k),f=curF(),on=v=>f.i?f.i.includes(v):!(f.x||[]).includes(v),o=optsOf();
 POP.querySelector('.opts').innerHTML=o.slice(0,400).map(([v,m])=>`<label><input type="checkbox" data-v="${esc(v)}"${on(v)?' checked':''}> ${c.lab?c.lab(v):esc(v)} <span class="meta">${num(m)}</span></label>`).join('')+(o.length>400?`<p class="meta">and ${o.length-400} more: use the words above</p>`:'')}
POP.oninput=e=>{const t=e.target;if(!popAt||t.type==='checkbox')return;const {T,k}=popAt,f=curF();
 if(t.dataset.q!=null)f.q=t.value.trim();else if(t.dataset.n)f[t.dataset.n]=t.value===''?null:+t.value;
 clearTimeout(popT);popT=setTimeout(()=>{setFilter(T,k,f);if(POP.querySelector('.opts'))drawOpts()},200)};
POP.onchange=e=>{const t=e.target;if(!popAt||t.type!=='checkbox')return;const {T,k}=popAt,f=curF(),v=t.dataset.v;
 if(f.i)f.i=t.checked?[...f.i,v]:f.i.filter(x=>x!==v);else{f.x=t.checked?(f.x||[]).filter(x=>x!==v):[...(f.x||[]),v];if(!f.x.length)delete f.x}
 setFilter(T,k,f);drawOpts()};
POP.onclick=e=>{const t=e.target;if(!popAt)return;const {T,k}=popAt,f=curF();
 if(t.dataset.s){setSort(T,t.dataset.s);return closePop()}
 if(t.dataset.clr!=null){setFilter(T,k,{});return closePop()}
 if(t.dataset.all!=null){delete f.i;delete f.x}else if(t.dataset.none!=null){f.i=[];delete f.x}
 else if(t.dataset.inv!=null){const all=optsOf().map(x=>x[0]),on=v=>f.i?f.i.includes(v):!(f.x||[]).includes(v);const x=all.filter(on);delete f.i;f.x=x;if(!x.length)delete f.x}else return;
 setFilter(T,k,f);drawOpts()};
document.addEventListener('mousedown',e=>{if(popAt&&!POP.contains(e.target)&&!e.target.classList.contains('fb'))closePop()});
document.addEventListener('keydown',e=>{if(e.key==='Escape')closePop()});
// ---- the copy model's verdicts, tied to the donor's segments (the one of its match that holds its start)
const memo={};
function verdicts(s){const key=s.d+'|'+s.m;if(memo[key])return memo[key];const G=(D.G||{})[s.d]||[],S=(D.S||{})[s.d]||[];
 const byKey={};for(const x of S)(byKey[MT[x[0]][1]]??=[]).push(x[0]);const at={};G.forEach((g,i)=>(at[g[0]+'|'+g[1]]??=[]).push(i));
 const seg=new Map(),mv=new Map();
 for(const v of D.verdicts)if(v[0]===s.d&&v[1]===s.m){const o={src:v[2],code:v[6],sup:v[7],ver:v[8]},mis=byKey[v[10]]||[],mb=v[5]/1e6;let hit=null;
  for(const mi of mis){for(const i of at[mi+'|'+v[4]]||[]){const g=G[i];if(mb>=g[4]-0.01&&mb<=g[5]+0.01){hit=i;break}}if(hit!=null)break}
  if(hit!=null)seg.set(hit,[...(seg.get(hit)||[]),o].sort((a,b)=>VR[a.ver]-VR[b.ver]));const mi=hit!=null?G[hit][0]:mis[0];if(mi==null)continue;
  const c=mv.get(mi)||{agrees:0,unclear:0,dissents:0};c[o.ver]++;mv.set(mi,c)}
 for(const c of mv.values())c.worst=c.dissents?'dissents':c.unclear?'unclear':'agrees';return memo[key]={seg,mv}}
// ---- the match list
function matchRows(s){const key='m|'+s.d+'|'+s.m;if(memo[key])return memo[key];const vs=verdicts(s);
 return memo[key]=((D.S||{})[s.d]||[]).map(x=>{const m=MT[x[0]],lk=m[4];
  const r={mi:x[0],plat:PL[m[0]],name:m[2],surn:m[3],link:lk,shared:x[1],longest:x[2],nseg:x[3],place:x[4],agree:x[5],bucket:x[6],range:x[7],vrel:x[8],also:x[9].map(dn),rel:x[10],path:x[11],cm:x[12]||'',cmag:x[13],e:x[14]||null,ver:vs.mv.get(x[0])||null};
  r.from=r.e?(r.nseg?'list and segments':'list only'):'segments only';
  r.surns=[r.e&&r.e.shared_surnames,r.surn].filter(Boolean).join(' · ');
  r.clash=!!(r.path&&r.cm&&!r.cm.startsWith(r.path.slice(0,2))&&!r.path.startsWith(r.cm));
  r.kind=lk?(lk[0]==='confirmed'?'confirmed':lk[1].length>1?'name join, ambiguous':'name join'):r.vrel?'vendor tree only':'';return r})}
const person=i=>{const p=TP[i]||[i,i];return `<a href="family.html#p=${encodeURIComponent(p[0])}" title="The family page on them">${esc(p[1])}</a> <span class="meta">${esc(yrs(p))}</span>`};
function treeHtml(r){if(!r.kind)return '';const k=`<span class="k ${r.kind==='confirmed'?'confirmed':r.kind==='vendor tree only'?'vendor':''}" title="${esc(KIND[r.kind])}"></span>`;
 if(r.kind==='vendor tree only')return k+`<span class="meta">${esc(r.plat.split(' ')[0])} tree:</span> ${esc(r.vrel)}`;
 const ps=r.link[1];return k+(ps.length>1?`<span class="meta">${ps.length} candidates:</span> `+ps.slice(0,3).map(person).join(', '):person(ps[0])+(r.rel?` · ${esc(r.rel)}`:''))}
const treeTxt=r=>r.kind?[r.kind,...(r.link?r.link[1].map(i=>(TP[i]||[0,i])[1]):[]),r.rel,r.vrel].join(' '):'';
const verHtml=r=>r.ver?[['agrees','✓'],['unclear','?'],['dissents','✗']].filter(([k])=>r.ver[k]).map(([k,g])=>`<span class="${k==='dissents'?'bad':''}" title="${r.ver[k]} ${VER[k]}">${r.ver[k]}${g}</span>`).join(' '):'';
const MT_=mkTable('matches','m',[
 {k:'name',t:'Match',v:r=>r.name,help:TH.match},
 {k:'tree',t:'In the tree',v:r=>r.kind?KR[r.kind]:null,txt:treeTxt,html:treeHtml,cat:r=>r.kind,order:(a,b)=>(KR[a]??9)-(KR[b]??9),help:TH.tree},
 {k:'path',t:'Path',v:r=>r.path||null,html:r=>chipc(r.path),cat:r=>r.path.slice(0,2),order:(a,b)=>a.localeCompare(b),help:TH.path},
 {k:'place',t:'Placed',v:r=>r.place||null,html:r=>chipc(r.place)+(r.agree!=null&&r.agree<1&&r.place?` <span class="meta">${pct(r.agree)}</span>`:''),cat:r=>r.place,order:(a,b)=>a.localeCompare(b),help:TH.place},
 {k:'paint',t:'Painting puts',v:r=>r.cm||null,txt:r=>r.cm+(r.clash?' ≠ tree':''),
  html:r=>chipc(r.cm)+(r.cmag!=null&&r.cmag<1&&r.cm?` <span class="meta">${pct(r.cmag)}</span>`:'')+(r.clash?' <span class="bad" title="The tree\'s path names another grandparent">≠ tree</span>':''),
  cat:r=>[r.cm,r.clash?'≠ tree':''],order:(a,b)=>(a==='≠ tree')-(b==='≠ tree')||a.localeCompare(b),help:TH.paint},
 {k:'ver',t:'Verdicts',v:r=>r.ver?VR[r.ver.worst]:null,txt:r=>r.ver?r.ver.worst:'',html:verHtml,cat:r=>r.ver?r.ver.worst:'',order:(a,b)=>VR[a]-VR[b],help:TH.ver},
 {k:'shared',t:'cM',num:1,v:r=>r.shared,help:TH.shared},
 {k:'longest',t:'Longest',num:1,v:r=>r.longest,help:TH.longest},
 {k:'nseg',t:'Segs',num:1,v:r=>r.nseg,help:TH.nseg},
 {k:'also',t:'Also matches',v:r=>r.also.join(', ')||null,cat:r=>r.also,help:TH.also},
 {k:'plat',t:'Platform',v:r=>r.plat,cat:r=>r.plat,help:TH.plat},
 {k:'vendor',t:'Vendor says',v:r=>[r.bucket,r.range].filter(Boolean).join(' · ')||null,txt:r=>[r.bucket,r.range,r.vrel].join(' '),
  html:r=>[r.bucket&&esc(r.bucket),r.range&&`<span class="meta">${esc(r.range)}</span>`].filter(Boolean).join(' · '),cat:r=>r.bucket,help:TH.vendor},
 {k:'tsize',t:'Their tree',num:1,v:r=>r.e?r.e.tree_size??null:null,html:r=>{const e=r.e;if(!e)return '';const n=e.tree_size!=null?num(e.tree_size):e.has_tree===false?'none':e.has_tree?'yes':'';
  return n+(e.tree_url?` <a href="${esc(e.tree_url)}" target="_blank" rel="noopener" title="Their tree at the vendor">↗</a>`:'')},help:TH.tsize},
 {k:'seen',t:'Matched',v:r=>r.e?r.e.match_date||null:null,cat:r=>r.e&&r.e.match_date?r.e.match_date.slice(0,4):'',order:(a,b)=>b.localeCompare(a),help:TH.seen},
 {k:'surn',t:'Surnames',v:r=>r.surns||null,html:r=>r.surns?`<span class="trunc" title="${esc(r.surns)}">${r.e&&r.e.shared_surnames?`<b>${esc(r.e.shared_surnames)}</b>`+(r.surn?' · ':''):''}${esc(r.surn)}</span>`:'',help:TH.surn},
 {k:'from',t:'From',v:r=>r.from,html:r=>`<span class="meta">${r.from}</span>`,cat:r=>r.from,help:TH.from}],'-shared',100);
MT_.attr=r=>` data-m="${r.mi}" class="${r.kind&&r.kind!=='vendor tree only'?'lk':''}${state().sel.includes(r.mi)?' on':''}"`;
MT_.row=(mi,e)=>{const s=state();let sel=s.sel;if(e.metaKey||e.ctrlKey||e.shiftKey)sel=sel.includes(mi)?sel.filter(x=>x!==mi):[...sel,mi];else sel=sel.length===1&&sel[0]===mi?[]:[mi];SEGS.limit=SEGS.page;setH({s:sel.join(',')})};
MT_.hover=mi=>{for(const b of document.querySelectorAll('#chroms b.hl'))b.classList.remove('hl');if(mi!=null)for(const b of document.querySelectorAll(`#chroms b[data-m="${mi}"]`))b.classList.add('hl')};
// two quick filters: tree-linked only, dissents only
const QUICK={tree:['tree',{x:['(none)','vendor tree only']}],dis:['ver',{i:['dissents']}]};
MT_.toggle=q=>{const [k,f]=QUICK[q];setFilter(MT_,k,JSON.stringify(MT_.F[k]||{})===JSON.stringify(f)?{}:JSON.parse(JSON.stringify(f)))};
function mkTable(id,key,cols,sort0,page){return {id,key,cols,sort0,page,limit:page,rows:[],view:[],F:{},sort:sort0}}
// a card per selected match: what the match list says (grouped as kits.ENTRY), and what we have
const GROUPS={match:'The match',dna:'Shared DNA',person:'The person',contact:'Contact',tree:'Their tree'};
function fval(f,v){if(typeof v==='boolean')return v?'yes':'no';if(/_url$/.test(f))return `<a href="${esc(v)}" target="_blank" rel="noopener">open ↗</a>`;
 if(f==='email')return `<a href="mailto:${esc(v)}">${esc(v)}</a>`;return esc(typeof v==='number'?num(v):v)}
function card(r,mi){const m=MT[mi];if(!r)return `<div class="card"><h3>${esc(m[2])}</h3><p class="meta">Not a match of ${esc(dn(state().d))}.</p></div>`;
 const e=r.e,h=[`<h3>${esc(r.name)} <span class="meta">${esc(r.plat)}</span></h3>`];
 h.push(`<p class="meta">${e?`Match list: ${esc(e.sources)}${e.list_date?' ('+esc(e.list_date)+')':''}.`:'No match-list entry: known from segments only.'} ${r.nseg?`${r.nseg} segment${r.nseg>1?'s':''} exported.`:'No segments exported: nothing to draw.'}</p>`);
 if(e){let g='';const dl=[];for(const [f,lab,grp,help] of D.EF||[]){if(e[f]==null||e[f]==='')continue;if(grp!==g){dl.push(`<div class="g">${GROUPS[grp]||grp}</div>`);g=grp}
   dl.push(`<dt title="${esc(help)}">${esc(lab)}</dt><dd>${fval(f,e[f])}</dd>`)}
  if(r.surn)dl.push(`<dt>Ancestral surnames</dt><dd>${esc(r.surn)}</dd>`);h.push(`<dl>${dl.join('')}</dl>`)}
 return `<div class="card">${h.join('')}</div>`}
// ---- the segment list: the segments of the matches the list shows (or of the selected ones)
const SEGS=mkTable('segs','g',[
 {k:'name',t:'Match',v:r=>r.name,help:TH.match},
 {k:'chr',t:'Chr',v:r=>+r.chrom||23,txt:r=>r.chrom,html:r=>esc(r.chrom),cat:r=>r.chrom,order:(a,b)=>(+a||23)-(+b||23),help:TH.chr},
 {k:'s',t:'Start Mb',num:1,v:r=>r.s,help:TH.mb},{k:'e',t:'End Mb',num:1,v:r=>r.e,help:TH.mb},
 {k:'cM',t:'cM',num:1,v:r=>r.cM,help:TH.cm},
 {k:'side',t:'Side',v:r=>r.par||null,html:r=>r.par?chipc(r.par)+`<span class="meta">${SIDE[r.par]||''}</span>`:'',cat:r=>r.par,lab:v=>esc(SIDE[v]?v+' '+SIDE[v]:v),help:TH.side},
 {k:'gp',t:'Grandparent',v:r=>r.gp||null,html:r=>chipc(r.gp),cat:r=>r.gp,order:(a,b)=>a.localeCompare(b),help:TH.gp},
 {k:'why',t:'No side, because',v:r=>r.why||null,html:r=>`<span class="meta">${esc(r.why)}</span>`,cat:r=>r.why,help:TH.why},
 {k:'paint',t:'Painting says',v:r=>r.cm||(r.iff||r.ifm?'~'+r.iff+r.ifm:null),txt:r=>[r.cm,r.iff,r.ifm].join(' '),
  html:r=>r.cm?chipc(r.cm)+(r.cmp!=null?` <span class="meta">${r.cmp.toFixed(2)}</span>`:''):r.iff||r.ifm?`<span class="meta">F:</span> ${r.iff?chipc(r.iff):'?'} <span class="meta">M:</span> ${r.ifm?chipc(r.ifm):'?'}`:'',
  cat:r=>r.cm||(r.iff||r.ifm?`${r.iff||'?'} or ${r.ifm||'?'}`:''),order:(a,b)=>a.length-b.length||a.localeCompare(b),help:TH.spaint},
 {k:'as',t:'Asserted',v:r=>r.v?r.v.code:null,txt:r=>r.vl.map(v=>v.code+' '+v.src).join(' '),html:r=>r.vl.map(v=>chipc(v.code)+` <span class="meta">${esc(v.src)}</span>`).join('<br>'),cat:r=>r.vl.map(v=>v.code.slice(0,2)),order:(a,b)=>a.localeCompare(b),help:TH.as},
 {k:'sver',t:'Verdict',v:r=>r.v?VR[r.v.ver]:null,html:r=>r.vl.map(v=>`<span class="${v.ver==='dissents'?'bad':''}">${esc(v.ver)}</span>`).join('<br>'),cat:r=>r.vl.map(v=>v.ver),order:(a,b)=>VR[a]-VR[b],help:TH.sver},
 {k:'sup',t:'Support',num:1,v:r=>r.v?r.v.sup:null,html:r=>r.vl.map(v=>`<span class="${v.ver==='dissents'?'bad':''}">${v.sup.toFixed(2)}</span>`).join('<br>'),help:TH.sup}],'chr',200);
SEGS.attr=r=>` data-m="${r.mi}"`;SEGS.row=(mi,e)=>MT_.row(mi,e);SEGS.hover=MT_.hover;
// ---- painting helpers
function render(){const tip=document.getElementById('tip');tip.style.display='none';
 if(!DONORS.length){document.querySelector('main').innerHTML=`<section><h2>Nothing to show</h2><p>${esc(D.none||'No segment lists and no painting.')}</p></section>`;return}
 const s=state(),P=D.blocks[s.d],bl=P&&s.m?P[s.m][s.l]:null,L=+s.l,prior=1/2**(L-1),why=(D.donors||{})[s.d];
 seg('donors',DONORS.map(d=>[d,dn(d)]),s.d,'d',true,'The donor in focus');
 seg('levels',P?[['2','grandparents',!P[s.m]['2']],['3','great-grandparents',!P[s.m]['3']]]:[],s.l,'l',false,'How far back the codes go');
 // single donor always applies; the siblings model only with phased full siblings, and is then the default
 seg('models',P?['single','siblings'].map(m=>[m,m==='siblings'?'siblings model':'single donor',!s.ms.includes(m)]):[],s.m,'m',false,'Which copy model painted the blocks: this donor alone, or the siblings modelled together through their shared phasing (needs raw kits for full siblings; preferred when there)');
 const F=document.getElementById('focus');F.innerHTML=P&&s.c?`<span class="chip" style="background:${col(s.c)}"></span><span class="code">${s.c}</span> ${who(s.c)} <span class="meta">${esc(yrs(D.anc[s.c]))}</span><a title="Show every ancestor">✕</a>`:'';
 if(P&&s.c)F.querySelector('a').onclick=()=>setH({c:null},true);
 // the match list
 MT_.rows=matchRows(s);compute(MT_,s);
 const R=MT_.rows,nl=R.filter(r=>r.kind==='confirmed').length,nn=R.filter(r=>r.kind&&r.kind.startsWith('name')).length,nd=R.filter(r=>r.ver&&r.ver.worst==='dissents').length;
 const byP={};for(const r of R)byP[r.plat]=(byP[r.plat]||0)+1;
 const qOn=q=>JSON.stringify(MT_.F[QUICK[q][0]]||{})===JSON.stringify(QUICK[q][1]);
 MT_.limit=Math.max(MT_.limit,0);
 drawTable(MT_,`<h2>Matches of ${esc(dn(s.d))} <span class="meta">${Object.entries(byP).map(([p,n])=>`${num(n)} on ${esc(p)}`).join(', ')}</span></h2>`+
  `<div class="bar"><button class="tog${qOn('tree')?' on':''}" data-tog="tree" title="Only matches the tree links to a person (by hand or by name)">In the tree: ${num(nl)} confirmed, ${num(nn)} by name</button>`+
  (nd?`<button class="tog${qOn('dis')?' on':''}" data-tog="dis" title="Only matches with an assertion the copy model dissents from: the work to do">${num(nd)} with dissents</button>`:'')+
  `<span class="meta">${num(MT_.view.length)} listed${MT_.view.length<R.length?` of ${num(R.length)}`:''}</span>`+
  (s.sel.length?`<span class="fchip">${s.sel.length} selected <a data-sel title="Let go of the selection">✕</a></span>`:'')+`</div>`);
 if(s.sel.length){const byMi=new Map(R.map(r=>[r.mi,r]));document.getElementById('matches').insertAdjacentHTML('beforeend',`<div class="cards">${s.sel.slice(0,4).map(mi=>card(byMi.get(mi),mi)).join('')}</div>`+(s.sel.length>4?`<p class="meta">and ${s.sel.length-4} more selected</p>`:''))}
 const ms=document.querySelector('#matches [data-sel]');if(ms)ms.onclick=e=>{e.stopPropagation();setH({s:null})};
 // the segments of the matches shown (or selected)
 const sel=new Set(s.sel.length?s.sel:MT_.view.slice(0,MT_.limit).map(r=>r.mi)),G=(D.G||{})[s.d]||[],vs=verdicts(s);
 SEGS.rows=[];G.forEach((g,i)=>{if(sel.has(g[0]))SEGS.rows.push({i,mi:g[0],name:MT[g[0]][2],chrom:g[1],a:g[2],b:g[3],s:g[4],e:g[5],cM:g[6],par:g[7],gp:g[8],why:RS[g[9]]||'',cm:g[10]||'',cmp:g[11],iff:g[12]||'',ifm:g[13]||'',vl:vs.seg.get(i)||[],v:(vs.seg.get(i)||[])[0]})});
 compute(SEGS,s);
 const whose=s.sel.length?`the ${s.sel.length} selected match${s.sel.length>1?'es':''}`:`the ${num(sel.size)} match${sel.size===1?'':'es'} listed above`;
 drawTable(SEGS,`<h2>Segments <span class="meta">of ${whose}: ${num(SEGS.view.length)}${SEGS.view.length<SEGS.rows.length?` of ${num(SEGS.rows.length)}`:''}; the filters here narrow the drawing too</span></h2>`);
 // chromosomes
 const chroms=Object.keys(D.lengths).sort((a,b)=>(+a||99)-(+b||99)),mx=Math.max(...Object.values(D.lengths));
 const held=code=>!s.c||code.startsWith(s.c)||s.c.startsWith(code);
 const op=(p,code)=>((0.15+0.85*Math.max(0,Math.min(1,(p-prior)/(1-prior))))*(held(code)?1:0.2)).toFixed(2);
 const side=g=>g.par||(/^[FM]{2}$/.test(g.gp)?g.gp[0]:'')||'?';
 const DRAW=SEGS.view.slice(0,6000),lanes={};for(const g of DRAW)(lanes[g.chrom+side(g)]??=[]).push(g);
 const scol=g=>/^[FM]{2}$/.test(g.gp)?col(g.gp):g.par?col(g.par):'var(--mut)';
 const lane=(ch,sd,len,w)=>{const gs=(lanes[ch+sd]||[]).slice().sort((a,b)=>a.a-b.a),ends=[];let h='';
  for(const g of gs){let k=ends.findIndex(e=>e<g.a);if(k<0){if(ends.length<8){k=ends.length;ends.push(0)}else k=ends.indexOf(Math.min(...ends))}ends[k]=Math.max(ends[k],g.b+0.3);
   h+=`<b data-g="${g.i}" data-m="${g.mi}" class="${g.v&&g.v.ver==='dissents'?'dis':''}" style="top:${k*5}px;left:${100*g.a/len}%;width:${100*(g.b-g.a)/len}%;background:${scol(g)};opacity:${g.par||g.gp?1:0.7}"></b>`}
  return ends.length?`<div class="ln${sd==='?'?' unk':''}" style="width:${w}%;height:${ends.length*5}px">${h}</div>`:''};
 const SG=new Map(SEGS.rows.map(r=>[r.i,r]));
 document.getElementById('chroms').innerHTML=`<h2>Chromosomes <span class="meta">${P?'paternal copy':'paternal side'} and its segments, then the maternal, then segments with no side (dashed); width by <span class="help" title="${esc(TH.cm)}">cM</span>; the segments listed below${SEGS.view.length>DRAW.length?` (the first ${num(DRAW.length)})`:''}</span></h2>`+
  (P?'':`<p class="meta">No painting for ${esc(dn(s.d))}: ${esc(why||'the copy model has no blocks for them')}. The copies are drawn bare.</p>`)+chroms.map(ch=>{
  const w=100*D.lengths[ch]/mx,len=D.lengths[ch];
  const track=sd=>`<div class="tr" style="width:${w}%">`+(bl||[]).map((b,i)=>b[0]===ch&&b[1]===sd?`<i data-i="${i}" style="left:${100*b[2]/len}%;width:${Math.max(0.3,100*(b[3]-b[2])/len)}%;background:${col(b[6])};opacity:${op(b[7],b[6])}"></i>`:'').join('')+'</div>'+lane(ch,sd,len,w);
  return `<div class="cr"><span>${ch}</span><div>${track('F')}${track('M')}${lane(ch,'?',len,w)}</div></div>`}).join('')+
  `<p class="legend"><span>A segment takes its grandparent's colour where placement has one, its parent's where it has only the side; grey: no side. Red outline: an assertion the model dissents from.</span>${P?'<span>A block fades from its prior (unsure) to sure.</span>':''}<span>Click a segment to select its match.</span></p>`;
 // the painting's key: counts per code
 const C=document.getElementById('counts');
 if(!P){C.innerHTML=`<h2>Painting</h2><p class="meta">None for ${esc(dn(s.d))}: ${esc(why||'no copy-model blocks')}.</p>`}
 else{const V=D.verdicts.filter(v=>v[0]===s.d&&v[1]===s.m).map(v=>({code:v[6],ver:v[8]}));
  const tot={F:0,M:0},by={};for(const b of bl){const w=b[3]-b[2];tot[b[1]]+=w;const o=by[b[6]]??={cm:0,sure:0};o.cm+=w;if(b[7]>=D.sure)o.sure+=w}
  const codes=Object.keys(D.col).filter(c=>c.length===L).sort();
  C.innerHTML=`<h2>Painting: ${esc(dn(s.d))}'s share of each copy by ${L===2?'grandparent':'great-grandparent'} (${s.m==='siblings'?'siblings model':'single donor'})</h2><table><tr>${th('code','Code')}${th('anc','Ancestor')}${th('bar','Share of the copy')}${th('share','Share',1)}${th('sure','Sure',1)}${th('agree','Assertions agree',1)}${th('conf','dissent',1)}</tr>`+
  codes.map(c=>{const o=by[c]||{cm:0,sure:0},t=tot[c[0]]||1,a=D.anc[c],vs=V.filter(v=>v.code.startsWith(c)),ag=vs.filter(v=>v.ver==='agrees').length,cf=vs.filter(v=>v.ver==='dissents').length;
   return `<tr${s.c&&c.startsWith(s.c)?' class="on"':''}><td><span class="chip" style="background:${col(c)}"></span><a class="code" href="${link('c',c)}" title="Hold out this ancestor">${c}</a></td><td>${a?`<a href="family.html#p=${encodeURIComponent(a[0])}">${who(c)}</a> <span class="meta">${esc(yrs(a))}</span>`:who(c)}</td>`+
    `<td><div class="share" title="Expected ${pct(prior)}"><i style="width:${100*o.cm/t}%;background:${col(c)}"></i><b style="left:${100*prior}%"></b></div></td>`+
    `<td class="n">${pct(o.cm/t)}</td><td class="n">${pct(o.sure/t)}</td><td class="n">${ag}</td><td class="n${cf?' bad':''}">${cf}</td></tr>`}).join('')+'</table>'+
  `<p class="legend"><span>Bar: the code's share of its copy; tick: the expected ${pct(prior)}.</span></p>`}
 const ch=document.getElementById('chroms');
 ch.onmousemove=e=>{const t=e.target;let h='';
  if(t.dataset.i!=null&&bl){const b=bl[+t.dataset.i],a=D.anc[b[6]];
   h=`<b><span class="code">${b[6]}</span> ${who(b[6])}</b> <span class="meta">${esc(yrs(a))}</span><br>chr ${b[0]}, ${b[2]}–${b[3]} cM (${(b[4]/1e6).toFixed(1)}–${(b[5]/1e6).toFixed(1)} Mb)<br>posterior ${b[7].toFixed(2)} (prior ${prior.toFixed(2)})`+(a?'<br><span class="meta">click: the family page on them</span>':'')}
  else if(t.dataset.g!=null){const g=SG.get(+t.dataset.g),m=MT[g.mi];
   h=`<b>${esc(m[2])}</b> <span class="meta">${esc(PL[m[0]])}</span><br>chr ${esc(g.chrom)}, ${g.s.toFixed(1)}–${g.e.toFixed(1)} Mb, ${g.cM} cM<br>`+(g.par?`${SIDE[g.par]}${g.gp?', <span class="code">'+esc(g.gp)+'</span> '+who(g.gp):''}`:`no side: ${esc(g.why||'unknown')}`)+
    (g.cm?`<br>painting: <span class="code">${esc(g.cm)}</span> ${who(g.cm)} (${g.cmp})`:g.iff||g.ifm?`<br>painting: ${esc(g.iff||'?')} if paternal, ${esc(g.ifm||'?')} if maternal`:'')+
    (g.v?`<br>asserted <span class="code">${esc(g.v.code)}</span>: <span class="${g.v.ver==='dissents'?'bad':''}">${g.v.ver}</span>, support without it ${g.v.sup.toFixed(2)}`:'')+'<br><span class="meta">click: select this match</span>'}
  tip.style.display=h?'block':'none';if(h){tip.innerHTML=h;tip.style.left=Math.min(e.clientX+12,innerWidth-350)+'px';tip.style.top=(e.clientY+14)+'px'}};
 ch.onmouseleave=()=>tip.style.display='none';
 ch.onclick=e=>{const t=e.target;if(t.dataset.g!=null)return MT_.row(+t.dataset.m,e);const i=t.dataset.i;if(i==null||!bl)return;const a=D.anc[bl[+i][6]];if(a)location.href='family.html#p='+encodeURIComponent(a[0])};
 if(popAt)drawPop(false);
}
window.addEventListener('hashchange',render);render();
</script>__DATA__</body></html>
"""


def _main(argv):
    import config
    import familyview
    import gedcom_io
    import intervals as iv
    import outputs
    import tree_store
    cfg = config.load()
    D = cfg["data_dir"]
    path = config.path(cfg, "genome.html")
    empty = pd.DataFrame(columns="chrom side start_cm end_cm start end lineage posterior subject level model".split())
    blocks = (outputs.read(D, "copy_model_blocks.csv", dtype={"chrom": str})
              if outputs.has(D, "copy_model_blocks.csv") else empty)
    verdicts = (outputs.read(D, "copy_model_verdicts.csv", dtype={"chrom": str})
                if outputs.has(D, "copy_model_verdicts.csv") else None)
    segs = (outputs.read(D, "placed_segments.csv", dtype={"chrom": str})
            if outputs.has(D, "placed_segments.csv") else pd.DataFrame(columns="platform subject match_key match chrom start end cM parent parent_reason grandparent".split()))
    placed = outputs.read(D, "placed_matches.csv") if outputs.has(D, "placed_matches.csv") else None
    db, root = tree_store.default_store().db, familyview.proband_id(cfg)
    anc = ancestors(db, root)
    import kits
    try:
        entries = kits.match_entries(cfg)
    except (FileNotFoundError, ValueError, KeyError) as e:
        print("no match lists:", e)
        entries = None
    subj = sorted(set(blocks.subject.astype(str)) | set(segs.subject.dropna().astype(str))
                  | set(entries.subject.astype(str) if entries is not None else ()))
    mh = {d: (cfg.get("people", {}).get(d) or {}).get("mh") for d in subj}
    why = fit(parents(db), root, mh)
    painted = set(blocks.subject)
    blocks = blocks[blocks.subject.map(lambda d: why[d] is None)]
    if verdicts is not None:
        verdicts = verdicts[verdicts.subject.map(lambda d: why.get(d, "") is None)]
    matches = (dict(outputs.read(D, "copy_model_placed_matches.csv", usecols=["match_key", "match"]).values)
               if outputs.has(D, "copy_model_placed_matches.csv") else None)
    data = collect(blocks, verdicts, anc, {}, matches)
    # the match list, with the tree's links to the matches
    links, relate, people = {}, None, {}
    try:
        tree, proband = gedcom_io.load(cfg)
        keys = pd.concat([x[["platform", "match_key", "match"]] for x in (segs, placed, entries) if x is not None])
        links = tree_links(cfg, tree, proband, keys.dropna().astype(str).drop_duplicates(["platform", "match_key"]), db)
        relate = relater(tree, mh)
        people = {i: tree_person(tree, i) for _, ids in links.values() for i in ids}
    except (KeyError, FileNotFoundError) as e:
        print("no tree links:", e)
    cm_segs, cm_matches = (outputs.read(D, f, dtype={"chrom": str}) if outputs.has(D, f) else None
                           for f in ("copy_model_placed_segments.csv", "copy_model_placed_matches.csv"))
    ml = match_list(segs, placed, iv.GeneticMap.load(cfg, quiet=True), links, relate, people, cm_segs, cm_matches, entries)
    ml["EF"] = [list(x) for x in kits.ENTRY]
    # a verdict keyed by a folded selection's name key goes to the full export's match
    import identity
    known, by_name = {m[1] for m in ml["M"]}, {}
    for m in ml["M"]:
        by_name.setdefault(identity.name_key(m[2]), m[1])
    for v in data["verdicts"]:
        if v[10] not in known and str(v[10]).startswith("name:"):
            v[10] = by_name.get(v[10][5:], v[10])
    for ch, (cm, mb) in ml.pop("ends").items():
        data["lengths"][ch] = max(data["lengths"].get(ch, 0), cm)
        data["mb"][ch] = max(data["mb"].get(ch, 0), mb)
    data.update(ml, names={d: config.display_name(cfg, d) for d in subj},
                first=next((d for d in subj if mh[d] == root), None),
                donors={d: why[d] or (None if d in painted else "the copy model has no blocks for them") for d in subj})
    data["none"] = ("No match lists or segment lists for any donor: name them in family.toml "
                    "([[segment_exports]], with `match_list` for a list) and run match_placement.py.")
    write(path, data)
    n = sum(map(len, ml["S"].values()))
    print(f"{len(subj)} donors ({len(data['blocks'])} painted), {n} match rows "
          f"({sum(1 for v in links.values() if v[0] == 'confirmed')} confirmed and "
          f"{sum(1 for v in links.values() if v[0] == 'name')} name-joined to the tree), "
          f"{sum(map(len, ml['G'].values()))} segments, {len(data['verdicts'])} verdicts -> {path}")


if __name__ == "__main__":
    _main(sys.argv[1:])
