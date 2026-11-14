# synthetic_genealogy

Always loaded: principles, glossary and decisions (@docs/concepts.md) and the
modules by layer (@docs/architecture.md). Read the rest when the task needs it:

- docs/genetics.md, docs/records.md: how the genetics and the records work.
- docs/roadmap.md: what comes next, and the open items per area. Read it
  before proposing new work or a roadmap delta.
- docs/privacy-workflow.md: public/private changesets (git and jj),
  parallel sessions, backups. Read it before any commit, rebase or push.
- docs/pipeline.md, docs/data.md: run order, the data folder's layers.
- docs/man/: man pages for the tools run by hand (index: intro.1.md).
  Read tree-edits.7.md before making tree edits or errata.
- README.md: the public face (for people, not for working on the code).

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
