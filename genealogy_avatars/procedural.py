"""Offline, deterministic cartoon portraits as SVG.

The 'medium' follows the era so a tree reads like an album:
  baroque/georgian -> painted oil portrait in a gilded oval frame
  victorian        -> sepia cabinet card
  early20          -> black-and-white snapshot with white border
  modern           -> full colour circle
Same Person.id -> same face, whatever else changes.
"""
from __future__ import annotations
import math
import random
from .person import Person

STYLE_VERSION = "proc-1"

SKIN = ["#ffe0c9", "#f9d2b4", "#f1c27d", "#e0ac69", "#c68642", "#8d5524"]
HAIR = ["#2c1b10", "#4a2e1d", "#6b4226", "#8b5a2b", "#b8875a", "#d9b679", "#a23b1e"]
CLOTH_DARK = ["#1f2a44", "#2e2e2e", "#3d2b1f", "#2f3e2f", "#4a1f2a"]
CLOTH_BRIGHT = ["#e76f51", "#2a9d8f", "#e9c46a", "#457b9d", "#9b5de5", "#f28482", "#6a994e"]
PASTEL = ["#fde2e4", "#e2ece9", "#dfe7fd", "#fff1c1", "#e8dff5", "#d8f3dc"]

SEPIA = "0.393 0.769 0.189 0 0 0.349 0.686 0.168 0 0 0.272 0.534 0.131 0 0 0 0 0 1 0"
GREY = "0.3 0.59 0.11 0 0 0.3 0.59 0.11 0 0 0.3 0.59 0.11 0 0 0 0 0 1 0"


def _chance(r: random.Random, p: float) -> bool:
    return r.random() < p


