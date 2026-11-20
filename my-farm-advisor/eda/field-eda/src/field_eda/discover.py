"""Runtime discovery and schema validation.

Everything this subskill reads is an existing data-pipeline output. Discovery is
strict on purpose: a grower that has some but not all inputs fails loudly rather
than being silently dropped, and any soil table in the input set aborts the run.
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Sequence

import pandas as pd

WEATHER_REQUIRED = (
    "field_id",
    "lat",
    "lon",
    "date",
    "T2M",
    "T2M_MAX",
    "T2M_MIN",
    "PRECTOTCORR",
)

CDL_REQUIRED = (
    "field_id",
    "year",
    "crop_code",
    "crop_name",
    "pixel_count",
    "pct",
    "crop_source",
)

BOUNDARY_REQUIRED = ("field_id", "geometry")

#: Duplicated from ``data-pipeline/src/scripts/lib/paths.py`` on purpose: this
#: subskill must not import the pipeline package just to name a file.
def artifact_prefix(farm_slug: str) -> str:
    normalized = farm_slug.replace("-", "_")
    if normalized == "iowa_demo_farm":
        return "iowa"
    if normalized.endswith("_farm"):
        normalized = normalized[: -len("_farm")]
    return normalized


def _soil_like(path: Path) -> bool:
    name = path.name.lower()
    return "soil" in name or "ssurgo" in name


class DiscoveryError(RuntimeError):
    """Raised when the runtime is missing inputs or carries a soil table."""


@dataclass(frozen=True)
class FarmInputs:
    grower_slug: str
    farm_slug: str
    state: str
    display_name: str
    boundary_path: Path
    weather_path: Path
    cdl_path: Path
    field_ids: tuple[str, ...] = field(default=())

    @property
    def grower_label(self) -> str:
        return f"{self.state or self.grower_slug}"


@dataclass
class GrowerInputs:
    slug: str
    display_name: str
    state: str
    farms: list[FarmInputs] = field(default_factory=list)
    grid_cells: int = 0
    fields: tuple[str, ...] = field(default=())

    @property
    def label(self) -> str:
        return self.state or self.slug


@dataclass(frozen=True)
class RunConfig:
    season_start_month: int = 4
    season_end_month: int = 9
    dpi: int = 150
    seed: int = 20261120
    bootstrap: int = 2000


@dataclass
class Dataset:
    root: Path
    growers: list[GrowerInputs]
    config: RunConfig

    @property
    def farms(self) -> list[FarmInputs]:
        return [farm for grower in self.growers for farm in grower.farms]

    @property
    def field_count(self) -> int:
        return sum(len(grower.fields) for grower in self.growers)

    @property
    def states(self) -> list[str]:
        return sorted({grower.state for grower in self.growers if grower.state})


def _read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:  # pragma: no cover - defensive
        raise DiscoveryError(f"cannot read metadata {path}: {exc}") from exc


def _header(path: Path) -> list[str]:
    try:
        with path.open(newline="", encoding="utf-8") as handle:
            return next(csv.reader(handle))
    except (OSError, StopIteration) as exc:
        raise DiscoveryError(f"cannot read table header {path}: {exc}") from exc


def assert_schema(path: Path, required: Sequence[str], label: str) -> None:
    if not path.is_file():
        raise DiscoveryError(f"{label} is missing: {path}")
    if _soil_like(path):
        raise DiscoveryError(
            f"{label} looks like a soil table ({path.name}); field-eda does not "
            "read soil inputs"
        )
    header = set(_header(path))
    missing = [column for column in required if column not in header]
    if missing:
        raise DiscoveryError(
            f"{label} {path.name} is missing required column(s): "
            + ", ".join(missing)
        )


def _only(paths: Iterable[Path], pattern: str, label: str) -> Path:
    matches = sorted(paths)
    if not matches:
        raise DiscoveryError(f"no {label} matching {pattern} found")
    if len(matches) > 1:
        raise DiscoveryError(
            f"multiple {label} files matching {pattern}: "
            + ", ".join(m.name for m in matches)
        )
    return matches[0]


def _boundary_field_ids(path: Path) -> tuple[str, ...]:
    import geopandas as gpd

    frame = gpd.read_file(path, columns=["field_id"])
    ids = sorted({str(value) for value in frame["field_id"].dropna()})
    if not ids:
        raise DiscoveryError(f"boundary file has no field_id values: {path}")
    return tuple(ids)


def _grid_cells(path: Path) -> int:
    frame = pd.read_csv(path, usecols=["lat", "lon"])
    cells = {
        (round(float(lat) / 0.5), round(float(lon) / 0.625))
        for lat, lon in zip(frame["lat"], frame["lon"])
    }
    return len(cells)


def discover(
    root: Path,
    growers: Sequence[str] | None = None,
    config: RunConfig | None = None,
) -> Dataset:
    """Walk ``<root>/data-pipeline/growers`` and validate every candidate grower."""

    root = Path(root).expanduser().resolve()
    base = root / "data-pipeline" if (root / "data-pipeline").is_dir() else root
    growers_dir = base / "growers"
    if not growers_dir.is_dir():
        raise DiscoveryError(
            f"{root} does not look like a runtime root (missing data-pipeline/growers)"
        )

    wanted = {slug for slug in growers} if growers else None
    discovered: list[GrowerInputs] = []

    for grower_dir in sorted(p for p in growers_dir.iterdir() if p.is_dir()):
        slug = grower_dir.name
        if wanted is not None and slug not in wanted:
            continue
        farm_dirs = sorted(p for p in (grower_dir / "farms").glob("*") if p.is_dir())
        if not farm_dirs:
            raise DiscoveryError(f"grower {slug} has no farms")

        grower_meta = (
            _read_json(grower_dir / "grower.json")
            if (grower_dir / "grower.json").is_file()
            else {}
        )
        grower = GrowerInputs(
            slug=slug,
            display_name=str(grower_meta.get("display_name") or slug),
            state=str(grower_meta.get("state") or ""),
        )

        for farm_dir in farm_dirs:
            farm_slug = farm_dir.name
            farm_meta = _read_json(farm_dir / "farm.json")
            prefix = artifact_prefix(farm_slug)
            tables = farm_dir / "derived" / "tables"
            boundary_path = farm_dir / "boundary" / "field_boundaries.geojson"
            weather_path = _only(
                tables.glob(f"{prefix}_weather_*.csv"),
                f"{prefix}_weather_*.csv",
                f"weather table for {farm_slug}",
            )
            cdl_path = _only(
                tables.glob(f"{prefix}_cdl_*_full_composition.csv"),
                f"{prefix}_cdl_*_full_composition.csv",
                f"CDL composition table for {farm_slug}",
            )
            assert_schema(weather_path, WEATHER_REQUIRED, f"weather table for {farm_slug}")
            assert_schema(cdl_path, CDL_REQUIRED, f"CDL table for {farm_slug}")
            if not boundary_path.is_file():
                raise DiscoveryError(f"boundary file is missing: {boundary_path}")

            field_ids = _boundary_field_ids(boundary_path)
            state = str(farm_meta.get("state") or grower.state or "")
            grower.state = grower.state or state
            grower.farms.append(
                FarmInputs(
                    grower_slug=slug,
                    farm_slug=farm_slug,
                    state=state,
                    display_name=str(farm_meta.get("display_name") or farm_slug),
                    boundary_path=boundary_path,
                    weather_path=weather_path,
                    cdl_path=cdl_path,
                    field_ids=field_ids,
                )
            )
            grower.fields += field_ids
            grower.grid_cells = max(grower.grid_cells, _grid_cells(weather_path))

        discovered.append(grower)

    if wanted is not None:
        missing = sorted(wanted - {grower.slug for grower in discovered})
        if missing:
            raise DiscoveryError("requested grower(s) not found: " + ", ".join(missing))
    if not discovered:
        raise DiscoveryError(f"no growers discovered under {growers_dir}")

    return Dataset(root=root, growers=discovered, config=config or RunConfig())


def describe(dataset: Dataset) -> str:
    lines = [
        f"runtime: {dataset.root}",
        f"growers: {len(dataset.growers)}",
        f"fields:  {dataset.field_count}",
    ]
    for grower in dataset.growers:
        lines.append(
            f"  {grower.label:>2}  {grower.slug:22} "
            f"{len(grower.fields):2} fields  "
            f"{len(grower.farms)} farm(s)  "
            f"{grower.grid_cells} NASA POWER grid cell(s)"
        )
    lines.append(
        "season: months "
        f"{dataset.config.season_start_month}-{dataset.config.season_end_month}"
    )
    return "\n".join(lines)
