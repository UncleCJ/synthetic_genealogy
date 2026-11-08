"""python -m genealogy_avatars.cli demo
   python -m genealogy_avatars.cli matches path/to/myheritage.csv [--backend dicebear]
   python -m genealogy_avatars.cli prompts            # print the image prompts only
"""
from __future__ import annotations
import argparse, csv, html
from pathlib import Path
from .person import Person
from .backends import BACKENDS, build_prompt
from .cache import AvatarCache

# A fictional 8-generation direct line plus some siblings, for trying out the look.
DEMO = [
    Person("S1", "Anders Persson", "M", 1702, 58, "Västergötland"),
    Person("S2", "Brita Olofsdotter", "F", 1706, 50, "Västergötland"),
    Person("S3", "Olof Andersson", "M", 1741, 45, "Västergötland"),
    Person("S4", "Kerstin Jonsdotter", "F", 1745, 62, "Dalsland"),
    Person("S5", "Johan Olsson", "M", 1778, 70, "Dalsland"),
    Person("S6", "Maja Larsdotter", "F", 1782, 38, "Bohuslän"),
    Person("S7", "Lars Johansson", "M", 1815, 33, "Bohuslän"),
    Person("S8", "Stina Andersdotter", "F", 1819, 76, "Bohuslän"),
    Person("S9", "Carl Larsson Ekström", "M", 1852, 48, "Göteborg"),
    Person("S10", "Hilda Pettersson", "F", 1858, 40, "Göteborg"),
    Person("S11", "Gustaf Ekström", "M", 1889, 60, "Göteborg"),
    Person("S12", "Elin Karlsson", "F", 1893, 30, "Värmland"),
    Person("S13", "Erik Ekström", "M", 1921, 35, "Stockholm"),
    Person("S14", "Margit Holm", "F", 1925, 28, "Stockholm"),
    Person("S15", "Per Ekström", "M", 1950, 45, "Stockholm"),
    Person("S16", "Anna Lind", "F", 1953, 40, "Uppsala"),
    Person("S17", "Sofia Ekström", "F", 1982, 30, "Stockholm"),
    Person("S18", "Jonas Ekström", "M", 1985, 22, "Stockholm"),
    Person("S19", "Unknown sibling", "U", 1880, 20),
    Person("S20", "Unknown father", "U", None),
]

COLS = {"match id": ["DNA-matchnings-ID", "Match ID"],
        "match": ["Namn på matchning", "Matchnamn", "Match Name"]}


def read_matches(path: str) -> list[Person]:
    """One Person per distinct match. Living people: modern era, sex unknown -> neutral face."""
    with open(path, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    pick = lambda row, key: next((row[c] for c in COLS[key] if c in row and row[c]), "")
    seen: dict[str, Person] = {}
    for row in rows:
        name = pick(row, "match")
        mid = pick(row, "match id") or name     # chromosome-browser exports have no ID column
        if mid and mid not in seen:
            seen[mid] = Person(id=mid, name=name, sex="U", birth_year=1970, portrait_age=40)
    return list(seen.values())


def gallery(people: list[Person], paths: list[Path], out: Path, title: str) -> None:
    cards = "".join(
        f'<figure><img src="{html.escape(str(pa.relative_to(out.parent)))}" alt="">'
        f'<figcaption><b>{html.escape(p.name or p.id)}</b><br>'
        f'{p.birth_year or "?"} · {p.era}</figcaption></figure>'
        for p, pa in zip(people, paths))
    out.write_text(f"""<!doctype html><meta charset="utf-8"><title>{html.escape(title)}</title>
<style>body{{font:14px system-ui;margin:2rem;background:#faf8f4;color:#222}}
main{{display:grid;grid-template-columns:repeat(auto-fill,minmax(140px,1fr));gap:1rem}}
figure{{margin:0;text-align:center}}img{{width:120px;height:120px;object-fit:cover;border-radius:8px}}
@media(prefers-color-scheme:dark){{body{{background:#1b1b1b;color:#eee}}}}</style>
<h1>{html.escape(title)}</h1><main>{cards}</main>""", encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser(prog="genealogy_avatars")
    ap.add_argument("command", choices=["demo", "matches", "prompts"])
    ap.add_argument("csv", nargs="?")
    ap.add_argument("--backend", default="procedural", choices=BACKENDS)
    ap.add_argument("--out", default="avatars")
    ap.add_argument("--limit", type=int, default=60)
    ap.add_argument("--refresh", action="store_true")
    a = ap.parse_args()

    people = DEMO if a.command in ("demo", "prompts") else read_matches(a.csv)[: a.limit]
    if a.command == "prompts":
        for p in people:
            print(f"{p.id:5} {build_prompt(p)}")
        return
    backend, cache = BACKENDS[a.backend](), AvatarCache(a.out)
    paths = [cache.get(p, backend, refresh=a.refresh) for p in people]
    out = Path(a.out) / f"gallery-{a.command}-{backend.name}.html"
    gallery(people, paths, out, f"{a.command} · {backend.name}")
    print(f"{len(paths)} avatars -> {out}")


if __name__ == "__main__":
    main()
