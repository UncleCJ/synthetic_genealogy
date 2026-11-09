"""
Automated visual phasing for three full siblings: a conceptual sketch.

Idea
----
At every position on a chromosome, each sibling carries one of dad's two
copies and one of mum's two copies. Those copies are themselves the
grandparents' DNA, so "which copy" means "which grandparent".

The manual visual phasing method compares sibling pairs (FIR / HIR / NIR)
and reasons that when a crossover happens in sibling X, both comparisons
involving X change while the third pair stays the same. That reasoning is
exactly a hidden Markov model over "inheritance vectors" (the Lander-Green
algorithm). We let a Viterbi decoder do the bookkeeping.

Hidden state (16 values), relative to sibling 1:
    dA2, dA3 : did sib 2 / sib 3 get the OTHER side-A copy than sib 1?
    dB2, dB3 : same for side B
Side A/B rather than paternal/maternal: from siblings alone the two
parents are indistinguishable on autosomes. Labelling needs outside
evidence (e.g. shared matches with known paternal or maternal cousins).

First run 2026-11-08 on three FTDNA sibling kits (see TEMPER below);
phasing_labels.py names the sides and grandparents from a parent's kit
and DNA Painter assertions.
"""
import gzip
import itertools
import numpy as np
import pandas as pd

SIBS = ["sib1", "sib2", "sib3"]   # replaced by run() with your donor keys
EPS = 0.005   # per-genotype error rate
# Emissions are raised to this power. Neighbouring SNPs are in linkage
# disequilibrium and q = 0.5 overstates how informative each SNP is, so
# untempered evidence is overcounted: on three FTDNA sibling kits (596k
# shared SNPs) TEMPER = 1 gave 321 crossovers with ~60 spurious <2 Mb double
# flips; 0.3 gave 183 (expected ~205 for three children) and 2.
TEMPER = 0.3

# --------------------------------------------------------------------------
# 1. Load and harmonise raw data
# --------------------------------------------------------------------------
def load_raw(path, name):
    """Raw genotype files, plain or gzipped, format detected from the header.
    Validated: FTDNA Family Finder ("Autosomal_o37", build 37): unquoted
    RSID,CHROMOSOME,POSITION,RESULT, including legacy Y markers at
    chromosome 0 position 0 and no-calls '--'. From documentation only:
    MyHeritage (same columns, quoted, '#' comment lines first), 23andMe
    ('# rsid<TAB>chromosome<TAB>position<TAB>genotype'), AncestryDNA
    (rsid, chromosome, position, allele1, allele2)."""
    opener = gzip.open if str(path).endswith(".gz") else open
    with opener(path, "rt", encoding="utf-8-sig") as f:
        for i, line in enumerate(f):         # header: first line that starts with rsid
            if line.lstrip("#\" ").lower().startswith("rsid"):
                break
    sep = "\t" if "\t" in line else ","
    df = pd.read_csv(path, sep=sep, skiprows=i, dtype=str, encoding="utf-8-sig")
    df.columns = [c.strip().strip('"').lstrip("# ").lower() for c in df.columns]
    if "result" in df or "genotype" in df:           # FTDNA, MyHeritage, 23andMe
        g = df.get("result", df.get("genotype")).str.strip()
        df["a1"], df["a2"] = g.str[0], g.str[1]
    df = df.rename(columns={"allele1": "a1", "allele2": "a2", "position": "pos",
                            "chromosome": "chrom"})
    df["chrom"] = df["chrom"].str.strip().replace({"23": "X", "25": "X"})
    autosomal_or_x = df["chrom"].isin([str(c) for c in range(1, 23)] + ["X"])
    called = df.a1.isin(list("ACGT")) & df.a2.isin(list("ACGT"))   # drops '--', indels
    keep = autosomal_or_x & called
    print(f"{name}: {len(df)} rows, {(~autosomal_or_x).sum()} off-autosome "
          f"(e.g. legacy Y markers at chromosome 0), "
          f"{(autosomal_or_x & ~called).sum()} no-calls, {keep.sum()} kept")
    df = df[keep].assign(pos=lambda d: pd.to_numeric(d["pos"]))
    return df.set_index("rsid")[["chrom", "pos", "a1", "a2"]].add_suffix(f"_{name}")

