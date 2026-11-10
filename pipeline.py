"""
Run the analysis chain in order and keep a log of what each step did.

    python3 pipeline.py              # every step
    python3 pipeline.py placement    # from a step onward (see STEPS)
    python3 pipeline.py --only icw   # one step

Each run writes its log as it goes: per step the command, the time it
took, whether it succeeded, and its summary lines (the lines a step prints,
minus per-file loader chatter), and while a step runs, which one.
`output/pipeline_log.md` is the current or latest run (watch it with
`python3 serve.py`); each run also keeps its own file in `output/logs/`, so
nothing is rotated or overwritten. A lock file allows one run at a time.
The log is private (it names matches and relatives); docs/pipeline.md shows an
anonymised example.

The grandparents in the painting are named by documented relatives and
tree links ([phasing] anchors in family.toml); DNA Painter paintings are
read but, unless listed there, only compared with the placement.

Order matters: placement needs the painting, the consistency check needs
placement, and the phasing model uses the shared segments the previous
placement found (so a first run on new data may want a second pass).
"""
import os
import subprocess
import sys
import time
from datetime import datetime

import config

# (name, command, what it does)
STEPS = [
    ("tests", ["-m", "unittest", "discover", "-s", "tests", "-q"], "smoke tests on synthetic data"),
    ("painter", ["dnapainter_io.py"], "DNA Painter backups -> lineage assertions (a check, not an input, unless [phasing] anchors lists them)"),
    ("anchors", ["documented_anchors.py"], "documented relatives and tree links -> weighted anchor assertions"),
    ("phasing", ["phasing_labels.py"], "raw kits + mother -> inheritance HMM -> grandparent painting"),
    ("placement", ["revelations.py"], "segment exports -> parent and grandparent per segment and match"),
    ("consistency", ["sibling_consistency.py"], "segments siblings share vs the painting; short-block corrections"),
    ("placement2", ["revelations.py"], "placement again, on the corrected painting"),
    ("copymodel", ["copy_model.py"], "copy model from lineage assertions alone, beside the painting (round 2 sketch)"),
    ("icw", ["icw_phasing.py"], "shared-match graphs vs the placement; candidates"),
    ("export", ["dnapainter_export.py"], "painting -> DNA Painter backups and PNGs"),
    ("graph", ["match_graph.py"], "merged shared-match graph with observability -> GEXF, PNGs"),
    ("prospects", ["prospects.py"], "close matches not in the tree, with side and branch hints"),
    ("relatives", ["relationship_check.py"], "confirmed relatives: expected (kinship) vs observed cM"),
    ("store", ["tree_store.py", "import-genetics", "pipeline"], "genetics into the tree store (edits kept)"),
    ("places", ["tree_store.py", "import-places", "pipeline"], "gazetteer places into the tree store; events linked to places"),
    ("volumes", ["volumes.py"], "record volumes; residence timelines and life maps -> volumes.html, people.html"),
    ("residences", ["residences.py"], "residence histories: gaps, moves, uncollated stays -> residences.csv"),
    ("geography", ["geoview.py"], "filterable map of events and records -> geography.html"),
    ("placerules", ["places_rules.py"], "place-recognition rules, and which rule resolved each place string -> places_rules.html"),
    ("gedmatch", ["gedmatch_io.py"], "model vs GEDmatch one-to-one FIR/HIR (validation)"),
    ("research", ["research_log.py"], "check research entries, write notes/research/INDEX.md"),
    ("index", ["serve.py", "--index"], "index page of all outputs (browse with: python3 serve.py)"),
]
# A fixed hash seed makes runs reproducible: several steps iterate sets of
# names (shared-match graphs), and ties then break the same way every run.
ENV = dict(os.environ, PYTHONHASHSEED="0")
NOISE = ("rows,", "shared by all", "exact duplicate", "DtypeWarning", "low_memory")


def _alive(pid):
    try:
        os.kill(pid, 0)
        return True
    except (OSError, ValueError):
        return False


def _lock(out):
    """One run at a time: output/.pipeline.lock holds the running pid; a
    lock left by a run that died is taken over."""
    lock = out / ".pipeline.lock"
    for _ in range(2):
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, f"{os.getpid()} {datetime.now():%Y-%m-%d %H:%M:%S}\n".encode())
            os.close(fd)
            return lock
        except FileExistsError:
            pid, _, since = lock.read_text().partition(" ")
            if pid.strip().isdigit() and _alive(int(pid)):
                raise SystemExit(f"another pipeline run is going (pid {pid.strip()}, since {since.strip()}); "
                                 f"watch output/pipeline_log.md")
            lock.unlink(missing_ok=True)
    raise SystemExit("could not take the pipeline lock")


def _write(paths, text):
    """Replace each file whole (write a temporary file, then rename), so a
    reader never sees half a log."""
    for p in paths:
        tmp = p.with_name(p.name + ".tmp")
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, p)


def run(names):
    """Run the steps in order. The log is rewritten after every step (and
    says which step is running), so it can be watched while the run goes:
    output/pipeline_log.md is the current or latest run, and every run also
    keeps its own file, output/logs/pipeline_<date>_<time>.md."""
    cfg = config.load()
    out = cfg["data_dir"].layer("output")
    logs = out / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    lock = _lock(out)
    started = datetime.now()
    files = [out / "pipeline_log.md", logs / f"pipeline_{started:%Y-%m-%d_%H%M%S}.md"]
    todo = [s for s in STEPS if s[0] in names]
    head = (f"# Pipeline run {started:%Y-%m-%d %H:%M:%S}\n\n"
            f"Steps: {', '.join(n for n, *_ in todo)}. Earlier runs: `logs/`.\n")
    parts, ok, status_line = [], 0, ""
    try:
        for i, (name, cmd, what) in enumerate(todo, 1):
            _write(files, head + f"\n**Status: running** step {i} of {len(todo)}: {name} "
                          f"({what}), since {datetime.now():%H:%M:%S}\n\n" + "\n".join(parts))
            t0 = time.time()
            p = subprocess.run([sys.executable, *cmd], capture_output=True, text=True, env=ENV)
            dt = time.time() - t0
            lines = [l for l in (p.stdout + ("\n" + p.stderr if p.returncode else "")).splitlines()
                     if l.strip() and not any(n in l for n in NOISE)]
            status = "ok" if p.returncode == 0 else f"FAILED ({p.returncode})"
            body = "\n".join(lines[-25:])
            parts.append(f"## {name}: {what}\n\n`python3 {' '.join(cmd)}`, {dt:.0f} s, {status}\n"
                         + ("\n```\n" + body + "\n```\n" if body else ""))
            print(f"{name:12s} {status:10s} {dt:6.0f} s  {what}")
            if p.returncode:
                print(body)
                status_line = f"**Status: stopped** at step {name} (failed)"
                break
            ok += 1
        else:
            status_line = f"**Status: finished** {datetime.now():%H:%M:%S}, {ok} of {len(todo)} steps ok"
    except KeyboardInterrupt:
        status_line = "**Status: interrupted**"
        raise
    finally:
        _write(files, head + f"\n{status_line or '**Status: stopped**'} "
                             f"({(datetime.now() - started).seconds // 60} min)\n\n" + "\n".join(parts))
        lock.unlink(missing_ok=True)
    print(f"log -> {files[0]} (and {files[1].name})")


if __name__ == "__main__":
    names = [n for n, *_ in STEPS]
    a = sys.argv[1:]
    if a[:1] == ["--only"]:
        names = a[1:]
    elif a:
        names = names[names.index(a[0]):]
    run(names)
