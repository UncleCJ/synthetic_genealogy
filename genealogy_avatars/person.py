"""Minimal person record: just the attributes that influence how an avatar looks."""
from __future__ import annotations
from dataclasses import dataclass, asdict
import hashlib, json


@dataclass(frozen=True)
class Person:
    id: str                       # stable key: GEDCOM @I12@, MyHeritage match ID, synthetic ID...
    name: str = ""
    sex: str = "U"                # "M", "F" or "U" (unknown)
    birth_year: int | None = None
    portrait_age: int = 40        # age to depict; e.g. min(40, lifespan)
    region: str = ""              # free text, e.g. "Västergötland"; used in prompts

    @property
    def era(self) -> str:
        y = self.birth_year
        if y is None:   return "unknown"
        if y < 1750:    return "baroque"
        if y < 1840:    return "georgian"
        if y < 1900:    return "victorian"
        if y < 1945:    return "early20"
        return "modern"

    def fingerprint(self, style_version: str) -> str:
        """Cache key: changes when any visual input or the generator version changes."""
        blob = json.dumps({**asdict(self), "v": style_version}, sort_keys=True)
        return hashlib.sha256(blob.encode()).hexdigest()[:16]

    def seed(self) -> int:
        """Seed depends on id only, so editing a birth year keeps the same 'face'."""
        return int(hashlib.sha256(self.id.encode()).hexdigest()[:12], 16)
