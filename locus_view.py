"""
Segment-locus view: everyone in the family who shares DNA at one place on
one chromosome, with whom, and on which copy. One self-contained HTML file.

    python3 locus_view.py --at 2:236           # chromosome 2 at 236 Mb
    python3 locus_view.py --at 15:75 --window 30 --min-cm 10 --out data/locus.html

For each tester (siblings and the mother):

- which grandparent's copy each sibling carries there (phased painting);
- every segment overlapping the window, packed into rows under the copy it
  lies on (paternal, maternal, or "side unknown"), coloured by grandparent;
- segments a match shares with two or more siblings with nearly the same
  ends (Jaccard ≥ 0.9) are outlined: those siblings carry the same copy;
- shared-match links (merged AutoCluster graph) between matches present at
  the locus: a segment overlap plus a shared-match link is triangulation;
- density: segments covering the locus against the genome-wide median per
  tester; a high ratio is a pile-up (shared because the haplotype is
  common, not because of a recent ancestor).

A table lists the matches at the locus with testers, cM, copies, platform
and linked tree persons. Private (it names matches): written to data/.
"""
import argparse
import html
import json
import re
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

import config
import icw_io
import match_placement as mp
from match_view import GRCH37


def density(segs, chrom, pos):
    """Segments covering `pos` per tester, and the tester's median over a
    1 Mb grid of the autosomes (same platforms)."""
    out = {}
    for t, g in segs.groupby("subject"):
        at = int(((g.chrom == chrom) & (g.start <= pos) & (g.end >= pos)).sum())
        counts = []
        for c, gc in g.groupby("chrom"):
            n = GRCH37[int(c) - 1] // 1_000_000
            cov = np.zeros(n + 1, int)
            for s, e in zip(gc.start // 1_000_000, gc.end // 1_000_000):
                cov[int(s):int(e) + 1] += 1
            counts.append(cov)
        med = float(np.median(np.concatenate(counts))) if counts else 0
        out[t] = (at, med)
    return out


def build(cfg, chrom, pos, window, min_cm):
    D = cfg["data_dir"]
    testers = cfg["children"] + [cfg["mother"]]
    segs = pd.read_csv(D / "placed_segments.csv", low_memory=False, dtype={"chrom": str})
    segs = segs[segs.chrom.isin([str(c) for c in range(1, 23)]) & segs.subject.isin(testers)]
    lo, hi = pos - window / 2, pos + window / 2
    w = segs[(segs.chrom == chrom) & (segs.end >= lo) & (segs.start <= hi) & (segs.cM >= min_cm)].copy()
    w["nk"] = w.match.map(icw_io.name_key)
    # sibling-shared, end to end
    shared = set()
    for (plat, key), g in w[w.subject.isin(cfg["children"])].groupby(["platform", "match_key"]):
        r = g.to_dict("records")
        for i in range(len(r)):
            for j in range(i + 1, len(r)):
                a, b = r[i], r[j]
                if a["subject"] == b["subject"]:
                    continue
                inter = min(a["end"], b["end"]) - max(a["start"], b["start"])
                union = max(a["end"], b["end"]) - min(a["start"], b["start"])
                if inter > 0 and inter / union >= 0.9:
                    shared |= {(a["subject"], plat, key, a["start"]), (b["subject"], plat, key, b["start"])}
    rows = []
    for r in w.itertuples():
        p = r.parent if isinstance(r.parent, str) else ""
        g = r.grandparent if isinstance(r.grandparent, str) else ""
        rows.append(dict(t=r.subject, m=r.match, k=r.nk, s=int(r.start), e=int(r.end), cm=round(r.cM, 1),
                         p=p, g=g, ip=r.if_paternal if isinstance(r.if_paternal, str) else "",
                         im=r.if_maternal if isinstance(r.if_maternal, str) else "",
                         why=r.parent_reason if isinstance(r.parent_reason, str) else "", src=r.platform,
                         sib=(r.subject, r.platform, r.match_key, r.start) in shared,
                         at=bool(r.start <= pos <= r.end)))
    paint = mp.load_painting(D)
    paint = paint[(paint.chrom.astype(str) == chrom) & (paint.end >= lo) & (paint.start <= hi)]
    # shared-match links among matches at the locus
    links = []
    present = {x["k"] for x in rows}
    try:
        import match_graph
        G, *_ = match_graph.build(cfg)
        nodes = {icw_io.name_key(d["label"]): k for k, d in G.nodes(data=True) if d.get("kind") == "match"}
        here = {nk: nodes[nk] for nk in present if nk in nodes}
        inv = {v: k for k, v in here.items()}
        for nk, k in here.items():
            for v, e in G[k].items():
                if e.get("kind") == "shared match" and v in inv and nk < inv[v]:
                    links.append(dict(a=nk, b=inv[v], support=e["support"], runs=f'{e["reported"]}/{e["observable"]}'))
    except Exception:
        pass
    dens = density(segs, chrom, pos)
    ident = {icw_io.name_key(x["match"]): x["tree"] for x in cfg.get("identity", [])}
    names = {k: config.display_name(cfg, k) for k in cfg["people"]}
    data = dict(chrom=chrom, pos=pos, lo=lo, hi=hi, testers=testers, children=cfg["children"],
                mother=cfg["mother"], names=names, segs=rows,
                paint=[dict(t=r.subject, p=r.parent, s=int(r.start), e=int(r.end), g=r.lineage) for r in paint.itertuples()],
                links=links, density={t: dict(at=a, med=m) for t, (a, m) in dens.items()},
                grandparents=cfg.get("grandparents", {}))
    # table: one row per match
    tab = defaultdict(lambda: dict(testers=set(), cM={}, copies=set(), platforms=set(), sib=False, at=False))
    for x in rows:
        d = tab[x["m"]]
        d["testers"].add(names.get(x["t"], x["t"]))
        d["cM"][names.get(x["t"], x["t"])] = max(d["cM"].get(names.get(x["t"], x["t"]), 0), x["cm"])
        d["copies"].add(x["g"] or (f"? (F:{x['ip'] or '–'} / M:{x['im'] or '–'})" if x["t"] != cfg["mother"] else "mother"))
        d["platforms"].add(x["src"]); d["sib"] |= x["sib"]; d["at"] |= x["at"]
    linked_to = defaultdict(int)
    for l in links:
        linked_to[l["a"]] += 1; linked_to[l["b"]] += 1
    table = pd.DataFrame([dict(match=m, covers_locus="yes" if d["at"] else "", testers=", ".join(sorted(d["testers"])),
                               cM=", ".join(f"{k} {v:g}" for k, v in sorted(d["cM"].items())),
                               copy=", ".join(sorted(d["copies"])), sibling_shared="yes" if d["sib"] else "",
                               shared_match_links=linked_to.get(icw_io.name_key(m), "") or "",
                               tree=ident.get(icw_io.name_key(m), ""), platform=", ".join(sorted(d["platforms"])))
                          for m, d in tab.items()])
    if len(table):
        table = table.sort_values(["covers_locus", "sibling_shared", "match"], ascending=[False, False, True])
    return data, table


PAGE = r"""<!doctype html><html lang="sv"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>__TITLE__</title>
<style>
:root{--bg:#fbfaf7;--fg:#1d1d1b;--muted:#6b6a64;--line:#d9d6cc;--panel:#fff;
--FF:#2b6cb0;--FM:#2f855a;--MF:#c05621;--MM:#805ad5;--none:#b8b5ab;--hot:#c53030}
@media (prefers-color-scheme:dark){:root{--bg:#161614;--fg:#ecebe6;--muted:#a3a198;--line:#3a3934;--panel:#1f1f1c;
--FF:#63a4e8;--FM:#5fbf8a;--MF:#ef8a4f;--MM:#a98af0;--none:#5b5a54;--hot:#f56565}}
body{margin:0;background:var(--bg);color:var(--fg);font:14px/1.45 system-ui,-apple-system,Segoe UI,sans-serif}
main{max-width:1180px;margin:0 auto;padding:20px 16px 60px}h1{font-size:21px;margin:0 0 4px}
h2{font-size:16px;margin:26px 0 8px}.sub{color:var(--muted)}
.panel{background:var(--panel);border:1px solid var(--line);border-radius:6px;padding:8px 10px;margin:8px 0;overflow-x:auto}
.legend span{display:inline-flex;align-items:center;margin-right:14px;font-size:12px;color:var(--muted)}
.legend i{display:inline-block;width:14px;height:10px;margin-right:5px;border-radius:2px}
table{border-collapse:collapse;font-size:13px}th,td{border-bottom:1px solid var(--line);padding:3px 8px;text-align:left}
th{color:var(--muted);font-weight:600}svg text{fill:var(--muted);font-size:10px}
#tip{position:fixed;pointer-events:none;background:var(--panel);border:1px solid var(--line);border-radius:5px;
padding:6px 8px;font-size:12px;display:none;max-width:340px;box-shadow:0 2px 8px rgba(0,0,0,.15);z-index:9}
.dens b.hot{color:var(--hot)}label{font-size:13px;color:var(--muted);margin-right:14px}
</style></head><body><main>
<h1>__TITLE__</h1><div class="sub">__SUB__</div>
<div class="panel dens" id="dens"></div>
<div class="legend" id="legend"></div>
<div><label><input type="checkbox" id="links" checked> shared-match links between matches at the locus</label>
<label><input type="checkbox" id="onlyAt"> only segments covering the locus</label></div>
<div id="tracks"></div>
<h2>Matches in the window</h2>__TABLE__
</main><div id="tip"></div>
<script>
const D=__DATA__;
const css=k=>getComputedStyle(document.documentElement).getPropertyValue('--'+(k||'none')).trim()||'#999';
const leg=document.getElementById('legend');
for(const g of ["FF","FM","MF","MM"])leg.innerHTML+=`<span><i style="background:${css(g)}"></i>${g} ${D.grandparents[g]||''}</span>`;
leg.innerHTML+=`<span><i style="background:${css('none')}"></i>not placed</span><span><i style="border:2px solid var(--fg)"></i>shared end to end with another sibling</span><span><i style="border-left:2px solid var(--hot)"></i>the locus</span>`;
const dens=document.getElementById('dens');
dens.innerHTML="Segments covering the locus (genome median per 1 Mb): "+D.testers.map(t=>{const d=D.density[t]||{at:0,med:0};const r=d.med?d.at/d.med:0;
  return `${D.names[t]||t} <b class="${r>=3?'hot':''}">${d.at}</b> (${d.med.toFixed(1)}${r>=3?', ×'+r.toFixed(1)+' — pile-up?':''})`}).join(' · ');
const tip=document.getElementById('tip');
document.addEventListener('mousemove',e=>{const t=e.target.closest&&e.target.closest('[data-tip]');
  if(t){tip.innerHTML=decodeURIComponent(t.dataset.tip);tip.style.display='block';tip.style.left=Math.min(e.clientX+12,innerWidth-350)+'px';tip.style.top=(e.clientY+12)+'px'}else tip.style.display='none'});
function pack(segs){const rows=[];for(const s of segs.sort((a,b)=>a.s-b.s)){let r=rows.findIndex(end=>end<s.s);if(r<0){r=rows.length;rows.push(0)}rows[r]=s.e;s.row=r}return rows.length}
function render(){
  const W=Math.min(1140,innerWidth-40),X=v=>90+(W-100)*(Math.min(Math.max(v,D.lo),D.hi)-D.lo)/(D.hi-D.lo);
  const onlyAt=document.getElementById('onlyAt').checked,showL=document.getElementById('links').checked;
  let out='';const ypos={};
  for(const t of D.testers){
    const isMum=t===D.mother;
    const groups=isMum?[["mother's segments",x=>true]]:[["paternal copy",x=>x.p==='F'],["maternal copy",x=>x.p==='M'],["side unknown",x=>!x.p]];
    let y=18,s='';
    if(!isMum){["F","M"].forEach((p,k)=>{s+=`<text x="0" y="${y+8}">${p==='F'?'carries (F)':'carries (M)'}</text>`;
      for(const b of D.paint.filter(b=>b.t===t&&b.p===p))s+=`<rect x="${X(b.s)}" y="${y}" width="${Math.max(1,X(b.e)-X(b.s))}" height="9" fill="${css(b.g)}" opacity=".55" data-tip="${encodeURIComponent(`${D.names[t]}'s ${p==='F'?'paternal':'maternal'} copy here: ${b.g}`)}"/>`;
      y+=12});y+=6}
    for(const [label,f] of groups){
      const segs=D.segs.filter(x=>x.t===t&&f(x)&&(!onlyAt||x.at));if(!segs.length)continue;
      const n=pack(segs);s+=`<text x="0" y="${y+8}">${label}</text>`;
      for(const x of segs){const yy=y+x.row*9;ypos[t+'|'+x.k]=ypos[t+'|'+x.k]||[];ypos[t+'|'+x.k].push([X((x.s+x.e)/2),yy+3]);
        const g=x.g||(t===D.mother?'':'');
        s+=`<rect x="${X(x.s)}" y="${yy}" width="${Math.max(2,X(x.e)-X(x.s))}" height="7" rx="1" fill="${css(x.g||'none')}" ${x.sib?'stroke="var(--fg)" stroke-width="1.4"':''} data-tip="${encodeURIComponent(`<b>${x.m}</b> · ${D.names[t]}<br>${(x.s/1e6).toFixed(2)}–${(x.e/1e6).toFixed(2)} Mb · ${x.cm} cM · ${x.src}<br>${x.p?`parent ${x.p} → ${x.g||'?'}`:(t===D.mother?(x.g?'mother: '+x.g:''):`side unknown: if F ${x.ip||'?'}, if M ${x.im||'?'}`)}${x.sib?'<br>shared end to end with another sibling':''}<br><span style="color:var(--muted)">${x.why}</span>`)}"/>`}
      y+=n*9+10}
    const H=y+8;
    let svg=`<svg width="${W}" height="${H}">${s}<line x1="${X(D.pos)}" x2="${X(D.pos)}" y1="0" y2="${H}" stroke="var(--hot)" stroke-width="1.5"/>`;
    if(showL){for(const l of D.links){const A=(ypos[t+'|'+l.a]||[])[0],B=(ypos[t+'|'+l.b]||[])[0];
      if(A&&B)svg+=`<path d="M${A[0]},${A[1]} Q${(A[0]+B[0])/2},${Math.min(A[1],B[1])-14} ${B[0]},${B[1]}" fill="none" stroke="var(--fg)" stroke-opacity="${.15+.5*l.support}" data-tip="${encodeURIComponent(`shared-match link: ${l.a} — ${l.b}<br>support ${l.support} (${l.runs} runs)`)}"/>`}}
    for(let mb=Math.ceil(D.lo/1e6/5)*5;mb<=D.hi/1e6;mb+=5)svg+=`<text x="${X(mb*1e6)}" y="10">${mb}</text>`;
    out+=`<div class="panel"><b>${D.names[t]||t}</b>${svg}</svg></div>`}
  document.getElementById('tracks').innerHTML=out}
document.getElementById('links').onchange=render;document.getElementById('onlyAt').onchange=render;render();addEventListener('resize',render);
</script></body></html>"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--at", required=True, help="chrom:Mb, e.g. 2:236")
    ap.add_argument("--window", type=float, default=20, help="Mb")
    ap.add_argument("--min-cm", type=float, default=7)
    ap.add_argument("--out")
    a = ap.parse_args()
    chrom, mb = a.at.split(":")
    cfg = config.load()
    data, table = build(cfg, chrom, float(mb) * 1e6, a.window * 1e6, a.min_cm)
    title = f"chr {chrom} at {float(mb):g} Mb (±{a.window / 2:g} Mb, segments ≥ {a.min_cm:g} cM)"
    sub = (f"{len(data['segs'])} segments, {table.match.nunique() if len(table) else 0} matches, "
           f"{len(data['links'])} shared-match links · placed_segments.csv, phased painting, AutoCluster graph · "
           f"{pd.Timestamp.today().date()}")
    page = (PAGE.replace("__TITLE__", html.escape(title)).replace("__SUB__", html.escape(sub))
            .replace("__TABLE__", table.to_html(index=False, border=0, na_rep="") if len(table) else "<p>none</p>")
            .replace("__DATA__", json.dumps(data, ensure_ascii=False)))
    out = Path(a.out) if a.out else cfg["data_dir"] / f"locus_chr{chrom}_{float(mb):g}Mb.html"
    out.write_text(page, encoding="utf-8")
    print(f"{len(data['segs'])} segments, {len(data['links'])} links, density "
          + ", ".join(f"{t} {d['at']}/{d['med']:.1f}" for t, d in data["density"].items()) + f" -> {out}")


if __name__ == "__main__":
    main()
