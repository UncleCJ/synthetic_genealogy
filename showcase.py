"""
Public screenshots of the private views (geography, archives), with
the people pseudonymised and the places left as they are.

    python3 showcase.py                 # pseudonymised copies in data/output/showcase/
                                        # and docs/img/painting.png (matplotlib)
    python3 showcase.py shots           # ... and PNGs in docs/img/ (headless Chrome,
                                        #     serve.py must be running: --port N)

Who is kept: ancestors from the great-grandparents back (lineage code of
three or more letters), born before 1900 (with no birth year: from the
great-great-grandparents back). Everyone else (the proband,
parents, grandparents, relatives, spouses of relatives) is dropped with all
their rows. A kept ancestor is named by Ahnentafel number and lineage code
only ("No. 23 · FMMM (1801–1869)"); MyHeritage ids and links, raw notes and
errata go. Place strings, parishes, volumes, pages and Riksarkivet links stay:
they are public archive facts about people dead for a century or more.

The copies are written into data/output/showcase/ (git-ignored): only the
PNGs are meant for the public line, after a look. `check()` scans the
copies for every name in the tree and fails on any hit.

Sketch: reads the embedded JSON of the pages geoview.py and volumes.py
write, so it follows their data shape and must change with it.
"""
import json
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

from lineage import ahnentafel  # 'FMMF' -> 22: father 2n, mother 2n + 1

ROOT = Path(__file__).resolve().parent
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"




def _first(lineage):
    return (lineage or "").split()[0] if lineage else ""


def keep_person(kin, lineage, born):
    lin = _first(lineage)
    if kin != "ancestor" or len(lin) < 3:
        return False
    # no birth year: kept from the great-great-grandparents back (born well before 1900)
    return born < 1900 if isinstance(born, int) else len(lin) >= 4


def pseudonym(lineage, born, died):
    lin = _first(lineage)
    life = f" ({born or ''}–{died or ''})" if born or died else ""
    return f"A{ahnentafel(lin)}", f"No. {ahnentafel(lin)} · {lin}{life}"


def _embedded(page, start):
    i = page.index(start)
    data, n = json.JSONDecoder().raw_decode(page[i:])
    return page[:i], data, page[i + n:]


def _dump(data):
    return json.dumps(data, ensure_ascii=False, default=str).replace("</", "<\\/")


def kept_people(geo):
    """MyHeritage id -> (pseudonym id, label) for everyone kept, read from
    the geography page's people."""
    _, d, _ = _embedded(geo.read_text(encoding="utf-8"), '{"tabs"')
    return {p[0]: pseudonym(p[5], p[6], p[7]) for p in d["people"] if keep_person(p[3], p[5], p[6])}


def archives_page(src, dst, kept):
    head, d, tail = _embedded(src.read_text(encoding="utf-8"), '{"rows"')
    rows = []
    for r in d["rows"]:
        if r.get("mh_id") not in kept:
            continue
        pid, label = kept[r["mh_id"]]
        rows.append(dict(r, person=pid, label=label, mh_id=pid, lineage=_first(r.get("lineage")),
                         url="", notes="", errata="") | ({"source_title": ""} if "MyHeritage" in r.get("source_title", "") else {}))
    d.update(rows=rows, proband="")
    dst.write_text(head + _dump(d) + tail, encoding="utf-8")


def geography_page(src, dst, kept):
    head, d, tail = _embedded(src.read_text(encoding="utf-8"), '{"tabs"')
    old = d["people"]
    keep = [i for i, p in enumerate(old) if p[0] in kept]
    new_ix = {i: n for n, i in enumerate(keep)}
    people = []
    for i in keep:
        mh, _, _, kin, branch, lineage, born, died, spouses = old[i]
        pid, label = kept[mh]
        lin = _first(lineage)
        people.append([pid, label, f"{lin[:3]}… line", kin, branch, lin, born, died,
                       [new_ix[s] for s in spouses if s in new_ix]])
    rows = []
    for r in d["rows"]:
        if r[0] in new_ix:
            r = list(r)
            r[0] = new_ix[r[0]]
            r[14] = ""                    # MyHeritage link
            rows.append(r)
    d.update(people=people, rows=rows)
    dst.write_text(head + _dump(d) + tail, encoding="utf-8")


def check(folder, gedcom):
    """Fail if any person's name from the tree, or a MyHeritage id, is in
    the copies. Names are matched as whole given-name + surname pairs and
    as rare surnames; place names that are also surnames are allowed."""
    import gedcom_io
    tree = gedcom_io.Tree(gedcom, keep_unlinked=True)     # every name in the file, linked or not
    text = " ".join(_dump(_embedded(p.read_text(encoding="utf-8"), start)[1])     # the data, not the code
                    for p, start in ((folder / "archives.html", '{"rows"'), (folder / "geography.html", '{"tabs"')))
    if (folder / "painting.svg").exists():
        text += " " + svg_text(folder / "painting.svg")
    hits = set(re.findall(r"MH:I\d+|@I\d+@", text))
    for p in tree.people.values():
        given = re.sub(r"[*]", "", p.get("given") or "").split()
        surname = (p.get("surname") or "").split(" (")[0].strip()
        for g in given:
            if surname and len(g) > 2 and re.search(rf"\b{re.escape(g)} (?:\w+ )*{re.escape(surname)}\b", text):
                hits.add(f"{g} … {surname}")
    return sorted(hits)


