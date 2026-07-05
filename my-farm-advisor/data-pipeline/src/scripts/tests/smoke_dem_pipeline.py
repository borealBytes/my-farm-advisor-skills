#!/usr/bin/env python3
"""Offline smoke checks for DEM pipeline orchestration guardrails."""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile
import types
import uuid
from pathlib import Path
from typing import Callable


SCRIPT_PATH = Path(__file__).resolve()
SCRIPTS_DIR = SCRIPT_PATH.parents[1]
REPO_ROOT = SCRIPT_PATH.parents[5]
RUN_PIPELINE_PATH = SCRIPTS_DIR / "run_farm_pipeline.py"
DIRECT_DEM_PATH = SCRIPTS_DIR / "ingest" / "download_dem_terrain.py"
PACKAGE_VALIDATION_PATH = (
    REPO_ROOT
    / "my-farm-advisor"
    / "terrain"
    / "dem-terrain"
    / "src"
    / "dem_terrain"
    / "package_validation.py"
)


class SmokeFailure(AssertionError):
    """Raised when a smoke check fails."""


def main() -> int:
    checks: list[tuple[str, Callable[[], None]]] = [
        ("default DEM command order and safe flags", check_default_dem_command),
        ("structure-test remains DEM-free", check_structure_test_no_dem),
        ("DEM child failure halts pipeline strictly", check_dem_failure_strictness),
        ("package validation rejects synthetic manifests by default", check_package_validation_synthetic_guard),
        ("direct DEM CLI requires explicit synthetic override", check_direct_dem_cli_synthetic_guard),
    ]
    for label, check in checks:
        check()
        print(f"PASS: {label}")
    print(f"PASS: {len(checks)} DEM pipeline smoke checks completed")
    return 0


def check_default_dem_command() -> None:
    with tempfile.TemporaryDirectory(prefix="mfa-dem-orchestrator-") as raw_root:
        module = _load_run_pipeline_module(Path(raw_root))
        _seed_boundary(module, grower="smoke-grower", farm="smoke-farm")
        commands, output, code = _run_orchestrator(
            module,
            [
                "--grower-slug",
                "smoke-grower",
                "--farm-slug",
                "smoke-farm",
                "--farm-name",
                "Smoke Farm",
                "--dem-context-meters",
                "33.5",
                "--dem-source-policy",
                "usgs-tnm",
            ],
        )
        _assert_equal(code, 0, output)
        scripts = _relative_command_scripts(module, commands)
        _assert_equal(scripts[0], "ingest/download_fields.py", scripts)
        _assert_equal(scripts[1], "ingest/download_dem_terrain.py", scripts)
        _assert_equal(
            commands[1][2:],
            ["--allow-live-downloads", "--context-meters", "33.5", "--source-policy", "usgs-tnm"],
            commands[1],
        )
        all_args = [arg for command in commands for arg in command[2:]]
        _assert_not_in("--offline-fixtures", all_args)
        _assert_not_in("--allow-synthetic-fixtures", all_args)


def check_structure_test_no_dem() -> None:
    with tempfile.TemporaryDirectory(prefix="mfa-dem-structure-") as raw_root:
        module = _load_run_pipeline_module(Path(raw_root))
        commands, output, code = _run_orchestrator(module, ["--structure-test"])
        _assert_equal(code, 0, output)
        _assert_equal(commands, [], commands)
        _assert_in("Structure test complete.", output)
        _assert_not_in("DEM terrain ingest", output)


def check_dem_failure_strictness() -> None:
    def fail_dem(command: list[str]) -> int:
        return 1 if command[1].endswith("ingest/download_dem_terrain.py") else 0

    with tempfile.TemporaryDirectory(prefix="mfa-dem-strict-") as raw_root:
        module = _load_run_pipeline_module(Path(raw_root))
        _seed_boundary(module, grower="smoke-grower", farm="smoke-farm")
        commands, output, code = _run_orchestrator(
            module,
            ["--grower-slug", "smoke-grower", "--farm-slug", "smoke-farm"],
            returncode_for_command=fail_dem,
        )
        _assert_equal(code, 1, output)
        scripts = _relative_command_scripts(module, commands)
        _assert_equal(scripts, ["ingest/download_fields.py", "ingest/download_dem_terrain.py"], scripts)
        _assert_in("Pipeline halted at: ingest/download_dem_terrain.py", output)
        _assert_not_in("ingest/download_soil.py", scripts)


