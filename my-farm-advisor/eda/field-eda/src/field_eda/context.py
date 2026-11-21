"""Lazily loaded analysis context shared by the three category modules."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from . import maturity, metrics
from .discover import Dataset


@dataclass
class Analysis:
    dataset: Dataset
    out_dir: Path
    dpi: int
    _fields: object | None = field(default=None, repr=False)
    _cdl: pd.DataFrame | None = field(default=None, repr=False)
    _dominant: pd.DataFrame | None = field(default=None, repr=False)
    _weather: pd.DataFrame | None = field(default=None, repr=False)
    _season: pd.DataFrame | None = field(default=None, repr=False)
    _field_year: pd.DataFrame | None = field(default=None, repr=False)
    _maturity_targets: dict | None = field(default=None, repr=False)
    _maturity_fit: pd.DataFrame | None = field(default=None, repr=False)
    _risk: pd.DataFrame | None = field(default=None, repr=False)

    # ------------------------------------------------------------------ #
    # Output locations
    # ------------------------------------------------------------------ #

    @property
    def figures_dir(self) -> Path:
        return self.out_dir / "figures"

    @property
    def maps_dir(self) -> Path:
        return self.out_dir / "maps"

    @property
    def tables_dir(self) -> Path:
        return self.out_dir / "tables"

    def ensure_dirs(self) -> None:
        for path in (self.figures_dir, self.maps_dir, self.tables_dir):
            path.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------ #
    # Cached inputs
    # ------------------------------------------------------------------ #

    @property
    def fields(self):
        if self._fields is None:
            self._fields = metrics.load_boundaries(self.dataset)
        return self._fields

    @property
    def cdl(self) -> pd.DataFrame:
        if self._cdl is None:
            self._cdl = metrics.load_cdl(self.dataset)
        return self._cdl

    @property
    def dominant(self) -> pd.DataFrame:
        if self._dominant is None:
            self._dominant = metrics.corn_after_corn(metrics.dominant_crops(self.cdl))
        return self._dominant

    @property
    def weather(self) -> pd.DataFrame:
        if self._weather is None:
            self._weather = metrics.load_weather(self.dataset)
        return self._weather

    @property
    def season(self) -> pd.DataFrame:
        if self._season is None:
            self._season = metrics.season_slice(self.weather, self.dataset.config)
        return self._season

    @property
    def field_year_weather(self) -> pd.DataFrame:
        if self._field_year is None:
            self._field_year = metrics.field_year_weather(self.season)
        return self._field_year

    @property
    def farm_county(self) -> dict[str, str]:
        return {farm.farm_slug: farm.county_fips for farm in self.dataset.farms}

    @property
    def maturity_targets(self) -> dict:
        if self._maturity_targets is None:
            self._maturity_targets = maturity.county_targets(self.dataset)
        return self._maturity_targets

    @property
    def field_maturity(self) -> pd.DataFrame:
        if self._maturity_fit is None:
            self._maturity_fit = maturity.maturity_fit(
                self.weather, self.farm_county, self.maturity_targets
            )
        return self._maturity_fit

    @property
    def risk(self) -> pd.DataFrame:
        if self._risk is None:
            self._risk = metrics.field_year_risk(self.season)
        return self._risk

    # ------------------------------------------------------------------ #
    # Convenience
    # ------------------------------------------------------------------ #

    @property
    def growers(self):
        return self.dataset.growers

    @property
    def grower_index(self) -> dict[str, int]:
        return {grower.slug: index for index, grower in enumerate(self.dataset.growers)}

    def input_names(self, *, maturity: bool = False) -> list[str]:
        """Input paths relative to the runtime root, safe to commit in captions."""

        root = self.dataset.root
        paths: list[Path] = []
        for farm in self.dataset.farms:
            paths.extend((farm.boundary_path, farm.weather_path, farm.cdl_path))
        if maturity and self.dataset.maturity is not None:
            paths.extend(sorted(self.dataset.maturity.annual.values()))
            paths.extend(
                (self.dataset.maturity.average, self.dataset.maturity.soybean_average)
            )

        names: list[str] = []
        for path in paths:
            try:
                names.append(path.relative_to(root).as_posix())
            except ValueError:
                names.append(path.name)
        return names
