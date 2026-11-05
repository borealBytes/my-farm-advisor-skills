# Local Instructions

## Purpose

This folder owns geospatial administration workflows for selecting and preparing administrative boundary layers used by the farm advisor skill. Any-country L1/L2 levels are built with `download_geoadmin.py --gadm-iso <ISO3>` (see GUIDE.md, "Any-country L1/L2").

## Safe edit scope

Edits should stay in this folder and its children unless the user explicitly asks for a broader skill change. Do not change parent `SKILL.md`, sibling workflows, or root policy from a subskill task unless explicitly requested.

## Read nearby docs first

Read `GUIDE.md` first. If routing context is needed, read `../INDEX.md` and `../../SKILL.md`.

## Local validation

Run `./scripts/validate.sh` from the repository root after structural changes. If you change geoadmin downloader behavior elsewhere, also run the nearby command documented with that downloader when dependencies are available.

## Local-delta-only reminder

This nested AGENTS.md only records instructions that differ from the parent or root files. Do not duplicate root-wide asset, vendor, or validation policy here except this pointer to `../../../AGENTS.md`.
