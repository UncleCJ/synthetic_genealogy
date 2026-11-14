# BACKUP(1)

## NAME

backup.py — which hand-kept private files changed since the last backup, and zip snapshots for reading elsewhere

## SYNOPSIS

    python3 backup.py [status]
    python3 backup.py mark [FILE ...]
    python3 backup.py snapshot [--input] [--to DIR]

## DESCRIPTION

**status** (the default; any unknown word prints the usage text instead)
lists every tracked file as new, changed, unchanged or gone locally,
compared by SHA-256 with the record of the last backup, with the Drive
subfolder it belongs in, its size and the date last marked. The last line
counts files to back up and unchanged ones.

**mark** records the current checksums as backed up. With no *FILE*, all
tracked files; otherwise only those named (by the key shown in `status`, or
by path). Run it after the upload, not before.

**snapshot** writes one dated zip of `output/` (at the top) and `notes/`
(as `notes/`), plus `serve.py` and a README. `--input` adds the downloads
in `input/`. It goes to `--to`, else `[backup] snapshot_dir` in
`family.toml`, else `snapshots/` in the data folder. On another computer,
unzip and run `serve.py --dir` on the folder. A snapshot is for reading,
not the backup of record.

The program never uploads. The upload is done by hand or through the
Drive connector, then `mark`. What is tracked and where it goes:
`docs/privacy-workflow.md`, "Backing up the private side".

## OPTIONS

`--input` — snapshot also the downloads.

`--to` *DIR* — snapshot destination (`~` is expanded; created if missing).

## FILES

Tracked: `family.toml`; for the main family also `PRIVATE_NOTES.md` and
`docs/concepts.md`, `docs/roadmap.md` (for chats that cannot reach GitHub);
everything under the data folder's `notes/` except `INDEX.md`; the store's
`tree_edits.json` and `tree_notes.md`; and the small Markdown reports in
`output/` (read-only copies).

Writes `cache/backup_state.json` in the data folder (`mark` only) and the
snapshot zip (written as `.part`, then renamed, so a synced folder never
sees half a zip). All private.

## ENVIRONMENT

`FAMILY_CONFIG` — another family's `family.toml`. That family's file is the
one tracked, and `PRIVATE_NOTES.md` and the public docs are left out.

## EXAMPLES

    python3 backup.py status
    python3 backup.py mark notes/research/q-example.md
    python3 backup.py snapshot --input --to ~/Example/snapshots

## SEE ALSO

serve(1), `docs/privacy-workflow.md`, `docs/data.md`
