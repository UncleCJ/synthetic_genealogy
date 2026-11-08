"""Side data for each photo, so measurements are only used when the photo can support them.

Three layers, by how far each fact travels:
  context     about the photo itself: year, age in photo, colour mode, light, head turn, expression
  appearance  stable       -> may be inherited through the tree (eye colour, natural hair colour)
              age_dependent-> drawn for this person at that age, never inherited (grey, balding)
              transient    -> drawn only for this photo (glasses, beard, clothes, hearing aid)
  trusted     which geometry measurements survive the context (head turn, open smile)

Automatic now: colour mode, head-turn estimate, face size, trust rules.
By eye for now (filled in chat): age, glasses, facial hair, hair, expression, clothes.
Later candidates for automation: insightface age estimate, CLIP zero-shot ('glasses', 'beard').
"""
from __future__ import annotations
import math
import numpy as np

CHEEK_R, CHEEK_L, NOSE_TIP = 234, 454, 1
WIDTH_BASED = {"face_width", "face_length", "eye_spacing", "eye_size", "mouth_width"}
VERTICAL = {"brow_height", "nose_length"}


def colour_mode(img_rgb: np.ndarray) -> str:
    """greyscale / sepia (one tint) / colour, from how well luminance predicts each channel."""
    x = img_rgb.reshape(-1, 3).astype(float)[::7]
    lum = x.mean(1)
    resid = []
    for k in range(3):
        a, b = np.polyfit(lum, x[:, k], 1)
        resid.append(np.mean(np.abs(x[:, k] - (a * lum + b))))
    if max(resid) > 7:
        return "colour"
    return "sepia" if np.mean(x[:, 0] - x[:, 2]) > 12 else "greyscale"


def head_turn(pts: np.ndarray) -> tuple[float, float]:
    """(index, rough degrees). Index = nose-to-cheek asymmetry: 0 frontal, ±1 full profile."""
    a = np.linalg.norm(pts[NOSE_TIP] - pts[CHEEK_R])
    b = np.linalg.norm(pts[NOSE_TIP] - pts[CHEEK_L])
    idx = float((a - b) / (a + b))
    return round(idx, 2), round(math.degrees(math.asin(max(-1, min(1, idx)))))


def trusted(turn_index: float, expression: str, face_px: float | None = None, full_beard: bool = False) -> list[str]:
    """Which geometry survives this photo.
    - face under ~100 px tall (forehead to chin, original pixels): no geometry at all
    - head turned more than ~15 degrees: only vertical ratios
    - open mouth: no mouth width
    - full beard: the chin and mouth corners are guessed under the beard, so face length/width and mouth go"""
    if face_px is not None and face_px < 100:
        return []
    keep = set(VERTICAL)
    if abs(turn_index) < 0.25:
        keep |= WIDTH_BASED
    if expression in ("open smile", "laughing", "talking"):
        keep.discard("mouth_width")
    if full_beard:
        keep -= {"face_width", "face_length", "mouth_width"}
    return sorted(keep)


def auto_context(img_rgb: np.ndarray, pts: np.ndarray) -> dict:
    idx, deg = head_turn(pts)
    face_px = float(np.linalg.norm(pts[10] - pts[152]))
    return {"colour_mode": colour_mode(img_rgb), "head_turn_index": idx, "head_turn_deg_approx": deg,
            "face_height_px": round(face_px)}


def photo_era(born: int | None, ctx: dict) -> str | None:
    """Era of the photo itself (photo year, else birth year + middle of the age estimate)."""
    year = ctx.get("photo_year")
    age = ctx.get("age_in_photo") or {}
    if year is None and born and "low" in age:
        year = born + (age["low"] + age["high"]) // 2
    if year is None:
        return None
    return ("baroque" if year < 1750 else "georgian" if year < 1840 else "victorian" if year < 1900
            else "early20" if year < 1945 else "modern")
