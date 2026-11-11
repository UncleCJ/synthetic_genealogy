"""
The place-recognition rules, as a page: how a place string from the tree
or a citation becomes a parish, a village or a farm.

Two parts:

1. Generic rules: every normalisation, suffix and genitive rule, filter and
   lookup order the code applies, each with its source location, its
   pattern and examples evaluated live, so the page cannot drift from the
   code. Includes where volumes.py and gazetteer.py fold parish names
   differently.
2. This family's data: the hand rules that exist (parish aliases, place
   variants and jordnatur in the public gazetteer, the private plac_map and
   errata), and for every place string in the tree store which rule
   resolved it. That part is private and written only into data/output/.

The per-string trace is gazetteer.Gazetteer.explain_plac, which
resolve_plac itself runs, so the rule named is the rule that fired.

Not a source of truth: the code is. Sketch, unvalidated beyond the
agreement check.

    python3 places_rules.py                  # -> data/output/places_rules.html
    python3 places_rules.py trace Fuxerna    # how each matching place string and
                                             # citation is read, by both parsers
"""
import csv
import html
import inspect
import re
import sqlite3
import sys
import tomllib
from collections import Counter
from pathlib import Path

import gazetteer as gz
import places
import textfix
import volumes

ROOT = Path(__file__).resolve().parent


# -- tracing one place string -----------------------------------------------------

def parish_how(g, part):
    """(canonical parish or None, rule) for one comma-separated part."""
    return g.parish_rule(part)


def place_how(g, parish, written):
    """(place id or None, rule) as Gazetteer.place resolves it."""
    return g.place_rule(parish, written)


def explain_plac(g, plac):
    """(id, rule, parish rule, part used): Gazetteer.explain_plac, the
    resolver itself."""
    return g.explain_plac(plac)


# -- the generic part ---------------------------------------------------------------

def _where(obj):
    try:
        f = Path(inspect.getsourcefile(obj)).name
        return f"{f}:{inspect.getsourcelines(obj)[1]}"
    except (TypeError, OSError):
        return ""


def _doc(obj):
    d = inspect.getdoc(obj) or ""
    return d.split("\n\n")[0]


def _try(fn, *a):
    try:
        v = fn(*a)
    except Exception as e:                          # noqa: BLE001 - shown on the page
        return f"error: {type(e).__name__}: {e}"
    return repr(v) if not isinstance(v, str) else v


def _parish_key_gaz(s):
    return gz.fold(gz.PARISH_SUFFIX.sub("", (s or "").strip()))


def _parish_key_vol(s):
    return volumes._key(volumes.PLAC_SUFFIX.sub("", s or ""))


