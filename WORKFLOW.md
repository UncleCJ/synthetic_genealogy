# Public and private changesets

The code and ideas are public; the family's DNA and research notes are not.
The history keeps them apart as two lines, the private one a superset of the
public one:

```
private   PRIVATE: family data, config, research log, notebook outputs
   |
master    public commits: code, family.example.toml, schema docs, README
   |
  ...     (pushed to origin/main and the gist)
```

- **Public** (`master`): generic code. Everything family-specific is read
  from `family.toml`; `family.example.toml` shows the format with made-up
  values.
- **Private** (`private`): one commit, subject starting `PRIVATE:`, holding
  `data/`, `family.toml`, `donors.csv`, `research/` entries, `.vscode/` and
  the notebook with its outputs (pseudonymised: Donor A, Match 01, ...).
- `.gitignore` lists the private paths, so a public commit cannot pick them
  up by accident. In the private commit they are force-added; once tracked,
  git and jj keep tracking them.
- Never push `private`. Two guards, set up once per clone:
  - git: `git config core.hooksPath hooks` (runs `hooks/pre-push`)
  - jj (which does not run git hooks):
    `jj config set --repo git.private-commits 'private:: | description(glob:"PRIVATE:*")'`

Notebooks go public with outputs stripped and example names; the private
commit adds the outputs, pseudonymised. The original real-name outputs of
`segments.ipynb` survive in its 2021 commits on origin/main (published then,
deliberately kept) and in the jj operation log (`jj op log`).

## With jj (colocated)

Once: `brew install jj`, then in the repo `jj git init --colocate`. Existing
branches become bookmarks `master` and `private`.

Work always happens on top of `private`, so the data is on disk:

```bash
jj new private                      # working-copy change on top of private
```

When a piece of work is public, give it a home below `private` and move the
files there; descendants rebase automatically:

```bash
jj new --no-edit --insert-before private -m "Place matches on X"   # empty public change
jj squash --into 'description(substring:"Place matches on X")' some_module.py   # or -i to pick hunks
jj bookmark set master -r 'private-'                                # master = tip of public line
```

Private additions go into the private change:

```bash
jj file track --include-ignored data/new_export.csv   # private paths are ignored;
                                    # without the flag jj silently skips them
jj squash --into private data/new_export.csv
```

Small fixes to a public change that is not pushed yet can amend it directly
(bookmarks follow the rewrite):

```bash
jj squash --into master WORKFLOW.md
```

Publish the public line only. jj pushes a bookmark to the remote branch of
the same name, and GitHub's branch is `main`, so publish through a `main`
bookmark:

```bash
jj bookmark track main@origin       # once: local main = origin's main
jj bookmark set main -r master      # move it to the public tip
jj git push --remote origin -b main # never --all
```

With `git.private-commits` set, jj refuses any push that would include a
private commit (try `--dry-run`).

jj tracks the executable bit even where git has `core.fileMode = false`;
a file that is executable on disk but not in git shows up as a mode change
(`chmod 644` it).

## With plain git

Switching to `master` removes the private files from the working tree (they
are tracked only in `private`), so make public commits in a separate
worktree and rebase:

```bash
git worktree add ../genealogy-public master
# edit and commit in ../genealogy-public
git rebase master private
```
