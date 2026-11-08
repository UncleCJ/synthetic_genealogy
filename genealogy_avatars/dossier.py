"""A pedigree page from the GEDCOM: avatar, facts and source links for each ancestor.

    python -m genealogy_avatars.dossier tree.ged @I0003@ [generations]   -> avatars/pedigree.html
"""
from __future__ import annotations
import html, sys
from pathlib import Path
from . import gedcom
from .procedural import render

KINDS = [  # (label, test) for sorting citation links into photo/record leads
    ("MyHeritage profile (photo lead)", lambda u: "/person-" in u),
    ("Church-book scan (Riksarkivet)", lambda u: "riksarkivet.se" in u),
    ("ArkivDigital", lambda u: "arkivdigital" in u),
    ("MyHeritage record", lambda u: "myheritage" in u and "/research/" in u),
    ("Other link", lambda u: u.startswith("http")),
]
ROLE = {1: "You", 2: "Father", 3: "Mother"}


def _role(n: int) -> str:
    if n in ROLE:
        return ROLE[n]
    gen, side = n.bit_length() - 1, ""
    first = n >> (gen - 1)                       # 2 = father's side, 3 = mother's side
    side = "paternal" if first == 2 else "maternal"
    base = "grandfather" if n % 2 == 0 else "grandmother"
    return f"{'great-' * (gen - 2)}{base} ({side})".capitalize()


def _links(p: gedcom.Indi) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for c in p.citations:
        for u in [c["page"]] + gedcom.MH_PROFILE.findall(c["text"]):
            u = u.strip()
            for label, test in KINDS:
                if test(u):
                    if u not in out.setdefault(label, []):
                        out[label].append(u)
                    break
    return out


def _card(n: int, p: gedcom.Indi | None) -> str:
    if p is None:
        return f'<div class="card empty"><div class="role">{_role(n)}</div><div class="who">not in tree</div></div>'
    years = f'{p.birth_year or "?"}–{p.death_year or ("" if p.possibly_living() else "?")}'
    given = " ".join(f"<u>{html.escape(w)}</u>" if w.strip("()\"") == p.callname else html.escape(w)
                     for w in p.given.split())
    facts = []
    if p.birth_date: facts.append(f"Born {html.escape(p.birth_date)}" + (f", {html.escape(p.birth_place)}" if p.birth_place else ""))
    if p.death_date and p.death_date != "dead":
        facts.append(f"Died {html.escape(p.death_date)}" + (f", {html.escape(p.death_place)}" if p.death_place else "")
                     + (f" ({html.escape(p.death_cause)})" if p.death_cause else ""))
    if p.occupations: facts.append("Occupation: " + html.escape(", ".join(dict.fromkeys(p.occupations))))
    homes = [pl for _, pl in p.residences if pl]
    if homes: facts.append(f"Lived at {len(set(homes))} places, e.g. " + html.escape(homes[0]))
    for note in p.notes[:2]: facts.append("Note: " + html.escape(note[:300]))
    records = [c["text"] for c in p.citations if len(c["text"]) > 80 and "Smart Match" not in c["text"]]
    if records:   # longest transcription first: usually a household record listing family members
        rec = max(records, key=len)
        rec = "\n".join(l.strip() for l in rec.splitlines() if l.strip() and "http" not in l)[:600]
        facts.append(f'From the records ({len(records)} transcriptions):<pre>{html.escape(rec)}</pre>')
    links = "".join(
        f"<li>{label}: " + " ".join(f'<a href="{html.escape(u)}" target="_blank" rel="noopener">{k + 1}</a>'
                                   for k, u in enumerate(us[:8])) + (f" (+{len(us) - 8})" if len(us) > 8 else "") + "</li>"
        for label, us in _links(p).items())
    return f"""<details class="card">
<summary>{render(p.to_person(), size=64)}<div><div class="role">{_role(n)}</div>
<div class="who">{given} <b>{html.escape(p.surname)}</b></div><div class="yrs">{years} · MyHeritage {p.mh_id}</div></div></summary>
<ul class="facts">{''.join(f'<li>{f}</li>' for f in facts)}</ul>
{f'<div class="src">Sources and photo leads</div><ul class="links">{links}</ul>' if links else ''}
</details>"""


