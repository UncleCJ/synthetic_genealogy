"""Read a GEDCOM 5.5.1 file (Gramps / MyHeritage export) into plain Python records.

Handles: CONT/CONC continuation, shared NOTE records, Swedish call names marked with '*'
(e.g. 'Anna Maria Kristina*' -> called Kristina), MyHeritage IDs stored as 'FACT MH:I123'.
"""
from __future__ import annotations
import re
from dataclasses import dataclass, field
from pathlib import Path
from .person import Person

YEAR = re.compile(r"(\d{4})")


@dataclass
class Indi:
    xref: str
    name: str = ""
    given: str = ""
    surname: str = ""
    callname: str = ""
    sex: str = "U"
    birth_date: str = ""
    birth_place: str = ""
    death_date: str = ""
    death_place: str = ""
    occupations: list[str] = field(default_factory=list)
    residences: list[tuple[str, str]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    mh_id: str = ""
    death_cause: str = ""
    citations: list[dict] = field(default_factory=list)   # {"page": url/str, "text": transcription}
    famc: list[str] = field(default_factory=list)
    fams: list[str] = field(default_factory=list)
    father: str | None = None
    mother: str | None = None

    @property
    def birth_year(self) -> int | None:
        m = YEAR.search(self.birth_date)
        return int(m.group(1)) if m else None

    @property
    def death_year(self) -> int | None:
        m = YEAR.search(self.death_date)
        return int(m.group(1)) if m else None

    @property
    def display(self) -> str:
        first = self.callname or (self.given.split()[0] if self.given else "")
        return f"{first} {self.surname}".strip() or self.xref

    def possibly_living(self, this_year: int = 2026) -> bool:
        if self.death_date:
            return False
        return self.birth_year is None or self.birth_year > this_year - 105

    def to_person(self, this_year: int = 2026) -> Person:
        by, dy = self.birth_year, self.death_year
        end = dy or this_year
        age = 45 if by is None else max(1, min(45, end - by))
        region = self.birth_place.split(",")[0].strip() if self.birth_place else ""
        return Person(self.xref, self.display, self.sex, by, age, region)


@dataclass
class Fam:
    xref: str
    husb: str | None = None
    wife: str | None = None
    chil: list[str] = field(default_factory=list)
    marr_date: str = ""


def _records(path: Path):
    """Yield (level, xref, tag, value) with CONT/CONC folded into the previous value."""
    lines = []
    with open(path, encoding="utf-8-sig", errors="replace") as f:
        for raw in f:
            raw = raw.rstrip("\r\n")
            if not raw:
                continue
            parts = raw.split(" ", 2)
            level = int(parts[0])
            if len(parts) > 1 and parts[1].startswith("@") and parts[1].endswith("@"):
                xref, rest = parts[1], parts[2] if len(parts) > 2 else ""
                tag, _, value = rest.partition(" ")
            else:
                xref, tag = None, parts[1]
                value = parts[2] if len(parts) > 2 else ""
            if tag in ("CONT", "CONC") and lines:
                lv, x, t, v = lines[-1]
                lines[-1] = (lv, x, t, v + ("\n" if tag == "CONT" else "") + value)
            else:
                lines.append((level, xref, tag, value))
    return lines


def load(path: str | Path) -> tuple[dict[str, Indi], dict[str, Fam]]:
    lines = _records(Path(path))
    indis: dict[str, Indi] = {}
    fams: dict[str, Fam] = {}
    notes: dict[str, str] = {}
    cur, kind, ctx = None, None, []          # ctx = tag stack by level
    for level, xref, tag, value in lines:
        if level == 0:
            kind, cur = tag, None
            if tag == "INDI":
                cur = indis.setdefault(xref, Indi(xref))
            elif tag == "FAM":
                cur = fams.setdefault(xref, Fam(xref))
            elif tag == "NOTE":
                notes[xref] = value
                cur = xref
            ctx = [tag]
            continue
        ctx = ctx[:level] + [tag]
        if kind == "NOTE" and level == 1 and tag in ("CONT", "CONC"):
            continue
        if kind == "INDI":
            p: Indi = cur
            parent = ctx[level - 1] if level >= 1 else ""
            if level == 1:
                if tag == "NAME" and not p.name:
                    p.name = value
                    given, _, rest = value.partition("/")
                    p.surname = rest.split("/")[0].strip()
                    m = re.search(r"([^\s()*]+)\*", given)       # 'Anna Elisabeth (Lisa*)' -> Lisa
                    p.callname = m.group(1) if m else ""
                    p.given = " ".join(given.replace("*", "").split())
                elif tag == "SEX":
                    p.sex = value.strip()[:1] or "U"
                elif tag == "OCCU" and value:
                    p.occupations.append(value)
                elif tag == "NOTE":
                    p.notes.append(value)          # resolved below if it's a @N@ pointer
                elif tag == "FACT" and value.startswith("MH:"):
                    p.mh_id = value[3:]
                elif tag == "FAMC":
                    p.famc.append(value)
                elif tag == "FAMS":
                    p.fams.append(value)
                elif tag == "RESI":
                    p.residences.append(("", ""))
                elif tag == "SOUR":
                    p.citations.append({"source": value, "page": "", "text": ""})
            elif level == 2:
                if parent == "BIRT" and tag == "DATE": p.birth_date = value
                elif parent == "BIRT" and tag == "PLAC": p.birth_place = value
                elif parent == "DEAT" and tag == "DATE": p.death_date = value or "Y"
                elif parent == "DEAT" and tag == "PLAC": p.death_place = value
                elif parent == "DEAT" and tag == "CAUS": p.death_cause = value
                elif parent == "SOUR" and tag == "PAGE" and p.citations: p.citations[-1]["page"] = value
                elif parent == "RESI" and p.residences:
                    d, pl = p.residences[-1]
                    p.residences[-1] = (value, pl) if tag == "DATE" else (d, value) if tag == "PLAC" else (d, pl)
            elif level == 3 and tag == "TEXT" and ctx[1] == "SOUR" and p.citations:
                p.citations[-1]["text"] = value
            if level == 1 and tag == "DEAT" and not p.death_date:
                p.death_date = value.strip() or "Y"   # 'DEAT Y' = known dead, no date
        elif kind == "FAM" and level == 1:
            f: Fam = cur
            if tag == "HUSB": f.husb = value
            elif tag == "WIFE": f.wife = value
            elif tag == "CHIL": f.chil.append(value)
        elif kind == "FAM" and level == 2 and ctx[1] == "MARR" and tag == "DATE":
            cur.marr_date = value

    for p in indis.values():
        p.notes = [notes.get(n, n) if n.startswith("@") else n for n in p.notes]
        p.notes = [n for n in p.notes if n.strip()]
        if p.death_date == "Y":
            p.death_date = "dead"
        for fx in p.famc[:1]:                    # first FAMC = birth family
            fam = fams.get(fx)
            if fam:
                p.father, p.mother = fam.husb, fam.wife
    return indis, fams


MH_PROFILE = re.compile(r"https?://www\.myheritage\.[a-z.]+/person-[^\s;]+")


def profile_links(p: Indi) -> list[str]:
    """MyHeritage profile pages cited for this person (Smart Matches in other trees: photo leads)."""
    seen = []
    for c in p.citations:
        for url in MH_PROFILE.findall(c["page"] + " " + c["text"]):
            if url not in seen:
                seen.append(url)
    return seen


def find(indis: dict[str, Indi], text: str) -> list[Indi]:
    t = text.lower()
    return [p for p in indis.values() if t in p.name.lower().replace("/", "").replace("*", "")]


def ancestors(indis: dict[str, Indi], root: str, generations: int) -> dict[int, str | None]:
    """Ahnentafel numbering: 1 = root, 2n = father of n, 2n+1 = mother of n."""
    out: dict[int, str | None] = {1: root}
    for n in range(1, 2 ** generations):
        x = out.get(n)
        if 2 * n >= 2 ** generations:
            break
        p = indis.get(x) if x else None
        out[2 * n] = p.father if p else None
        out[2 * n + 1] = p.mother if p else None
    return out