def check_package_validation_synthetic_guard() -> None:
    with tempfile.TemporaryDirectory(prefix="mfa-dem-validation-") as raw_dir:
        manifest = Path(raw_dir) / "dem_terrain_manifest.json"
        manifest.write_text(
            json.dumps(
                {
                    "synthetic_fixture": True,
                    "fallback_reason": "offline_fixture_mode",
                    "selected_source": {"fallback_reason": "offline_fixture_mode"},
                    "outputs": {},
                    "warnings": ["synthetic_fixture=true"],
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

        rejected = _run_package_validation(manifest)
        _assert_equal(rejected.returncode, 1, rejected.stdout + rejected.stderr)
        rejected_payload = json.loads(rejected.stdout)
        rejected_errors = "\n".join(rejected_payload.get("errors", []))
        _assert_in("synthetic DEM fixture package detected", rejected_errors)
        _assert_in("--allow-synthetic-fixture-package", rejected_errors)

        allowed = _run_package_validation(manifest, allow_synthetic=True)
        _assert_equal(allowed.returncode, 1, allowed.stdout + allowed.stderr)
        allowed_payload = json.loads(allowed.stdout)
        allowed_warnings = "\n".join(allowed_payload.get("warnings", []))
        allowed_errors = "\n".join(allowed_payload.get("errors", []))
        _assert_in("allowed by --allow-synthetic-fixture-package", allowed_warnings)
        _assert_not_in("rerun with --allow-synthetic-fixture-package", allowed_errors)


def check_direct_dem_cli_synthetic_guard() -> None:
    with tempfile.TemporaryDirectory(prefix="mfa-dem-direct-") as raw_root:
        env = os.environ.copy()
        env["DATA_PIPELINE_DATA_ROOT"] = raw_root
        completed = subprocess.run(
            [sys.executable, str(DIRECT_DEM_PATH), "--offline-fixtures"],
            cwd=REPO_ROOT,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        combined = completed.stdout + completed.stderr
        _assert_equal(completed.returncode, 2, combined)
        _assert_in("synthetic_fixture_override_required", combined)
        _assert_in("--allow-synthetic-fixtures", combined)


def _load_run_pipeline_module(data_root: Path) -> types.ModuleType:
    os.environ["DATA_PIPELINE_DATA_ROOT"] = str(data_root)
    for path in (SCRIPTS_DIR, SCRIPTS_DIR / "lib"):
        path_text = str(path)
        if path_text not in sys.path:
            sys.path.insert(0, path_text)
    for name in (
        "bootstrap_runtime",
        "lib.paths",
        "paths",
        "lib.runtime_paths",
        "runtime_paths",
        "reporting_bootstrap",
    ):
        sys.modules.pop(name, None)

    fake_bootstrap = types.ModuleType("bootstrap_runtime")
    setattr(fake_bootstrap, "ensure_runtime_environment", lambda: None)
    sys.modules["bootstrap_runtime"] = fake_bootstrap

    module_name = f"run_farm_pipeline_smoke_{uuid.uuid4().hex}"
    spec = importlib.util.spec_from_file_location(module_name, RUN_PIPELINE_PATH)
    if spec is None or spec.loader is None:
        raise SmokeFailure(f"could not load {RUN_PIPELINE_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    setattr(module, "ensure_canonical_data_tree", lambda **_: ["field-one"])
    return module


def _seed_boundary(module: types.ModuleType, *, grower: str, farm: str) -> None:
    boundary = module.farm_boundary_path(grower, farm)
    boundary.parent.mkdir(parents=True, exist_ok=True)
    boundary.write_text('{"type":"FeatureCollection","features":[]}\n', encoding="utf-8")


def _run_orchestrator(
    module: types.ModuleType,
    args: list[str],
    *,
    returncode_for_command: Callable[[list[str]], int] | None = None,
) -> tuple[list[list[str]], str, int]:
    commands: list[list[str]] = []
    original_argv = sys.argv[:]
    original_run = module.subprocess.run
    stdout = io.StringIO()

    def fake_run(command: list[str], **_: object) -> types.SimpleNamespace:
        commands.append([str(part) for part in command])
        return types.SimpleNamespace(returncode=(returncode_for_command or (lambda _command: 0))(commands[-1]))

    module.subprocess.run = fake_run
    sys.argv = [str(RUN_PIPELINE_PATH), *args]
    code = 0
    try:
        with contextlib.redirect_stdout(stdout):
            try:
                module.main()
            except SystemExit as exc:
                code = int(exc.code) if isinstance(exc.code, int) else 1
    finally:
        sys.argv = original_argv
        module.subprocess.run = original_run
    return commands, stdout.getvalue(), code


def _relative_command_scripts(module: types.ModuleType, commands: list[list[str]]) -> list[str]:
    return [Path(command[1]).relative_to(module._SCRIPTS).as_posix() for command in commands]


def _run_package_validation(manifest: Path, *, allow_synthetic: bool = False) -> subprocess.CompletedProcess[str]:
    command = [
        sys.executable,
        str(PACKAGE_VALIDATION_PATH),
        str(manifest),
        "--json",
        "--no-git-check",
    ]
    if allow_synthetic:
        command.append("--allow-synthetic-fixture-package")
    return subprocess.run(
        command,
        cwd=REPO_ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def _assert_equal(actual: object, expected: object, context: object) -> None:
    if actual != expected:
        raise SmokeFailure(f"expected {expected!r}, got {actual!r}; context={context!r}")


def _assert_in(needle: str, haystack: str | list[str]) -> None:
    if needle not in haystack:
        raise SmokeFailure(f"expected to find {needle!r} in {haystack!r}")


def _assert_not_in(needle: str, haystack: str | list[str]) -> None:
    if needle in haystack:
        raise SmokeFailure(f"did not expect {needle!r} in {haystack!r}")


if __name__ == "__main__":
    raise SystemExit(main())
