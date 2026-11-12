"""
Simulate what a known pedigree's DNA looks like to the vendors, with the
truth kept: for tests and for calibrating the inference.

    ped = Pedigree()
    ped.add("gf", "M"); ped.add("gm", "F")
    ped.add("dad", "M", father="gf", mother="gm")
    ...
    sim = simulate(ped, seed=1)          # every person's two copies, as mosaics
    sim.lineage("me", "1", 50e6)          # ("F", "FM"): paternal copy from FM...
    segs = detect(sim, testers=["me", "cousin"], seed=1)   # vendor-style segments

Meioses are Poisson crossovers in cM through a GeneticMap (flat 1 cM/Mb by
default; a map per sex can be given); `twin_of=` makes identical twins;
`detect` adds vendor flaws (cM threshold, end noise, false short segments).
Not modelled: genotypes, pile-ups, population IBD, chip differences, X.

Ped-sim (optional, external, GPL; github.com/williamslab/ped-sim):
`pedsim_def` writes a Pedigree as a Ped-sim def file, `run_pedsim` runs it,
and `from_pedsim` reads its output back as Simulations under our names, so
true_ibd, detect and lineage work unchanged on sex-specific maps with
interference. Only its output files are read; nothing is bundled.

How it works: docs/genetics.md, "Simulation".
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

import intervals as iv

# rough sex-averaged autosome lengths (cM) and sizes (Mb), GRCh37
CHROM_CM = {"1": 278, "2": 263, "3": 224, "4": 214, "5": 209, "6": 194, "7": 186,
            "8": 170, "9": 168, "10": 181, "11": 159, "12": 173, "13": 128, "14": 118,
            "15": 128, "16": 134, "17": 129, "18": 117, "19": 107, "20": 108,
            "21": 63, "22": 72}


@dataclass
class Person:
    name: str
    sex: str
    father: str | None = None
    mother: str | None = None
    twin_of: str | None = None


@dataclass
class Pedigree:
    people: dict = field(default_factory=dict)

    def add(self, name, sex, father=None, mother=None, twin_of=None):
        if twin_of:
            t = self.people[twin_of]
            father, mother = t.father, t.mother
        self.people[name] = Person(name, sex, father, mother, twin_of)
        return self

    def order(self):
        """Parents before children (twins after their co-twin)."""
        done, out = set(), []

        def visit(n):
            if n in done:
                return
            p = self.people[n]
            for q in (p.father, p.mother, p.twin_of):
                if q:
                    visit(q)
            done.add(n)
            out.append(n)
        for n in self.people:
            visit(n)
        return out

    def path(self, who, ancestor):
        """Lineage codes from `who` up to `ancestor` (F/M per step), all paths."""
        if who == ancestor:
            return [""]
        p = self.people[who]
        out = []
        for step, q in (("F", p.father), ("M", p.mother)):
            if q:
                out += [step + c for c in self.path(q, ancestor)]
        return out


# A mosaic is, per chromosome, a list of (start_cM, end_cM, founder copy label)
@dataclass
class Simulation:
    ped: Pedigree
    genomes: dict          # person -> {"F": {chrom: mosaic}, "M": {chrom: mosaic}}
    maps: dict             # "average"/"female"/"male" -> GeneticMap
    lengths: dict = None   # chrom -> cM length (default CHROM_CM; a Ped-sim run sets its map's)

    def __post_init__(self):
        self.lengths = self.lengths or CHROM_CM

    def copy_at(self, who, side, chrom, cm):
        for a, b, lab in self.genomes[who][side][str(chrom)]:
            if a <= cm < b or (cm == b and b == self.lengths[str(chrom)]):
                return lab
        return None

    def founder_of(self, label):
        return label.rsplit(":", 1)[0]

    def lineage(self, who, chrom, bp):
        """(paternal, maternal) lineage codes at a bp position: the path from
        `who` up to the founder whose copy each of the two copies is."""
        cm = float(self.maps["average"].cm(chrom, bp))
        out = []
        for side in "FM":
            lab = self.copy_at(who, side, chrom, cm)
            f = self.founder_of(lab)
            paths = [p for p in self.ped.path(who, f) if p.startswith(side)]
            out.append(paths[0] if len(paths) == 1 else "|".join(sorted(paths)))
        return tuple(out)


def _meiosis(parent_genome, rng, sex, chroms):
    """One gamete: per chromosome, a mosaic made from the parent's two."""
    out = {}
    for c in chroms:
        L = CHROM_CM[c]
        # female meioses have more crossovers (about 1.6x); scale around the average
        rate = {"F": 1.25, "M": 0.78}.get(sex, 1.0)
        n = rng.poisson(L / 100 * rate)
        cuts = np.sort(rng.uniform(0, L, n))
        start_side = rng.integers(2)
        bounds = np.r_[0, cuts, L]
        pieces = []
        for i in range(len(bounds) - 1):
            src = parent_genome["FM"[(start_side + i) % 2]][c]
            a, b = bounds[i], bounds[i + 1]
            for s0, s1, lab in src:
                lo, hi = max(a, s0), min(b, s1)
                if hi > lo:
                    pieces.append([lo, hi, lab])
        merged = []
        for p in pieces:            # join neighbours from the same founder copy
            if merged and merged[-1][2] == p[2] and abs(merged[-1][1] - p[0]) < 1e-9:
                merged[-1][1] = p[1]
            else:
                merged.append(p)
        out[c] = [tuple(m) for m in merged]
    return out


