# Synthetic Genealogy

**Family history from DNA and records together: chromosome paintings that check the family tree, and a map of the records the tree was built from.**

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/)
[![Tests](https://github.com/UncleCJ/synthetic_genealogy/actions/workflows/tests.yml/badge.svg)](https://github.com/UncleCJ/synthetic_genealogy/actions/workflows/tests.yml)

Genealogy tools keep two things apart: the paths DNA took down a family tree, and the places and records the tree was built from. This repository joins them, working from ordinary exports: a GEDCOM file, vendor segment and match lists, and raw DNA files where relatives lend them.

- **DNA paths on the tree.** Siblings' raw data, with a tested parent, are painted onto the four grandparents' copies of each chromosome. Every match segment is then placed on one grandparent, so a match becomes a claim about a branch of the tree. The tree checks the painting and the painting checks the tree: for one sibling, 210 of 238 segments from tree-linked matches land on the grandparent their tree path predicts, and most of the rest come from matches linked to the tree only by a common name. In the other direction, the tree says which relatives should share a segment and which should not.
- **Geography from a plain export.** Every place string in the GEDCOM goes to a parish (Riksarkivet archive code, Wikidata item) and, where it can, to a farm or village. The [gazetteer](gazetteer/README.md) holds spelling variants and the usual misreadings, such as a long s (ſ) read as f. Every citation goes to an archive volume and page. Residences become stays, and the years no volume covers are listed with the volumes that would cover them. The result is a map of each ancestor's life that shows where every point comes from.
- **Your research, kept private and backed up.** Downloads are kept as received, hand-kept notes go to a private cloud folder, the rest is rebuilt by one command, and a dated snapshot can be read on any computer with Python.

Each layer catches the others' errors: a wrong link in the tree puts a segment on the wrong grandparent; a misread farm name shows up as a jump on the map or a gap in the volumes; a match joined to the wrong person disagrees with the painting. Nothing edits the master tree. Corrections are kept beside it with sources, so every view can be rebuilt and every disagreement stays visible.

The code is readable Python sketches, run on one family's data; treat it as unvalidated unless a check says otherwise.

## Contents

- [What it looks like](#what-it-looks-like)
- [Getting started](#getting-started)
- [Keeping your research private](#keeping-your-research-private)
- [Documentation](#documentation)
- [Related work](#related-work)
- [Background](#background)
- [License](#license)

## What it looks like

The screenshots below come from one family's own data, as of November 2026. Places, parishes, volumes and pages are left as they are; people are pseudonymised ([showcase.py](showcase.py)). Only ancestors from the great-grandparents back are shown, each named by Ahnentafel number and lineage code: No. 12 · MFF is the mother's father's father. Colours are the four grandparent branches (FF, FM, MF, MM).

**DNA: one sibling's chromosomes painted by grandparent.** For each chromosome, the paternal lane sits above the maternal one. Pale blocks are the grandparent copies decoded from the siblings' and the mother's raw data. Placed match segments of 12 cM or more lie on top, with tree-linked ones darker. Each block is labelled with its support: the number of match segments placed on it, ✓ tree-linked segments that agree with its grandparent, and ✗ those that don't. The ✗ are the cases worth opening first.

![A sibling's grandparent painting with placed match segments and per-block support](docs/img/painting.png)

**People: one couple's lives on a map.** Every residence, household examination, birth and marriage of a husband and wife, numbered in order and joined into paths. The list below the map gives the date, the farm or village, how precisely it is placed, and whether it comes from a cited record or only from the tree.

![Pair map: a couple's residences and records on one map](docs/img/people_pair_map.png)

**People: residence timelines.** One bar per stay, coloured by parish. Thin bars are the tree's own residence events. Red marks years where no household-examination volume is cited yet, and the notes below each person list the Riksarkivet volumes that would close the gap.

![Residence timelines per ancestor, with gaps and the volumes to open](docs/img/people_timelines.png)

**Volumes: the references.** Each parish carries its Riksarkivet archive code and Wikidata item, with a bar showing how its citations are sourced. The densest farms are listed with every volume and page cited for them.

![Record volumes: parishes with archive codes, farms with every cited volume and page](docs/img/volumes.png)

**Geography: every located event, filterable like a tag browser.** Facets by time, layer, event type, branch, precision of place and date, and parish. The address bar keeps the filter, so any view can be linked.

![All located events of the ancestors, coloured by grandparent branch](docs/img/geography_branches.png)

**Geography, way back: where each grandparent branch lived before 1750.** The same view, filtered to events before 1750.

![Located events before 1750, coloured by grandparent branch](docs/img/geography_before_1750.png)

## Getting started

Python 3.11 or later.

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

## Keeping your research private

The code is public; the family's DNA and research are not. The project treats that as a feature, not an afterthought:

- **A data folder in layers** by what a file is: `input/` (downloads as received, never edited), `notes/` and `store/` (kept by hand), `cache/` and `output/` (rebuilt) ([docs/data.md](docs/data.md)).
- **Two lines of history:** public commits on `master`, and one `PRIVATE:` commit on top holding the data and config. A git pre-push hook and jj's `git.private-commits` refuse to push it ([docs/privacy-workflow.md](docs/privacy-workflow.md)).
- **Backups outside git:** `python3 backup.py status` lists hand-kept files that changed since the last backup to a private cloud folder, and `backup.py mark` records them; everything else is rebuilt by `pipeline.py`.
- **Snapshots:** `python3 backup.py snapshot` writes the outputs and notes as one dated zip that `serve.py` can browse on another computer.
- **A research log:** questions, hypotheses and findings as dated entries that cite the computed output ([schema](research/README.md); the entries stay private).
- **A pseudonymised showcase:** `showcase.py` makes the public screenshots above, with a check for names and ids.

## Documentation

| Document | What it covers |
| --- | --- |
| [docs/concepts.md](docs/concepts.md) | Principles, glossary and decisions |
| [docs/architecture.md](docs/architecture.md) | How the modules fit together, by layer |
| [docs/pipeline.md](docs/pipeline.md) | Each step in run order, with an anonymised run |
| [docs/data.md](docs/data.md) | The data folder's layers and viewing the results |
| [docs/privacy-workflow.md](docs/privacy-workflow.md) | Public and private changesets (git and jj), backups |
| [docs/roadmap.md](docs/roadmap.md) | What comes next |
| [gazetteer/README.md](gazetteer/README.md) | The public gazetteer of parishes and farms |
| [research/README.md](research/README.md) | The research log's entry format |

## Related work

This project reads several of these tools' outputs and leans on public archives; it does not replace them.

| Tool | What it does | Here |
| --- | --- | --- |
| [Genetic Affairs](https://dna-explained.com/2022/02/21/autokinship-at-gedmatch-by-genetic-affairs) | AutoCluster, AutoSegment, AutoTree, AutoKinship | AutoCluster runs are read |
| [DNA Painter](https://dnapainter.com) | Manual chromosome mapping, WATO | backups are read, and the painting is written back |
| [GEDmatch](https://www.gedmatch.com) | One-to-one and one-to-many comparisons, triangulation | one-to-one pages validate the phasing |
| [Borland Genetics](https://borlandgenetics.blogspot.com/2024/09/explore-advanced-chromosome-mapping.html) | Ancestor DNA reconstruction from relatives' raw data | a different route to grandparent copies |
| [BanyanDNA](https://www.yourdnaguide.com/ydgblog/wato-plus-vs-banyandna) / WATO | Ranks pedigree hypotheses from shared cM | relationship hypotheses without segment positions |
| [Gramps](https://gramps-project.org) | Open-source genealogy program | opens the store's GEDCOM export |
| [Underlay](https://underlay.mit.edu) | A distributed graph of assertions with provenance | the model for how claims are stored |

Archives and open data: [Riksarkivet](https://riksarkivet.se) (volumes and reference codes, through its open OAI-PMH service), [Wikidata](https://www.wikidata.org) (parishes and farms), [OpenStreetMap](https://www.openstreetmap.org) (coordinates and map tiles).

## Background

The project started as an enumeration of what a "synthetic genealogy" could combine, written in October 2020 ([Synthetic Genealogy.md](https://gist.github.com/UncleCJ/6f9b36f55214e1d9ca5d128a9854e9f3)). Its 2026 revision, which marked each facet by where it stood and surveyed the tool landscape, is kept as the [README at commit 3e7bc20](https://github.com/UncleCJ/synthetic_genealogy/blob/3e7bc20e0669fcb98de3ba4b20e09edd9b89a854/README.md).

## License

Code: [MIT](LICENSE). The gazetteer's data draws on Wikidata, Riksarkivet and OpenStreetMap, whose own terms apply to it ([gazetteer/README.md](gazetteer/README.md)).