def merge_sibs(paths):
    dfs = [load_raw(p, n) for p, n in zip(paths, SIBS)]
    m = dfs[0].join(dfs[1:], how="inner")          # only SNPs all chips share
    # Kits from different vendors or chip versions overlap only partly
    # (an older FTDNA chip vs MyHeritage's newer one may share a minority).
    print(f"shared by all {len(dfs)}: {len(m)} of " +
          ", ".join(f"{n}={len(d)}" for n, d in zip(SIBS, dfs)))
    m["chrom"], m["pos"] = m[f"chrom_{SIBS[0]}"], m[f"pos_{SIBS[0]}"]
    return m.sort_values(["chrom", "pos"])

def encode(m):
    """Return (N, 3) alt-allele counts, keeping only biallelic,
    polymorphic SNPs (monomorphic ones carry no information)."""
    cols = [f"{a}_{s}" for s in SIBS for a in ("a1", "a2")]
    alleles = m[cols].to_numpy()
    n_alleles = pd.DataFrame(alleles).nunique(axis=1).to_numpy()
    keep = n_alleles == 2
    ref = alleles[:, 0]
    geno = (alleles != ref[:, None]).reshape(-1, 3, 2).sum(-1)
    return m[keep], geno[keep]

# --------------------------------------------------------------------------
# 2. Model: states, allele configurations, predicted genotypes
# --------------------------------------------------------------------------
STATES = list(itertools.product([0, 1], repeat=4))    # (dA2, dA3, dB2, dB3)
# Alleles (0/1) on the four parental copies (A0, A1, B0, B1),
# where A0/B0 are the copies sibling 1 received.
CONFIGS = np.array(list(itertools.product([0, 1], repeat=4)))

def build_predictions():
    pred = np.zeros((16, 16, 3), dtype=int)
    for s, (a2, a3, b2, b3) in enumerate(STATES):
        a_copy, b_copy = (0, a2, a3), (0, b2, b3)
        for c, (A0, A1, B0, B1) in enumerate(CONFIGS):
            A, B = (A0, A1), (B0, B1)
            pred[s, c] = [A[a_copy[k]] + B[b_copy[k]] for k in range(3)]
    return pred

PRED = build_predictions()    # PRED[state, config] -> genotypes of 3 sibs

def emissions(geno, q):
    """P(observed genotypes | state), summing over unknown parental alleles.
    q = alt allele frequency per SNP (from a reference panel such as
    1000 Genomes; 0.5 everywhere is a crude fallback)."""
    match = geno[:, None, None, :] == PRED[None]                # N,16,16,3
    lik = np.where(match, 1 - EPS, EPS / 2).prod(-1)            # N,16,16
    qq = q[:, None, None]
    prior = np.where(CONFIGS[None] == 1, qq, 1 - qq).prod(-1)   # N,16
    return ((lik * prior[:, None, :]).sum(-1)) ** TEMPER        # N,16

def parent_factor(mg):
    """Optional tested parent (taken as side B): P(her genotype | config),
    (N, 16). mg = her alt-allele count per SNP, NaN where missing or not
    one of the siblings' two alleles."""
    pred = CONFIGS[:, 2] + CONFIGS[:, 3]                         # B0 + B1
    f = np.where(mg[:, None] == pred[None], 1 - EPS, EPS / 2)
    return np.where(np.isnan(mg)[:, None], 1.0, f)


def emissions_with_parent(geno, q, mg):
    match = geno[:, None, None, :] == PRED[None]
    lik = np.where(match, 1 - EPS, EPS / 2).prod(-1) * parent_factor(mg)[:, None, :]
    qq = q[:, None, None]
    prior = np.where(CONFIGS[None] == 1, qq, 1 - qq).prod(-1)
    return ((lik * prior[:, None, :]).sum(-1)) ** TEMPER


# Optional evidence that two siblings carry the SAME copy of one side over
# an interval (a segment both share end to end with one match). Each merged
# interval adds log(IBD_LAMBDA) in total, spread over its SNPs, against the
# states where the two differ on that side. Soft: a false shared segment
# (pile-up) costs no more than this.
IBD_LAMBDA = 20.0