def simulate(ped, seed=0, chroms=None, genetic_map=None):
    """Drop founder copies through the pedigree. genetic_map: a GeneticMap
    for bp conversion (default flat 1 cM/Mb)."""
    rng = np.random.default_rng(seed)
    chroms = chroms or list(CHROM_CM)
    gm = genetic_map or iv.GeneticMap.flat()
    genomes = {}
    for n in ped.order():
        p = ped.people[n]
        if p.twin_of:
            genomes[n] = genomes[p.twin_of]
        elif p.father is None and p.mother is None:
            genomes[n] = {s: {c: [(0.0, float(CHROM_CM[c]), f"{n}:{s}")] for c in chroms}
                          for s in "FM"}
        else:
            if p.father is None or p.mother is None:
                raise ValueError(f"{n}: give both parents or none (use an unnamed founder)")
            genomes[n] = {"F": _meiosis(genomes[p.father], rng, "M", chroms),
                          "M": _meiosis(genomes[p.mother], rng, "F", chroms)}
    return Simulation(ped, genomes, {"average": gm})


def true_ibd(sim, a, b, min_cm=0.0, join=False):
    """Half-identical stretches between a and b: DataFrame with chrom,
    start_cm, end_cm, start, end (bp), cM, copy_a, copy_b (F/M), founder copy.

    join: merge touching pieces on the same pair of copies, as a vendor
    sees them. Without it, IBD through a deeper ancestor is cut wherever
    that ancestor's copy changes founder (a crossover in an older meiosis),
    which no vendor can see; the founder_copy of a joined piece is its first."""
    rows = []
    gm = sim.maps["average"]
    for c in sim.genomes[a]["F"]:
        for sa in "FM":
            for sb in "FM":
                A, B = sim.genomes[a][sa][c], sim.genomes[b][sb][c]
                for a0, a1, la in A:
                    for b0, b1, lb in B:
                        if la != lb:
                            continue
                        lo, hi = max(a0, b0), min(a1, b1)
                        if hi - lo > min_cm:
                            rows.append(dict(chrom=c, start_cm=lo, end_cm=hi, copy_a=sa,
                                             copy_b=sb, founder_copy=la))
    df = pd.DataFrame(rows, columns=["chrom", "start_cm", "end_cm", "copy_a", "copy_b",
                                     "founder_copy"])
    # adjacent pieces from the two copies of one founder stay separate:
    # they are different IBD (a crossover in the founder's meiosis lies
    # between them); `join` merges them as a vendor would see them
    if join and len(df):
        df = df.sort_values(["chrom", "copy_a", "copy_b", "start_cm"]).reset_index(drop=True)
        keep = []
        for r in df.to_dict("records"):
            k = keep[-1] if keep else None
            if (k and k["chrom"] == r["chrom"] and k["copy_a"] == r["copy_a"]
                    and k["copy_b"] == r["copy_b"] and abs(k["end_cm"] - r["start_cm"]) < 1e-9):
                k["end_cm"] = r["end_cm"]
            else:
                keep.append(r)
        df = pd.DataFrame(keep, columns=df.columns)
        df = df[df.end_cm - df.start_cm > min_cm]
    if not len(df):
        return df.assign(start=[], end=[], cM=[])
    df["start"] = [float(gm.bp(c, x)) for c, x in zip(df.chrom, df.start_cm)]
    df["end"] = [float(gm.bp(c, x)) for c, x in zip(df.chrom, df.end_cm)]
    df["cM"] = df.end_cm - df.start_cm
    df["_c"] = df.chrom.map(_ckey)
    return df.sort_values(["_c", "start_cm"]).drop(columns="_c").reset_index(drop=True)


