#!/usr/bin/env python3
"""Backfill root-relative ``*_rel`` fields into pre-existing pipeline journals.

Journals written before the path-normalization PR carry machine-absolute
paths only, which makes them the wrong first commit for a provenance repo
(the pointers die on the next clone). This pass is additive and idempotent:
it re-emits each recognized journal with ``*_rel`` siblings computed from the
paths it already stores, touching files only when something changes.

Recognized artifacts (all under ${DATA_PIPELINE_DATA_ROOT}/data-pipeline):
  dem_terrain_summary.json   dem_clipped_rel, dem_conditioned_rel, products[].path_rel
  dem_terrain_summary.csv    dem_clipped_rel, dem_conditioned_rel columns
  dem_source_reference.json  source_paths_rel
  dem_terrain_manifest.json  assets[*].href_rel / source_paths_rel
  soilgrids_provenance.json  stats_table_rel, journal_rel
  step manifests (*_render*.json / manifest dir)  inputs_rel, outputs_rel

Usage:
  DATA_PIPELINE_DATA_ROOT=/abs/root python3 scripts/backfill_journal_rel.py [--dry-run]
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import os
import sys
from pathlib import Path


def rel_to_root(root: Path, value: str) -> str | None:
    """Root-relative POSIX string for an absolute path, or None if no change needed."""
    if not value or not isinstance(value, str):
        return None
    p = Path(value)
    if not p.is_absolute():
        return None  # already relative (or a URL); nothing to add
    try:
        rel = p.resolve().relative_to(root.resolve()).as_posix()
    except (ValueError, OSError):
        return None  # outside the runtime root: journal it as-is upstream too
    return rel


def fix_paths(root: Path, obj: dict, key: str, rel_key: str, counts: dict) -> bool:
    changed = False
    val = obj.get(key)
    if isinstance(val, str) and rel_key not in obj:
        rel = rel_to_root(root, val)
        if rel is not None:
            obj[rel_key] = rel
            counts[rel_key] = counts.get(rel_key, 0) + 1
            changed = True
    elif isinstance(val, list) and rel_key not in obj:
        rels = [rel_to_root(root, v) if isinstance(v, str) else None for v in val]
        if any(r is not None for r in rels):
            obj[rel_key] = [r if r is not None else v for r, v in zip(rels, val)]
            counts[rel_key] = counts.get(rel_key, 0) + 1
            changed = True
    return changed


def fix_json(root: Path, path: Path, counts: dict, dry: bool) -> bool:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return False
    if not isinstance(data, dict):
        return False
    changed = False
    if path.name == "dem_terrain_summary.json":
        changed |= fix_paths(root, data, "dem_clipped", "dem_clipped_rel", counts)
        changed |= fix_paths(root, data, "dem_conditioned", "dem_conditioned_rel", counts)
        for prod in data.get("products", []):
            if isinstance(prod, dict) and "path_rel" not in prod:
                rel = rel_to_root(root, prod.get("path", ""))
                if rel is not None:
                    prod["path_rel"] = rel
                    counts["products[].path_rel"] = counts.get("products[].path_rel", 0) + 1
                    changed = True
    elif path.name == "dem_source_reference.json":
        changed |= fix_paths(root, data, "source_paths", "source_paths_rel", counts)
    elif path.name == "dem_terrain_manifest.json":
        assets = data.get("assets", {})
        records = list(assets.values()) if isinstance(assets, dict) else assets
        for rec in records:
            if isinstance(rec, dict):
                changed |= fix_paths(root, rec, "href", "href_rel", counts)
                changed |= fix_paths(root, rec, "source_paths", "source_paths_rel", counts)
        changed |= fix_paths(root, data, "source_paths", "source_paths_rel", counts)
    elif path.name == "soilgrids_provenance.json":
        changed |= fix_paths(root, data, "stats_table", "stats_table_rel", counts)
        changed |= fix_paths(root, data, "journal", "journal_rel", counts)
    elif "inputs" in data and "outputs" in data and "step_name" in data:
        # reporting step manifest (farm_html_render.json, ndvi_card_render_*.json, ...)
        changed |= fix_paths(root, data, "inputs", "inputs_rel", counts)
        changed |= fix_paths(root, data, "outputs", "outputs_rel", counts)
    if changed and not dry:
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(tmp, path)
    return changed


def fix_csv(root: Path, path: Path, counts: dict, dry: bool) -> bool:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return False
    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None or "dem_clipped" not in reader.fieldnames:
        return False
    rows = list(reader)
    if "dem_clipped_rel" in reader.fieldnames:
        return False
    fieldnames = list(reader.fieldnames)
    fieldnames.insert(fieldnames.index("dem_clipped") + 1, "dem_clipped_rel")
    fieldnames.insert(fieldnames.index("dem_conditioned") + 1, "dem_conditioned_rel")
    changed = False
    for row in rows:
        rel_c = rel_to_root(root, row.get("dem_clipped", ""))
        rel_d = rel_to_root(root, row.get("dem_conditioned", ""))
        row["dem_clipped_rel"] = rel_c or row.get("dem_clipped", "")
        row["dem_conditioned_rel"] = rel_d or row.get("dem_conditioned", "")
        if rel_c or rel_d:
            counts["csv rel columns"] = counts.get("csv rel columns", 0) + 1
            changed = True
    if changed and not dry:
        out = io.StringIO()
        writer = csv.DictWriter(out, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(out.getvalue(), encoding="utf-8")
        os.replace(tmp, path)
    return changed


def main() -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    parser.add_argument("--dry-run", action="store_true", help="count changes, write nothing")
    args = parser.parse_args()

    root_env = os.environ.get("DATA_PIPELINE_DATA_ROOT")
    if not root_env:
        print("ERROR: DATA_PIPELINE_DATA_ROOT is required (same contract as the pipeline)", file=sys.stderr)
        return 2
    root = Path(root_env).expanduser().resolve() / "data-pipeline"
    if not root.is_dir():
        print(f"ERROR: runtime root not found: {root}", file=sys.stderr)
        return 2

    counts: dict = {}
    touched = 0
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if path.name in {
            "dem_terrain_summary.json",
            "dem_source_reference.json",
            "dem_terrain_manifest.json",
            "soilgrids_provenance.json",
        } or (path.suffix == ".json" and path.parent.name == "manifests" and "_render" in path.name):
            touched += fix_json(root, path, counts, args.dry_run)
        elif path.name == "dem_terrain_summary.csv":
            touched += fix_csv(root, path, counts, args.dry_run)

    mode = "dry-run" if args.dry_run else "applied"
    print(f"backfill {mode}: {touched} journal files changed under {root}")
    for key, value in sorted(counts.items()):
        print(f"  {key}: {value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
