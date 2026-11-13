#!/usr/bin/env python3
"""Mirror-diff-zero attestation + release tagging for the skills trio.

Why: the deployed profile mirrors have repeatedly run AHEAD of the repo
(sections authored in-place during sessions), and a plugin that vendors the
repo via subtree-split would then ship a tree older than what the runtime
runs. A release tag is only honest if, at tag time, every payload path in
HEAD is byte-identical (post-clean-filter) to the deployed mirror.

Semantics (spec agreed 2026-11-13 in the plugin workstream):
  payload = paths listed in scripts/payload-paths.txt (one repo dir per line)
  compare = git ls-tree -r HEAD blobs (mode+oid+path) vs
            `git hash-object -w --path <rel> <mirror file>` for the same rel
            (the --path flag applies the repo's clean filters to the mirror
            file, so CRLF/text normalization cannot create false drift)
  extras  = any mirror file under a payload dir that is NOT tracked => drift
            (regenerable outputs must not live in a skill tree; the repo's
            policy already refuses committed generated examples)
  digest  = SHA-256 over the canonical manifest lines "mode oid path\\n"
            (sorted). The manifest is defined by the REPO side, so any
            checkout of the tagged tree reproduces the digest without
            consulting a mirror: verifiers re-run this script on the vendor
            subtree split (or with --digest-only on a checkout) and compare
            against the tag trailer.

Usage:
  scripts/mirror_diff_zero.py [--mirror-root DIR] [--list-extras]
                              [--fix-modes] [--tag TAG [--message MSG]]
  Mirror root defaults to $HERMES_MIRROR_SKILLS.
Tag trailer line:  Mirror-Diff-Zero: sha256:<digest>
"""
from __future__ import annotations

import argparse
import hashlib
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def git(*args: str, input: bytes | None = None) -> bytes:
    proc = subprocess.run(
        ["git", "-C", str(REPO), *args],
        input=input,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if proc.returncode != 0:
        sys.exit(f"git {' '.join(args)} failed: {proc.stderr.decode(errors='replace')}")
    return proc.stdout


def payload_paths() -> list[str]:
    manifest = REPO / "scripts" / "payload-paths.txt"
    paths = [
        line.strip()
        for line in manifest.read_text().splitlines()
        if line.strip() and not line.startswith("#")
    ]
    if not paths:
        sys.exit("payload-paths.txt lists no paths")
    return paths


def tracked_entries() -> list[tuple[str, str, str]]:
    """[(mode, oid, path)] for every blob under the payload paths at HEAD."""
    paths = payload_paths()
    out = git("ls-tree", "-r", "HEAD", "--format=%(objectmode) %(objecttype) %(objectname) tab=%(path)", *paths)
    entries = []
    for line in out.decode().splitlines():
        head, _, path = line.partition("tab=")
        parts = head.split()
        if len(parts) != 3:
            sys.exit(f"unparsable ls-tree line: {line!r}")
        mode, otype, oid = parts
        if otype != "blob":
            sys.exit(f"unsupported payload object {otype} at {path} (symlinks/submodules not allowed)")
        if mode not in ("100644", "100755"):
            sys.exit(f"unexpected mode {mode} at {path}")
        entries.append((mode, oid, path))
    if not entries:
        sys.exit("no tracked blobs under payload paths at HEAD")
    return entries


def digest(entries) -> str:
    blob = "".join(f"{mode} {oid} {path}\n" for mode, oid, path in sorted(entries)).encode()
    return hashlib.sha256(blob).hexdigest()


def check(entries, mirror_root: Path, *, fix_modes: bool) -> tuple[list[str], list[str], list[str]]:
    drift, missing, fixed = [], [], []
    seen = set()
    for mode, oid, rel in entries:
        seen.add(rel)
        fpath = mirror_root / rel
        if not fpath.is_file():
            missing.append(rel)
            continue
        got = git("hash-object", "-w", "--path", rel, str(fpath)).decode().strip()
        if got != oid:
            drift.append(rel)
        want_bit = mode == "100755"
        has_bit = os.access(fpath, os.X_OK)
        if want_bit != has_bit:
            if fix_modes:
                fpath.chmod(0o755 if want_bit else 0o644)
                fixed.append(rel)
            else:
                drift.append(f"{rel} (exec-bit {int(has_bit)} != {int(want_bit)}; pass --fix-modes)")
    tracked = seen
    extras = []
    for root_dir in payload_paths():
        base = mirror_root / root_dir
        if not base.is_dir():
            extras.append(f"{root_dir}/ (missing from mirror)")
            continue
        for dirpath, dirs, files in os.walk(base):
            dirs[:] = [d for d in dirs if d != "__pycache__"]
            for name in files:
                if name == ".DS_Store" or name.endswith(".pyc"):
                    continue  # interpreter/OS noise, never payload
                rel = str((Path(dirpath) / name).relative_to(mirror_root))
                if rel not in tracked:
                    extras.append(rel)
    return drift, missing, extras


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mirror-root", default=os.environ.get("HERMES_MIRROR_SKILLS", ""))
    ap.add_argument("--list-extras", action="store_true")
    ap.add_argument("--fix-modes", action="store_true")
    ap.add_argument("--tag", default="")
    ap.add_argument("--message", default="skills trio release")
    args = ap.parse_args()
    if not args.mirror_root:
        sys.exit("no mirror root: pass --mirror-root or set HERMES_MIRROR_SKILLS")
    mirror_root = Path(args.mirror_root).resolve()

    entries = tracked_entries()
    digest_value = digest(entries)
    if args.list_extras:
        _d, _m, extras = check(entries, mirror_root, fix_modes=False)
        for rel in sorted(extras):
            print(rel)
        return

    drift, missing, extras = check(entries, mirror_root, fix_modes=args.fix_modes)
    if args.fix_modes and not (drift or missing or extras):
        # re-attest after mode repair so the report never mixes pre/post state
        entries = tracked_entries()
        digest_value = digest(entries)
        drift, missing, extras = check(entries, mirror_root, fix_modes=False)

    problems = [f"drifted: {r}" for r in drift] + [f"missing: {r}" for r in missing] + [
        f"untracked-in-mirror: {r}" for r in extras
    ]
    if problems:
        print("MIRROR-DIFF-ZERO: FAIL")
        for p in problems:
            print(" ", p)
        sys.exit(1)

    print(f"MIRROR-DIFF-ZERO: PASS ({len(entries)} blobs, digest sha256:{digest_value})")
    if args.tag:
        tag_msg = f"{args.message}\n\nMirror-Diff-Zero: sha256:{digest_value}\nPayload-Paths: {', '.join(payload_paths())}\n"
        git("tag", "-a", args.tag, "-m", tag_msg)
        print(f"tagged {args.tag}")


if __name__ == "__main__":
    main()
