# synthetic_genealogy

What it is and how to run it: @README.md
Principles, glossary, decisions: @docs/concepts.md
Modules by layer: @docs/architecture.md
What comes next: @docs/roadmap.md
Public/private changesets (git and jj), backups: @docs/privacy-workflow.md

## Rules
- This repo is public. Committed files use generic examples only: no names of
  living people, kit IDs, segment data or credentials.
- Genetic data stays in `data/` (git-ignored). Never stage anything from it on
  the public line; private files live only in the one `PRIVATE:` commit
  (docs/privacy-workflow.md). Never push `private`.
- Load segment exports through `ftdna_io.py` / `myheritage_io.py` (via
  `kits.py` and `family.toml`); keep vendor quirks there.
- Code may be readable sketches; flag what is unvalidated.
- Tests run on synthetic data only, with no private files (CI depends on it).
- Work frugally (docs/concepts.md, "How we work"). Before adding a module,
  flag, file or doc section, ask whether an existing one can do the job.
- Docs describe what exists: intentions go in the roadmap, findings in the
  research log or design docs; roadmap entries record state, not a diary.
- When a shared concept stops fitting, say so in one line (and in the
  roadmap if it lasts). Don't fix it unasked.
- After substantial work, propose a short delta for docs/roadmap.md, and
  docs/concepts.md for a new term or decision.
