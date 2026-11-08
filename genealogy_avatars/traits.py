"""The 'visible' face vector: a few standardised facial measurements a cartoon can show.

Each trait is a z-score (0 = population average, ±1 = one standard deviation).
These are what gets inherited through the tree and drawn. The 512-d identity
embedding (see extract.py) is kept alongside for similarity, but cannot be drawn directly.
"""
from __future__ import annotations
import math
import numpy as np

TRAITS = [
    "face_width",    # bizygomatic width / face height, from landmarks
    "face_length",
    "eye_spacing",   # inter-pupil distance / face width
    "eye_size",
    "brow_height",   # brow-to-eye distance
    "nose_length",
    "mouth_width",
    "skin_tone",     # lightness of cheek pixels (higher = darker here)
    "hair_tone",     # lightness of hair pixels (higher = lighter/blonder)
]
D = len(TRAITS)

_SKIN = ["#ffe6d2", "#f9d2b4", "#f1c27d", "#e0ac69", "#c68642", "#8d5524"]
_HAIR = ["#1e130b", "#3b2416", "#5a3825", "#7d5233", "#a9784b", "#d1ad73", "#ecd9a0"]


def _lerp(lo: float, hi: float, z: float) -> float:
    return lo + (hi - lo) / (1 + math.exp(-1.3 * z))   # squashes z into [lo, hi]


def _ramp(colors: list[str], z: float) -> str:
    t = _lerp(0, len(colors) - 1, z)
    i = min(int(t), len(colors) - 2)
    a, b, f = colors[i], colors[i + 1], t - i
    mix = [round(int(a[k:k + 2], 16) * (1 - f) + int(b[k:k + 2], 16) * f) for k in (1, 3, 5)]
    return "#" + "".join(f"{c:02x}" for c in mix)


def to_render(z: np.ndarray) -> dict:
    """Map a trait z-vector to the renderer's drawing parameters (exaggerated on purpose)."""
    t = dict(zip(TRAITS, map(float, z)))
    return {
        "rx": _lerp(28, 39, t["face_width"]),
        "ry": _lerp(34, 46, t["face_length"]),
        "es": _lerp(10, 16.5, t["eye_spacing"]),
        "er": _lerp(2.4, 4.6, t["eye_size"]),
        "brow": _lerp(-1, 5, t["brow_height"]),
        "nl": _lerp(6, 15, t["nose_length"]),
        "mw": _lerp(6.5, 14, t["mouth_width"]),
        "skin": _ramp(_SKIN, t["skin_tone"]),
        "hair": _ramp(_HAIR, t["hair_tone"]),
    }
