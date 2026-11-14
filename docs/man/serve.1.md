# SERVE(1)

## NAME

serve.py — browse the pipeline's results in a browser, without Claude

## SYNOPSIS

    python3 serve.py [--port N] [--no-browser] [--lan]
    python3 serve.py --index
    python3 serve.py --dir FOLDER [--port N] [--no-browser]

## DESCRIPTION

Writes `index.html` into the output folder (every output grouped as Views,
Reports, Tables, Images, Other, with a line on what each is, and the
research notes after the views), then serves that folder over HTTP and
opens the browser. Stop with Ctrl-C.

Markdown files open as formatted pages that can follow changes (on by
default for logs, so `pipeline_log.md` updates during a run; a "running"
badge shows while it does). CSV files open as sortable, filterable tables,
2000 rows shown at a time, 50000 read. Add `?raw=1` to any URL for the
file itself. Rendering Markdown loads `marked` from a CDN, so it needs
internet; without it the page falls back to plain text.

The hand-kept notes folder is served read-only under `/notes/`. Pages hold
names and DNA results, so it listens on 127.0.0.1 only.

## OPTIONS

`--port` *N* — default 8000.

`--no-browser` — do not open a browser tab.

`--lan` — listen on all interfaces and print the machine's local-network
addresses. There is no password: a home network only.

`--index` — write `index.html` and exit; no server. The pipeline's last
step does this.

`--dir` *FOLDER* — serve an unzipped snapshot from backup(1) instead of the
configured data folder; needs no `family.toml`. Notes are read from the
folder's `notes/`.

## FILES

Reads the family's `output/` and `notes/` layers (`--dir`: the folder and
its `notes/`). Writes only `index.html` in the folder served. The output
folder is created if missing.

## ENVIRONMENT

`FAMILY_CONFIG` — another family's `family.toml` (and so its folders).
Not read with `--dir`.

## EXAMPLES

    python3 serve.py
    python3 serve.py --port 8765 --no-browser
    python3 serve.py --dir ~/Downloads/example_snapshot

## BUGS

Entries in `KNOWN` (the index descriptions) name files by hand; a renamed
output is listed without its description.

## SEE ALSO

pipeline(1), backup(1), `docs/data.md`
