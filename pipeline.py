"""Run the analysis chain in order and keep a log of what each step did.

    python3 pipeline.py              # every step
    python3 pipeline.py placement    # from a step onward (see STEPS)
    python3 pipeline.py --only icw   # one step
    python3 pipeline.py --keep-going # run every step, list the failed ones at the end

The log is written as it goes: `output/pipeline_log.md` is the current or
latest run (watch it with `python3 serve.py`), and each run keeps its own file
in `output/logs/`. A lock file allows one run at a time. The log is private;
docs/pipeline.md shows an anonymised example.

Order matters: placement needs the painting, the consistency check needs
placement, and the phasing model uses the shared segments the previous
placement found (a first run on new data may want a second pass). Each step in
order: docs/pipeline.md.
"""
import os
import subprocess
import sys
import time
from datetime import datetime

from sg.common import config

# (name, command, what it does)
STEPS = [
    ("tests", ["-m", "unittest", "discover", "-s", "tests", "-q"], "smoke tests on synthetic data"),
    ("painter", ["-m", "sg.readers.dnapainter_io"], "DNA Painter backups -> lineage assertions (a check, not an input, unless [phasing] anchors lists them)"),
    ("anchors", ["-m", "sg.genetics.documented_anchors"], "documented relatives and tree links -> weighted anchor assertions"),
    ("phasing", ["-m", "sg.genetics.phasing_labels"], "raw kits + mother -> inheritance HMM -> grandparent painting"),
    ("placement", ["-m", "sg.genetics.revelations"], "segment exports -> parent and grandparent per segment and match"),
    ("consistency", ["-m", "sg.genetics.sibling_consistency"], "segments siblings share vs the painting; short-block corrections"),
    ("placement2", ["-m", "sg.genetics.revelations"], "placement again, on the corrected painting"),
    ("copymodel", ["-m", "sg.genetics.copy_model"], "copy model from lineage assertions and copy labels; placement through it, compared with the painting's"),
    ("deep", ["-m", "sg.genetics.deep_labels", "--png"], "great-grandparent labels: coverage, claims, dissents; deep paintings"),
    ("icw", ["-m", "sg.genetics.icw_phasing"], "shared-match graphs vs the placement; candidates"),
    ("export", ["-m", "sg.views.dnapainter_export"], "painting -> DNA Painter backups and PNGs"),
    ("graph", ["-m", "sg.genetics.match_graph"], "merged shared-match graph with observability -> GEXF, PNGs"),
    ("prospects", ["-m", "sg.genetics.prospects"], "close matches not in the tree, with side and branch hints"),
    ("relatives", ["-m", "sg.genetics.relationship_check"], "confirmed relatives: expected (kinship) vs observed cM"),
    ("tree", ["-m", "sg.store.tree_store", "import-tree"], "the configured GEDCOM replaces the tree in the store (edits kept)"),
    ("store", ["-m", "sg.store.tree_store", "import-genetics", "pipeline"], "genetics into the tree store (edits kept)"),
    ("places", ["-m", "sg.store.tree_store", "import-places", "pipeline"], "gazetteer places into the tree store; events linked to places"),
    ("volumes", ["-m", "sg.records.volumes"], "record volumes, pages and farms -> archives.html, volume_refs.csv"),
    ("residences", ["-m", "sg.records.residences"], "residence histories: gaps, moves, uncollated stays -> residences.csv"),
    ("geography", ["-m", "sg.views.geoview"], "filterable map of events and records -> geography.html"),
    ("family", ["-m", "sg.views.familyview"], "one person in focus: pedigree, close family, counts -> family.html"),
    ("genome", ["-m", "sg.views.genomeview"], "one donor's matches and their segments on the copies the copy model paints -> genome.html"),
    ("placerules", ["-m", "sg.views.places_rules"], "place-recognition rules, and which rule resolved each place string -> places_rules.html"),
    ("gedmatch", ["-m", "sg.readers.gedmatch_io"], "model vs GEDmatch one-to-one FIR/HIR (validation)"),
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


def run(names, keep_going=False):
    """Run the steps in order. The log is rewritten after every step (and
    says which step is running), so it can be watched while the run goes:
    output/pipeline_log.md is the current or latest run, and every run also
    keeps its own file, output/logs/pipeline_<date>_<time>.md. With
    keep_going a failed step does not stop the run (a family without raw
    kits fails at the painting and everything reading it); the failed steps
    are listed at the end. Returns the names of the failed steps."""
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
    parts, ok, status_line, failed = [], 0, "", []
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
                failed.append(name)
                if not keep_going:
                    status_line = f"**Status: stopped** at step {name} (failed)"
                    break
                continue
            ok += 1
        else:
            status_line = f"**Status: finished** {datetime.now():%H:%M:%S}, {ok} of {len(todo)} steps ok"
            if failed:
                status_line += f"; failed: {', '.join(failed)}"
    except KeyboardInterrupt:
        status_line = "**Status: interrupted**"
        raise
    finally:
        _write(files, head + f"\n{status_line or '**Status: stopped**'} "
                             f"({(datetime.now() - started).seconds // 60} min)\n\n" + "\n".join(parts))
        lock.unlink(missing_ok=True)
    print(f"log -> {files[0]} (and {files[1].name})")
    if failed and keep_going:
        print(f"failed: {', '.join(failed)}")
    return failed


if __name__ == "__main__":
    names = [n for n, *_ in STEPS]
    a = sys.argv[1:]
    keep = "--keep-going" in a
    a = [x for x in a if x != "--keep-going"]
    unknown = [x for x in (a[1:] if a[:1] == ["--only"] else a[:1]) if x not in names]
    if unknown or len(a) > 1 and a[0] != "--only":
        raise SystemExit(f"unknown step or argument: {' '.join(unknown or a[1:])}\n"
                         f"usage: pipeline.py [--keep-going] [STEP | --only STEP...]\n"
                         f"steps: {' '.join(names)}")
    if a[:1] == ["--only"]:
        names = a[1:]
    elif a:
        names = names[names.index(a[0]):]
    sys.exit(1 if run(names, keep_going=keep) else 0)
