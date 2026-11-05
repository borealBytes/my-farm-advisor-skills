# Porting skill/runtime drift back to the skills repo

Three copies of the skills exist and silently diverge: (a) the GitHub repo
`borealBytes/my-farm-advisor` (`skills/<name>/`), (b) the live local skill tree
`~/.hermes/profiles/<profile>/skills/` (the install source of truth, evolves via sessions),
and (c) the installed runtime under `${DATA_PIPELINE_DATA_ROOT}/data-pipeline/src` (gitignored
in consumer repos; sessions hot-patch code there). When asked to 'capture the fixes', audit all
three, in this order:

## 1. Audit runtime code changes deterministically — never by memory

The installed runtime src carries an install-time hash manifest. From
`${DATA_PIPELINE_DATA_ROOT}/data-pipeline/src`:

```bash
sha256sum -c .my-farm-advisor-source-manifest.sha256 | grep -v ': OK'
```

The FAILED list is exactly the set of files a session modified since install. Diff each against
the local skill tree for the precise hunks. `.my-farm-advisor-source.json` records the skill root
the install came from. Session notes (e.g. `research/notes/pipeline_runtime_patches.md` in a
consumer repo) give the WHY — pair both, trust the manifest for WHAT.

## 2. Audit local skill vs repo

`diff -rq <local skills>/<skill> <repo clone>/skills/<skill>` filtering out generated geoadmin/
maturity payloads (PROVENANCE.md exclusions). The local tree is usually AHEAD (renames like
`r2-seed-pipeline/ → data-pipeline/`, `PLAYBOOK.md → AGENTS.md`, new subtrees) — the repo is not
the source of truth for skill content, the local tree is.

## 3. Port rules

- Work on a git **worktree feature branch** (main clone stays clean for other sessions).
- Skill that owns the pipeline (`my-farm-advisor`): mirror the local tree fully — git records
  restructures as renames; verify the delete set is only renamed/junk files before committing.
- Sibling skills whose local copy has restructured `examples/` while the repo keeps a different
  taxonomy: use an **additive overlay** (rsync without `--delete`) — capture the updates,
  don't destroy repo-side content the local copy merely pruned for context.
- Apply runtime patches on top as their own commit, citing the manifest check; copy dependency-
  pairing fixes into `requirements.txt` with a comment stating WHY (e.g. an xarray/zarr pin pair
  that installs broken-together must be bumped as a pair, not one side).
- Never port input-data-side fixes into the skills repo (converters that live in the consumer
  project) — note them in the commit message instead.
- Keep determinism: every ported fix must be re-runnable from code + pinned URLs alone, no
  manual runtime state. A gitignored runtime tree is not a record; the repo commit is.
