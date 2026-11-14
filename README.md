<div align="center">

# Synthetic Genealogy

Family history where each kind of evidence checks the others: DNA, the family tree, church records and the places they name.

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE) [![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/) [![Tests](https://github.com/UncleCJ/synthetic_genealogy/actions/workflows/tests.yml/badge.svg)](https://github.com/UncleCJ/synthetic_genealogy/actions/workflows/tests.yml)

</div>

<div align="center">

### Släktforskare? Läs det här först

Det här är mitt hobbyprojekt för att låta släktträdet, kyrkböckerna, orterna och DNA-tester pröva och stödja varandra. Du behöver inte kunna något om DNA, och du behöver ingen AI. Allt är vanliga program som körs på din egen dator, och din data stannar hos dig. Vill du prova? Hör av dig, så sätter vi oss tillsammans.

</div>

<details>
<summary>Läs mer på svenska</summary>

- Från arkivsidan: programmen läser en vanlig GEDCOM-export, till exempel från MyHeritage. Varje ortnamn knyts till sin socken (med Riksarkivets referenskod) och, där det går, till gården. Varje källhänvisning blir volym och sida i husförhörslängden. Du får se vilka år som saknar källa, och vilken volym som skulle täcka luckan, plus en karta över varje anfaders liv.
- Från DNA-sidan: har några syskon testat sig, gärna med en förälder, kan programmen räkna ut vilken farfar, farmor, morfar eller mormor varje bit DNA kommer ifrån. Då hamnar varje DNA-matchning på en gren i trädet, och trädet och DNA:t kontrollerar varandra.
- Om AI: jag har skrivit mycket av koden med hjälp av AI. Det är bekvämt, men inget du behöver för att använda verktygen.
- Om integritet: inget laddas upp någonstans. DNA-uppgifter är känsliga enligt GDPR, så allt personligt stannar i en privat mapp.
- Delar du dina MyHeritage-matchningar med mig: [så laddar du ned segmenten](docs/myheritage-download.sv.md).
- Det här är ett pågående projekt, inte en färdig tjänst. Resten av sidan är på engelska och mer teknisk.

</details>

## Contents

- [What it is](#what-it-is)
- [Who it's for](#who-its-for)
- [Keeping your research private](#keeping-your-research-private)
- [Trying it](#trying-it)
- [Showcase](#showcase)
- [Documentation](#documentation)
- [Background](#background)
- [License](#license)

## What it is

Genealogy's evidence is scattered: DNA results with one vendor, the family tree with another, church records in archives and their indexes, places on maps. Each piece is partial, and together they can check one another. This project connects them, working from ordinary exports: a GEDCOM file, vendor segment and match lists, and raw DNA files where relatives lend them.

- **Records.** Every place in the tree goes to its parish (with Riksarkivet's reference code) and, where it can, to a farm or village; every citation becomes a volume and page. Residences become stays, the years no volume covers are listed with the volumes that would cover them, and each ancestor's life becomes a map.
- **DNA.** Siblings' raw data, ideally with a donor parent, are painted onto the four grandparents' copies of each chromosome, and every match segment is placed on one grandparent. The tree and the DNA then check each other: for one sibling, 210 of 238 segments from tree-linked matches land on the grandparent their tree path predicts, and most of the rest come from matches linked to the tree only by a common name.

Nothing edits the master tree; corrections are kept beside it with sources, so every view can be rebuilt and every disagreement stays visible. The code is readable Python sketches; treat it as unvalidated unless a check says otherwise.

**Geography: one couple's lives on a map.** A husband chosen in the geography view, his wife added with one click: each one's dated events numbered in order and joined into a path, beside their household examinations. The table below the map gives the date, the farm or village, how precisely it is placed, and whether it comes from a cited record or only from the tree.

![Pair map: a couple's events and records on one map](docs/img/geography_pair.png)

(People are pseudonymised; more views under [Showcase](#showcase).)

## Who it's for

My own family's research comes first. After that, a few pilots, who talk to me before they try it. It is not a public service.

## Keeping your research private

The code is public; the family's DNA and research are not. The project treats that as a feature, not an afterthought:

- **A data folder in layers** by what a file is: `input/` (downloads as received, never edited), `notes/` and `store/` (kept by hand), `cache/` and `output/` (rebuilt) ([docs/data.md](docs/data.md)).
- **Two lines of history:** public commits on `main`, and one `PRIVATE:` commit on top holding the data and config. A git pre-push hook and jj's `git.private-commits` refuse to push it ([docs/privacy-workflow.md](docs/privacy-workflow.md)).
- **Backups outside git:** `python3 backup.py status` lists hand-kept files that changed since the last backup to a private cloud folder, and `backup.py mark` records them; everything else is rebuilt by `pipeline.py`.
- **Data exports:** `python3 backup.py snapshot` writes the outputs and notes as one dated zip that `serve.py` can browse on another computer.
- **A research log:** questions, hypotheses and findings as dated entries that cite the computed output ([schema](research/README.md); the entries stay private).
- **A pseudonymised showcase:** `showcase.py` makes the public screenshots on this page, with a check for names and ids.

## Trying it

The easiest way is together with me: get in touch. Alone, you need Python 3.11 or later:

```bash
git clone https://github.com/UncleCJ/synthetic_genealogy.git
cd synthetic_genealogy
pip install -r requirements.txt
python3 -m unittest discover -s tests      # synthetic data only, no private files
cp examples/family.example.toml family.toml # then describe your own kits, exports and tree
python3 pipeline.py                         # runs the chain, outputs to data/output/
python3 serve.py                            # browse the results on http://127.0.0.1:8000
```

[docs/pipeline.md](docs/pipeline.md) walks through each step with an anonymised run, and what a run on new data needs. To keep several families or experiments apart, point `FAMILY_CONFIG` at another `family.toml`.

## Showcase

The screenshots below come from one family's own data, as of November 2026. Places, parishes, volumes and pages are left as they are; people are pseudonymised ([showcase.py](showcase.py)). Only ancestors from the great-grandparents back are shown, each named by Ahnentafel number and lineage code: No. 12 · MFF is the mother's father's father. Their children and spouses born before 1900 are named after them ("Son 3 of No. 38"). Colours are the four grandparent branches (FF, FM, MF, MM).

**Family: one person in focus.** A great-grandfather, No. 12 · MFF: four generations up, his parents' household and his own, each person with a lifeline on one time scale (the tick is the marriage; a life with no recorded end fades). Two sons born the same day are twins. Below are his life events in date order: residences, occupations, and what happened around him (children born, a parent's death), linked to the people involved. Further down (not shown), his references, volume by volume and page by page. A line on top says how the focus is related to No. 1, with the people along the path as links. Clicking anyone moves the focus.

![The family lens on a great-grandfather: pedigree, households with lifelines, life events](docs/img/family.png)

**Family: walking sideways.** The focus can leave the direct line. Here it is a 3× great-uncle, one of twelve children: the lifelines show at a glance who reached old age and whose end the records don't give. The pedigree and the colours still say where he sits: his parents' colour is the FF branch's, and his sister No. 19, the direct ancestor, has 9 tree-linked matches.

![The family lens on a 3× great-uncle in a household of twelve](docs/img/family_household.png)

**DNA: one sibling's chromosomes painted by grandparent.** For each chromosome, the paternal lane sits above the maternal one. Pale blocks are the grandparent copies decoded from the siblings' and the mother's raw data. Placed match segments of 12 cM or more lie on top, with tree-linked ones darker. Each block is labelled with its support: the number of match segments placed on it, ✓ tree-linked segments that agree with its grandparent, and ✗ those that don't. The ✗ are the cases worth opening first.

![A sibling's grandparent painting with placed match segments and per-block support](docs/img/painting.png)

**Archives: the references.** Each parish carries its Riksarkivet archive code and Wikidata item, with a bar showing how its citations are sourced; the densest farms are listed with every volume and page cited for them. A chosen parish shows its volumes by series, page by page, and its farms and villages on the map; one volume's farms can be coloured by page, to see the order the book walks through the parish.

![Archives: parishes with archive codes, farms with every cited volume and page](docs/img/archives.png)

**Geography: every located event, filterable like a tag browser.** Facets by time, layer, event type, branch, precision of place and date, and parish. Clusters show the colour mix of their points as a ring. The address bar keeps the filter, so any view can be linked.

![All located events of the ancestors, coloured by grandparent branch](docs/img/geography_branches.png)

**Geography, one branch at a time.** The same view and map frame, filtered to each grandparent branch in turn (FF, FM above; MF, MM below). The time facet re-ranges to the filter, so each panel also shows how far back that branch's places reach: from the 1570s on the father's father's side, the 1760s on the mother's mother's.

![The geography view filtered to each grandparent branch in turn, two by two](docs/img/geography_by_branch.png)

## Documentation

| Document | What it covers |
| --- | --- |
| [docs/concepts.md](docs/concepts.md) | Principles, glossary and decisions |
| [docs/genetics.md](docs/genetics.md) | How the genetics work: phasing, placement, the copy model, recursive deduction |
| [docs/records.md](docs/records.md) | How the records work: parishes and congregations, place strings, volumes |
| [docs/architecture.md](docs/architecture.md) | How the modules fit together, by layer |
| [docs/pipeline.md](docs/pipeline.md) | Each step in run order, with an anonymised run |
| [docs/data.md](docs/data.md) | The data folder's layers and viewing the results |
| [docs/myheritage-download.md](docs/myheritage-download.md) | Downloading MyHeritage segments, for donors sharing theirs ([svenska](docs/myheritage-download.sv.md)) |
| [docs/privacy-workflow.md](docs/privacy-workflow.md) | Public and private changesets (git and jj), backups |
| [docs/roadmap.md](docs/roadmap.md) | What comes next |
| [gazetteer/README.md](gazetteer/README.md) | The public gazetteer of parishes and farms |
| [research/README.md](research/README.md) | The research log's entry format |

## Background

The project started as an enumeration of what a "synthetic genealogy" could combine, written in October 2020 ([Synthetic Genealogy.md](https://gist.github.com/UncleCJ/6f9b36f55214e1d9ca5d128a9854e9f3)). Its 2026 revision, which marked each facet by where it stood and surveyed the tool landscape, is kept as the [README at commit 3e7bc20](https://github.com/UncleCJ/synthetic_genealogy/blob/3e7bc20e0669fcb98de3ba4b20e09edd9b89a854/README.md).

## License

Code: [MIT](LICENSE). The gazetteer's data draws on Wikidata, Riksarkivet and OpenStreetMap, whose own terms apply to it ([gazetteer/README.md](gazetteer/README.md)).