# (title, function or None, pattern objects, prose, examples as tuples of args)
GENERIC = [
    ("Repairing vendor text", textfix.fix, [textfix._MOJIBAKE, textfix._ENTITY, textfix._DIAERESIS],
     "Applied first, to every string: UTF-8 read as cp1252 (mojibake), HTML entities, "
     "a combining diaeresis or ring written as a separate character.",
     [("KÃ¤lleryd",), ("G&ouml;hestra",), ("Ka¨lleryd",)]),
    ("fold(): the comparison key", gz.fold, [],
     "Every lookup of a parish or place goes through it: lower case, spaces/underscores/"
     "hyphens as one space, w→v, q→k, ph→f, th→t, dt→t, ck→k, z→s, gd/g:d → gård, "
     "doubled letters single. å/ä/ö are kept.",
     [("Swenshult",), ("Qvatarp",), ("Bultagd",), ("Wäne-Ryr",), ("Hallanda",)]),
    ("modern(): the display spelling", gz.modern, [],
     "How a new gazetteer entry is named. The written forms are kept as variants.",
     [("Swenshult",), ("Ulfvestorp",), ("Qvatarp",), ("Vestergården",), ("Bultagd",)]),
    ("jordnatur(): tenure written beside a name", gz.jordnatur, [gz._JORDNATUR],
     "Skatte, krono, frälse (and mixed) before or after the name, optionally after 'Mantal', "
     "are split off and kept as an attribute. As a compound ('Skattegård') it stays part of the name.",
     [("Possarp Skatte",), ("Skatte Porssarp",), ("Mantal Elmtomta Södergård Frälse",), ("Skattegården",)]),
    ("unalias(): one name per string", gz.unalias, [gz._DESIGNATOR, gz._ELLER],
     "Of 'A eller B' the last is kept; a parish written in front is dropped; then jordnatur().",
     [("Duve eller Dårebo",), ("Gr. Landsförsaml. Björket",), ("Eller Kjellerö Högaberg",)]),
    ("parse(): levels (rote, farm, croft)", gz.parse, gz._ROTE + [gz._TORP, gz._UNDER, gz._TORP_ALONE],
     "A written name split into levels, outermost first; the innermost level is what a lookup "
     "falls back to.",
     [("Roten Ingarp Rote Swenshult",), ("Swenshult Torpet Swenstorp",), ("Moen under Askaremålen",),
      ("Ingarps rote",)]),
    ("rote_name()", gz.rote_name, [],
     "A rote's display name, with the genitive s added after a consonant.",
     [("Ingarp",), ("Ingarps",), ("Källerö",)]),
    ("generic() and parts of farms", gz.generic, [gz.GENERIC, gz.FARM_TYPE],
     "A part or kind of farm ('Sörgården', 'Torpet', 'Skattegård') names no place on its own: "
     "never resolved alone from a PLAC part, never split off as a place.",
     [("Sörgården",), ("Torpet",), ("Hagelstorp",)]),
    ("Filters when building from the tree", None, [gz.NONPLACE, gz.STREET],
     "gazetteer build skips names with digits, street words, non-places ('på socknen', 'okänd') and "
     "the parish itself; outside household-examination citations it takes PLAC parts before 1950 only.",
     []),
    ("ortho(): looser key, within one parish", gz.ortho, [gz.FILLER],
     "On top of fold(): e/ä, o/å/ö, kj/k, -gården/-gård, genitive s per word, joint d/t before "
     "-storp, silent h, filler words (hemman, byn, nr). Used by split_known and by automatic "
     "merging at build time; never across parishes.",
     [("Kjellshyltan",), ("Källshyltan",), ("Algudstorp",), ("Sundsdahlen",), ("Hemmanet Näs",)]),
    ("_loose(): second-tier key for merging", gz._loose, [gz._GARD_CUT],
     "On an ortho() key: cut-short gård written out, -stad as -sta, f as v, joint s/d between "
     "consonants dropped, å/o as a, unstressed e dropped.",
     [("valdshult",), ("valshult",), ("grimsas",), ("grimsås",)]),
    ("clear_variant(): same place, two spellings?", gz.clear_variant, [],
     "Automatic merges at build time: equal under ortho(), or close and equal without unstressed e, "
     "or close and equal under _loose(). Neighbour farms (Väster/Öster, Norra/Södra, Stora/Lilla, "
     "different farm kinds) never merge. Less clear pairs go to gazetteer_todo.md for a person.",
     [("Storegården", "Storgården"), ("Måleskog", "Målskog"), ("Tuggarp Västergård", "Tuggarp Östergård"),
      ("Valdshult", "Valshult")]),
    ("Parish lookup (gazetteer)", _parish_key_gaz, [gz.PARISH_SUFFIX],
     "Gazetteer.parish(): the folded string as a parish name or alias; else with the suffix "
     "below dropped; else with a final s dropped (genitive). The examples show the key looked up "
     "after the suffix is dropped.",
     [("Källeryds socken",), ("Gränna lf.",), ("Adelövs kyrkoförsamling",), ("Wäne-Ryrs församling",)]),
    ("Abbreviated parish names (Wikidata candidates)", places.expand, [],
     "places.py, only when asking Wikidata for candidate parishes: N./S./V./Ö./W. written out. "
     "Candidates, never answers ('W.' can be Väne- or Västra).",
     [("N. Ryr",), ("W. Ryr",)]),
]

ORDER = """\
<ol>
<li><b>plac_map</b> (private, hand-kept): the whole string, after textfix, as a key. Wins over everything.</li>
<li>Split on commas. The first part that is a parish (name, alias, suffix dropped, genitive s dropped) fixes the parish.</li>
<li>Parts before it, most specific first: two neighbouring parts joined ("Finnanäs, Norrgård" → "Finnanäs Norrgård"),
    then each part on its own, skipping generic parts. Each is tried as a place name or recorded variant (after fold()),
    as a variant without its jordnatur, by parse()'s innermost level, then as a known village + known place (split_known, with ortho()).</li>
<li>No place found: the parish alone.</li>
<li>No parish in the string: a part that names a place in exactly one parish ("unique village name").</li>
<li>Else unresolved. The tree store then tries a town or region already looked up by geocode.py (cache only).</li>
</ol>
<p>Citation rows (volumes.py) go through <code>Gazetteer.resolve(parish, farm)</code> first, with
plac_map keys "<i>raw string</i>" or "<i>Parish</i>: <i>farm</i>", then the whole PLAC string as above, and errata
(field <code>place_id</code>, <code>farm</code> or <code>parish</code>) last.</p>
"""

