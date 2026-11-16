# TEXTFIX(1)

## NAME

textfix.py — repair Swedish letters damaged by vendor exports

## SYNOPSIS

    python3 textfix.py 'SkÃ¶vde Ka¨lleryd'
    python3 textfix.py -c
    python3 textfix.py < in.txt > out.txt

## DESCRIPTION

Applies `textfix.fix()` (what the loaders apply on import): decomposed
letters, spacing marks (`Ka¨lleryd`), mojibake (`SkÃ¶vde`, `Ã` + line
break for Å), lone C1 controls, and HTML entities and line-break tags.
Prints the result to stdout and `textfix: changed` or `textfix: unchanged`
to stderr.

Text comes from the arguments (joined by spaces), else from stdin.

**-c**, **--clip** repairs the macOS clipboard in place: copy a damaged
string (say from MyHeritage's editor), run it, paste the fixed one back.

The repair is narrow on purpose: ¨ joins only a, o, u; the ring only a.

## SEE ALSO

`docs/records.md` (text repair), errata(5)
