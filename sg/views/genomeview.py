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
the copy they come through, folded to one thin line per side by default
(a chromosome, or all, unfold into rows, one per overlap), and the segment list lists the same; its
filters narrow the drawing too. Last, the painting's key: per code its
share of its copy against the expected, how much is sure, and the
verdicts under it. Column heads explain themselves on hover.

Blocks are painted for the proband and full siblings only (the codes run
from the proband); other donors get their matches and segments on bare
copies, with the reason.

Link scheme (after #): d=<donor>&c=<code>&l=<2|3>&m=<siblings|single>
&s=<selected matches>&u=<unfolded chromosomes|all>&f=<filters>&o=<sorts>
(f and o JSON, per table).
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

from sg.common import lineage
from sg.views import viewkit

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
    from sg.views import familyview
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
    from sg.views import familyview
    from sg.store import tree_store
    from sg.common.intervals import years
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
    from sg.readers import gedcom_io
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
    from sg.common import identity
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
    longest cM, segments, placement's branch, its split, bucket, range,
    vendor's tree link, other donors, relationship, path, the painting's
    branch, its split, entry]; G donor -> segments [match, chrom, start cM, end cM,
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
    from sg.common import intervals as iv
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
        (str(r["subject"]), str(r["platform"]), str(r["match_key"])): _branch(r) for r in cm_matches.to_dict("records")}
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
        place, split = _branch(r) if any(g in r for g in GPS) else (_s(r.get("placement")), "")
        rel, path = relate(d, lk[1][0]) if lk and relate and len(lk[1]) == 1 else ("", "")
        S.setdefault(d, []).append([idx[(p, k)], shared if shared is not None else a[0],
                                    longest if longest is not None else a[1], n.get((d, p, k), 0),
                                    place, split, _s(r.get("Matching Bucket")),
                                    _s(r.get("Relationship Range")), _s(r.get("Linked Relationship")),
                                    [x for x in who[(p, k)] if x != d], rel, path, *cmm.get((d, p, k), ("", "")), e])
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


GPS = ("FF", "FM", "MF", "MM")


def _branch(r):
    """(branch, split) of a per-match row with cM per grandparent: where the
    match's lines meet (match_placement.branch) and the shares, largest
    first ("FF 52 · FM 48"); ("", "") when nothing is placed."""
    from sg.genetics import match_placement as mp
    v = {g: float(r.get(g) or 0) for g in GPS if (r.get(g) or 0) == (r.get(g) or 0)}
    tot = sum(v.values())
    if not tot:
        return "", ""
    split = " · ".join(f"{g} {round(100 * x / tot)}" for g, x in sorted(v.items(), key=lambda t: -t[1]) if x > 0)
    return mp.branch(v), split


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
    path.write_text(viewkit.embed(HTML.replace("__NAV__", viewkit.nav("genome.html")), data), encoding="utf-8")


HTML = viewkit.template("genome")


def _main(argv):
    from sg.common import config
    from sg.views import familyview
    from sg.readers import gedcom_io
    from sg.common import intervals as iv
    from sg.common import outputs
    from sg.store import tree_store
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
    from sg.common import kits
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
    from sg.common import identity
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
