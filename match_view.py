"""
A match-centred chromosome browser and research report, as one HTML file.

    python3 match_view.py --entry q-some-question            # focus = entry's people
    python3 match_view.py --focus "Erik Example" --focus "Anna Example" --title "..."

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

Click a chromosome to enlarge it; hover a segment for details. Everything
is inside the file (no network); it names matches and positions, so it
stays in data/ (private) unless you decide otherwise.
"""
import argparse
import html
import json
import re
from pathlib import Path

import pandas as pd

import outputs

import config
import icw_io
import match_placement as mp

GRCH37 = [249250621, 243199373, 198022430, 191154276, 180915260, 171115067, 159138663, 146364022,
          141213431, 135534747, 135006516, 133851895, 115169878, 107349540, 102531392, 90354753,
          81195210, 78077248, 59128983, 63025520, 48129895, 51304566]
MIN_CM, MIN_OVERLAP, MAX_NEIGHBOURS = 7.0, 0.5, 12


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

    for line in text.splitlines():
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
    names = {k: config.display_name(cfg, k) for k in cfg["people"]}
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
                                   near=r.match))
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
    return data, totals, pd.DataFrame(graph_rows), links


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
<h1>__TITLE__</h1><div class="sub">__SUB__</div>
<h2>Totals per tester (cM)</h2>__TOTALS__
__LINKS__
<h2>Chromosome browser</h2>
<div class="legend" id="legend"></div>
<div><label><input type="checkbox" id="showN" checked> other matches on the same stretch</label>
<label><input type="checkbox" id="onlyFocus" checked> only chromosomes with a focus segment</label></div>
<div id="big"></div><div class="grid" id="grid"></div>
<h2>Focus segments and neighbours</h2>__SEGTABLE__
<h2>Shared matches (merged AutoCluster runs)</h2>__GRAPH__
<h2>Research notes</h2><div class="notes">__NOTES__</div>
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
    a = ap.parse_args()
    cfg = config.load()
    D = cfg["data_dir"]
    body, meta = "", {}
    if a.entry:
        import research_log
        meta, body = read_entry(research_log.DIR / f"{a.entry}.md")
    focus = a.focus or [p for p in meta.get("people", [])]
    title = a.title or meta.get("title") or ", ".join(focus)
    data, totals, graph, links = build(cfg, focus, title, body)
    found = sorted({f["m"] for f in data["focus"]})
    sub = (f"Focus: {', '.join(found) or '(no segments found)'} · generated from placed_segments.csv, the phased "
           f"painting and the AutoCluster runs · {pd.Timestamp.today().date()}")
    seg = pd.DataFrame(data["focus"] + [dict(n, near=n["near"]) for n in data["neigh"]])
    if len(seg):
        seg = seg.assign(Mb=lambda d: (d.s / 1e6).round(1).astype(str) + "–" + (d.e / 1e6).round(1).astype(str))
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
            .replace("__TOTALS__", table(totals.reset_index().rename(columns={"match": "match"})))
            .replace("__LINKS__", links_html).replace("__SEGTABLE__", table(seg))
            .replace("__GRAPH__", table(graph.sort_values("support", ascending=False) if len(graph) and "support" in graph and graph.support.astype(str).str.len().gt(0).all() else graph))
            .replace("__NOTES__", md_to_html(body) if body else "<p class='sub'>no entry given</p>")
            .replace("__DATA__", json.dumps(data, ensure_ascii=False)))
    out = Path(a.out) if a.out else D / f"report_{re.sub(r'[^a-z0-9]+', '_', title.lower())[:40]}.html"
    out.write_text(page, encoding="utf-8")
    print(f"{len(data['focus'])} focus segments, {len(data['neigh'])} neighbours -> {out}")


if __name__ == "__main__":
    main()
