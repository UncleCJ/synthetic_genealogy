"""
One place for the keys that say who or what a row is about, and how far
each can be trusted.

Matches
-------
A match row carries a `match_key`, made by its reader and stored as is
(the store, tree_edits.json and the anchors in family.toml refer to it):

    "D-<kit>"          MyHeritage match kit (from the DNA Match ID
                       "D-<donor kit>-D-<match kit>"): strong, the same
                       person in every donor's list
    "name:<name>"      MyHeritage one-to-many export, names only: weak
    "<name>"           FTDNA, the display name lower-cased (ftdna_key):
                       weak, names repeat and change ("A B" -> "A C B")

To join rows from different sources (a DNA Painter label, a tree person, a
shared-match list) use name_key() on the display names: one rule for every
module. key_strength() says how much a join on a key is worth.

Trees and places
----------------
    mh_id(facts)       the "MH:I<n>" MyHeritage id among a person's facts
    "Parish/Name"      a gazetteer place; "parish:<n>" a parish; "osm:<id>" a
                       point from OpenStreetMap (see gazetteer.py, geocode.py)

Sketch: no fuzzy matching here (see prospects.loose_tree_hits for that);
key strength is a label, not yet a weight anyone uses.
"""
import re

_WS = re.compile(r"\s+")
# kit IDs are UUID-shaped, but not always hex (letters beyond F occur)
MH_PAIR = re.compile(r"^(D-[0-9A-Z-]{36})-(D-[0-9A-Z-]{36})$", re.I)
MH_PAIR_IN = re.compile(r"D-[0-9A-Z-]{36}-(D-[0-9A-Z-]{36})", re.I)   # inside a URL or text


def name_key(s):
    """The join key for a display name: lower case, punctuation as spaces,
    the call-name star dropped ("Eva*" -> "eva"), spaces collapsed."""
    return _WS.sub(" ", re.sub(r"[^\w\s]", " ", str(s).replace("*", ""))).strip().lower()


def ftdna_key(s):
    """FTDNA's match_key: the display name lower-cased, with commas and
    hyphens as spaces (the segment export writes "Ancelet, Jr." as
    "Ancelet- Jr.")."""
    return _WS.sub(" ", re.sub(r"[,\-]", " ", str(s))).strip().lower()


def mh_match_id(identifier):
    """MyHeritage match kit from an "Identifier" column ("D-" prefixed)."""
    return "D-" + str(identifier).strip().upper()


def mh_pair(text):
    """(donor kit, match kit) from a DNA Match ID, or (None, None)."""
    m = MH_PAIR.match(str(text or "").strip())
    return (m.group(1).upper(), m.group(2).upper()) if m else (None, None)


def mh_match_in(text):
    """The match kit from a DNA Match ID anywhere in a text (e.g. a DNA
    Painter evidence URL), or None."""
    m = MH_PAIR_IN.search(str(text or ""))
    return m.group(1).upper() if m else None


def key_strength(match_key):
    """"strong" for a vendor kit id, "weak" for a name."""
    k = str(match_key or "")
    return "strong" if re.match(r"^D-[0-9A-Z-]{36}$", k, re.I) else "weak"


def mh_id(facts):
    """The "MH:I<n>" fact among a tree person's facts, or None."""
    return next((f for f in facts if str(f).startswith("MH:")), None)
