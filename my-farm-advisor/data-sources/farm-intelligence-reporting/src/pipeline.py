from __future__ import annotations

import hashlib
import json
import logging
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

STEP_FIELDS_NORMALIZE = "fields_normalize"
STEP_HEADLANDS_BUILD = "headlands_build"
STEP_SSURGO_DOWNLOAD = "ssurgo_download"
STEP_SSURGO_SUMMARIZE = "ssurgo_summarize"
STEP_WEATHER_DOWNLOAD = "weather_download"
STEP_WEATHER_SUMMARIZE = "weather_summarize"
STEP_CDL_DOWNLOAD = "cdl_download"
STEP_CDL_EXTRACT = "cdl_extract"
STEP_CDL_SUMMARIZE = "cdl_summarize"
STEP_SENTINEL_SUMMARIZE = "sentinel_summarize"
STEP_LANDSAT_SUMMARIZE = "landsat_summarize"
STEP_FIELD_METRICS_BUILD = "field_metrics_build"
STEP_FARM_METRICS_BUILD = "farm_metrics_build"
STEP_FIELD_POSTER_RENDER = "field_poster_render"
STEP_FARM_POSTER_RENDER = "farm_poster_render"
STEP_FARM_HTML_RENDER = "farm_html_render"
STEP_FARM_MARKDOWN = "farm_markdown"
STEP_GEOADMIN_PREPARE = "geoadmin_prepare"
STEP_FIELD_FIPS_MAP = "field_fips_map"
STEP_COUNTY_WEATHER_TRANSFORM = "county_weather_transform"
STEP_COUNTY_GDD_BUILD = "county_gdd_build"
STEP_CORN_RM_BUILD = "corn_rm_build"
STEP_SOYBEAN_MG_BUILD = "soybean_mg_build"
STEP_MATURITY_MAP_RENDER = "maturity_map_render"

STEP_ORDER = [
    STEP_FIELDS_NORMALIZE,
    STEP_HEADLANDS_BUILD,
    STEP_SSURGO_DOWNLOAD,
    STEP_SSURGO_SUMMARIZE,
    STEP_WEATHER_DOWNLOAD,
    STEP_WEATHER_SUMMARIZE,
    STEP_CDL_DOWNLOAD,
    STEP_CDL_EXTRACT,
    STEP_CDL_SUMMARIZE,
    STEP_SENTINEL_SUMMARIZE,
    STEP_LANDSAT_SUMMARIZE,
    STEP_FIELD_METRICS_BUILD,
    STEP_FARM_METRICS_BUILD,
    STEP_FIELD_POSTER_RENDER,
    STEP_FARM_POSTER_RENDER,
    STEP_FARM_HTML_RENDER,
    STEP_FARM_MARKDOWN,
]

ANNUAL_MATURITY_STEP_ORDER = [
    STEP_GEOADMIN_PREPARE,
    STEP_FIELD_FIPS_MAP,
    STEP_COUNTY_WEATHER_TRANSFORM,
    STEP_COUNTY_GDD_BUILD,
    STEP_CORN_RM_BUILD,
    STEP_SOYBEAN_MG_BUILD,
    STEP_MATURITY_MAP_RENDER,
]


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _sha256_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8192), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


@dataclass(slots=True)
class FieldReportingConfig:
    farm_name: str
    field_boundary_path: str
    grower_slug: str = "default-grower"
    farm_slug: str = "default-farm"
    output_dir: str = "data/my-farm-advisor/EDA"
    reporting_dir: str = "data/my-farm-advisor/reporting"
    headland_width_m: float = 9.0
    weather_years: tuple[int, ...] = (2021, 2022, 2023, 2024, 2025)
    cdl_years: tuple[int, ...] = (2021, 2022, 2023, 2024, 2025)
    imagery_years: tuple[int, ...] = (2021, 2022, 2023, 2024, 2025, 2026)
    imagery_start_date: str = "2025-03-01"
    imagery_end_date: str = "2025-11-30"
    sentinel_cloud_cover_max: float = 20.0
    landsat_cloud_cover_max: float = 20.0
    compute_ndvi_integral: bool = True

    @property
    def farm_root(self) -> Path:
        return Path("data") / "growers" / self.grower_slug / "farms" / self.farm_slug

    @property
    def farm_manifest_dir(self) -> Path:
        return self.farm_root / "manifests"

    @property
    def farm_logs_dir(self) -> Path:
        return self.farm_root / "logs"

    def field_root(self, field_slug: str) -> Path:
        return self.farm_root / "fields" / field_slug

    def field_manifest_dir(self, field_slug: str) -> Path:
        return self.field_root(field_slug) / "manifests"

    def field_logs_dir(self, field_slug: str) -> Path:
        return self.field_root(field_slug) / "logs"


