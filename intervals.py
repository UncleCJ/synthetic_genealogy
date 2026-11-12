"""Intervals for both halves: stretches of a chromosome (bp, and cM through a
genetic map) and spans of years in a life (from GEDCOM dates).

Genome: GRCh37 bp, closed intervals [start, end] as the vendors write them;
the helpers work on numpy arrays.

    overlap(a0, a1, b0, b1)          bp shared by two intervals (elementwise)
    covered(start, end, others)      bp of [start, end] covered by the union of others
    jaccard(a0, a1, b0, b1)          shared / joint length
    merge(intervals, gap=0)          union of (start, end) pairs, sorted
    bins(start, end, size)           which fixed bins (e.g. 1 Mb) a midpoint falls in

    s = IntervalSet.of("7", pairs)   # one chromosome's stretches, merged
    s | t, s & t, s - t              # union, intersection, difference
    s.bp, s.cm(gm), s.longest(gm)    # total bp, total cM, longest stretch

    gm = GeneticMap.load(cfg)        # [genetic_map] in family.toml, else flat 1 cM/Mb
    gm.cm("7", pos)                  # array of cM positions
    gm.length("7", start, end)       # cM between two positions

Map files are not in the repository; `[genetic_map] dir` points at one (see
GeneticMap.read). Without one, `flat()` stands in, and says so.

Years: YearSpan is a fuzzy span read from a GEDCOM date ("12 MAR 1850", "ABT",
"BEF", "AFT", "FROM .. TO ..", "BET .. AND .."). Open ends are None;
`precision` is "day", "year" or "none"; comparisons treat open ends as
unbounded.

Sketch-level: no vendor endpoint noise, centromeres or pile-ups.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import numpy as np

AUTOSOMES = [str(c) for c in range(1, 23)]


# ------------------------------------------------------------------ genome
def overlap(a0, a1, b0, b1):
    """Length shared by [a0, a1] and [b0, b1], elementwise, >= 0."""
    return np.clip(np.minimum(a1, b1) - np.maximum(a0, b0), 0, None)


def jaccard(a0, a1, b0, b1):
    """Shared length / joint length (0 when disjoint)."""
    inter = overlap(a0, a1, b0, b1)
    joint = np.maximum(a1, b1) - np.minimum(a0, b0)
    return np.where(joint > 0, inter / np.where(joint > 0, joint, 1), 0.0)


def merge(intervals, gap=0):
    """Union of (start, end) pairs: sorted, overlapping (or closer than
    `gap`) ones joined. Returns a list of [start, end]."""
    out = []
    for a, b in sorted((float(a), float(b)) for a, b in intervals):
        if out and a <= out[-1][1] + gap:
            out[-1][1] = max(out[-1][1], b)
        else:
            out.append([a, b])
    return out


def covered(start, end, others):
    """Length of [start, end] covered by the union of `others` ((start,
    end) pairs)."""
    total = 0.0
    for a, b in merge(others):
        a, b = max(a, start), min(b, end)
        if b > a:
            total += b - a
    return total


def bins(start, end, size):
    """Index of the fixed-size bin holding each interval's midpoint."""
    return ((np.asarray(start) + np.asarray(end)) / 2 // size).astype(int)


@dataclass(frozen=True)
class IntervalSet:
    """A set of stretches on one chromosome: sorted, disjoint (start, end)
    bp pairs, normalised by `merge` (touching stretches join, empty ones
    drop). Lengths are end − start, as everywhere in this module. Not copy
    aware, no fuzzy ends or Allen relations: plain sets of bp."""
    chrom: str
    spans: tuple = ()

    @classmethod
    def of(cls, chrom, intervals=(), gap=0):
        return cls(str(chrom), tuple((a, b) for a, b in merge(intervals, gap) if b > a))

    def _same(self, other):
        if self.chrom != other.chrom:
            raise ValueError(f"chromosome {self.chrom} vs {other.chrom}")

    def __or__(self, other):
        self._same(other)
        return IntervalSet.of(self.chrom, self.spans + other.spans)

    def __and__(self, other):
        self._same(other)
        out, i, j = [], 0, 0
        a, b = self.spans, other.spans
        while i < len(a) and j < len(b):
            lo, hi = max(a[i][0], b[j][0]), min(a[i][1], b[j][1])
            if hi > lo:
                out.append((lo, hi))
            if a[i][1] < b[j][1]:
                i += 1
            else:
                j += 1
        return IntervalSet(self.chrom, tuple(out))

    def __sub__(self, other):
        self._same(other)
        out = []
        for lo, hi in self.spans:
            for c, d in other.spans:
                if d <= lo:
                    continue
                if c >= hi:
                    break
                if c > lo:
                    out.append((lo, c))
                lo = max(lo, d)
            if hi > lo:
                out.append((lo, hi))
        return IntervalSet(self.chrom, tuple(out))

    union, intersection, difference = __or__, __and__, __sub__

    def __iter__(self):
        return iter(self.spans)

    def __bool__(self):
        return bool(self.spans)

    @property
    def bp(self):
        """Total length in bp."""
        return sum(b - a for a, b in self.spans)

    def cm(self, gm):
        """Total length in cM through a GeneticMap."""
        return sum(float(gm.length(self.chrom, a, b)) for a, b in self.spans)

    def longest(self, gm=None):
        """The longest stretch's length: bp, or cM through `gm`."""
        if not self.spans:
            return 0.0
        if gm is None:
            return max(b - a for a, b in self.spans)
        return max(float(gm.length(self.chrom, a, b)) for a, b in self.spans)


class GeneticMap:
    """bp -> cM per chromosome, by linear interpolation between map points.

    `sex` is a label only ("average", "female", "male"): one map object is
    one map; load the sex-specific ones as separate objects."""

    def __init__(self, points, name="", sex="average", flat_rate=None):
        # points: {chrom: (bp array, cM array)}, both increasing
        self.points = {str(c): (np.asarray(bp, float), np.asarray(cm, float))
                       for c, (bp, cm) in points.items()}
        self.name, self.sex, self.flat_rate = name, sex, flat_rate

    def __repr__(self):
        return f"GeneticMap({self.name or 'unnamed'}, {self.sex}, {len(self.points)} chromosomes)"

    @property
    def is_flat(self):
        return self.flat_rate is not None

    @classmethod
    def flat(cls, rate=1.0):
        """`rate` cM per Mb everywhere: the stand-in when no map is given."""
        return cls({}, name=f"flat {rate} cM/Mb", flat_rate=rate)

    def cm(self, chrom, bp):
        bp = np.asarray(bp, float)
        if self.is_flat:
            return bp / 1e6 * self.flat_rate
        x, y = self.points[str(chrom)]
        return np.interp(bp, x, y)

    def bp(self, chrom, cm):
        """The inverse: cM -> bp (where the map is flat, the first bp)."""
        cm = np.asarray(cm, float)
        if self.is_flat:
            return cm / self.flat_rate * 1e6
        x, y = self.points[str(chrom)]
        return np.interp(cm, y, x)

    def length(self, chrom, start, end):
        return self.cm(chrom, end) - self.cm(chrom, start)

    def has(self, chrom):
        return self.is_flat or str(chrom) in self.points

    # --------------------------------------------------------------- files
    @classmethod
    def read(cls, path, sex="average", name=None):
        """Read a map from a file or a folder of per-chromosome files.

        Recognised layouts (whitespace or comma separated, header optional):
          * 4 columns  chrom, bp, rate (cM/Mb), cM   (HapMap II, Bherer et al. 2017)
          * 3 columns  bp, rate, cM                  (one file per chromosome;
                                                      chromosome from the file name)
          * PLINK .map chrom, id, cM, bp
        Chromosome names may carry a "chr" prefix."""
        path = Path(path)
        files = sorted(path.glob("*")) if path.is_dir() else [path]
        pts = {}
        for f in files:
            if not f.is_file() or f.name.startswith("."):
                continue
            pts.update(_read_map_file(f))
        if not pts:
            raise ValueError(f"no map points read from {path}")
        return cls(pts, name=name or path.name, sex=sex)

    @classmethod
    def load(cls, cfg, sex=None, quiet=False):
        """The map named in family.toml:

            [genetic_map]
            dir = "maps/bherer2017/sexavg"      # under data/, or absolute
            sex = "average"
            # female = "maps/bherer2017/female"   (optional, sex-specific)
            # male = "maps/bherer2017/male"

        Without it, or if the folder is missing: flat 1 cM/Mb, with a note."""
        g = cfg.get("genetic_map") or {}
        key = {"female": "female", "male": "male"}.get(sex, "dir")
        rel = g.get(key)
        if rel:
            p = Path(rel)
            p = p if p.is_absolute() else cfg["data_dir"].layer("input") / rel
            if p.exists():
                return cls.read(p, sex=sex or g.get("sex", "average"))
            if not quiet:
                print(f"genetic map {p} not found: using flat 1 cM/Mb")
        elif not quiet:
            print("no [genetic_map] in family.toml: using flat 1 cM/Mb")
        return cls.flat()


def _read_map_tab4(f):
    """Fast path for tab-separated 4-column files with a header (HapMap II):
    the same points as the line reader, parsed by pandas' C reader."""
    import pandas as pd
    try:
        d = pd.read_csv(f, sep="\t", header=0, dtype={0: str})
    except Exception:
        return None
    if d.shape[1] != 4:
        return None
    bp = pd.to_numeric(d.iloc[:, 1], errors="coerce").to_numpy(float)
    cm = pd.to_numeric(d.iloc[:, 3], errors="coerce").to_numpy(float)
    if np.isnan(bp).any() or np.isnan(cm).any():
        return None
    chrom = d.iloc[:, 0].astype(str).str.replace(r"^chr", "", regex=True, case=False).to_numpy()
    out = {}
    for c in dict.fromkeys(chrom):
        m = chrom == c
        o = np.lexsort((cm[m], bp[m]))                 # as sorted((bp, cm)) tuples
        out[c] = (bp[m][o], np.maximum.accumulate(cm[m][o]))
    return out


def _read_map_file(f):
    if f.suffix != ".map":
        fast = _read_map_tab4(f)
        if fast is not None:
            return fast
    from_name = re.search(r"chr(?:omosome)?[_-]?(\d{1,2}|X)\b", f.name, re.I)
    rows = {}
    with open(f, encoding="utf-8", errors="replace") as h:
        for line in h:
            t = line.replace(",", " ").split()
            if not t or t[0].startswith("#"):
                continue
            try:
                if f.suffix == ".map" and len(t) == 4:              # PLINK
                    c, cm, bp = t[0], float(t[2]), float(t[3])
                elif len(t) >= 4:
                    c, bp, cm = t[0], float(t[1]), float(t[3])
                elif len(t) == 3 and from_name:
                    c, bp, cm = from_name.group(1), float(t[0]), float(t[2])
                else:
                    continue
            except ValueError:                                    # header line
                continue
            c = re.sub(r"^chr", "", c, flags=re.I)
            rows.setdefault(c, []).append((bp, cm))
    out = {}
    for c, r in rows.items():
        a = np.array(sorted(r))
        out[c] = (a[:, 0], np.maximum.accumulate(a[:, 1]))
    return out


# ------------------------------------------------------------------- years
YEAR = re.compile(r"\b(1[5-9]\d\d|20\d\d)\b")
DAY = re.compile(r"\b\d{1,2}\s+[A-Za-z]{3}\b")


@dataclass(frozen=True)
class YearSpan:
    start: int | None
    end: int | None
    precision: str = "year"        # "day", "year" or "none"
    approx: bool = False           # ABT, EST, CAL

    @classmethod
    def parse(cls, date):
        """GEDCOM date text -> YearSpan. "BEF"/"TO" leave the start open,
        "AFT"/"FROM" (without TO) the end; otherwise the earliest and
        latest year written."""
        d = (date or "").strip().upper()
        ys = [int(y) for y in YEAR.findall(d)]
        if not ys:
            return cls(None, None, "none")
        prec = "day" if DAY.search(d) else "year"
        approx = d.startswith(("ABT", "EST", "CAL"))
        if d.startswith(("TO ", "BEF")):
            return cls(None, max(ys), prec, approx)
        if d.startswith(("FROM ", "AFT")) and " TO " not in d:
            return cls(min(ys), None, prec, approx)
        return cls(min(ys), max(ys), prec, approx)

    @property
    def known(self):
        return self.start is not None or self.end is not None

    def bounds(self, open_=9999):
        """(start, end) with open ends as -open_ / +open_."""
        return (self.start if self.start is not None else -open_,
                self.end if self.end is not None else open_)

    def overlaps(self, other):
        if not (self.known and other.known):
            return False
        a0, a1 = self.bounds()
        b0, b1 = other.bounds()
        return a0 <= b1 and b0 <= a1

    def as_tuple(self):
        return self.start, self.end


def year_range(text):
    """(earliest, latest) year written in a text, ignoring BEF/AFT and the
    like ("1850-1856" -> (1850, 1856)); (None, None) without a year."""
    ys = [int(y) for y in YEAR.findall(text or "")]
    return (min(ys), max(ys)) if ys else (None, None)


def years(date):
    """(start, end) years of a GEDCOM date; open ends None."""
    return YearSpan.parse(date).as_tuple()


def is_dated(date):
    """True if the date names a day ("12 MAR 1850")."""
    return bool(DAY.search(date or ""))
