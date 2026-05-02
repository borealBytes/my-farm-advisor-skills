# my-farm-advisor-skills

Domain-specific skills for the My Farm Advisor agent ecosystem. This repository holds the approved My Farm Advisor skill catalog. It depends on reusable Superior Byteworks skills maintained in a separate repository. No Superior Byteworks skills are vendored or copied here.

---

## Purpose

This repository is the canonical home for My Farm Advisor agent skills. It contains the umbrella skill and three domain-specific skills that power farm data management, breeding trial workflows, quantitative trait locus analysis, and third-party data ingestion. The repo is kept small and focused: upstream source provenance is recorded for every import, large generated assets are excluded, and reusable cross-cutting skills are treated as external dependencies.

---

## Skill Tree

```
my-farm-advisor-skills/
├── my-farm-advisor/                          # Umbrella skill
│   ├── README.md                              # Farm data hierarchy & pipeline overview
│   ├── data-sources/
│   │   ├── INDEX.md                           # Data source discovery
│   │   ├── farm-data-rebuild/
│   │   │   └── PLAYBOOK.md                    # Deterministic farm data rebuild
│   │   ├── farm-intelligence-reporting/
│   │   │   └── PLAYBOOK.md                    # Farm reporting pipeline
│   │   └── john-deere-ingestion/              # NEW: John Deere Operations Center import
│   │       ├── README.md                      # CLI commands, env vars, R2 contract
│   │       └── PLAYBOOK.md                    # Execution examples & troubleshooting
│   ├── field-management/
│   ├── soil/
│   ├── weather/
│   ├── strategy/
│   ├── imagery/
│   ├── eda/
│   └── admin/
├── my-farm-breeding-trial-management/        # Breeding trial skill
│   └── README.md                              # Trial design, fieldbook, germplasm
└── my-farm-qtl-analysis/                     # QTL analysis skill
    └── README.md                              # QTL mapping, GWAS, genomic prediction
```

---

## Skill Catalog

| Skill | Path | Description |
|---|---|---|
| **[my-farm-advisor](my-farm-advisor/)** | `my-farm-advisor/` | Umbrella skill that coordinates farm data pipelines, dashboard workflows, and shared utilities such as geoadmin spatial data orchestration. |
| **[my-farm-breeding-trial-management](my-farm-breeding-trial-management/)** | `my-farm-breeding-trial-management/` | End-to-end breeding trial workflows: design, fieldbook management, germplasm selection, crossing plans, and field trial placement. |
| **[my-farm-qtl-analysis](my-farm-qtl-analysis/)** | `my-farm-qtl-analysis/` | Quantitative trait locus mapping, quality control, population structure analysis, genomic prediction, and reporting. |

### Subskills & Playbooks (under my-farm-advisor)

| Subskill | Path | Description |
|---|---|---|
| **[John Deere Ingestion](my-farm-advisor/data-sources/john-deere-ingestion/)** | `my-farm-advisor/data-sources/john-deere-ingestion/` | Standalone CLI that connects to John Deere Operations Center, enumerates every supported API operation, and exports raw + normalized grower/farm/field data into the canonical farm tree. |
| **[Farm Data Rebuild](my-farm-advisor/data-sources/farm-data-rebuild/)** | `my-farm-advisor/data-sources/farm-data-rebuild/` | Deterministic playbook for rebuilding farm data from seed sources. |
| **[Farm Intelligence Reporting](my-farm-advisor/data-sources/farm-intelligence-reporting/)** | `my-farm-advisor/data-sources/farm-intelligence-reporting/` | Playbook for generating farm intelligence reports and dashboards. |

### What Is Not Here

The following old My Farm Advisor Superior Byteworks skill copies are explicitly excluded and do not exist in this repository:

- `superior-byte-works-wrighter` (superseded by the canonical Wrighter delivery in `superior-byte-works-skills`)
- `superior-byte-works-google-timesfm-forecasting` (superseded by the Google-approved TimesFM forecasting skill in `superior-byte-works-skills`)