def _ckey(c):
    return int(c) if str(c).isdigit() else 99


def detect(sim, testers, seed=0, min_cm=7.0, end_sd_cm=0.5, false_per_pair=2.0,
           false_cm=(7.0, 10.0), matches=None, join=False):
    """What a vendor would list: per tester and match, segments in the
    vendor shape (subject, match_key, match, chrom, start, end, cM) plus
    truth columns (real: a real or a false segment; true_copy: the tester's copy,
    F/M, for real ones).

    testers: people whose match lists are made; matches: people they are
    compared with (default: every other tester). Ends get normal noise
    (sd end_sd_cm), segments under min_cm are dropped, and each pair gets
    Poisson(false_per_pair) false segments of false_cm length, placed at
    random (on either copy: they belong to neither)."""
    rng = np.random.default_rng(seed)
    gm = sim.maps["average"]
    matches = matches or testers
    rows = []
    for t in testers:
        for m in matches:
            if m == t:
                continue
            ibd = true_ibd(sim, t, m, join=join)
            for r in ibd.itertuples():
                a = r.start_cm + rng.normal(0, end_sd_cm)
                b = r.end_cm + rng.normal(0, end_sd_cm)
                a, b = max(a, 0.0), min(b, sim.lengths[r.chrom])
                if b - a >= min_cm:
                    rows.append(dict(subject=t, match_key=m, match=m, chrom=r.chrom,
                                     start=float(gm.bp(r.chrom, a)), end=float(gm.bp(r.chrom, b)),
                                     cM=round(b - a, 2), real=True, true_copy=r.copy_a,
                                     founder_copy=r.founder_copy))
            for _ in range(rng.poisson(false_per_pair)):
                c = rng.choice(list(sim.lengths))
                L = rng.uniform(*false_cm)
                a = rng.uniform(0, sim.lengths[c] - L)
                rows.append(dict(subject=t, match_key=m, match=m, chrom=c,
                                 start=float(gm.bp(c, a)), end=float(gm.bp(c, a + L)),
                                 cM=round(L, 2), real=False, true_copy="", founder_copy=""))
    return pd.DataFrame(rows, columns=["subject", "match_key", "match", "chrom", "start", "end",
                                       "cM", "real", "true_copy", "founder_copy"])


# ------------------------------------------------------------- Ped-sim
def _heights(ped):
    kids = {}
    for p in ped.people.values():
        for q in (p.father, p.mother):
            if q:
                kids.setdefault(q, []).append(p.name)
    h = {}

    def height(n):
        if n not in h:
            h[n] = 1 + max((height(k) for k in kids.get(n, [])), default=-1)
        return h[n]
    for n in ped.people:
        height(n)
    return h, kids