def _differs(i, j, side):
    """(16,) bool: states where sibs i and j carry different copies of side."""
    out = np.zeros(16, bool)
    for s, (a2, a3, b2, b3) in enumerate(STATES):
        c = (0, a2, a3) if side == "A" else (0, b2, b3)
        out[s] = c[i] != c[j]
    return out


def apply_ibd(E, pos, intervals):
    """intervals: iterable of (i, j, side, start, end) for this chromosome."""
    logE = np.log(E + 1e-300)
    for i, j, side, start, end in intervals:
        inside = (pos >= start) & (pos <= end)
        n = inside.sum()
        if n == 0:
            continue
        logE[np.ix_(inside, _differs(i, j, side))] -= np.log(IBD_LAMBDA) / n
    return np.exp(logE)


def side_transition(r):
    """4x4 transition for one side's (d2, d3) bits. Each of the three
    meioses flips with prob r. A flip in sib 1 flips BOTH relative bits,
    a flip in sib 2 or 3 flips only its own: the visual phasing rule."""
    T = np.zeros((4, 4))
    for f1, f2, f3 in itertools.product([0, 1], repeat=3):
        p = np.prod([r if f else 1 - r for f in (f1, f2, f3)])
        for a in range(4):
            d2, d3 = a >> 1, a & 1
            T[a, ((d2 ^ f1 ^ f2) << 1) | (d3 ^ f1 ^ f3)] += p
    return T

def haldane(d_cm):
    return 0.5 * (1 - np.exp(-2 * np.clip(d_cm, 1e-8, None) / 100))

# --------------------------------------------------------------------------
# 3. Decode the most likely inheritance path along a chromosome
# --------------------------------------------------------------------------
def viterbi(E, cm):
    N = len(E)
    logE = np.log(E + 1e-300)
    r = haldane(np.diff(cm))
    V = np.log(np.full(16, 1 / 16)) + logE[0]
    back = np.zeros((N, 16), dtype=int)
    for i in range(1, N):
        T = side_transition(r[i - 1])
        scores = V[:, None] + np.log(np.kron(T, T))   # sides independent
        back[i] = scores.argmax(0)
        V = scores.max(0) + logE[i]
    path = np.empty(N, dtype=int)
    path[-1] = V.argmax()
    for i in range(N - 1, 0, -1):
        path[i - 1] = back[i, path[i]]
    return path

# --------------------------------------------------------------------------
# 4. Interpret: pairwise FIR/HIR/NIR, crossover attribution, painting
# --------------------------------------------------------------------------
def pairwise_view(path):
    """The classic visual phasing chart, derived from the decoded states."""
    S = np.array([STATES[s] for s in path])
    copies_A = np.stack([np.zeros(len(S), int), S[:, 0], S[:, 1]], 1)
    copies_B = np.stack([np.zeros(len(S), int), S[:, 2], S[:, 3]], 1)
    label = {2: "FIR", 1: "HIR", 0: "NIR"}
    out = {}
    for i, j in itertools.combinations(range(3), 2):
        shared = (copies_A[:, i] == copies_A[:, j]).astype(int) + \
                 (copies_B[:, i] == copies_B[:, j])
        out[f"{SIBS[i]}-{SIBS[j]}"] = [label[x] for x in shared]
    return pd.DataFrame(out)

def crossovers(path, pos):
    who_by_flip = {(1, 1): SIBS[0], (1, 0): SIBS[1], (0, 1): SIBS[2]}
    events = []
    for i in np.flatnonzero(path[1:] != path[:-1]) + 1:
        a, b = np.array(STATES[path[i - 1]]), np.array(STATES[path[i]])
        for side, sl in (("A", slice(0, 2)), ("B", slice(2, 4))):
            who = who_by_flip.get(tuple(a[sl] ^ b[sl]))
            if who:
                events.append((pos[i - 1], pos[i], who, side))
    return pd.DataFrame(events, columns=["after_bp", "before_bp",
                                         "sibling", "side"])

