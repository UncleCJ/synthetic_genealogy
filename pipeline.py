"""
Run the analysis chain in order and keep a log of what each step did.

    python3 pipeline.py              # every step
    python3 pipeline.py placement    # from a step onward (see STEPS)
    python3 pipeline.py --only icw   # one step

Each run appends to `<data_dir>/pipeline_log.md`: per step the command,
the time it took, whether it succeeded, and its summary lines (the lines a
step prints, minus per-file loader chatter). The log lives in `data/`
because the output names matches and relatives; PIPELINE.md shows an
anonymised example.

Order matters: placement needs the painting, the consistency check needs
placement, and the phasing model uses the shared segments the previous
placement found (so a first run on new data may want a second pass).
"""
import subprocess
import sys
import time
from datetime import datetime

import config

# (name, command, what it does)
STEPS = [
    ("painter", ["dnapainter_io.py"], "DNA Painter backups -> lineage assertions"),
    ("anchors", ["documented_anchors.py"], "documented relatives -> weighted anchor assertions"),
    ("phasing", ["phasing_labels.py"], "raw kits + mother -> inheritance HMM -> grandparent painting"),
    ("placement", ["revelations.py"], "segment exports -> parent and grandparent per segment and match"),
    ("consistency", ["sibling_consistency.py"], "segments siblings share vs the painting; short-block corrections"),
    ("placement2", ["revelations.py"], "placement again, on the corrected painting"),
    ("icw", ["icw_phasing.py"], "shared-match graphs vs the placement; candidates"),
    ("export", ["dnapainter_export.py"], "painting -> DNA Painter backups and PNGs"),
    ("graph", ["match_graph.py"], "merged shared-match graph with observability -> GEXF, PNGs"),
    ("prospects", ["prospects.py"], "close matches not in the tree, with side and branch hints"),
    ("gedmatch", ["gedmatch_io.py"], "model vs GEDmatch one-to-one FIR/HIR (validation)"),
    ("research", ["research_log.py"], "check research entries, write research/INDEX.md"),
]
NOISE = ("rows,", "shared by all", "exact duplicate", "DtypeWarning", "low_memory")


def run(names):
    cfg = config.load()
    log = cfg["data_dir"] / "pipeline_log.md"
    out = [f"\n## Run {datetime.now():%Y-%m-%d %H:%M}\n"]
    for name, cmd, what in STEPS:
        if name not in names:
            continue
        t0 = time.time()
        p = subprocess.run([sys.executable, *cmd], capture_output=True, text=True)
        dt = time.time() - t0
        lines = [l for l in (p.stdout + ("\n" + p.stderr if p.returncode else "")).splitlines()
                 if l.strip() and not any(n in l for n in NOISE)]
        status = "ok" if p.returncode == 0 else f"FAILED ({p.returncode})"
        head = f"### {name}: {what}\n\n`python3 {' '.join(cmd)}`, {dt:.0f} s, {status}\n"
        body = "\n".join(lines[-25:])
        out.append(head + ("\n```\n" + body + "\n```\n" if body else ""))
        print(f"{name:12s} {status:10s} {dt:6.0f} s  {what}")
        if p.returncode:
            print(body)
            break
    with open(log, "a", encoding="utf-8") as f:
        f.write("\n".join(out))
    print(f"log -> {log}")


if __name__ == "__main__":
    names = [n for n, *_ in STEPS]
    a = sys.argv[1:]
    if a[:1] == ["--only"]:
        names = a[1:]
    elif a:
        names = names[names.index(a[0]):]
    run(names)