def pedsim_def(ped, name="ped", copies=1):
    """A Pedigree as a Ped-sim def file. Returns (text, {our name: Ped-sim
    id without the copy number}, e.g. "sib1": "_g5-b1-i1"; the id of copy k
    is name + str(k) + that).

    Needs every leaf in the last generation and parents one generation above
    their children (true of `ancestry`, `grandmother` and the like). A
    founder whose spouse is not a founder becomes Ped-sim's founder spouse
    of that branch, unnamed by us; children of one couple are listed
    together, so they are full siblings, and a parent with two spouses gives
    half-siblings. No twins."""
    h, kids = _heights(ped)
    H = max(h.values())
    gen = {n: H - h[n] + 1 for n in ped.people}
    P = ped.people
    founder = {n: P[n].father is None and P[n].mother is None for n in P}
    for n, p in P.items():
        if p.twin_of:
            raise ValueError("Ped-sim def: twins are not supported")
        for q in (p.father, p.mother):
            if q and gen[q] != gen[n] - 1:
                raise ValueError(f"{n}: parent {q} is not one generation up")
    # branch people: non-founders, and founders in generation 1
    implicit = {n for n in P if founder[n] and gen[n] > 1}
    for n in implicit:
        mates = {(P[k].father if P[k].mother == n else P[k].mother) for k in kids.get(n, [])}
        if any(founder[m] for m in mates):
            raise ValueError(f"{n}: two founders below generation 1")
    branches = {g: [n for n in P if gen[n] == g and n not in implicit] for g in range(1, H + 2)}
    bno = {n: i + 1 for g in branches for i, n in enumerate(branches[g])}
    lines = [f"def {name} {copies} {H + 1}"]
    for g in range(1, H + 2):
        bs = branches[g]
        specs = [f"{bno[n]}s{P[n].sex}" for n in bs]
        if g > 1:
            groups = {}
            for n in bs:
                pa = tuple(q for q in (P[n].father, P[n].mother) if q not in implicit)
                groups.setdefault((P[n].father, P[n].mother), (pa, []))[1].append(str(bno[n]))
            for pa, members in groups.values():
                specs.append(",".join(members) + ":" + "_".join(str(bno[q]) for q in pa))
        lines.append(f"{g} 1 {len(bs)} " + " ".join(specs))
    ids = {n: f"_g{gen[n]}-b{bno[n]}-i1" for n in bno}
    return "\n".join(lines) + "\n", ids


def read_simmap(path):
    """Ped-sim's sex-specific map (chrom, bp, male cM, female cM) as
    {"male", "female", "average"} GeneticMaps."""
    df = pd.read_csv(path, sep=r"\s+", comment="#", header=None, names=["chrom", "bp", "m", "f"],
                     dtype={"chrom": str})
    out = {}
    for key, col in (("male", df.m), ("female", df.f), ("average", (df.m + df.f) / 2)):
        out[key] = iv.GeneticMap({c: (g.bp.values, col[g.index].values) for c, g in df.groupby("chrom")},
                                 name=Path(path).name, sex=key)
    return out