def paint_grandparents(path):
    """For each sibling and side: 0/1 = which grandparent. Which of the two
    is grandpa vs grandma is arbitrary until anchored by a cousin match."""
    S = np.array([STATES[s] for s in path])
    out = {}
    for side, (c2, c3) in (("A", (0, 1)), ("B", (2, 3))):
        sib1_flip = (np.diff(S[:, c2]) != 0) & (np.diff(S[:, c3]) != 0)
        g = np.concatenate([[0], np.cumsum(sib1_flip) % 2])
        out[(SIBS[0], side)] = g
        out[(SIBS[1], side)] = g ^ S[:, c2]
        out[(SIBS[2], side)] = g ^ S[:, c3]
    return pd.DataFrame(out)

def reconstruct_parental_alleles(geno, path):
    """Where the decoded state pins down an allele uniquely, recover it.
    Columns A0, A1, B0, B1 (relative to sib 1); NaN where ambiguous.
    Remap with paint_grandparents() to get per-grandparent haplotypes."""
    ok = (geno[:, None, :] == PRED[path]).all(-1)         # N,16 consistent
    hap = np.full((len(geno), 4), np.nan)
    for j in range(4):
        has0 = (ok & (CONFIGS[None, :, j] == 0)).any(1)
        has1 = (ok & (CONFIGS[None, :, j] == 1)).any(1)
        hap[has0 & ~has1, j], hap[has1 & ~has0, j] = 0, 1
    return hap

# --------------------------------------------------------------------------
# 5. Pipeline
# --------------------------------------------------------------------------
def run(donor_files, genetic_map=None, parent=None, ibd=None):
    """donor_files: {donor key: raw data path} for exactly three full
    siblings, keys matching the donor registry used by segments_io.
    parent: load_raw() output of one tested parent, used in the model as
    side B (so B is that parent's side). ibd: DataFrame with sib_a, sib_b
    (donor keys), side ("A"/"B"), chrom, start, end: evidence that two
    siblings carry the same copy there (see apply_ibd)."""
    global SIBS
    SIBS = list(donor_files)
    m = merge_sibs(list(donor_files.values()))
    if parent is not None:
        pm = parent.reindex(m.index)
        m["pa1"], m["pa2"] = pm.iloc[:, 2].to_numpy(), pm.iloc[:, 3].to_numpy()
    results = {}
    for chrom, chunk in m.groupby("chrom"):
        if chrom in ("X", "Y", "MT"):
            continue                      # X needs its own sex-aware model
        chunk, geno = encode(chunk)
        pos = chunk["pos"].to_numpy()
        # cM positions: interpolate from a real map (e.g. HapMap GRCh37);
        # 1 cM per Mb is a rough fallback
        cm = (np.interp(pos, genetic_map[chrom].bp, genetic_map[chrom].cm)
              if genetic_map else pos / 1e6)
        q = np.full(len(pos), 0.5)
        if parent is not None:
            ref = chunk[f"a1_{SIBS[0]}"].to_numpy()
            alleles = chunk[[f"{a}_{s}" for s in SIBS for a in ("a1", "a2")]].to_numpy()
            alt = np.where(alleles[:, 0:1] != alleles, alleles, "").max(1)   # the other allele
            pa1, pa2 = chunk["pa1"].to_numpy(), chunk["pa2"].to_numpy()
            ok = np.isin(pa1, ["A", "C", "G", "T"]) & ((pa1 == ref) | (pa1 == alt)) \
                & ((pa2 == ref) | (pa2 == alt))
            mg = np.where(ok, (pa1 != ref).astype(float) + (pa2 != ref), np.nan)
            E = emissions_with_parent(geno, q, mg)
        else:
            E = emissions(geno, q)
        if ibd is not None and len(ibd):
            idx = {k: n for n, k in enumerate(SIBS)}
            iv = ibd[ibd.chrom.astype(str) == str(chrom)]
            E = apply_ibd(E, pos, [(idx[r.sib_a], idx[r.sib_b], r.side, r.start, r.end)
                                   for r in iv.itertuples()])
        path = viterbi(E, cm)
        results[chrom] = dict(
            pos=pos, path=path, geno=geno, rsid=chunk.index.to_numpy(),
            ref=chunk[f"a1_{SIBS[0]}"].to_numpy(),   # allele counted as 0
            pairwise=pairwise_view(path),
            crossovers=crossovers(path, pos),
            painting=paint_grandparents(path),
            haplotypes=reconstruct_parental_alleles(geno, path),
        )
    return results