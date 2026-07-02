# Local Instructions

## Purpose

This folder owns the Assignment 1 grower-level interactive web map subskill.
It generates lightweight, self-contained HTML maps from pipeline field boundary
GeoJSON for any existing grower/farm in the runtime.

## Safe edit scope

Edits should stay in this folder and its children unless the user explicitly
asks for a broader skill change. Do not change parent `SKILL.md`, sibling
workflows, or root policy from a subskill task unless explicitly requested.

## Read nearby docs first

Read `GUIDE.md` first. If routing context is needed, read `../INDEX.md` and
`../../SKILL.md`.

## Local validation

Run `./scripts/validate.sh` from the repository root after structural changes.
If you change the generator script behavior, also run the generator against a
live grower when dependencies are available.

## Local-delta-only reminder

This nested AGENTS.md only records instructions that differ from the parent or
root files. Do not duplicate root-wide asset, vendor, or validation policy here
except this pointer to `../../../AGENTS.md`.
