# RESEARCH_LOG(1)

## NAME

research_log.py — check the research entries, write their index, create entries, find entries by chromosome position

## SYNOPSIS

    python3 research_log.py
    python3 research_log.py new <kind> <title>
    python3 research_log.py at <chrom> <bp>

## DESCRIPTION

With no argument, reads every entry, checks it, rewrites `INDEX.md` (active
entries first, then settled, by kind, newest first, with a one-line
summary) and prints the entry count. Each problem is printed as
`problem: ...` and the exit status is 1. Problems checked: no `+++` TOML
header; a missing `id`, `kind`, `title`, `status` or `created`; `id` not
equal to the file name; unknown kind; a status not allowed for the kind;
a `related` id with no entry. The pipeline's `research` step runs this.

Kinds and their statuses (the first is the starting one):

| Kind | Id prefix | Statuses |
|---|---|---|
| `question` | `q-` | open, parked, answered |
| `hypothesis` | `h-` | open, supported, refuted, parked |
| `segment` | `s-` | open, explained, parked |
| `finding` | `f-` | settled, retracted |
| `note` | `n-` | open, done |

**new** writes a skeleton entry (header with today's date, sections
Context, Evidence, Next, Log) and prints its path. The id is the prefix and
a slug of the title (lowercase, at most 40 characters); an existing file is
refused. It does not rebuild the index.

**at** prints each entry whose `segments` list holds one covering
*chrom* and *bp* (a number, e.g. `52000000`): id, status, subject,
position in Mb, match.

The entry format and header fields are in `research/README.md`.

## FILES

Entries: `notes/research/*.md` in the family's data folder (private).
If that folder does not exist, or the config cannot be loaded, the
repo's `research/` is used instead. `README.md` and `INDEX.md` are not
entries. Writes `INDEX.md` there, and new entries.

## ENVIRONMENT

`FAMILY_CONFIG` — another family's `family.toml` (and so its notes).

## EXAMPLES

    python3 research_log.py new question "How is Example related to us?"
    python3 research_log.py
    python3 research_log.py at 7 52000000

## BUGS

`at` does not check its arguments beyond the count; a non-numeric *bp*
is a Python error. The checks do not validate `confidence`, dates or
`segments` fields.

## SEE ALSO

pipeline(1), serve(1), `research/README.md`, `docs/data.md`