DIFFERENCES = """\
<p>volumes.py reads parish names before the gazetteer is consulted, with its own, plainer rules:</p>
<ul>
<li><b>Key:</b> <code>volumes._key</code> lower-cases and evens out spaces, hyphens and underscores only;
<code>gazetteer.fold</code> also folds w/v, q/k, ph/f, th/t, dt/t, ck/k, z/s, gd and doubled letters.
"Wäne-Ryr" and "Väne-Ryr" are one parish to the gazetteer, two to volumes.py.</li>
<li><b>Suffix:</b> <code>volumes.PLAC_SUFFIX</code> lacks "kyrkoförsamling", abbreviated "lands förs." and a
trailing full stop, which <code>gazetteer.PARISH_SUFFIX</code> drops.</li>
<li><b>Genitive:</b> <code>volumes.degenitive</code> drops a final s after a consonant from archive names
("Källeryds kyrkoarkiv") before anything else; it would cut a parish whose own name ends in consonant + s.
Both then try a final s dropped as a fallback.</li>
<li><b>Names known:</b> volumes.py only knows the parishes cited in the tree's records (plus <code>extra_parishes</code>);
the gazetteer knows its parishes.toml with aliases. volumes.run then puts each row's parish through
<code>Gazetteer.parish</code>, so the gazetteer's answer wins where it has one.</li>
</ul>
"""

LONG_S = """\
<p><b>Not in the code yet:</b> fixes for the long s (ſ) misread as f or p (roadmap: places). The candidate rules
(f→s before s/h/t giving a known name in the parish; edit distance against TORA or OSM names; ortho() fallback on
a unique hit) are unvalidated. Old f for v (Kalf-, Hof-) is left to hand renames, since a general rule would break
names like Rolf. Today such readings resolve only through a recorded variant or plac_map.</p>
"""


def _e(s):
    return html.escape(str(s if s is not None else ""))


def generic_html():
    out = ["<h2 id='generic'>1. Generic rules</h2>",
           "<p>Each rule as the code has it now; examples are computed when this page is written.</p>",
           "<h3>Lookup order for a place string</h3>", ORDER]
    for title, fn, pats, prose, examples in GENERIC:
        where = _where(gz.Gazetteer.parish if fn is _parish_key_gaz else fn) if fn else "gazetteer.py: build()"
        name = fn.__name__ if fn else ""
        out.append(f"<h3>{_e(title)} <span class='where'>{_e(where)}</span></h3><p>{_e(prose)}</p>")
        if fn and _doc(fn):
            out.append(f"<p class='doc'>{_e(_doc(fn))}</p>")
        for rx in pats:
            out.append(f"<pre>{_e(rx.pattern)}</pre>")
        if examples:
            rows = "".join(f"<tr><td>{_e(', '.join(map(repr, a)))}</td><td>{_e(_try(fn, *a))}</td></tr>"
                           for a in examples)
            out.append(f"<table class='ex'><tr><th>{_e(name)}(…)</th><th>result</th></tr>{rows}</table>")
    out.append("<h3>volumes.py and gazetteer.py fold parish names differently</h3>")
    out.append(DIFFERENCES)
    samples = ["Wäne-Ryr", "Väne-Ryr", "Källeryds socken", "Adelövs kyrkoförsamling", "Gränna lf.",
               "Gränna lands förs.", "Linderås", "Hallanda kyrka"]
    def diff(s):
        d = []
        if gz.PARISH_SUFFIX.sub("", s.strip()) != volumes.PLAC_SUFFIX.sub("", s):
            d.append("suffix dropped by the gazetteer only")
        single = lambda k: re.sub(r"([a-zåäö])\1+", r"\1", k)
        bare = volumes.PLAC_SUFFIX.sub("", s)
        if single(gz.fold(bare)) != single(volumes._key(bare).rstrip(".,")):
            d.append("spelling (w/v, q/k, ...) folded by the gazetteer only")
        return "; ".join(d)
    rows = "".join(f"<tr><td>{_e(s)}</td><td>{_e(_parish_key_gaz(s))}</td><td>{_e(_parish_key_vol(s))}</td>"
                   f"<td>{_e(diff(s))}</td></tr>" for s in samples)
    out.append("<p>Doubled letters fold on one side only, but each side compares within its own keys, so that "
               "alone changes nothing; the suffix and spelling folds do.</p>"
               "<table class='ex'><tr><th>PLAC part</th><th>gazetteer key</th><th>volumes key</th>"
               f"<th>what differs</th></tr>{rows}</table>")
    out.append(f"<pre>gazetteer.PARISH_SUFFIX  {_e(gz.PARISH_SUFFIX.pattern)}\n"
               f"volumes.PLAC_SUFFIX      {_e(volumes.PLAC_SUFFIX.pattern)}</pre>")
    out.append("<h3>Long s (ſ)</h3>" + LONG_S)
    return "\n".join(out)


