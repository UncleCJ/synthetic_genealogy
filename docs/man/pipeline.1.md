# PIPELINE(1)

## NAME

pipeline.py — run the analysis chain in order and log what each step did

## SYNOPSIS

    python3 pipeline.py [--keep-going]
    python3 pipeline.py [--keep-going] <step>
    python3 pipeline.py [--keep-going] --only <step> [<step> ...]

## DESCRIPTION

Runs each step of the chain as `python3 <script> ...` in a subprocess, in
the fixed order of `STEPS` in the source, and prints one line per step
(name, ok or FAILED, seconds). The steps and why they come in this order
are in `docs/pipeline.md`; do not rely on the list here.

With no argument every step runs. A step name runs from that step onward.
`--only` runs just the steps named (still in chain order). An unknown step
name is not checked: a name as first argument raises a Python `ValueError`,
and names after `--only` are silently skipped.

The first failing step stops the run, exit status 1. With `--keep-going`
the run continues and the failed steps are listed at the end; steps that
read a failed step's output will fail too (a family without raw kits fails
at the painting and everything after it). Exit status is 1 if any step
failed, else 0.

`PYTHONHASHSEED=0` is set for every step so runs are reproducible.
One run at a time: the lock `output/.pipeline.lock` holds the running pid;
a second run exits with a message, a lock left by a dead run is taken over.

## OPTIONS

`--keep-going` — may stand anywhere among the arguments.

## FILES

Reads nothing itself; the steps read and write the data folder. Writes, in
the family's `output/` layer:

`pipeline_log.md` — the current or latest run, rewritten after every step
with a status line (running, stopped, finished, interrupted). Watch it with
serve(1).

`logs/pipeline_<date>_<time>.md` — the same, kept for each run.

`.pipeline.lock` — see above.

Each log entry shows the command, seconds, status and the last 25 lines of
the step's output (noise lines filtered; stderr only on failure). The logs
are private; `docs/pipeline.md` shows an anonymised example.

## ENVIRONMENT

`FAMILY_CONFIG` — another family's `family.toml`, and so its data folder.
Passed on to every step.

## EXAMPLES

Everything, watching the log in another terminal:

    python3 pipeline.py
    python3 serve.py

After new segment exports, from placement onward:

    python3 pipeline.py placement

Rebuild the tree and the views only, then the index:

    python3 pipeline.py --only tree store places family index

A second family, whatever fails:

    FAMILY_CONFIG=data-example/family.toml python3 pipeline.py --keep-going

## BUGS

The `tests` step comes first, so a failing test stops a plain run; start
from the next step or use `--only` to skip it.

## SEE ALSO

serve(1), research_log(1), `docs/pipeline.md`, `docs/data.md`