def painting(cfg, out, svg_dir):
    """One sibling's grandparent painting with placed match segments and
    block support (dnapainter_export.plot), titled "Sibling 1". The figure
    holds no names: lineage codes, counts and positions only. An SVG copy
    with real text goes to svg_dir for check()."""
    import matplotlib
    matplotlib.use("Agg")
    matplotlib.rcParams["svg.fonttype"] = "none"
    import pandas as pd

    import outputs
    import dnapainter_export as dx
    import match_placement as mp
    D = cfg["data_dir"]
    key = next(k for k, p in cfg["people"].items() if p.get("role") == "child")
    blocks = mp.load_painting(D)
    segs = outputs.read(D, "placed_segments.csv")
    placed = outputs.read(D, "placed_matches.csv")
    import gedcom_io
    tree, proband = gedcom_io.load(cfg)
    deep = dx.deep_codes(tree, proband, placed)
    b, sg = blocks[blocks.subject == key], segs[segs.subject == key]
    out.mkdir(parents=True, exist_ok=True)
    dx.plot("Sibling 1", b, sg, deep, out / "painting.png")
    dx.plot("Sibling 1", b, sg, deep, svg_dir / "painting.svg")
    return svg_dir / "painting.svg"


def svg_text(path):
    import html
    return " ".join(html.unescape(t) for t in re.findall(r">([^<>]+)</text>|>([^<>]+)</tspan>", path.read_text(encoding="utf-8")) for t in t if t)


def shots(port, out):
    out.mkdir(parents=True, exist_ok=True)
    base = f"http://127.0.0.1:{port}/showcase"
    plan = {
        "geography_pair.png": ("geography.html#person={pair}&lines=1", (1400, 1000)),
        "archives.png": ("archives.html", (1400, 1000)),
        "geography_branches.png": ("geography.html#color=branch&view=57.6,14.3,8", (1400, 900)),
    }
    pair = (ROOT / "data/output/showcase/.pair").read_text().strip()
    for name, (url, (w, h)) in plan.items():
        _chrome(f"{base}/{url.format(pair=pair)}", (w, h), out / name)
    # one branch at a time in one shared frame: the time facet re-ranges to
    # the branch, so each panel shows how far back that branch's places reach
    panels = []
    for b in ("FF", "FM", "MF", "MM"):
        png = out / f".branch_{b}.png"
        _chrome(f"{base}/geography.html#branch={b}&open=branch&view=57.75,14.2,8", (1100, 860), png)
        panels.append(png)
    _grid(panels, out / "geography_by_branch.png", crop=(0, 0, 1100, 562))


def _chrome(url, size, png):
    w, h = size
    subprocess.run([CHROME, "--headless=new", "--hide-scrollbars", f"--window-size={w},{h}",
                    "--virtual-time-budget=20000", f"--screenshot={png}", url],
                   check=True, capture_output=True)
    print(f"{png.name}  <- {url}")


def _grid(pngs, dst, crop, gap=6):
    """Cropped screenshots two by two in one PNG; the parts are deleted."""
    from PIL import Image
    ims = [Image.open(p).convert("RGB").crop(crop) for p in pngs]
    w, h = ims[0].size
    grid = Image.new("RGB", (2 * w + gap, 2 * h + gap), "white")
    for i, im in enumerate(ims):
        grid.paste(im, ((i % 2) * (w + gap), (i // 2) * (h + gap)))
    grid.quantize(256).save(dst, optimize=True)
    for p in pngs:
        p.unlink()


def _main(argv):
    import config
    cfg = config.load()
    src = config.path(cfg, "geography.html").parent
    dst = src / "showcase"
    dst.mkdir(exist_ok=True)
    kept = kept_people(src / "geography.html")
    archives_page(src / "archives.html", dst / "archives.html", kept)
    geography_page(src / "geography.html", dst / "geography.html", kept)
    # a couple to show on the pair map: the husband (even number) and wife
    # with the most points between them
    d = _embedded((dst / "geography.html").read_text(encoding="utf-8"), '{"tabs"')[1]
    n = Counter(r[0] for r in d["rows"])
    pairs = [(n[i] + sum(n[s] for s in p[8]), p[0], [d["people"][s][0] for s in p[8]])
             for i, p in enumerate(d["people"]) if p[8] and int(p[0][1:]) % 2 == 0]
    best = max(pairs)
    (dst / ".pair").write_text(",".join([best[1]] + best[2]))
    painting(cfg, ROOT / "docs" / "img", dst)
    leaks = check(dst, config.path(cfg, cfg["gedcom"]["file"]))
    print(f"showcase: {len(kept)} ancestors kept -> {dst}; pair {best[1]}+{','.join(best[2])}")
    if leaks:
        sys.exit(f"names or ids left in the copies: {leaks[:20]}")
    if argv and argv[0] == "shots":
        port = argv[argv.index("--port") + 1] if "--port" in argv else "8765"
        shots(port, ROOT / "docs" / "img")


if __name__ == "__main__":
    _main(sys.argv[1:])