---

## Quick Start by Skill

### Farm Data & Operations ([my-farm-advisor](my-farm-advisor/))

The umbrella skill defines the canonical farm data hierarchy:

```
grower/                          # Customer or operating entity
└── farms/
    └── farm/                    # Named operating unit
        └── fields/
            └── field/           # Atomic agronomic unit
                ├── boundary/
                ├── soil/
                ├── weather/
                ├── satellite/
                ├── manifests/
                └── derived/
```

Start here for:
- [Farm data rebuild workflow](my-farm-advisor/data-sources/farm-data-rebuild/PLAYBOOK.md)
- [Farm intelligence reporting](my-farm-advisor/data-sources/farm-intelligence-reporting/PLAYBOOK.md)
- [John Deere data ingestion](my-farm-advisor/data-sources/john-deere-ingestion/README.md)
- [Field boundaries](my-farm-advisor/field-management/field-boundaries/GUIDE.md)
- [SSURGO soil workflows](my-farm-advisor/soil/ssurgo-soil/GUIDE.md)
- [Sentinel-2 imagery](my-farm-advisor/imagery/sentinel2-imagery/GUIDE.md)
- [NASA POWER weather](my-farm-advisor/weather/nasa-power-weather/GUIDE.md)

### Breeding Trials ([my-farm-breeding-trial-management](my-farm-breeding-trial-management/))

End-to-end breeding trial management including trial design, fieldbook generation, germplasm selection, crossing plans, and field trial placement.

### QTL Analysis ([my-farm-qtl-analysis](my-farm-qtl-analysis/))

Quantitative trait locus mapping with support for quality control, population structure analysis, genomic prediction, and structured reporting.

---

## John Deere Ingestion (New)

The [`john-deere-ingestion`](my-farm-advisor/data-sources/john-deere-ingestion/) subskill is a standalone TypeScript CLI that imports grower data from the John Deere Operations Center into the canonical farm tree.

**Key features:**
- OAuth Authorization Code flow with local callback server
- Portable token store (dev v1, replaceable for production)
- Operation registry covering all `deere-sdk` APIs + unsupported entries
- Immutable raw snapshots + normalized grower/farm/field projections
- Local webhook receiver for real-time event ingestion
- Mock mode for deterministic CI/testing without credentials
- R2-ready tree alignment (direct wiring deferred to future milestone)

**Quick commands:**
```bash
cd my-farm-advisor/data-sources/john-deere-ingestion
npm install && npm run build

# Show resolved paths (no credentials needed)
node ./dist/src/cli.js paths --dry-run

# Mock ingest for testing
node ./dist/src/cli.js ingest --mock --force

# With live credentials
JD_CLIENT_ID=xxx JD_CLIENT_SECRET=xxx node ./dist/src/cli.js init --environment sandboxapi
```

See the [subskill README](my-farm-advisor/data-sources/john-deere-ingestion/README.md) for full documentation.

---

## Dependencies

This repository depends on reusable Superior Byteworks skills, which are **external dependencies installed separately**. They are **not vendored, copied, or mirrored** into this repo.

- **superior-byte-works-skills** — the canonical repository for reusable Superior Byteworks skills such as Wrighter delivery and TimesFM forecasting.

Installation and version requirements for each dependency are documented in the per-skill `SKILL.md` files.

---

## Installation

### 1. Clone This Repository

```bash
git clone https://github.com/borealBytes/my-farm-advisor-skills.git
cd my-farm-advisor-skills
```

### 2. Install Superior Byteworks Dependencies

This repository depends on Superior Byteworks skills that must be installed separately. Do not copy them into this repository.

Clone the SBW skills repository into a sibling directory:

```bash
# From the parent of my-farm-advisor-skills
git clone https://github.com/superiorbyteworks/superior-byte-works-skills.git
```

Expected directory layout after both clones:

```
parent-directory/
├── my-farm-advisor-skills/      # this repo
└── superior-byte-works-skills/  # dependency
    ├── wrighter/
    └── timesfm-forecasting/
```