def render(p: Person, size: int = 200, traits: dict | None = None,
           evidence: int | None = None, side: float | None = None, observed: dict | None = None) -> str:
    """traits: render parameters from traits.to_render() (overrides the random face).
    evidence: 0-3 dots (3 = photographed, 2 = well inferred, 1 = weak, 0 = guess).
    side: 0..1 share of resemblance to the father's side, drawn as a blue/orange bar.
    observed: what a photo shows directly and isn't inherited: {"skin": hex, "hair": hex,
              "glasses": "round"|"rect"|None, "smile": "open"|"closed"}."""
    observed = observed or {}
    r = random.Random(p.seed())
    uid = f"a{p.seed() % 10**8}"
    era, sex, age = observed.get("era") or p.era, p.sex.upper()[:1] or "U", p.portrait_age

    # Draw the random numbers in a fixed order so a face stays stable.
    skin = r.choice(SKIN)
    hair = r.choice(HAIR)
    rx, ry = r.uniform(31, 36), r.uniform(37, 42)
    es, er, nl, mw = 13.0, 3.3, 11.0, 10.0          # eye spacing/size, nose length, mouth half-width
    bg = r.choice(PASTEL)
    dark, bright = r.choice(CLOTH_DARK), r.choice(CLOTH_BRIGHT)
    rolls = [r.random() for _ in range(8)]  # reserved dice for feature choices
    brow = rolls[2] * 2
    if traits:
        skin, hair = traits["skin"], traits["hair"]
        rx, ry, es, er, nl, mw, brow = (traits[k] for k in ("rx", "ry", "es", "er", "nl", "mw", "brow"))
    if age >= 72:
        hair = "#ececec"
    elif age >= 55:
        hair = "#b9b9b9"
    if "face_aspect" in observed:          # face length / width measured on the photo
        rx = max(28.0, min(39.0, ry / observed["face_aspect"]))
    bright = observed.get("cloth", bright)
    skin = observed.get("skin", skin)
    hair = observed.get("hair", hair)       # a photo beats both inheritance and age rules

    ghost = sex not in ("M", "F") and era == "unknown"   # nothing known: placeholder silhouette
    out: list[str] = []
    add = out.append

    # ---- clothing / shoulders -------------------------------------------
    shoulders = "M28,205 C32,152 70,138 100,138 C130,138 168,152 172,205 Z"
    add(f'<rect x="88" y="112" width="24" height="30" fill="{skin}"/>')
    add('<rect x="88" y="112" width="24" height="10" fill="#000" opacity=".08"/>')
    if ghost:
        add(f'<path d="{shoulders}" fill="#9aa0a6"/>')
    elif sex not in ("M", "F"):   # sex unknown but era known: neutral clothes
        add(f'<path d="{shoulders}" fill="{bright if era == "modern" else dark}"/>')
    elif sex == "M":
        coat = bright if era == "modern" else dark
        add(f'<path d="{shoulders}" fill="{coat}"/>')
        if era in ("baroque", "georgian"):
            add('<path d="M88,138 L112,138 L106,170 Q100,176 94,170 Z" fill="#fbfaf5"/>')
            add('<path d="M94,150 Q100,156 106,150 M93,160 Q100,166 107,160" '
                'stroke="#d6d2c4" fill="none" stroke-width="1.5"/>')
        elif era == "victorian":
            add('<path d="M86,136 L100,150 L114,136 L114,146 L100,158 L86,146 Z" fill="#fbfaf5"/>')
            add('<path d="M91,152 L100,157 L109,152 L109,162 L100,157 L91,162 Z" fill="#111"/>')
        elif era in ("early20", "unknown"):
            add('<path d="M84,138 L100,175 L116,138 Z" fill="#f4f4f4"/>')
            add(f'<path d="M97,146 L103,146 L105,175 L100,180 L95,175 Z" fill="{bright}"/>')
            add(f'<path d="M84,138 L100,175 L76,160 Z M116,138 L100,175 L124,160 Z" fill="{dark}" '
                'stroke="#000" stroke-opacity=".25"/>')
        else:  # modern
            if observed.get("suit"):                         # dark suit, white shirt, tie, pocket square
                add('<path d="M84,138 L100,178 L116,138 Z" fill="#f4f4f4"/>')
                add(f'<path d="M97,146 L103,146 L105,178 L100,184 L95,178 Z" fill="{observed.get("tie", "#141414")}"/>')
                add(f'<path d="M84,138 L100,178 L74,162 Z M116,138 L100,178 L126,162 Z" fill="{_shade(bright, 1.4)}"/>')
                if observed.get("pocket_square", True):
                    sq = observed["pocket_square"] if isinstance(observed.get("pocket_square"), str) else "#f4f4f4"
                    add(f'<path d="M128,172 L142,170 L139,176 L131,177 Z" fill="{sq}"/>')
            if observed.get("plaid"):                        # checked shirt with a button-down collar
                pc = observed["plaid"]
                add(f'<clipPath id="{uid}q"><path d="{shoulders}"/></clipPath><g clip-path="url(#{uid}q)" stroke="{pc}">'
                    + "".join(f'<path d="M{x},130 L{x},210" stroke-width="{2.2 if x % 24 == 0 else 1}"/>' for x in range(28, 176, 8))
                    + "".join(f'<path d="M20,{y} L180,{y}" stroke-width="{2.2 if y % 24 == 0 else 1}" stroke-opacity=".6"/>' for y in range(140, 210, 8))
                    + '</g>')
                add(f'<path d="M86,137 L100,150 L92,158 Z M114,137 L100,150 L108,158 Z" fill="{bright}" stroke="{pc}" stroke-width=".8"/>')
            if observed.get("stripes"):
                add(f'<clipPath id="{uid}s"><path d="{shoulders}"/></clipPath><g clip-path="url(#{uid}s)" '
                    f'stroke="{observed["stripes"]}" stroke-width="2.6">'
                    + "".join(f'<path d="M20,{y} L180,{y}"/>' for y in range(146, 206, 7)) + '</g>')
            add('<path d="M86,138 Q100,152 114,138" fill="none" stroke="#000" stroke-opacity=".2" stroke-width="3"/>')
    else:  # F
        if era in ("baroque", "georgian"):
            add(f'<path d="{shoulders}" fill="{dark}"/>')
            add('<path d="M50,160 Q100,130 150,160 Q100,190 50,160 Z" fill="#fbfaf5"/>')  # fichu
        elif era == "victorian":
            add(f'<path d="{shoulders}" fill="{dark}"/>')
            add(f'<rect x="88" y="124" width="24" height="16" fill="{dark}"/>')        # high neck
            add('<circle cx="100" cy="146" r="5" fill="#d4af37" stroke="#7a5c12"/>')   # brooch
        elif era in ("early20", "unknown"):
            add(f'<path d="{shoulders}" fill="{bright}"/>')
            add('<path d="M86,137 L100,150 L92,156 Z M114,137 L100,150 L108,156 Z" fill="#fbfaf5"/>')
        else:
            add(f'<path d="{shoulders}" fill="{bright}"/>')
            if observed.get("pattern"):                      # floral print: scattered blobs
                rr = random.Random(p.seed() + 1)
                add(f'<clipPath id="{uid}p"><path d="{shoulders}"/></clipPath><g clip-path="url(#{uid}p)">'
                    + "".join(f'<circle cx="{rr.uniform(28, 172):.0f}" cy="{rr.uniform(140, 205):.0f}" '
                              f'r="{rr.uniform(4, 9):.1f}" fill="{rr.choice(observed["pattern"])}" opacity=".85"/>'
                              for _ in range(26)) + '</g>')
            if observed.get("blouse"):                       # light blouse under a darker top
                add(f'<path d="M84,138 L100,170 L116,138 Z" fill="{observed["blouse"]}"/>')
                if observed.get("bow"):
                    add(f'<path d="M92,146 Q100,140 108,146 L104,170 L100,160 L96,170 Z" fill="{observed["blouse"]}" stroke="#d8d2c4"/>')
            if observed.get("necklace"):
                add('<path d="M86,138 Q100,160 114,138" fill="none" stroke="#cfd3d8" stroke-width="2.4"/>')
            if observed.get("brooch"):
                add('<circle cx="72" cy="164" r="5" fill="#b07ab8" stroke="#e8e8e8" stroke-width="1.5"/>')
            if observed.get("scarf"):
                tri = "M80,138 L120,138 L106,182 L94,182 Z"
                add(f'<clipPath id="{uid}k"><path d="{tri}"/></clipPath><path d="{tri}" fill="#f4f4f4"/>'
                    f'<g clip-path="url(#{uid}k)" stroke="{observed["scarf"]}" stroke-width="3">'
                    + "".join(f'<path d="M70,{y} L130,{y - 14}"/>' for y in range(140, 200, 7)) + '</g>')
            elif rolls[0] < .5:
                add('<path d="M84,140 Q100,162 116,140" fill="none" stroke="#e5c07b" stroke-width="2"/>')

    # ---- long hair behind the face --------------------------------------
    long_hair = sex == "F" and (era == "modern" and rolls[1] < .6 or era == "early20" and rolls[1] < .3)
    if observed.get("hair_style"):
        long_hair = observed["hair_style"] == "long"
    if long_hair and observed.get("hair_style") == "long":
        L, R = 100 - rx, 100 + rx
        out.insert(0, f'<path d="M{L - 6:.1f},80 Q{L - 12:.1f},38 100,42 Q{R + 12:.1f},38 {R + 6:.1f},80 '
            f'Q{R + 18:.1f},112 {R + 12:.1f},140 Q{R + 24:.1f},160 {R + 14:.1f},184 Q100,178 {L - 14:.1f},184 '
            f'Q{L - 24:.1f},160 {L - 12:.1f},140 Q{L - 18:.1f},112 {L - 6:.1f},80 Z" fill="{hair}"/>')
    elif long_hair:
        add(f'<path d="M62,90 Q60,40 100,42 Q140,40 138,90 L144,150 Q100,160 56,150 Z" fill="{hair}"/>')

    # ---- unknown sex: neutral placeholder silhouette --------------------
    if ghost:
        add(f'<ellipse cx="100" cy="90" rx="{rx:.1f}" ry="{ry:.1f}" fill="#bfc4c9"/>')
        add('<text x="100" y="104" font-family="Georgia,serif" font-size="40" '
            'text-anchor="middle" fill="#fff">?</text>')
    else:
        # ---- head ---------------------------------------------------------
        for sx in (-1, 1):
            add(f'<circle cx="{100 + sx * rx:.1f}" cy="94" r="6.5" fill="{skin}"/>')
        add(f'<ellipse cx="100" cy="90" rx="{rx:.1f}" ry="{ry:.1f}" fill="{skin}"/>')

        # eyes, brows, nose, cheeks
        for sx in (-1, 1):
            add(f'<circle cx="{100 + sx * es:.1f}" cy="88" r="{er:.1f}" fill="#2b2b2b"/>')
            add(f'<circle cx="{100 + sx * es + 1:.1f}" cy="87" r="1" fill="#fff"/>')
            add(f'<path d="M{100 + sx * (es - 6):.1f},{80 - brow:.1f} Q{100 + sx * es:.1f},{76 - brow * 1.5:.1f} '
                f'{100 + sx * (es + 6):.1f},{80 - brow * .3:.1f}" stroke="{_shade(hair, .7) if age < 55 else "#999"}" '
                'stroke-width="2.4" fill="none" stroke-linecap="round"/>')
        add(f'<path d="M100,{103 - nl:.1f} Q96,101 101,103" stroke="#000" stroke-opacity=".3" fill="none" stroke-width="2"/>')
        if sex == "F" or age < 25:
            for sx in (-1, 1):
                add(f'<circle cx="{100 + sx * 20}" cy="101" r="5" fill="#ff7b7b" opacity=".25"/>')
        if age >= 55:  # crow's feet and forehead lines
            for sx in (-1, 1):
                add(f'<path d="M{100 + sx * 21},86 l{sx * 5},-2 M{100 + sx * 21},90 l{sx * 5},1" '
                    'stroke="#000" stroke-opacity=".2"/>')
            add('<path d="M88,68 Q100,65 112,68 M90,73 Q100,70 110,73" stroke="#000" '
                'stroke-opacity=".15" fill="none"/>')

        # facial hair (men) or mouth
        beard_p = {"baroque": .1, "georgian": .1, "victorian": .65, "early20": .25}.get(era, .3)
        mouth = (f'<path d="M{100 - mw:.1f},108 Q100,124 {100 + mw:.1f},108 Z" fill="#7a3b2e"/>'
                 f'<path d="M{100 - mw + 2:.1f},109 Q100,113 {100 + mw - 2:.1f},109 L{100 + mw - 3:.1f},111 Q100,115 {100 - mw + 3:.1f},111 Z" fill="#fff"/>'
                 ) if observed.get("smile") == "open" else f'<path d="M{100 - mw:.1f},110 Q100,118 {100 + mw:.1f},110" stroke="#7a3b2e" stroke-width="2.4" fill="none" stroke-linecap="round"/>'
        fh = observed.get("facial_hair")
        if fh == "goatee":                                   # short chin beard + moustache
            bc = observed.get("beard_colour", _shade(hair, .9))
            add(mouth)
            add(f'<path d="M86,104 Q93,99 100,102 Q107,99 114,104 Q100,104 86,104 Z" fill="{bc}" opacity=".85"/>')
            bl = observed.get("beard_length", 130)           # chin tip y; 130 short, ~144 long
            hw = 12 + (bl - 130) * .35
            add(f'<path d="M{100 - hw:.1f},112 Q{100 - hw + 2:.1f},{bl - 4:.1f} 100,{bl:.1f} Q{100 + hw - 2:.1f},{bl - 4:.1f} {100 + hw:.1f},112 '
                f'Q106,122 100,122 Q94,122 {100 - hw:.1f},112 Z" fill="{bc}" opacity=".9"/>')
            add(f'<path d="M{100 - rx + 4:.1f},104 Q{100 - rx + 8:.1f},122 88,116 M{100 + rx - 4:.1f},104 '
                f'Q{100 + rx - 8:.1f},122 112,116" stroke="{bc}" stroke-opacity=".35" stroke-width="3" fill="none"/>')
        elif fh == "full":                                   # full beard and moustache, own colour
            bc = observed.get("beard_colour", hair)
            add(f'<path d="M{100 - rx + 1:.1f},90 C{100 - rx + 2:.1f},146 {100 + rx - 2:.1f},146 '
                f'{100 + rx - 1:.1f},90 C{100 + rx - 8:.1f},114 {100 - rx + 8:.1f},114 {100 - rx + 1:.1f},90 Z" fill="{bc}"/>')
            add(f'<path d="M84,108 Q92,100 100,104 Q108,100 116,108 Q100,110 84,108 Z" fill="{bc}"/>')
            add('<path d="M93,114 Q100,117 107,114" stroke="#7a3b2e" stroke-width="2" fill="none"/>')
        elif fh == "none":
            add(mouth)
        elif sex == "M" and rolls[3] < beard_p:
            add(f'<path d="M{100 - rx + 1:.1f},92 C{100 - rx + 3:.1f},142 {100 + rx - 3:.1f},142 '
                f'{100 + rx - 1:.1f},92 C{100 + rx - 8:.1f},116 {100 - rx + 8:.1f},116 {100 - rx + 1:.1f},92 Z" fill="{hair}"/>')
            add(f'<path d="M86,106 Q100,100 114,106 Q100,110 86,106 Z" fill="{hair}"/>')
            add('<path d="M93,113 Q100,117 107,113" stroke="#7a3b2e" stroke-width="2" fill="none"/>')
        elif sex == "M" and rolls[3] < beard_p + .2 and era != "modern":
            add(mouth)
            add(f'<path d="M84,107 Q92,100 100,104 Q108,100 116,107 Q100,106 84,107 Z" fill="{hair}"/>')
        else:
            add(mouth)

        # ---- hair / headwear on top ----------------------------------------
        top = (f'M{100 - rx - 2:.1f},88 C{100 - rx - 4:.1f},44 {100 + rx + 4:.1f},44 {100 + rx + 2:.1f},88 '
               f'C{100 + rx - 4:.1f},66 {100 - rx + 4:.1f},66 {100 - rx - 2:.1f},88 Z')
        if sex == "M":
            if era in ("baroque", "georgian") and rolls[4] < .6:            # powdered wig
                for sx in (-1, 1):
                    for cy in (82, 96, 110):
                        add(f'<circle cx="{100 + sx * (rx + 4):.1f}" cy="{cy}" r="8" fill="#eeeae0" stroke="#cfc9b8"/>')
                add(f'<path d="{top}" fill="#eeeae0" stroke="#cfc9b8"/>')
            elif age >= 55 and rolls[5] < .4 and not observed.get("hair_style"):                               # balding
                for sx in (-1, 1):
                    add(f'<path d="M{100 + sx * (rx + 1):.1f},96 Q{100 + sx * (rx + 3):.1f},72 '
                        f'{100 + sx * (rx - 8):.1f},66" stroke="{hair}" stroke-width="7" fill="none" stroke-linecap="round"/>')
            elif observed.get("hair_style") == "curly":                     # short permed curls
                L, R = 100 - rx, 100 + rx
                add(f'<path d="{top}" fill="{hair}"/>')
                for k in range(11):
                    t = math.pi * (0.95 + k * 1.1 / 10)
                    cx, cy = 100 + (rx + 3) * math.cos(t), 86 + (ry * .95) * math.sin(t)
                    add(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{7.5 + (k % 3):.1f}" fill="{hair}" stroke="{_shade(hair, .8)}" stroke-width=".8"/>')
            elif observed.get("hair_style") == "receding":                  # high forehead, sides kept
                for sx in (-1, 1):
                    add(f'<path d="M{100 + sx * (rx + 1):.1f},98 Q{100 + sx * (rx + 4):.1f},70 {100 + sx * (rx - 10):.1f},58 '
                        f'L{100 + sx * (rx - 16):.1f},62 Q{100 + sx * (rx - 4):.1f},74 {100 + sx * (rx - 4):.1f},98 Z" fill="{hair}" '
                        f'stroke="{_outline(hair)}" stroke-width="1.2"/>')
                add(f'<path d="M{100 - rx + 14:.1f},56 Q100,50 {100 + rx - 14:.1f},56" stroke="{hair}" stroke-width="3" fill="none" opacity=".7"/>')
            elif observed.get("hair_style") == "spiky":                     # short, gelled up
                L, R = 100 - rx, 100 + rx
                spikes = " ".join(f"L{L + 6 + k * (2 * rx - 12) / 14:.1f},"
                                  f"{(47 if k % 2 else 54) - 4 * math.sin(math.pi * k / 14):.1f}"
                                  for k in range(15))
                add(f'<path d="M{L - 2:.1f},86 C{L - 4:.1f},64 {L + 2:.1f},58 {L + 6:.1f},54 {spikes} '
                    f'L{R - 6:.1f},54 C{R - 2:.1f},58 {R + 4:.1f},64 {R + 2:.1f},86 C{R - 4:.1f},68 {L + 4:.1f},68 {L - 2:.1f},86 Z" fill="{hair}"/>')
            elif observed.get("hair_style") == "full":                      # thick, swept up and back
                add(f'<path d="M{100 - rx - 3:.1f},92 C{100 - rx - 8:.1f},40 {100 + rx + 2:.1f},26 {100 + rx + 4:.1f},86 '
                    f'C{100 + rx - 2:.1f},66 {100 - rx + 14:.1f},50 {100 - rx + 3:.1f},74 L{100 - rx + 1:.1f},92 Z" fill="{hair}" stroke="{_outline(hair)}" stroke-width="1.4"/>')
                add(f'<path d="M{100 - rx + 8:.1f},52 Q100,44 {100 + rx - 6:.1f},50" stroke="#fff" stroke-opacity=".35" '
                    'stroke-width="2" fill="none"/>')
            else:
                add(f'<path d="{top}" fill="{hair}"/>')
        elif sex != "F":
            add(f'<path d="{top}" fill="{hair}"/>')
        else:
            if era in ("baroque", "georgian") and rolls[4] < .5:            # bonnet
                add(f'<path d="M{100 - rx - 10:.1f},100 C{100 - rx - 14:.1f},30 {100 + rx + 14:.1f},30 '
                    f'{100 + rx + 10:.1f},100 C{100 + rx},70 {100 - rx},70 {100 - rx - 10:.1f},100 Z" '
                    'fill="#fbfaf5" stroke="#d6d2c4"/>')
                add('<path d="M78,118 Q100,128 122,118" stroke="#c0392b" stroke-width="3" fill="none"/>')
            elif era in ("baroque", "georgian", "victorian") or (era == "unknown" and rolls[4] < .5):
                add(f'<circle cx="100" cy="47" r="12" fill="{hair}"/>')                      # bun
                add(f'<path d="{top}" fill="{hair}"/>')
                add('<path d="M100,56 L100,66" stroke="#000" stroke-opacity=".25" stroke-width="1.5"/>')  # parting
            elif (era == "early20" and not observed.get("hair_style") or observed.get("hair_style") == "bob") and not long_hair:                                        # bob
                add(f'<path d="M{100 - rx - 4:.1f},112 C{100 - rx - 8:.1f},40 {100 + rx + 8:.1f},40 '
                    f'{100 + rx + 4:.1f},112 L{100 + rx - 4:.1f},112 C{100 + rx - 2:.1f},80 100,62 '
                    f'{100 - rx + 6:.1f},76 L{100 - rx + 4:.1f},112 Z" fill="{hair}"/>')
            elif observed.get("hair_style") == "curly":                     # short permed curls
                L, R = 100 - rx, 100 + rx
                add(f'<path d="{top}" fill="{hair}"/>')
                for k in range(11):
                    t = math.pi * (0.95 + k * 1.1 / 10)
                    cx, cy = 100 + (rx + 3) * math.cos(t), 86 + (ry * .95) * math.sin(t)
                    add(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{7.5 + (k % 3):.1f}" fill="{hair}" stroke="{_shade(hair, .8)}" stroke-width=".8"/>')
            elif observed.get("hair_style") == "updo":                      # pinned up, soft waves
                add(f'<circle cx="100" cy="46" r="13" fill="{hair}" stroke="{_outline(hair)}" stroke-width="1.4"/>')
                add(f'<path d="M{100 - rx - 4:.1f},98 C{100 - rx - 10:.1f},44 {100 + rx + 10:.1f},44 {100 + rx + 4:.1f},98 '
                    f'C{100 + rx},72 {100 + rx - 8:.1f},62 100,64 C{100 - rx + 8:.1f},62 {100 - rx:.1f},72 {100 - rx - 4:.1f},98 Z" fill="{hair}"/>')
                for sx in (-1, 1):
                    add(f'<path d="M{100 + sx * (rx - 2):.1f},70 q{sx * 5},8 0,14 q{-sx * 5},6 0,12" stroke="{_shade(hair, .8)}" '
                        'stroke-width="1.5" fill="none"/>')
            elif observed.get("hair_style") == "short":                     # short, side-swept fringe
                add(f'<path d="M{100 - rx - 3:.1f},96 C{100 - rx - 8:.1f},38 {100 + rx + 8:.1f},38 {100 + rx + 3:.1f},96 '
                    f'C{100 + rx},74 {100 + rx - 10:.1f},62 {100 + 6:.1f},64 Q{100 - rx + 4:.1f},70 {100 - rx + 1:.1f},96 Z" fill="{hair}" stroke="{_outline(hair)}" stroke-width="1.4"/>')
                add(f'<path d="M{100 - rx + 6:.1f},62 Q100,52 {100 + rx - 4:.1f},60" stroke="{_shade(hair, .85)}" '
                    'stroke-width="1.6" fill="none"/>')
            elif observed.get("hair_style") == "long":                      # centre parting, side locks
                for sx in (-1, 1):
                    add(f'<path d="M100,46 Q{100 + sx * (rx + 4):.1f},46 {100 + sx * (rx + 3):.1f},92 '
                        f'Q{100 + sx * (rx + 14):.1f},130 {100 + sx * (rx + 4):.1f},166 '
                        f'Q{100 + sx * (rx - 6):.1f},150 {100 + sx * (rx - 2):.1f},128 '
                        f'Q{100 + sx * (rx - 6):.1f},96 {100 + sx * (rx - 7):.1f},76 Q{100 + sx * 18:.1f},56 100,52 Z" fill="{hair}"/>')
                add(f'<path d="M100,46 L100,54" stroke="{_shade(hair, .75)}" stroke-width="1.5"/>')
            else:
                add(f'<path d="{top}" fill="{hair}"/>')

        # glasses
        glasses_p = {"early20": .2, "modern": .3}.get(era, .05) + (.2 if age >= 55 else 0)
        shape = observed.get("glasses", "round" if rolls[6] < glasses_p else None)
        gcol = observed.get("glasses_colour")
        if shape == "large":                                  # big 80s/90s frames
            add(f'<g fill="{observed.get("lens_tint", "none")}" fill-opacity=".35" stroke="{gcol or "#7a6a4a"}" stroke-width="1.8">'
                f'<rect x="{100 - es - 11:.1f}" y="80" width="21" height="16" rx="6"/>'
                f'<rect x="{100 + es - 10:.1f}" y="80" width="21" height="16" rx="6"/>'
                f'<path d="M{100 - es + 10:.1f},86 Q100,83 {100 + es - 10:.1f},86" fill="none"/></g>')
        elif shape == "heavy":                                # thick black 60s/70s frames
            add(f'<g fill="none" stroke="{gcol or "#111"}" stroke-width="3.4" stroke-linejoin="round">'
                f'<rect x="{100 - es - 10:.1f}" y="81" width="20" height="14" rx="3"/>'
                f'<rect x="{100 + es - 10:.1f}" y="81" width="20" height="14" rx="3"/>'
                f'<path d="M{100 - es + 10:.1f},86 L{100 + es - 10:.1f},86"/></g>')
        elif shape == "cateye":                               # browline frames, upswept outer corners
            add(f'<g fill="none" stroke="{gcol or "#8c8f94"}" stroke-width="1.6">'
                + "".join(f'<path d="M{100 + sx * (es - 9):.1f},85 L{100 + sx * (es - 9):.1f},92 Q{100 + sx * es:.1f},96 '
                          f'{100 + sx * (es + 9):.1f},91 L{100 + sx * (es + 11):.1f},82 Q{100 + sx * es:.1f},80 {100 + sx * (es - 9):.1f},85 Z"/>'
                          for sx in (-1, 1))
                + f'<path d="M{100 - es + 9:.1f},86 Q100,84 {100 + es - 9:.1f},86"/></g>'
                + "".join(f'<path d="M{100 + sx * (es - 9):.1f},84 Q{100 + sx * es:.1f},79 {100 + sx * (es + 11):.1f},82" '
                          f'stroke="#3a3a3a" stroke-width="2.6" fill="none"/>' for sx in (-1, 1)))
        elif shape == "rect":
            add(f'<g fill="none" stroke="{gcol or "#5a4636"}" stroke-width="2">'
                f'<rect x="{100 - es - 9:.1f}" y="82" width="18" height="12" rx="3"/>'
                f'<rect x="{100 + es - 9:.1f}" y="82" width="18" height="12" rx="3"/>'
                f'<path d="M{100 - es + 9:.1f},87 Q100,84 {100 + es - 9:.1f},87"/></g>')
        elif shape == "thin":                                 # thin metal frames
            add('<g fill="none" stroke="#8a8a8a" stroke-width="1.2">'
                f'<rect x="{100 - es - 9:.1f}" y="83" width="18" height="11" rx="4"/>'
                f'<rect x="{100 + es - 9:.1f}" y="83" width="18" height="11" rx="4"/>'
                f'<path d="M{100 - es + 9:.1f},87 Q100,85 {100 + es - 9:.1f},87"/></g>')
        elif shape:
            add('<g fill="none" stroke="#333" stroke-width="1.8">'
                '<circle cx="87" cy="88" r="8"/><circle cx="113" cy="88" r="8"/>'
                '<path d="M95,88 Q100,85 105,88"/></g>')

    if observed.get("hearing_aid") and not ghost:
        add(f'<path d="M{100 - rx - 4:.1f},86 q-4,6 1,12" stroke="#c9b8a6" stroke-width="3" fill="none" stroke-linecap="round"/>')
    if observed.get("strap"):                               # bag strap across the chest
        add(f'<path d="M132,140 L146,146 L112,206 L96,206 Z" fill="{observed["strap"]}"/>')
    portrait = "".join(out)

    # ---- era 'medium': clip, colour filter, frame -----------------------
    defs, frame = [], ""
    if era in ("baroque", "georgian"):
        clip = '<ellipse cx="100" cy="100" rx="78" ry="94"/>'
        bgfill = "#3b4a3f" if rolls[7] < .5 else "#5a2e2e"
        frame = ('<ellipse cx="100" cy="100" rx="80" ry="96" fill="none" stroke="#b8892b" stroke-width="9"/>'
                 '<ellipse cx="100" cy="100" rx="80" ry="96" fill="none" stroke="#f3d27a" stroke-width="2"/>')
        filt = None
        outer = '<rect width="200" height="200" fill="#1c1c1c"/>'
    elif era == "victorian":
        clip = '<rect x="22" y="12" width="156" height="176" rx="14"/>'
        bgfill, filt = "#d8cfc0", SEPIA
        frame = '<rect x="22" y="12" width="156" height="176" rx="14" fill="none" stroke="#efe6d2" stroke-width="10"/>'
        outer = '<rect width="200" height="200" fill="#efe6d2"/>'
    elif era == "early20":
        clip = '<rect x="14" y="14" width="172" height="172"/>'
        bgfill, filt = "#cfcfcf", GREY
        frame = '<rect x="14" y="14" width="172" height="172" fill="none" stroke="#fafafa" stroke-width="12"/>'
        outer = '<rect width="200" height="200" fill="#fafafa"/>'
    else:
        clip = '<circle cx="100" cy="100" r="96"/>'
        bgfill, filt = bg, None
        outer = ""
    defs.append(f'<clipPath id="{uid}c">{clip}</clipPath>')
    fattr = ""
    if filt:
        defs.append(f'<filter id="{uid}f"><feColorMatrix type="matrix" values="{filt}"/></filter>')
        fattr = f' filter="url(#{uid}f)"'

    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 200" width="{size}" height="{size}">'
            f'<title>{_esc(p.name or p.id)}</title><defs>{"".join(defs)}</defs>{outer}'
            f'<g clip-path="url(#{uid}c)"{fattr}><rect width="200" height="200" fill="{bgfill}"/>{portrait}</g>'
            f'{frame}{_badges(evidence, side)}</svg>')


def _badges(evidence: int | None, side: float | None) -> str:
    out = ""
    if side is not None:   # paternal (blue) vs maternal (orange) resemblance bar
        w = 60
        out += (f'<rect x="70" y="186" width="{w}" height="7" rx="3.5" fill="#e8833a"/>'
                f'<rect x="70" y="186" width="{w * side:.1f}" height="7" rx="3.5" fill="#3a7bd5"/>'
                '<rect x="70" y="186" width="60" height="7" rx="3.5" fill="none" stroke="#fff" stroke-width="1.2"/>')
    if evidence is not None:
        for k in range(3):
            fill = "#222" if k < evidence else "#fff"
            out += f'<circle cx="{164 + k * 10}" cy="18" r="3.6" fill="{fill}" stroke="#222" stroke-width="1.2"/>'
    return out


def _outline(hexcol: str) -> str:
    """Thin outline so very light hair stays visible against pale skin and backgrounds."""
    lum = sum(int(hexcol[k:k + 2], 16) for k in (1, 3, 5)) / 3
    return _shade(hexcol, .72) if lum > 190 else "none"


def _shade(hexcol: str, f: float) -> str:
    c = [int(hexcol[k:k + 2], 16) for k in (1, 3, 5)]
    return "#" + "".join(f"{max(0, min(255, int(v * f))):02x}" for v in c)


def _esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