def from_pedsim(prefix, simmap, ids=None, name="ped"):
    """Read a Ped-sim run made with --bp_all --fam (prefix.bp,
    prefix-everyone.fam) as one Simulation per pedigree copy, with mosaics
    in the average map's cM. ids: from pedsim_def, to give the people our
    names (others keep Ped-sim's ids). h0 is the paternal haplotype
    (checked: every child's h0 descends from its father). Founder copies
    are labelled "<founder>:F" (h0) and ":M" (h1). simmap: a path, or
    read_simmap's result."""
    maps = read_simmap(simmap) if not isinstance(simmap, dict) else simmap
    gm = maps["average"]
    fam = pd.read_csv(f"{prefix}-everyone.fam", sep=r"\s+", header=None,
                      names=["fid", "iid", "father", "mother", "sex", "ph"], dtype=str)
    rename = {}
    for fid in fam.fid.unique():
        k = fid[len(name):]
        for ours, pid in (ids or {}).items():
            rename[f"{name}{k}{pid}"] = ours
    bp = {}
    for line in open(f"{prefix}.bp"):
        t = line.split()
        chroms, cur = {}, None
        for tok in t[3:]:
            if "|" in tok:
                cur, start = tok.split("|")
                chroms[cur] = [int(start), []]
            else:
                hap, end = tok.split(":")
                chroms[cur][1].append((int(hap), int(end)))
        bp[(t[0], t[2])] = chroms
    founder_hap = {}
    for r in fam.itertuples():
        if r.father == "0" and r.mother == "0":
            for h, side in (("h0", "F"), ("h1", "M")):
                hap = next(iter(bp[(r.iid, h)].values()))[1][0][0]
                founder_hap[hap] = f"{rename.get(r.iid, r.iid)}:{side}"
    lengths = {c: float(gm.points[c][1][-1]) for c in gm.points}
    sims = []
    for fid, g in fam.groupby("fid", sort=False):
        ped, genomes = Pedigree(), {}
        for r in g.itertuples():
            nm = rename.get(r.iid, r.iid)
            ped.add(nm, "M" if r.sex == "1" else "F",
                    father=None if r.father == "0" else rename.get(r.father, r.father),
                    mother=None if r.mother == "0" else rename.get(r.mother, r.mother))
            genomes[nm] = {}
            for h, side in (("h0", "F"), ("h1", "M")):
                genomes[nm][side] = {}
                for c, (start, pieces) in bp[(r.iid, h)].items():
                    mos, a = [], float(gm.cm(c, start))
                    for hap, end in pieces:
                        b = float(gm.cm(c, end))
                        if mos and mos[-1][2] == founder_hap[hap]:
                            mos[-1] = (mos[-1][0], b, mos[-1][2])
                        else:
                            mos.append((a, b, founder_hap[hap]))
                        a = b
                    genomes[nm][side][c] = mos
        sims.append(Simulation(ped, genomes, maps, lengths))
    return sims