def build(indis: dict[str, gedcom.Indi], root: str, generations: int = 4) -> str:
    anc = gedcom.ancestors(indis, root, generations)
    cols = []
    for g in range(generations):
        cells = "".join(
            f'<div class="cell" style="grid-row: span {2 ** (generations - 1 - g)}">{_card(n, indis.get(anc.get(n) or ""))}</div>'
            for n in range(2 ** g, 2 ** (g + 1)))
        cols.append(f'<div class="col" style="grid-template-rows: repeat({2 ** (generations - 1)}, auto)">{cells}</div>')
    me = indis[root]
    return f"""<!doctype html><html lang="sv"><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Pedigree · {html.escape(me.display)}</title>
<style>
:root{{--bg:#f7f4ee;--card:#fffdf9;--ink:#2a2622;--mute:#7a7066;--line:#e3dccf;--acc:#9a6b2f;color-scheme:light}}
@media (prefers-color-scheme:dark){{:root{{--bg:#1c1a17;--card:#262320;--ink:#ece6dc;--mute:#a59b8f;--line:#3a352f;--acc:#d9a35c;color-scheme:dark}}}}
body{{margin:0;padding:1.5rem;background:var(--bg);color:var(--ink);font:14px/1.45 Georgia,"Iowan Old Style",serif}}
h1{{font-weight:normal;margin:0 0 .2rem}} p.lede{{color:var(--mute);margin:0 0 1.2rem;font-family:system-ui,sans-serif;font-size:13px}}
.tree{{display:grid;grid-template-columns:repeat({generations},minmax(230px,1fr));gap:.8rem;overflow-x:auto}}
.col{{display:grid;gap:.5rem}} .cell{{display:flex;align-items:center}}
.card{{width:100%;background:var(--card);border:1px solid var(--line);border-radius:10px;padding:.45rem .6rem}}
.card summary{{display:flex;gap:.6rem;align-items:center;cursor:pointer;list-style:none}}
.card summary::-webkit-details-marker{{display:none}} .card svg{{flex:none;border-radius:6px}}
.role{{font:11px system-ui,sans-serif;text-transform:uppercase;letter-spacing:.06em;color:var(--acc)}}
.who u{{text-decoration-color:var(--acc);text-underline-offset:3px}} .yrs{{color:var(--mute);font-size:12px}}
.empty{{opacity:.5}} .facts,.links{{margin:.5rem 0 0;padding-left:1.1rem;font-size:12.5px}}
.src{{margin-top:.5rem;font:11px system-ui,sans-serif;text-transform:uppercase;color:var(--mute)}}
a{{color:var(--acc)}} pre{{white-space:pre-wrap;font:11.5px/1.4 ui-monospace,monospace;color:var(--mute);margin:.3rem 0 0}}
</style>
<h1>{html.escape(me.display)}’s ancestors</h1>
<p class="lede">Placeholder avatars styled by era (colour cartoon, black-and-white snapshot, sepia card, painted oval).
Underlined first name = the name they went by. Click a card for facts, record transcriptions and photo leads.</p>
<div class="tree">{''.join(cols)}</div></html>"""


if __name__ == "__main__":
    ged, root = sys.argv[1], sys.argv[2]
    gens = int(sys.argv[3]) if len(sys.argv) > 3 else 4
    indis, _ = gedcom.load(ged)
    Path("avatars").mkdir(exist_ok=True)
    Path("avatars/pedigree.html").write_text(build(indis, root, gens), encoding="utf-8")
    print("-> avatars/pedigree.html")