@dataclass(slots=True)
class StepManifest:
    step_name: str
    status: str
    inputs: list[str] = field(default_factory=list)
    outputs: list[str] = field(default_factory=list)
    input_fingerprints: dict[str, str] = field(default_factory=dict)
    code_fingerprints: dict[str, str] = field(default_factory=dict)
    config_fingerprint: str = ""

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, sort_keys=True)

    def write(self, path: str | Path) -> Path:
        output_path = Path(path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(self.to_json(), encoding="utf-8")
        return output_path


def load_manifest(manifest_path: str | Path) -> StepManifest | None:
    path = Path(manifest_path)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return StepManifest(**data)
    except Exception:
        return None


def build_code_fingerprint(code_paths: list[str | Path]) -> dict[str, str]:
    fingerprints: dict[str, str] = {}
    for raw_path in code_paths:
        path = Path(raw_path)
        if path.exists():
            fingerprints[str(path)] = _sha256_file(path)
    return fingerprints


def build_config_fingerprint(config: FieldReportingConfig | dict[str, Any]) -> str:
    value = asdict(config) if isinstance(config, FieldReportingConfig) else config
    return _sha256_text(json.dumps(value, sort_keys=True, default=str))


def build_step_manifest(
    step_name: str,
    input_paths: list[str | Path],
    output_paths: list[str | Path],
    code_paths: list[str | Path],
    config: FieldReportingConfig | dict[str, Any],
    status: str = "planned",
) -> StepManifest:
    inputs = [str(Path(p)) for p in input_paths]
    outputs = [str(Path(p)) for p in output_paths]
    input_fingerprints = {
        str(Path(p)): _sha256_file(Path(p)) for p in input_paths if Path(p).exists()
    }
    code_fingerprints = build_code_fingerprint(code_paths)
    config_fingerprint = build_config_fingerprint(config)
    return StepManifest(
        step_name=step_name,
        status=status,
        inputs=inputs,
        outputs=outputs,
        input_fingerprints=input_fingerprints,
        code_fingerprints=code_fingerprints,
        config_fingerprint=config_fingerprint,
    )


def step_is_stale(manifest: StepManifest, previous: StepManifest | None) -> bool:
    if previous is None:
        return True
    if manifest.outputs and not all(Path(p).exists() for p in manifest.outputs):
        return True
    return (
        manifest.input_fingerprints != previous.input_fingerprints
        or manifest.code_fingerprints != previous.code_fingerprints
        or manifest.config_fingerprint != previous.config_fingerprint
    )


def run_step(
    step_name: str,
    func: Callable[[], None],
    manifest: StepManifest,
    prior_manifest: StepManifest | None,
    manifest_dir: str | Path,
    *,
    force: bool = False,
) -> str:
    stale = force or step_is_stale(manifest, prior_manifest)
    if not stale:
        logger.info("skip  %s", step_name)
        return "skip"
    t0 = time.monotonic()
    try:
        func()
        manifest.status = "complete"
        elapsed = time.monotonic() - t0
        logger.info("run   %s  (%.1fs)", step_name, elapsed)
    except Exception as exc:
        manifest.status = "fail"
        logger.error("fail  %s  %s", step_name, exc)
        raise
    manifest.write(Path(manifest_dir) / f"{step_name}.json")
    return "run"


class PipelineRunner:
    def __init__(
        self,
        config: FieldReportingConfig,
        steps: dict[str, Callable[[], None]],
        code_paths: dict[str, list[str | Path]] | None = None,
        input_paths: dict[str, list[str | Path]] | None = None,
        output_paths: dict[str, list[str | Path]] | None = None,
        force_steps: list[str] | None = None,
    ) -> None:
        self.config = config
        self.steps = steps
        self.code_paths = code_paths or {}
        self.input_paths = input_paths or {}
        self.output_paths = output_paths or {}
        self.force_steps = set(force_steps or [])
        self.manifest_dir = config.farm_manifest_dir

    def run(self, from_step: str | None = None) -> dict[str, str]:
        results: dict[str, str] = {}
        active = from_step is None
        for step_name in STEP_ORDER:
            if step_name == from_step:
                active = True
            if not active or step_name not in self.steps:
                continue
            manifest_path = self.manifest_dir / f"{step_name}.json"
            prior = load_manifest(manifest_path)
            manifest = build_step_manifest(
                step_name=step_name,
                input_paths=self.input_paths.get(step_name, []),
                output_paths=self.output_paths.get(step_name, []),
                code_paths=self.code_paths.get(step_name, []),
                config=self.config,
            )
            result = run_step(
                step_name=step_name,
                func=self.steps[step_name],
                manifest=manifest,
                prior_manifest=prior,
                manifest_dir=self.manifest_dir,
                force=step_name in self.force_steps,
            )
            results[step_name] = result
        return results