def run_pedsim(ped, binary, simmap, workdir, copies=1, seed=0, intf=None, name="ped"):
    """Write the def, run Ped-sim (--bp_all --fam; interference when `intf`
    names its parameter file, else Poisson) and read it back: a list of
    `copies` Simulations under our names."""
    import subprocess
    workdir = Path(workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    text, ids = pedsim_def(ped, name=name, copies=copies)
    (workdir / f"{name}.def").write_text(text)
    cmd = [str(binary), "-d", str(workdir / f"{name}.def"), "-m", str(simmap), "-o",
           str(workdir / name), "--bp_all", "--fam", "--seed", str(seed)]
    cmd += ["--intf", str(intf)] if intf else ["--pois"]
    subprocess.run(cmd, check=True, capture_output=True)
    return from_pedsim(workdir / name, simmap, ids, name=name)


# ------------------------------------------------------------- scenarios
def family(cousin_depth=2, siblings=3, twin_fathers=False):
    """A standard test family, four grandparents back plus their parents:

        ggp: FFF FFM FMF FMM MFF MFM MMF MMM   (the eight great-grandparents)
        gp:  FF FM MF MM
        dad (F), mum (M), children sib1..sibN
        an aunt/uncle per grandparent couple, with a child (first cousins
        "c_F", "c_M"), and second cousins through each great-grandparent
        couple ("c2_FF", ...), so every branch has a tested relative.
        twin_fathers: dad has an identical twin "uncle_twin", whose son
        "twin_cousin" is genetically a half-sibling.
    Every spouse who marries in is an unnamed founder ("sp_..."); returns
    the Pedigree."""
    ped = Pedigree()
    gps = ["FF", "FM", "MF", "MM"]
    for g in gps:
        for s, sx in (("F", "M"), ("M", "F")):
            ped.add(g + s, sx)
    for g in gps:
        ped.add(g, "M" if g.endswith("F") else "F", father=g + "F", mother=g + "M")
    ped.add("F", "M", father="FF", mother="FM")
    ped.add("M", "F", father="MF", mother="MM")
    for i in range(1, siblings + 1):
        ped.add(f"sib{i}", "FM"[i % 2], father="F", mother="M")
    # first cousins through each grandparent couple
    for side, (g1, g2) in (("F", ("FF", "FM")), ("M", ("MF", "MM"))):
        ped.add(f"au_{side}", "F", father=g1, mother=g2)
        ped.add(f"sp_au_{side}", "M")
        ped.add(f"c_{side}", "M", father=f"sp_au_{side}", mother=f"au_{side}")
    # second cousins through each great-grandparent couple
    for g in gps:
        ped.add(f"ga_{g}", "M", father=g + "F", mother=g + "M")     # grand-aunt/uncle
        ped.add(f"sp_ga_{g}", "F")
        ped.add(f"p2_{g}", "F", father=f"ga_{g}", mother=f"sp_ga_{g}")
        ped.add(f"sp_p2_{g}", "M")
        ped.add(f"c2_{g}", "M", father=f"sp_p2_{g}", mother=f"p2_{g}")
    if twin_fathers:
        ped.add("uncle_twin", "M", twin_of="F")
        ped.add("sp_twin", "F")
        ped.add("twin_cousin", "M", father="uncle_twin", mother="sp_twin")
    ped.add("stranger", "F")          # an unrelated kit
    return ped


def ancestry(depth=4, siblings=1, relatives_per_couple=1, parent=True):
    """A full ancestry `depth` generations up from the siblings, with tested
    relatives through every ancestral couple: the test bed for the copy
    model.

    Ancestors are named by their lineage code from the siblings ("F",
    "FM", ..., founders at codes of length `depth`). For every ancestor c
    below the founders, the couple (c+"F", c+"M") gets `relatives_per_couple`
    other children, each with a line down to the siblings' generation:
    "rel_<c>_<i>", a (len(c) - 1)th cousin who shares DNA only through that
    couple, so the descent claim for them is "via c". Spouses marrying in
    are unnamed founders. The siblings are "sib1".., the parents "F" and
    "M" (`parent`: whether "M" is listed as a tester in DEEP_TESTERS).

    Returns (Pedigree, {relative: via code})."""
    ped = Pedigree()
    codes = [""]
    for k in range(1, depth + 1):
        codes += ["".join(t) for t in __import__("itertools").product("FM", repeat=k)]
    for c in sorted(codes[1:], key=len, reverse=True):         # founders first
        sex = "M" if c.endswith("F") else "F"
        if len(c) == depth:
            ped.add(c, sex)
    for c in sorted((c for c in codes[1:] if len(c) < depth), key=len, reverse=True):
        ped.add(c, "M" if c.endswith("F") else "F", father=c + "F", mother=c + "M")
    for i in range(1, siblings + 1):
        ped.add(f"sib{i}", "FM"[i % 2], father="F", mother="M")
    via = {}
    for c in (c for c in codes[1:] if len(c) < depth):
        for i in range(1, relatives_per_couple + 1):
            prev = f"rel_{c}_{i}_g0"
            ped.add(prev, "M" if i % 2 else "F", father=c + "F", mother=c + "M")
            for g in range(1, len(c) + 1):
                sp = f"sp_{c}_{i}_g{g}"
                ped.add(sp, "F" if ped.people[prev].sex == "M" else "M")
                kid = f"rel_{c}_{i}" if g == len(c) else f"rel_{c}_{i}_g{g}"
                f, m = (prev, sp) if ped.people[prev].sex == "M" else (sp, prev)
                ped.add(kid, "M" if (g + i) % 2 else "F", father=f, mother=m)
                prev = kid
            via[f"rel_{c}_{i}"] = c
    return ped, via


def _line(ped, top, generations, name, start_sex="F"):
    """A line of descent `generations` steps below `top`, each step with an
    unnamed founder spouse; the last person is `name`. Returns `name`."""
    prev = top
    for g in range(1, generations + 1):
        kid = name if g == generations else f"{name}_g{g}"
        sp = f"sp_{kid}"
        ped.add(sp, "F" if ped.people[prev].sex == "M" else "M")
        f, m = (prev, sp) if ped.people[prev].sex == "M" else (sp, prev)
        ped.add(kid, start_sex if g % 2 else "MF"[start_sex == "M"], father=f, mother=m)
        prev = kid
    return name


def grandmother(children=3, child_depth=1, father_side=2, mother_side=2, rel_depth=3,
                sisters=("full", "half"), sister_depth=2, siblings=3):
    """The test bed for recursive deduction (docs/genetics.md, "Recursive deduction"): the
    siblings' paternal grandmother G ("FM"), whose two own copies are to be
    split through her other descendants.

        G's parents "FMF" (her father) and "FMM" (her mother), each with
        their own parents as founders, so they have siblings;
        G married "FF" (a founder); their son "F" is the siblings' father,
        and `children` more children "gc<k>", each with a tested line
        `child_depth` steps down: "gline<k>" (1 = first cousin of the
        siblings, 2 = 1C1R);
        `father_side` tested relatives through G's father's sibling
        ("relP<i>", `rel_depth` steps below that sibling: 3 = third
        cousin), and `mother_side` through G's mother's sibling ("relM<i>");
        G's sisters with a tested line `sister_depth` steps down
        ("sis_<kind>_line"): "full" by FMF and FMM, "half" by FMM and an
        unrelated man "FMX".

    Returns (Pedigree, groups): groups maps each tested relative to
    "child", "P", "M" or "sister_full"/"sister_half"."""
    ped = Pedigree()
    for a in ("FMF", "FMM"):
        ped.add(a + "F", "M").add(a + "M", "F")
        ped.add(a, "M" if a.endswith("F") else "F", father=a + "F", mother=a + "M")
    ped.add("FMX", "M")
    ped.add("FM", "F", father="FMF", mother="FMM")
    ped.add("FF", "M")
    ped.add("F", "M", father="FF", mother="FM")
    ped.add("M", "F")
    for i in range(1, siblings + 1):
        ped.add(f"sib{i}", "FM"[i % 2], father="F", mother="M")
    groups = {}
    for k in range(1, children + 1):
        ped.add(f"gc{k}", "FM"[k % 2], father="FF", mother="FM")
        groups[_line(ped, f"gc{k}", child_depth, f"gline{k}")] = "child"
    for side, n in (("P", father_side), ("M", mother_side)):
        a = "FMF" if side == "P" else "FMM"
        for i in range(1, n + 1):
            ped.add(f"aunt{side}{i}", "F", father=a + "F", mother=a + "M")
            groups[_line(ped, f"aunt{side}{i}", rel_depth, f"rel{side}{i}")] = side
    for kind in sisters:
        ped.add(f"sis_{kind}", "F", father="FMF" if kind == "full" else "FMX", mother="FMM")
        groups[_line(ped, f"sis_{kind}", sister_depth, f"sis_{kind}_line")] = f"sister_{kind}"
    return ped, groups


def copy_labels(sim, sibs, seed=0, step_cm=0.5, error_runs=0):
    """What a phasing of these full siblings (with a tested parent) would
    give, from the truth: per sibling and parent, which of that parent's
    two copies the sibling carries (0/1), as runs like
    phasing_labels.copy_label_runs. The labels name no grandparent: per
    chromosome and parent, which copy is 0 is a coin flip. error_runs:
    that many short (1-3 cM) stretches per sibling with the label wrong,
    as a phasing would get near-coincident crossovers wrong."""
    rng = np.random.default_rng(seed)
    gm = sim.maps["average"]
    rows = []
    for c in sim.genomes[sibs[0]]["F"]:
        grid = np.arange(0, CHROM_CM[c], step_cm)
        for side in "FM":
            flip = int(rng.integers(2))
            for s in sibs:
                lab = np.array([("FM".index(sim.lineage(s, c, float(gm.bp(c, x)))["FM".index(side)][1])) ^ flip
                                for x in grid])
                for _ in range(error_runs):
                    a = rng.uniform(0, CHROM_CM[c] - 3)
                    sel = (grid >= a) & (grid <= a + rng.uniform(1, 3))
                    lab[sel] ^= 1
                starts = np.flatnonzero(np.r_[True, lab[1:] != lab[:-1]])
                ends = np.r_[starts[1:], len(lab)] - 1
                for i, j in zip(starts, ends):
                    rows.append(dict(chrom=c, sibling=s, parent=side, start=float(gm.bp(c, grid[i])),
                                     end=float(gm.bp(c, grid[j] + step_cm * 0.999)), label=int(lab[i]),
                                     block=0, snps=int(j - i + 1)))
    return pd.DataFrame(rows)


SCENARIOS = {
    # name: (testers whose kits we hold, matches they are compared with)
    "single donor": (["sib1"], None),
    "donor + parent": (["sib1", "M"], None),
    "twin cousin": (["sib1", "twin_cousin"], None),
    "three siblings + parent": (["sib1", "sib2", "sib3", "M"], None),
    "unrelated kit": (["sib1", "stranger"], None),
}
RELATIVES = ["c_F", "c_M", "c2_FF", "c2_FM", "c2_MF", "c2_MM"]


def scenario(name, seed=0, **detect_kw):
    """(simulation, segments) for a named data situation. Every tester is
    compared with the others and with the tested relatives (RELATIVES)."""
    testers, _ = SCENARIOS[name]
    ped = family(twin_fathers=("twin_cousin" in testers))
    sim = simulate(ped, seed=seed)
    segs = detect(sim, testers, seed=seed, matches=testers + RELATIVES, **detect_kw)
    return sim, segs


def relationship_cm(up_a, up_b, half=False, n=500, seed=0, min_cm=7.0):
    """Total detected cM between two people `up_a` and `up_b` generations
    below a common ancestor (a couple, or one person when `half`), over n
    simulated families: what a vendor would list (noisy ends, false
    segments, the min_cm threshold), conditioned on being listed as a
    match (total > 0). up_a = 0 makes A the ancestor (half is then moot).
    The relationship distributions behind relationship_check.odds."""
    ped = Pedigree()
    ped.add("c1", "M").add("c2", "F")
    top_f, top_m = ("c1", "c2") if not half or up_a == 0 or up_b == 0 else ("c1", "s0")
    if half and up_a and up_b:
        ped.add("s0", "F")

    def line(tag, gens):
        if gens == 0:
            return "c1"
        prev = None
        for g in range(gens):
            name = f"{tag}{g}"
            if g == 0:
                f, m = ("c1", "c2") if tag == "a" else (top_f, top_m)
            else:
                ped.add(f"{name}x", "F")
                f, m = prev, f"{name}x"
            ped.add(name, "M", father=f, mother=m)
            prev = name
        return prev
    a, b = line("a", up_a), line("b", up_b)
    out = []
    for i in range(n):
        sim = simulate(ped, seed=seed * 100003 + i)
        segs = detect(sim, testers=[a], matches=[b], seed=seed * 100003 + i, min_cm=min_cm, join=True)
        tot = _union_cm(segs)
        if tot > 0:
            out.append(tot)
    return np.array(out)


def _union_cm(segs):
    """Total length covered by the segments, as vendors count it: a
    stretch shared on both copies (full siblings) counts once."""
    tot = 0.0
    for _, g in segs.groupby("chrom"):
        end = -1.0
        for a, b, cm in sorted(zip(g.start, g.end, g.cM)):
            if b <= end:
                continue
            tot += cm * (b - max(a, end)) / (b - a) if a < end else cm
            end = b
    return tot
