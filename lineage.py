"""
Lineage codes: paths up the tree from a proband, one letter per step,
F for father and M for mother. "FM" is the father's mother, "MFF" the
mother's father's father. A code addresses a path, not a person: under
pedigree collapse one person has several codes.

Codes are kept at full depth wherever they are known; GRANDPARENTS and
grandparent() are for the places that work at grandparent level
(the phasing, today's placement), not a reason to truncate stored codes.

    ahnentafel("FMMF") == 22      father 2n, mother 2n + 1, proband 1
    from_ahnentafel(22) == "FMMF"
    common_prefix(["FMF", "FMM"]) == "FM"
    via(codes)                    the deepest node shared DNA must pass:
                                  a couple MRCA ("FMF", "FMM") -> "FM"
    is_couple_split(a, b)         DNA split over both grandparents of one side
"""
GRANDPARENTS = ("FF", "FM", "MF", "MM")
OTHER = {"FF": "FM", "FM": "FF", "MF": "MM", "MM": "MF"}
# a match descending from a grandparent couple shares DNA on both of its
# grandparents: at least this share of the pair, and this much in all
COUPLE_MIN_SHARE, COUPLE_MIN_CM = 0.25, 100.0


def ahnentafel(code):
    n = 1
    for c in code or "":
        n = 2 * n + (c == "M")
    return n


def from_ahnentafel(n):
    n, out = int(n), ""
    while n > 1:
        out = "FM"[n % 2] + out
        n //= 2
    return out


def common_prefix(codes):
    codes = [c for c in codes if c is not None]
    if not codes:
        return ""
    p = codes[0]
    for c in codes[1:]:
        while not c.startswith(p):
            p = p[:-1]
    return p


def via(codes):
    """The deepest code every path in `codes` passes through (their common
    prefix). For the two codes of a couple MRCA it is the couple's child on
    the proband's line."""
    return common_prefix(list(codes))


def split(text):
    """Codes from a space-separated string ("FMF FMM" -> ["FMF", "FMM"])."""
    return [c for c in str(text or "").split() if c]


def grandparent(code):
    """The grandparent-level part of a code ("" if shallower)."""
    return code[:2] if code and len(code) >= 2 else ""


def side(code):
    return code[:1] if code else ""


def is_couple_split(a, b, min_share=COUPLE_MIN_SHARE, min_cm=COUPLE_MIN_CM):
    """True if a and b cM (the two grandparents of one side) look like DNA
    from the grandparent couple, not from one of them."""
    return a + b >= min_cm and min(a, b) / (a + b) >= min_share
