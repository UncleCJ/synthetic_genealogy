# TREE_STORE(1)

## NAME

tree_store.py — the editable store: imports, rebuilds, and additions with provenance

## SYNOPSIS

    python3 tree_store.py [stats | notes]
    python3 tree_store.py import-tree | import-places | import-genetics [label]
    python3 tree_store.py rebuild <gedcom> [label]
    python3 tree_store.py export <out.ged> [--places]

    python3 tree_store.py [--who W] add-source <id> <title> [--author A] [--text T] --why R
    python3 tree_store.py [--who W] add-event <owner> <tag> [--type T] [--date D] [--place P]
                          [--value V] [--source S [--page P]] --why R
    python3 tree_store.py [--who W] cite <source> (--event N | --person ID) [--page P] --why R
    python3 tree_store.py [--who W] set-event <n> [--type T] [--date D] [--place P] [--value V] --why R
    python3 tree_store.py [--who W] link-match <match-id> <person> --why R
    python3 tree_store.py [--who W] drop (event|citation|source) <key> --why R

## DESCRIPTION

The store (`data/store/tree.sqlite`) holds the imported tree and genetics
plus your additions. Every edit is written at once to `tree_edits.json`
(replayed on every re-import) and, with its `--why`, to `tree_notes.md`.

The edit commands **add**. `set-event` and `drop` work on your own rows
only; an imported row is refused with a pointer to errata(5). Each edit
command prints the new row's id and nothing else, so it can be captured.

## EDIT COMMANDS

**add-source** *id* *title* — a source MyHeritage does not have. Ids are
yours; `SRC:<short-name>-<date>` reads well. Refuses an id in use.

**add-event** *owner* *tag* — an event on a person (`MH:I123`) or family
(`MH:F45`). *tag* is GEDCOM: `BIRT`, `DEAT`, `MARR`, `RESI`, `OCCU`, `EVEN`
(with `--type` for a free kind, e.g. `--type Letter`). Dates as GEDCOM
(`2 MAY 1931`, `ABT 1900`, `BEF 1931`). `--source` cites it in one go.
Prints the event number.

**cite** *source* — a citation on one event (`--event N`, imported or
yours) or on the person as a whole (`--person ID`). Prints the citation
number.

**set-event** *n* — change your own event's fields.

**link-match** *match-id* *person* — a DNA match is this tree person.

**drop** — remove your own event (with its citations), citation or source.

## OPTIONS

`--who` *W* — signs the edit (`origin = edit:W`); default `$TREE_WHO`,
else `$USER`. Goes before the subcommand.

`--why` *R* — required; the reason, as you would want to read it in a
year.

## FILES

`data/store/tree.sqlite` (rebuildable), `tree_edits.json` (your edits:
back it up), `tree_notes.md` (the log), `family.toml` or `$FAMILY_CONFIG`
(which data folder).

## EXAMPLES

    export TREE_WHO=AE

A letter, an event dated by it, and the letter cited on the event:

    src=$(python3 tree_store.py add-source SRC:letter-1931-05-02 \
          "Letter, Anna Exempel to her sister, 2 May 1931" --author "Anna Exempel" \
          --text "Transcribed from a scan" --why "family papers, scanned")
    ev=$(python3 tree_store.py add-event MH:I123 RESI --date "BEF 2 MAY 1931" \
          --place "Exempelstad" --source "$src" --page "p. 1" --why "letter is written from there")

The same memoir cited on every child of a couple:

    for c in $(python3 store_query.py --bare sql "select c.child from child c
                 join family f on f.id=c.family where f.husb='MH:I200'"); do
      python3 tree_store.py cite SRC:memoir-1960 --person "$c" --why "the memoir names all children"
    done

Cite a source on an imported birth:

    n=$(python3 store_query.py --bare sql "select n from event where owner='MH:I123' and tag='BIRT'")
    python3 tree_store.py cite SRC:memoir-1960 --event "$n" --page "p. 3" --why "gives the farm"

Link a DNA match:

    m=$(python3 store_query.py --bare sql "select id from dna_match where name like 'Erik Ex%'")
    python3 tree_store.py link-match "$m" MH:I456 --why "shared ancestors confirmed with Erik"

Undo your last event:

    python3 tree_store.py drop event "$ev" --why "wrong person"

What you have added so far:

    python3 tree_store.py notes | grep -v '· import:'

## BUGS

Person names, sexes and families have no edit command; changes to imported
people go to errata(5). `set_person` exists in the Python API but an edited
imported person is not refreshed by later imports.

## SEE ALSO

tree-edits(7), store_query(1), errata(5)