# -- the data-specific part ---------------------------------------------------------

def _toml(path):
    p = Path(path)
    return tomllib.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def tree_places(store_path):
    """[(place string, events, how stored)] from the tree store, or []."""
    if not Path(store_path).exists():
        return []
    db = sqlite3.connect(store_path)
    try:
        return db.execute("select place, count(*), max(place_how) from event "
                          "where place <> '' group by place order by count(*) desc").fetchall()
    finally:
        db.close()


def data_html(g, cfg_paths):
    import errata as er
    out = ["<h2 id='data'>2. This family's rules and place strings</h2>"]

    al = [(n, a) for n, p in sorted(g.parishes.items()) for a in p.get("aliases", [])]
    out.append(f"<h3>Parish aliases (gazetteer/parishes.toml): {len(al)}</h3>")
    out.append("<table><tr><th>parish</th><th>alias</th></tr>"
               + "".join(f"<tr><td>{_e(n)}</td><td>{_e(a)}</td></tr>" for n, a in al) + "</table>")

    nv = sum(len(p.get("variants", [])) for p in g.places.values())
    jn = [(pid, p["jordnatur"]) for pid, p in sorted(g.places.items()) if p.get("jordnatur")]
    chk = sum(1 for p in g.places.values() if p.get("checked"))
    out.append(f"<h3>Places (gazetteer/places.toml)</h3><p>{len(g.places)} places, {nv} written variants, "
               f"{chk} checked by hand, {len(jn)} with jordnatur. Every variant resolves to its place after fold(); "
               "variants come from build (written forms, automatic merges) or by hand. "
               "<code>python3 gazetteer.py show NAME</code> lists one entry's variants.</p>")
    if jn:
        out.append("<table><tr><th>place</th><th>jordnatur</th></tr>"
                   + "".join(f"<tr><td>{_e(p)}</td><td>{_e(j)}</td></tr>" for p, j in jn) + "</table>")

    pm = _toml(cfg_paths["plac_map"])
    out.append(f"<h3>plac_map (private, hand-kept): {len(pm)}</h3>")
    out.append("<table><tr><th>string</th><th>place</th><th>note</th></tr>"
               + "".join(f"<tr><td>{_e(k)}</td><td>{_e(v.get('place'))}</td><td>{_e(v.get('note'))}</td></tr>"
                         for k, v in pm.items()) + "</table>")

    e = er.load(cfg_paths["errata"])
    fixes = [f for f in e["fix"] if f.get("field") in ("place_id", "farm", "parish")
             or str(f.get("key", "")).startswith(("place:", "plac:"))]
    notes = [n for n in e["note"] if str(n.get("key", "")).startswith(("place:", "plac:"))]
    out.append(f"<h3>Errata on places (private): {len(fixes)} fixes, {len(notes)} notes</h3>")
    if fixes or notes:
        out.append("<table><tr><th>key</th><th>field</th><th>was → now / note</th></tr>"
                   + "".join(f"<tr><td>{_e(f.get('key'))}</td><td>{_e(f.get('field'))}</td>"
                             f"<td>{_e(f.get('was'))} → {_e(f.get('now'))}</td></tr>" for f in fixes)
                   + "".join(f"<tr><td>{_e(n.get('key'))}</td><td>note</td><td>{_e(n.get('text'))}</td></tr>"
                             for n in notes) + "</table>")

    refs = cfg_paths["volume_refs"]
    if Path(refs).exists():
        with open(refs, encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
        c = Counter((r.get("place_from") or ("no farm" if not r.get("farm") else "unresolved")) for r in rows)
        out.append(f"<h3>Citation rows (volume_refs.csv): {len(rows)}</h3><table><tr><th>resolved by</th><th>rows</th></tr>"
                   + "".join(f"<tr><td>{_e(k)}</td><td>{v}</td></tr>" for k, v in c.most_common()) + "</table>")

    tp = tree_places(cfg_paths["store"])
    if not tp:
        out.append("<p>No tree store yet (<code>python3 tree_store.py</code>); place strings not traced.</p>")
        return "\n".join(out)
    traced, mismatch = [], []
    for text, n, stored in tp:
        pid, rule, prule, used = explain_plac(g, text)
        want = g.resolve_plac(text)[0]
        if pid != want:
            mismatch.append((text, pid, want))
        traced.append((text, n, pid, rule, prule, used, stored))
    by_rule = Counter()
    for t in traced:
        by_rule[t[3]] += t[1]
    nstr = Counter(t[3] for t in traced)
    out.append(f"<h3>Place strings in the tree: {len(traced)} distinct, {sum(t[1] for t in traced)} events</h3>")
    out.append("<p>Event places (PLAC) in the tree store, traced through the lookup order above. "
               "'stored' is what the store recorded at import (tree_store.py import-places), which also "
               "uses towns from geocode.py's cache; address-only residences are not listed.</p>")
    out.append("<table><tr><th>rule</th><th>strings</th><th>events</th></tr>"
               + "".join(f"<tr><td>{_e(k)}</td><td>{nstr[k]}</td><td>{v}</td></tr>" for k, v in by_rule.most_common())
               + "</table>")
    if mismatch:
        out.append(f"<p class='warn'>{len(mismatch)} strings where this trace and resolve_plac disagree "
                   "(the page is behind the code):</p><table><tr><th>string</th><th>trace</th><th>resolve_plac</th></tr>"
                   + "".join(f"<tr><td>{_e(a)}</td><td>{_e(b)}</td><td>{_e(c)}</td></tr>" for a, b, c in mismatch)
                   + "</table>")
    else:
        out.append("<p>The trace agrees with resolve_plac on every string.</p>")
    opts = "".join(f"<option>{_e(k)}</option>" for k in sorted(nstr))
    out.append(f"<p>Filter: <select id='rule'><option value=''>all rules</option>{opts}</select> "
               "<input id='q' placeholder='text in string or place'></p>")
    out.append("<table id='strings'><tr><th>place string</th><th>events</th><th>resolved to</th><th>rule</th>"
               "<th>parish by</th><th>part used</th><th>stored</th></tr>"
               + "".join(f"<tr data-rule='{_e(r)}'><td>{_e(t)}</td><td>{n}</td><td>{_e(pid)}</td><td>{_e(r)}</td>"
                         f"<td>{_e(pr)}</td><td>{_e(u)}</td><td>{_e(s)}</td></tr>"
                         for t, n, pid, r, pr, u, s in traced) + "</table>")
    return "\n".join(out)


PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Place recognition rules</title>
<style>
body{{font:14px/1.45 system-ui,sans-serif;max-width:1100px;margin:0 auto;padding:0 16px 40px;color:#222;background:#fff}}
h2{{border-bottom:1px solid #ccc;margin-top:2em}} h3{{margin:1.6em 0 .3em}}
.where{{font:12px ui-monospace,monospace;color:#777;font-weight:normal}}
.doc{{color:#555;font-style:italic;white-space:pre-line}}
pre{{background:#f5f5f5;padding:6px 8px;overflow-x:auto;font-size:12px;white-space:pre-wrap;word-break:break-all}}
table{{border-collapse:collapse;margin:.4em 0;font-size:13px}} td,th{{border:1px solid #ddd;padding:2px 6px;text-align:left;vertical-align:top}}
th{{background:#f0f0f0}} .warn{{color:#a00}} nav a{{margin-right:1em}}
@media (prefers-color-scheme: dark){{body{{background:#1b1b1b;color:#ddd}} pre,th{{background:#2a2a2a}} td,th{{border-color:#444}}
.doc,.where{{color:#aaa}}}}
</style></head><body>
<h1>Place recognition rules</h1>
<p>How a place string from the tree or a citation becomes a parish, village or farm
(<code>gazetteer.py</code>, <code>volumes.py</code>, <code>places.py</code>, <code>textfix.py</code>).
Written by <code>places_rules.py</code>; the code is the source of truth.</p>
<nav><a href="#generic">Generic rules</a><a href="#data">This family's rules and strings</a></nav>
{generic}
{data}
<script>
const sel=document.getElementById('rule'), q=document.getElementById('q');
function f(){{ if(!sel) return; const r=sel.value, t=q.value.toLowerCase();
  document.querySelectorAll('#strings tr[data-rule]').forEach(tr=>{{
    tr.style.display=((!r||tr.dataset.rule===r)&&(!t||tr.textContent.toLowerCase().includes(t)))?'':'none';}});}}
if(sel){{sel.onchange=f; q.oninput=f;}}
</script>
</body></html>
"""


def write(cfg, out=None):
    import config
    g = gz.load(cfg)
    paths = dict(plac_map=config.path(cfg, "plac_map.toml"), errata=config.path(cfg, "errata.toml"),
                 volume_refs=config.path(cfg, "volume_refs.csv"), store=config.path(cfg, "tree.sqlite"))
    out = Path(out or config.path(cfg, "places_rules.html"))
    out.write_text(PAGE.format(generic=generic_html(), data=data_html(g, paths)), encoding="utf-8")
    return out


def trace(cfg, pattern, out=print):
    """Every place string and citation matching `pattern` (a regex over
    the place string, farm, parish, volume and MyHeritage label), each as
    the two parsers read it: volumes.normalise (parish, farm, detail for
    the archives and geography views) and Gazetteer.explain_plac (the place id
    the map and the store use), with the coordinates' level. One line per
    distinct reading, with a count; offline (caches only)."""
    import volumes
    rx = re.compile(pattern, re.I)
    g = gz.load(cfg)
    rows, _, _ = volumes.run(cfg, riksarkivet_lookups=False, gazetteer=g)
    seen = Counter()
    keep = {}
    for r in rows:
        hay = " | ".join(str(r.get(k) or "") for k in ("event_place", "farm", "parish", "volume",
                                                        "mh_label", "place_id"))
        if r.get("tier") == "tree" or not rx.search(hay):
            continue
        if r.get("tier") == "plac-only":
            pid, rule, prule, used = g.explain_plac(r.get("event_place"))
            key = ("place", r.get("event_place"), r.get("parish"), r.get("farm"),
                   r.get("plac_detail"), r.get("place_id"), r.get("place_from"), pid, rule, prule,
                   r.get("cited_as") or "")
        else:
            key = ("citation", r.get("tier"), "", r.get("parish"),
                   r.get("volume"), r.get("years"), r.get("page"), r.get("farm"), r.get("place_id"),
                   r.get("place_from"), r.get("ra_code") or "")
            keep.setdefault(key, r.get("mh_label") or r.get("url") or "")
        seen[key] += 1
    if not seen:
        out(f"nothing matches {pattern!r}")
    for key, n in sorted(seen.items(), key=lambda kv: (kv[0][0], -kv[1], str(kv[0]))):
        if key[0] == "place":
            _, text, par, farm, det, vpid, vhow, pid, rule, prule, cited = key
            c = g.coords(pid) if pid else None
            out(f"{n:4}x place  {text!r}")
            out(f"        parts      {gz.plac_parts(text)}")
            out(f"        volumes    parish={par or '-'} farm={farm or '-'}"
                + (f" detail={det}" if det else "")
                + (f" -> {vpid} ({vhow})" if vpid else " -> no place"))
            out(f"        gazetteer  {pid or '-'} [{rule}{'; ' + prule if prule else ''}]"
                + (f" at {c[2]} level" if c else " (no coordinates)" if pid else ""))
            if cited:
                out(f"        cited as   {cited} (the person's record citation)")
            if (vpid or None) != (pid if pid and not pid.startswith("parish:") else None):
                out("        ! the two readings differ")
        else:
            _, tier, _, par, vol, years, page, farm, vpid, vhow, code = key
            label = keep.get(key, "")
            out(f"{n:4}x {tier:9} {label[:150]!r}" + (" (one of them)" if n > 1 else ""))
            out(f"        read as    parish={par or '-'} volume={vol or '-'} years={years or '-'} "
                f"page={page or '-'} farm={farm or '-'}" + (f" code={code}" if code else ""))
            out(f"        place      {vpid or '-'}" + (f" ({vhow})" if vhow else ""))
            if tier == "mh-record" and not par:
                out("        ! a volume label without a parish")
            if tier == "mh-index" and label:
                out("        ! a volume label the pattern did not read")


def _main(argv):
    import config
    cfg = config.load()
    if argv and argv[0] == "trace":
        if len(argv) < 2:
            raise SystemExit("usage: places_rules.py trace <regex>")
        trace(cfg, " ".join(argv[1:]))
        return
    out = write(cfg)
    print(f"place rules -> {out}")


if __name__ == "__main__":
    _main(sys.argv[1:])
