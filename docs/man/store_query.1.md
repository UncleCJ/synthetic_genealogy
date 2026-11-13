# STORE_QUERY(1)

## NAME

store_query.py — read-only questions to the tree store

## SYNOPSIS

    python3 store_query.py [--db PATH] [--bare] find <name words>
    python3 store_query.py [--db PATH] [--bare] person <name words | id>
    python3 store_query.py [--db PATH] [--bare] sql "<select ...>"

## DESCRIPTION

**find** lists the people whose names contain every word, one line each.
Matching ignores case, accents and doubled letters (Andersson finds
Anderson) and covers married names.

**person** shows parents (with pedigree type), spouses, children and kits;
a name fitting several people lists them instead.

**sql** runs any query, tab-separated with a header line. `--bare` drops
the header, for `$(...)` and loops. The database is opened read-only.

## TABLES

| Table | Rows | Key columns |
|---|---|---|
| `person` | people | `id` (MH:I123), `given`, `surname`, `married` (JSON list), `origin` |
| `family` | couples | `id` (MH:F45), `husb`, `wife` |
| `child` | parent links | `family`, `child`, `pedi` (birth, adopted, …) |
| `event` | life events | `n`, `owner`, `tag`, `type`, `date`, `place`, `value`, `place_id`, `origin` |
| `source` | sources | `id`, `title`, `author`, `text_` |
| `citation` | citations | `n`, `owner`, `event` (null: the person as a whole), `source`, `page` |
| `dna_match` | matches | `id`, `vendor`, `name`, `person` (linked tree person) |
| `place` | places | `id`, `name`, `kind`, `parish`, `qid`, `lat`, `lon` |
| `change` | the edit log | `at`, `who`, `what`, `why` |

`origin` is `import:<label>` or `edit:<who>`. Dates are text as written in
GEDCOM; compare years with `substr(date, -4)` or `like '%1890'`.

## EXAMPLES

A person's events with their numbers (for `cite --event`):

    python3 store_query.py sql "select n, tag, type, date, place from event where owner='MH:I123' order by n"

What cites a person, and on which event:

    python3 store_query.py sql "select c.n, c.event, e.tag, s.title, c.page from citation c
      join source s on s.id=c.source left join event e on e.n=c.event where c.owner='MH:I123'"

Is that source already here?

    python3 store_query.py sql "select id, title from source where title like '%memoir%'"

Every addition so far:

    python3 store_query.py sql "select 'event' as kind, n, owner, tag, date from event where origin like 'edit:%'
      union all select 'citation', n, owner, source, page from citation where origin like 'edit:%'"

Everyone born in one place in the 1800s:

    python3 store_query.py sql "select owner, date from event where tag='BIRT' and place like 'Exempelby%'
      and date like '%18__'"

Person lines for a list of ids:

    for p in $(python3 store_query.py --bare sql "select child from child where family='MH:F45'"); do
      python3 store_query.py person "$p" | head -1
    done

Unlinked DNA matches with a name like a tree surname:

    python3 store_query.py sql "select id, name from dna_match where person is null and name like '%Exempel%'"

## ENVIRONMENT

`FAMILY_CONFIG` — another family's `family.toml` (and so its store).

## SEE ALSO

tree_store(1), tree-edits(7)
