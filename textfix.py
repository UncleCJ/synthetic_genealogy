"""
Repair Swedish letters damaged on their way through vendor exports.

Three kinds of damage occur in GEDCOM and FTDNA files:

1. Decomposed letters: "a" + U+0308 (combining diaeresis) instead of "ä".
   They look right, but "Gränna" and "Gränna" then compare unequal, so
   one parish or one name splits in two. NFC normalisation fixes them.
2. Spacing marks: a lossy conversion turned the combining mark into a
   character of its own: "Ka¨lleryd" (U+00A8), "Stora A°by" (U+00B0 or
   U+02DA). These are re-attached, then normalised.

3. Mojibake: UTF-8 bytes read as Windows-1252 or Latin-1: "SkÃ¶vde",
   "LidingÃ¶", "Ã\x85kesson" (Å, whose second byte is a Latin-1 line
   break and may have become a real newline or <br/>), "GaÌ\x88stgivare"
   (a decomposed ä, mark included). Each run is re-encoded and decoded as
   UTF-8, which is exact; a run that does not decode is left as it is.
   Lone C1 controls ("person\x92s") become their Windows-1252 character.

The repair is deliberately narrow: ¨ joins only a, o, u (ä ö ü) and the
ring only a (å), because "¨" also serves as a quote mark in some names
("¨Skotte¨"). Other spacing marks are left alone.
"""
import re
import unicodedata

# Mojibake: UTF-8 read as Windows-1252 or Latin-1. A lead byte shows as
# Â/Ã (Latin-1 letters) or Ì/Ë (UTF-8 combining marks and modifiers); the
# continuation byte (0x80-0xBF) as its Windows-1252 character or as a raw
# C1 control (U+0080-U+009F).
_CONT = "".join(sorted({bytes([b]).decode("cp1252", "ignore") for b in range(0x80, 0xC0)}
                       | {chr(c) for c in range(0x80, 0xC0)}))
_MOJIBAKE = re.compile("[\u00c2\u00c3\u00cb\u00cc][" + re.escape(_CONT) + "]")
# Å is C3 85; read as Latin-1, 85 is NEL, a line break, which later tools
# write as a newline or <br/>: "Ã\nkesson", "Ã<br/>kesson".
_BROKEN_A_RING = re.compile(r"\u00c3(?:\r?\n|<br\s*/?>)(?=\w)")


def _byte(ch):
    return bytes([ord(ch)]) if ord(ch) < 0x100 else ch.encode("cp1252")


def _demojibake(m):
    try:
        return b"".join(_byte(c) for c in m.group(0)).decode("utf-8")
    except UnicodeError:
        return m.group(0)


def _c1(m):
    """A lone C1 control is a Windows-1252 character read as Latin-1
    ("person\x92s" -> "person’s"); NEL alone is a line break."""
    c = m.group(0)
    return "\n" if c == "\x85" else bytes([ord(c)]).decode("cp1252", "ignore")


_DIAERESIS = re.compile(r"([aouAOU])\u00a8")
_RING = re.compile(r"([aA])[\u00b0\u02da]")


def fix(s):
    """Text with damaged å/ä/ö repaired; non-strings pass through."""
    if not isinstance(s, str):
        return s
    if any(c in s for c in "\u00c2\u00c3\u00cb\u00cc"):
        s = _BROKEN_A_RING.sub("\u00c5", s)
        s = _MOJIBAKE.sub(_demojibake, s)
    s = re.sub("[\u0080-\u009f]", _c1, s)
    s = _DIAERESIS.sub("\\1\u0308", s)
    s = _RING.sub("\\1\u030a", s)
    return unicodedata.normalize("NFC", s)


def fix_frame(df):
    """Apply fix() to every text column of a pandas DataFrame."""
    for c in df.columns:
        if df[c].dtype == object:
            df[c] = df[c].map(fix)
    df.columns = [fix(c) for c in df.columns]
    return df
