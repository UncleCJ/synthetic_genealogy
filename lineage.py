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


# Colours: one scheme for every view (CJ's sketch, 2026-11-13). Hue says
# where in the tree: every code owns a sector of the HSL hue wheel holding
# all its ancestors' sectors. F starts at 225 and M at 45, each 180 wide;
# going clockwise (hue falling) a person keeps the first OWN_SHARE of their
# sector, the same-sex parent takes the next half of the rest and the other
# parent the last half, so the straight lines stay opposite on the wheel.
# The share grows with the generation, leaving hue room for the far ones;
# past the listed generations the last share repeats. Lightness (OKLCH) says
# how far back: older generations fade towards the background. Within a
# couple the father is a step darker and the mother a step lighter, which
# keeps them apart where their hues are degrees apart. Tuned by eye in a
# fan chart; unvalidated beyond five generations.
OWN_SHARE = (0.07, 0.16, 0.28, 0.42)    # kept by parents, grandparents, ...
LIGHT = {False: (0.48, 0.085, 0.88), True: (0.80, -0.075, 0.38)}  # start, step, limit
COUPLE_STEP, CHROMA, CHROMA_FADE = 0.035, 0.17, 0.12
# dark yellows read as brown: lift lightness around OKLCH hue 95 (light theme)
YELLOW_LIFT, YELLOW_HUE = 0.20, 95.0


def hue_sector(code):
    """(start, width) in hue degrees; None for the proband ("")."""
    if not code:
        return None
    a, w = {"F": 225.0, "M": 45.0}[code[0]], 180.0
    for g, (prev, c) in enumerate(zip(code, code[1:])):
        p = OWN_SHARE[min(g, len(OWN_SHARE) - 1)]
        q = (1 - p) / 2
        a -= w * (p if c == prev else p + q)
        w *= q
    return a % 360, w


def _lin(v):
    return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4


def _oklab_hue(hsl_hue):
    """The OKLCH hue (radians) of the full-saturation HSL colour at hsl_hue."""
    import colorsys
    import math
    r, g, b = (_lin(v) for v in colorsys.hls_to_rgb(hsl_hue / 360, 0.5, 1.0))
    l, m, s = (math.copysign(abs(x) ** (1 / 3), x) for x in (
        0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b,
        0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b,
        0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b))
    return math.atan2(0.0259040371 * l + 0.7827717662 * m - 0.8086757660 * s,
                      1.9779984951 * l - 2.4285922050 * m + 0.4505937099 * s)


def _oklch_rgb(L, C, h):
    import math
    a, b = C * math.cos(h), C * math.sin(h)
    l, m, s = ((L + 0.3963377774 * a + 0.2158037573 * b) ** 3,
               (L - 0.1055613458 * a - 0.0638541728 * b) ** 3,
               (L - 0.0894841775 * a - 1.2914855480 * b) ** 3)
    return (4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s,
            -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
            -0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s)


def color(code, dark=False, pale=False):
    """Hex colour for a code (grey for the proband or no code); pale for
    backdrops behind the full colours."""
    sec = hue_sector(code)
    if sec is None:
        return "#8f8a80"
    g = len(code)
    start, step, limit = LIGHT[dark]
    L = min(start + step * (g - 1), limit) if step > 0 else max(start + step * (g - 1), limit)
    if g > 1:
        L += COUPLE_STEP * (-1 if code[-1] == "F" else 1)
    C = max(CHROMA * (1 - CHROMA_FADE * (g - 1)), 0.03)
    if pale:
        L, C = (0.30, 0.05) if dark else (0.92, 0.05)
    h = _oklab_hue(sec[0])
    if not dark and not pale:
        import math
        L = min(L + YELLOW_LIFT * max(0.0, math.cos(h - math.radians(YELLOW_HUE))) ** 6, 0.9)
    while C > 0 and not all(-1e-4 <= v <= 1 + 1e-4 for v in _oklch_rgb(L, C, h)):
        C -= 0.004
    rgb = _oklch_rgb(L, max(C, 0.0), h)
    enc = (12.92 * v if v <= 0.0031308 else 1.055 * v ** (1 / 2.4) - 0.055 for v in rgb)
    return "#%02x%02x%02x" % tuple(round(min(max(v, 0.0), 1.0) * 255) for v in enc)


def css_vars(dark=False, codes=("F", "M") + GRANDPARENTS):
    """CSS custom properties ("--FF:#...;...") for the views' :root."""
    return ";".join(f"--{c}:{color(c, dark)}" for c in codes)
