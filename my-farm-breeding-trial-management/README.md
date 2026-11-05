# My Farm Breeding Trial Management

> **Status:** initial stab — real, runnable workflows and examples; this tree will
> expand the most as the data-pipeline foundation underneath it matures.

My Farm Breeding Trial Management is the breeding-operations skill pack for this repo. It covers how breeding programs move from experimental design to fieldbooks, germplasm handling, selection decisions, and crossing plans.

Use this skill when the problem is operational breeding work rather than farm-wide advisory routing or downstream QTL interpretation.

## What This Skill Does

- Plans breeding trials with common experimental designs like RCBD, alpha-lattice, and augmented layouts.
- Generates fieldbooks and operational plot artifacts for field crews.
- Organizes germplasm, pedigree, and accession workflows.
- Supports ranking, shortlist generation, and selection-index style decisions.
- Builds crossing and mating-plan scaffolds for the next breeding cycle.
- Backfills a field-trial placement workflow for field-boundary-aware RCBD placement.

## How It Runs

```mermaid
flowchart TD
    accTitle: Breeding Operations Routing
    accDescr: Overview of how the breeding trial management skill routes a breeding workflow request into design, fieldbook, germplasm, selection, and crossing workflows that produce operational outputs.

    request([🌱 Breeding workflow request]) --> router[🧭 Breeding operations router]

    subgraph workflow_areas ["📚 Breeding workflow areas"]
        direction TB
        design[Design]
        fieldbook[Fieldbook]
        germplasm[Germplasm]
        selection[Selection]
        crossing[Crossing]
    end

    router --> workflow_areas
    workflow_areas --> output([✅ Operational breeding outputs])

    classDef primary fill:#dbeafe,stroke:#2563eb,stroke-width:2px,color:#1e3a5f
    classDef outcome fill:#dcfce7,stroke:#16a34a,stroke-width:2px,color:#14532d

    class request,router primary
    class output outcome
```

The skill revolves around grouped example modules plus a unified breeding CLI that map to the core phases of breeding operations.

## Core Workflow Areas

| Area | What it covers | Typical result |
| --- | --- | --- |
| Design | Trial layout planning and experimental structure | RCBD, alpha-lattice, or augmented designs |
| Fieldbook | Plot sheets, labels, imports, and field execution artifacts | crew-ready fieldbook outputs |
| Field Trial Placement | Field-boundary-aware plot placement | placed trial layouts tied to field geometry |
| Germplasm | Accession and pedigree handling | organized breeding material records |
| Selection | Ranking and shortlist generation | candidate line decisions |
| Cross | Crossing plans and mate pairing | next-cycle crossing scaffold |

## Breeding Program Flow

```mermaid
flowchart LR
    accTitle: Breeding Program Cycle
    accDescr: Typical breeding-program flow from objective setting through design, fieldbook generation, germplasm context, selection, and crossing for the next cycle.

    intake([🎯 Set breeding objective]) --> design_step[Choose design]
    design_step --> fieldbook_step[📒 Generate fieldbook]
    fieldbook_step --> germplasm_step[🧬 Capture germplasm context]
    germplasm_step --> selection_step[Select promising lines]
    selection_step --> cross_step[🌿 Build crossing plan]
    cross_step --> next_cycle([🔁 Prepare the next cycle])

    classDef primary fill:#dbeafe,stroke:#2563eb,stroke-width:2px,color:#1e3a5f
    classDef process fill:#fef3c7,stroke:#d97706,stroke-width:2px,color:#78350f
    classDef outcome fill:#dcfce7,stroke:#16a34a,stroke-width:2px,color:#14532d

    class intake primary
    class design_step,fieldbook_step,germplasm_step,selection_step,cross_step process
    class next_cycle outcome
```

## Example Modules Included

- Trial design: `examples/design/rcbd-design/`, `examples/design/alpha-lattice/`, `examples/design/augmented-design/`
- Fieldbooks and placement: `examples/fieldbook/field-book/`, `examples/fieldbook/data-import/`, `examples/fieldbook/iot-field-sync/`, `examples/field-trial-placement/`
- Germplasm and pedigree: `examples/germplasm/breedbase-client/`, `examples/germplasm/pedigree-management/`, `examples/germplasm/bms-client/`
- Selection and crossing: `examples/select/selection-index/`, `examples/select/breeding-value-ranking/`, `examples/select/breeding-simulation-simple-cycle/`, `examples/cross/crossing-plan/`

## Why It Matters In This Repo

```mermaid
flowchart TD
    accTitle: Breeding Skill Role In The Repo
    accDescr: Diagram showing how the breeding trial management skill supports trial execution, records, and operational decisions that feed downstream analysis workflows.

    repo([🌾 My Farm Advisor repo]) --> breeding_ops[🌱 Breeding trial management]
    breeding_ops --> trials[Trial execution]
    breeding_ops --> records[Germplasm and pedigree handling]
    breeding_ops --> decisions[Selection and crossing decisions]
    decisions --> downstream([📈 QTL and forecasting can build from here])

    classDef primary fill:#dbeafe,stroke:#2563eb,stroke-width:2px,color:#1e3a5f
    classDef support fill:#ecfccb,stroke:#65a30d,stroke-width:2px,color:#365314
    classDef outcome fill:#f3e8ff,stroke:#9333ea,stroke-width:2px,color:#581c87

    class repo,breeding_ops primary
    class trials,records,decisions support
    class downstream outcome
```

This skill is the operational breeding layer. It is what you use before or alongside QTL analysis when the work is about running breeding programs, not only analyzing marker-trait associations.

## Start Here

- Main entrypoint: [`SKILL.md`](SKILL.md)
- Progressive router: [`INDEX.md`](INDEX.md)
- Unified CLI: `python scripts/breeding_cli.py <design|fieldbook|germplasm|select|cross> --help`
- Trial design examples: [`examples/design/rcbd-design/`](examples/design/rcbd-design/)
- Field placement example (with rendered demo map): [`examples/field-trial-placement/`](examples/field-trial-placement/) — boundary-aware RCBD placement on a real Iowa field boundary; default output honors `DATA_PIPELINE_DATA_ROOT`
- Selection and crossing examples: [`examples/select/selection-index/`](examples/select/selection-index/) and [`examples/cross/crossing-plan/`](examples/cross/crossing-plan/)
- Simulation notes: [`examples/select/breeding-simulation-simple-cycle/README.md`](examples/select/breeding-simulation-simple-cycle/README.md)
