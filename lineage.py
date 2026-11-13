"""Lineage codes: paths up the tree from a proband, one letter per step,
F for father and M for mother ("MFF" is the mother's father's father).

Codes are kept at full depth; GRANDPARENTS and grandparent() are for the
places that work at grandparent level, not a reason to truncate stored codes.

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


# Colours: one hue scheme for every view (sketched 2026-11-13 on an HSL
# wheel). Every code owns a hue sector holding all its ancestors' sectors,
# so a branch is a hue range. F starts at 225 and M at 45, each 180 wide;
# going clockwise (hue falling) a person keeps the first third, the
# same-sex parent takes the second, the other parent the last. The swatch
# sits at the sector's start. Unvalidated past great-grandparents: from
# there the own band is 2.2 degrees and hue alone no longer tells codes apart.
SATURATION, LIGHTNESS = 0.62, {False: 0.40, True: 0.64}   # by dark theme


def hue_sector(code):
    """(start, width) in hue degrees; None for the proband ("")."""
    if not code:
        return None
    a, w = {"F": 225.0, "M": 45.0}[code[0]], 180.0
    for prev, c in zip(code, code[1:]):
        a -= w / 3 * (1 if c == prev else 2)
        w /= 3
    return a % 360, w


def color(code, dark=False, pale=False):
    """Hex colour for a code (grey for the proband or no code)."""
    import colorsys
    sec = hue_sector(code)
    if sec is None:
        return "#8f8a80"
    l, s = LIGHTNESS[dark], SATURATION
    if pale:
        l, s = (0.30, 0.35) if dark else (0.86, 0.45)
    r, g, b = colorsys.hls_to_rgb(sec[0] / 360, l, s)
    return "#%02x%02x%02x" % tuple(round(x * 255) for x in (r, g, b))


def css_vars(dark=False, codes=("F", "M") + GRANDPARENTS):
    """CSS custom properties ("--FF:#...;...") for the views' :root."""
    return ";".join(f"--{c}:{color(c, dark)}" for c in codes)
