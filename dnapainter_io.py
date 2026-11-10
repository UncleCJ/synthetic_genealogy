"""
Read DNA Painter profile backups into segment-origin assertions.

A backup is "<profile name><Male|Female>" followed by two JSON arrays
(painted segments, then groups) and a free-text description. A segment's
"group" is an index into the groups array.

Group names carry a lineage code as their first word, a path up from the
profile owner: "MFM Sven Andersson / Inga Jansdotter" = mother's father's
mother's parents. The first letter is the parent, the second the
grandparent, and so on. Groups without a code ("Cluster 7") are kept as
unplaced match segments.

Each row is one assertion: "<subject>'s DNA on chrom:start-end came down
the <lineage> path", with who asserted it, from which source and with
what confidence. Nothing here decides whether the assertion is true.
"""
import json
import re
from pathlib import Path

import pandas as pd

import family_filter

LINEAGE = re.compile(r"^([FM]+)\b")



def read_backup(path):
    text = Path(path).read_text(encoding="utf-8")
    start = text.index("[{")
    dec = json.JSONDecoder()
    segments, end = dec.raw_decode(text, start)
    groups, end2 = dec.raw_decode(text, end)
    header = text[:start]
    sex = next((s for s in ("Female", "Male") if header.endswith(s)), "")
    return dict(profile=header[: len(header) - len(sex)], sex=sex,
                segments=segments, groups=groups,
                description=text[end2:].strip())


def lineage_of(group):
    m = LINEAGE.match(group.get("name", "").strip())
    if m:
        return m.group(1)
    return {"pat": "F", "mat": "M"}.get(group.get("side"), "")


def assertions(path, subject, asserted_by="DNA Painter (manual)", close_family=()):
    """One row per painted segment of the backup at `path`, for the donor
    key `subject`. Matches whose whole name is in `close_family` (parents,
    siblings painted as matches; compared by family_filter.name_core) say
    nothing about lineage; they are kept but marked kind="close_family" so
    callers can drop them."""
    close_family = family_filter.FamilyFilter(close_family)
    b = read_backup(path)
    rows = []
    for s in b["segments"]:
        g = b["groups"][int(s["group"])]
        name = g.get("name", "").strip()
        code = lineage_of(g)
        side_painter = g.get("side", "")
        side_code = {"F": "pat", "M": "mat"}.get(code[:1], "")
        close = close_family.is_family(s["match"])
        rows.append(dict(
            assertion_id=f"dnapainter:{Path(path).stem}:{s.get('id')}",
            subject=subject,
            chrom=str(s["chromosome"]).strip(),
            start=int(s["start"]), end=int(s["end"]),
            cM=pd.to_numeric(s.get("cM") or None, errors="coerce"),
            snps=pd.to_numeric(s.get("SNPs") or None, errors="coerce"),
            match=s["match"].strip(),
            kind="close_family" if close else ("lineage" if code else "unplaced"),
            lineage=code,
            ancestral_couple=LINEAGE.sub("", name).strip() if code else "",
            cluster=name,
            # the group's side flag and the code in its name can disagree
            # (e.g. "MMFM ..." flagged "both"); the code wins, the flag is kept
            painter_side=side_painter,
            side_conflict=bool(side_code and side_painter in ("pat", "mat")
                               and side_code != side_painter),
            certainty=pd.to_numeric(s.get("certainty"), errors="coerce"),
            evidence=s.get("notes", "").strip(),
            asserted_by=asserted_by,
            source=f"{Path(path).name} (profile '{b['profile']}')",
        ))
    return pd.DataFrame(rows)


def load_all(backups, **kw):
    """backups: {donor key: backup path}; kw as for assertions()"""
    return pd.concat([assertions(p, k, **kw) for k, p in backups.items()],
                     ignore_index=True)


if __name__ == "__main__":
    import sys
    import config
    cfg = config.load()
    D = cfg["data_dir"]
    if not cfg.get("dnapainter"):
        raise SystemExit("no [dnapainter] backups in family.toml; nothing to read")
    df = load_all({k: D / f for k, f in cfg["dnapainter"].items()},
                  asserted_by=f"{cfg.get('owner', 'unknown')} (DNA Painter, manual)",
                  close_family=cfg.get("match_filter", {}).get("close_family", ()))
    if len(sys.argv) > 1:                      # an explicit file: just that
        out = sys.argv[1]
        df.to_csv(out, index=False)
    else:
        import outputs
        out = outputs.write(D, "assertions_dnapainter.csv", df)
    print(df.groupby(["subject", "kind"]).size().unstack(fill_value=0))
    print(df[df.kind == "lineage"].groupby(["subject", "lineage"]).size()
          .unstack(fill_value=0))
    print("side conflicts:", df.side_conflict.sum(), "->", out)
    print("phasing anchors:", ", ".join(config.anchor_sources(cfg)),
          "" if "dnapainter" in config.anchor_sources(cfg) else "(DNA Painter: a check only)")