### 3. How My Farm Skills Discover SBW Skills

My Farm skills reference SBW skills through relative path resolution or OpenCode skill discovery. The exact mechanism depends on your runtime:

- **OpenCode runtime**: Configure both repositories as skill sources. OpenCode resolves skill names across all configured sources.
- **Direct script usage**: Some My Farm scripts may resolve SBW skills via relative paths or environment variables. Check individual skill READMEs for path configuration.
- **Custom runtimes**: Set `SBW_SKILLS_PATH` or an equivalent environment variable to point to your `superior-byte-works-skills` checkout.

### 4. Update Order

When updating both repositories, always update SBW skills first, then My Farm skills:

1. Pull latest `superior-byte-works-skills` and verify it passes validation.
2. Pull latest `my-farm-advisor-skills` and verify it passes validation.
3. Test integration points between the two repositories.

This order ensures My Farm skills can adapt to any SBW API changes before you commit updates.

### Troubleshooting

| Problem | Cause | Fix |
|---|---|---|
| `Skill not found: wrighter` | SBW repo not cloned or not in expected location | Verify `superior-byte-works-skills/` exists as a sibling directory and contains `wrighter/SKILL.md` |
| `Path resolution failed` | Custom runtime without proper environment variables | Set `SBW_SKILLS_PATH` to the absolute path of your SBW checkout |
| Outdated skill behavior | Update order violated (My Farm updated before SBW) | Update SBW first, then re-test My Farm |
| Copied skill files in repo | SBW skills were duplicated into My Farm repo | Delete the copies and use the separate SBW checkout instead |

**Do not copy Superior Byteworks skills into the My Farm repository.** Copied skills drift from the canonical source, break update workflows, and violate the dependency boundary enforced by validation.

---

## Large Assets

This repository keeps asset hygiene strict. The following policy applies to large or generated spatial data:

- **Geoadmin metadata is preserved.** Source URL metadata and downloader orchestration scripts are committed so the agent can reproduce the data pipeline.
- **Large GeoJSON payloads are runtime-downloaded, not committed.** The generated `countries.geojson`, `states_usa.geojson`, and county-level GeoJSON outputs are produced at runtime by the downloader scripts and land under `data/my-farm-advisor/shared/geoadmin/`, which is excluded from version control.
- No generated output directories (`data/`, `.cache/`, build artifacts) are tracked.

For details on running the geoadmin downloader, see `my-farm-advisor/r2-seed-pipeline/src/scripts/ingest/download_geoadmin.py` after the skill is imported.

---

## Import Provenance

Every skill in this repository records its source. The table below summarizes the origin of the approved imports.

| Skill | Source | Source Path / Local Worktree | Ref / Commit | Baseline / Notes |
|---|---|---|---|---|
| my-farm-advisor | `borealBytes/my-farm-advisor` | `skills/my-farm-advisor` | `main` (`4a82ab7`) | Canonical remote source. Geoadmin GeoJSON payloads excluded; metadata and downloader scripts preserved. |
| my-farm-breeding-trial-management | Local worktree | `/media/clay/Data/dev/scientific-agent-skills-worktrees/scientific-agent-skills-breeding-trial-management/scientific-skills/breeding-trial-management` | Branch `feat/breeding-trial-management` (`f479f5d`) | Local wins as structural base. Backfilled remote-only completeness items from `borealBytes/my-farm-advisor@main:skills/my-farm-breeding-trial-management` (README, CLI script, field-trial-placement examples). |
| my-farm-qtl-analysis | Local worktree | `/media/clay/Data/dev/scientific-agent-skills-worktrees/scientific-agent-skills-qtl-analysis/scientific-skills/qtl-analysis` | Branch `feat/qtl-analysis` (`f479f5d`) | Local wins as structural base. Backfilled remote-only completeness items from `borealBytes/my-farm-advisor@main:skills/my-farm-qtl-analysis` (README, CLI script, richer SKILL metadata). Generated `output/` artifacts were excluded after audit; no new LFS assets were required. |
| john-deere-ingestion | Local development | `my-farm-advisor/data-sources/john-deere-ingestion/` | Branch `feat/john-deere-ingestion` | New standalone subskill. TypeScript CLI using `deere-sdk`. Isolated tooling under subskill directory. |

