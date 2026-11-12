"""Recognise the family's own kits in match lists and DNA Painter paintings.

A match is family when its WHOLE name equals one of `family_names` (compared by
`name_core`: case, "*", hyphens, commas, whitespace, manager suffix and
parenthesised birth or married names are normalised away), or its MyHeritage
`match_key` ("D-<kit>") is in `family_kits`. A first name alone never matches.
Vendors spell one person differently, so list each spelling's core.

Config ([match_filter] in family.toml):
  family_names  = ["Anna Example", "Dagmar Maria Example", ...]
  family_kits   = ["D-00000000-0000-0000-0000-000000000004", ...]
  close_family  = [...]   # DNA Painter: painted as matches, no lineage
"""
import re

_CO = re.compile(r"\s+c/o\s.*$", re.I)
_PAREN = re.compile(r"\([^)]*\)")
_PUNCT = re.compile(r"[*,\-]")


def name_core(s):
    s = _CO.sub("", str(s))
    s = _PAREN.sub(" ", s)
    s = _PUNCT.sub(" ", s)
    return " ".join(s.lower().split())


class FamilyFilter:
    def __init__(self, names=(), kits=()):
        self.names = {name_core(n) for n in names}
        self.kits = {str(k).strip().upper() for k in kits}

    def is_family(self, name, key=None):
        return (name_core(name) in self.names
                or (key is not None and str(key).upper() in self.kits))

    def mask(self, segs):
        """Boolean Series over a segment table: True for family rows."""
        by_name = segs["match"].map(name_core).isin(self.names)
        if "match_key" in segs and self.kits:
            by_kit = segs["match_key"].astype(str).str.upper().isin(self.kits)
            return by_name | by_kit
        return by_name


def from_config(cfg):
    f = cfg.get("match_filter", {})
    if "family_regex" in f:
        raise ValueError(
            "[match_filter] family_regex is no longer supported: a bare first name "
            "in it dropped unrelated matches. List whole names in family_names "
            "and MyHeritage kits in family_kits (see examples/family.example.toml).")
    return FamilyFilter(f.get("family_names", ()), f.get("family_kits", ()))


def close_family(cfg):
    return FamilyFilter(cfg.get("match_filter", {}).get("close_family", ()))


def drop_exact_duplicates(df, label):
    """Drop rows identical in every column, saying how many."""
    dup = df.duplicated()
    n = int(dup.sum())
    if n:
        print(f"{label}: dropped {n} exact duplicate segment row{'s' * (n != 1)}")
    return df[~dup] if n else df

