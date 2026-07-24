from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


class RuntimePathError(ValueError):
    pass


@dataclass(frozen=True)
class RuntimePaths:
    data_root: Path
    runtime_base: Path
    runtime_source: Path
    runtime_scripts: Path
    runtime_venv: Path

    @property
    def runtime_python(self) -> Path:
        return self.runtime_venv / "bin" / "python"


def resolve_runtime_paths(env: dict[str, str] | None = None) -> RuntimePaths:
    values = os.environ if env is None else env
    raw_data_root = values.get("DATA_PIPELINE_DATA_ROOT")
    if not raw_data_root:
        raise RuntimePathError(
            "DATA_PIPELINE_DATA_ROOT is required and must be an absolute path; "
            "run data-pipeline/scripts/install.sh --data-root <abs-path> or export it first."
        )

    data_root = Path(raw_data_root).expanduser()
    if not data_root.is_absolute():
        raise RuntimePathError(
            f"DATA_PIPELINE_DATA_ROOT must be an absolute path, got: {raw_data_root}"
        )

    data_root = data_root.resolve(strict=False)
    runtime_base = data_root / "data-pipeline"
    runtime_source = runtime_base / "src"

    raw_venv = values.get("DATA_PIPELINE_VENV_DIR")
    if raw_venv:
        runtime_venv = Path(raw_venv).expanduser()
        if not runtime_venv.is_absolute():
            raise RuntimePathError(
                f"DATA_PIPELINE_VENV_DIR must be an absolute path, got: {raw_venv}"
            )
        runtime_venv = runtime_venv.resolve(strict=False)
    else:
        runtime_venv = runtime_base / ".venv"

    return RuntimePaths(
        data_root=data_root,
        runtime_base=runtime_base,
        runtime_source=runtime_source,
        runtime_scripts=runtime_source / "scripts",
        runtime_venv=runtime_venv,
    )
