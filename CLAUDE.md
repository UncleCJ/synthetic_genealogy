# synthetic_genealogy

Concepts and landscape: @README.md
Working state, vocabulary, decisions, next steps: @CHECKPOINT.md
Public/private changesets (git and jj): @WORKFLOW.md

## Rules
- This repo is public. Committed files use generic examples only: no names of
  living people, kit IDs, segment data or credentials.
- Genetic data stays in `data/` (git-ignored). Never stage anything from it on
  the public line; private files live only in the one `PRIVATE:` commit
  (WORKFLOW.md). Never push `private`.
- Load segment exports through `ftdna_io.py` / `myheritage_io.py` (via
  `kits.py` and `family.toml`); keep vendor quirks there.
- Code may be readable sketches; flag what is unvalidated.
- After substantial work, propose a short delta for CHECKPOINT.md.
