"""Maturity fit: does each season's heat support the county recommendation?

The county relative-maturity product turns a five-year mean GDD total into an RM
target with one linear rule (20 GDD per RM). This module applies that same rule
to each field-year's own full-year GDD, so a shortfall is reported in the units
the recommendation is written in.

Both sides must use the same GDD definition: base 10 °C, upper cap 30 °C, and
the whole calendar year. That is *not* the April-September, uncapped seasonal GDD
used by the weather category; mixing the two invents a shortfall that is really a
window difference.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from . import metrics
from .discover import Dataset


@dataclass(frozen=True)
class CountyTarget:
    """The maturity a county's five-year heat total recommends."""

    fips: str
    county_name: str
    rm_target: float
    gdd_required_c: float
    soybean_mg: float | None


def county_targets(dataset: Dataset) -> dict[str, CountyTarget]:
    """Map county FIPS to its corn RM target and soybean MG reference."""

    if dataset.maturity is None:
        raise ValueError("no maturity inputs were discovered")

    corn = pd.read_parquet(dataset.maturity.average).copy()
    soy = pd.read_parquet(dataset.maturity.soybean_average).copy()
    corn["fips"] = corn["fips"].astype(str).str.zfill(5)
    soy["fips"] = soy["fips"].astype(str).str.zfill(5)
    soy_mg = dict(zip(soy["fips"], soy["mg_optimal"]))

    targets: dict[str, CountyTarget] = {}
    for farm in dataset.farms:
        rows = corn[corn["fips"] == farm.county_fips]
        if rows.empty:
            raise ValueError(
                f"county {farm.county_name or farm.county_fips} ({farm.county_fips}) "
                f"is absent from {dataset.maturity.average.name}"
            )
        row = rows.iloc[0]
        rm = round(float(row["rm_relative_maturity"]), 1)
        mg = soy_mg.get(farm.county_fips)
        targets[farm.county_fips] = CountyTarget(
            fips=farm.county_fips,
            county_name=farm.county_name or str(row.get("county_name_full", "")),
            rm_target=rm,
            gdd_required_c=rm * metrics.CORN_GDD_PER_RM,
            soybean_mg=None if mg is None or pd.isna(mg) else float(mg),
        )
    return targets


def maturity_fit(
    weather: pd.DataFrame,
    farm_county: dict[str, str],
    targets: dict[str, CountyTarget],
) -> pd.DataFrame:
    """Per field-year full-year GDD against the county RM requirement."""

    frame = metrics.maturity_gdd(weather)
    frame["county_fips"] = frame["farm_slug"].map(farm_county)
    missing = frame["county_fips"].isna()
    if missing.any():
        farms = ", ".join(sorted(frame.loc[missing, "farm_slug"].unique()))
        raise ValueError(f"no county FIPS for farm(s): {farms}")

    frame["rm_target"] = frame["county_fips"].map(
        lambda fips: targets[fips].rm_target
    )
    frame["gdd_required_c"] = frame["county_fips"].map(
        lambda fips: targets[fips].gdd_required_c
    )
    frame["shortfall_c"] = (frame["gdd_required_c"] - frame["gdd_maturity"]).clip(
        lower=0.0
    )
    frame["rm_shortfall"] = frame["shortfall_c"] / metrics.CORN_GDD_PER_RM
    frame["season_complete"] = frame["days"] >= 360
    return frame.sort_values(["grower", "field_id", "year"]).reset_index(drop=True)


__all__ = ["CountyTarget", "county_targets", "maturity_fit"]