Each skill directory contains a `PROVENANCE.md` with the exact source URL, resolved commit SHA, exclusions, local modifications, and step-by-step reproduction instructions.

---

## Validation

Run the repository validation entrypoint to check that required files, provenance records, and asset policies are intact:

```bash
# From the repository root
./scripts/validate.sh
```

What the validator checks:

- Required skill entrypoints (`SKILL.md`, `README.md`) exist for every skill in the catalog.
- Import provenance files are present and contain required fields.
- Forbidden paths (excluded old Superior Byteworks skills, generated `data/` outputs, `node_modules/`, `.cache/`) are absent from the tracked tree.
- Large asset policy compliance (no unmanaged GeoJSON payloads, no unexpected binary blobs).

If validation fails, the script prints the specific check that failed and exits non-zero.

---

## Update Policy

Skills in this repository are updated from upstream using the following rules:

1. **Umbrella skill (my-farm-advisor)** — synced from `borealBytes/my-farm-advisor@main`. Before updating, verify the remote ref with `git ls-remote https://github.com/borealBytes/my-farm-advisor.git refs/heads/main`, record the resolved commit SHA, and re-apply the geoadmin exclusion list.

2. **Breeding trial and QTL skills** — local worktrees are canonical. When the local worktree advances, re-import from the local path, re-apply remote-only backfill items, and update the provenance commit SHA and dirty-status fields.

3. **John Deere ingestion** — local development branch. When the branch is merged to main, update provenance with the merge commit SHA and any new exclusions or modifications.

4. **Backfill baseline** — the `borealBytes/my-farm-advisor` remote remains a comparison baseline. If the remote gains new completeness items (docs, scripts, examples) that are missing locally, backfill them rather than overwriting local structural improvements.

5. **Dependency skills** — Superior Byteworks skills are never copied into this repo. When they change, update the dependency reference or installation instructions in the affected `SKILL.md` files.

6. **Provenance refresh** — every update must refresh the corresponding `PROVENANCE.md` with the new source ref, commit SHA, date, and any new exclusions or modifications.

---

## Repository Layout

```
my-farm-advisor-skills/
├── README.md                          # this file
├── .gitignore                         # runtime data, caches, generated outputs
├── .gitattributes                     # LFS policy for required binary assets
├── scripts/
│   └── validate.sh                    # repository validation entrypoint
├── my-farm-advisor/                   # umbrella skill
│   ├── SKILL.md
│   ├── README.md
│   ├── PROVENANCE.md
│   ├── data-sources/
│   │   ├── INDEX.md                   # data source discovery
│   │   ├── farm-data-rebuild/
│   │   ├── farm-intelligence-reporting/
│   │   └── john-deere-ingestion/      # John Deere Operations Center import
│   │       ├── README.md
│   │       ├── PLAYBOOK.md
│   │       ├── PROVENANCE.md
│   │       ├── package.json
│   │       ├── src/                   # TypeScript CLI source
│   │       └── tests/                 # Vitest test suites
│   └── ...
├── my-farm-breeding-trial-management/ # breeding trial skill
│   ├── SKILL.md
│   ├── README.md
│   ├── PROVENANCE.md
│   └── ...
└── my-farm-qtl-analysis/              # QTL analysis skill
    ├── SKILL.md
    ├── README.md
    ├── PROVENANCE.md
    └── ...
```

---

## Contributing

When adding or updating a skill:

- Record import provenance before committing the skill tree.
- Exclude generated outputs and large runtime assets.
- Run `./scripts/validate.sh` and ensure it passes.
- Do not vendor Superior Byteworks skills; declare them as external dependencies.
- Update this root `README.md` with links to any new skills or subskills.
