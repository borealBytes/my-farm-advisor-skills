"""Shared colour standard for every rendered figure.

Implements references/colormap-recommendations.md (adopted 2026-11):

* continuous soil properties -> ISRIC-style single-hue continuous ramps
  interpolated through the published ``soil.legends`` stops, stretched to
  P2-P98 of the *field's own* data, colorbar TICKS at the agronomic
  breakpoints (the stepped BoundaryNorm is retired — the official SLDs are
  themselves discretized samples of a smooth ramp);
* pH -> diverging centered on 7.0 (meaningful midpoint);
* DEM -> relief classifier: <10 m tile land gets ``cividis`` on P2-P98,
  >50 m uplands may use hypsometric ``terrain``; never ``terrain`` on
  micro-relief (the whole scene collapses into one ramp segment);
* slope/TWI -> sequential with agronomic / field-quantile ticks;
* categoricals -> Okabe-Ito colour-blind-safe set (<=8 classes).

Every renderer (grid maps, terrain sheets, field stacks, NDVI cards, future
web maps) takes its scales from here so the whole product family stays
consistent.
"""
from __future__ import annotations

import csv
from pathlib import Path

import matplotlib
import numpy as np
from matplotlib.colors import LinearSegmentedColormap, Normalize, TwoSlopeNorm

_DATA = Path(__file__).resolve().parents[1] / "data" / "isric_legends"

# Agronomic / legend anchor ticks (colormap-recommendations.md "fixed
# breakpoint block"). None = quantiles of the clip's own histogram.
AGRO_TICKS: dict[str, list[float] | None] = {
    "clay":    [20.0, 27.0, 40.0],            # USDA texture limits on the clay axis
    "silt":    None,
    "sand":    None,
    "phh2o":   [4.5, 5.5, 6.5, 7.5],          # agronomic pH classes; center 7.0
    "phcac2":  [4.5, 5.5, 6.5, 7.5],
    "soc":     [5.0, 20.0, 50.0],             # gC/kg SOC tiers
    "cec":     [5.0, 10.0, 20.0, 30.0],       # cmol(c)/kg fertility classes
    "bdod":    [1.0, 1.2, 1.4, 1.6],          # Mg/m3 compaction thresholds
    "awch1k":  [0.08, 0.12, 0.16, 0.20],      # mm/mm plant-available water
    "awc":     [0.08, 0.12, 0.16, 0.20],
}
PH_CENTER = 7.0
_SLOPE_TICKS = [2.0, 5.0, 10.0, 18.0]         # % conservation classes
_NDVI_BANDS = [0.2, 0.4, 0.6, 0.8]            # NASA EO phenology bands

_OKABE_ITO = ["#E69F00", "#56B4E9", "#009E73", "#F0E442", "#0072B2",
              "#D55E0E", "#CC79A7", "#333333"]

_ISRIC_CACHE: dict[str, tuple[LinearSegmentedColormap, float, float]] = {}

# layer key -> (vendored ISRIC legend file stem, legend-units multiplier to
# reach true units). pH and bulk density legends are published x10.
_CODE2LEGEND = {
    "clay":   ("CLYPPT", 1.0), "silt": ("SLTPPT", 1.0), "sand": ("SNDPPT", 1.0),
    "phh2o":  ("PHIHOX", 0.1), "phhcl": ("PHIHOX", 0.1), "phcac2": ("PHIHOX", 0.1),
    "soc":    ("ORCDRC", 1.0), "carbon": ("ORCDRC", 0.1),
    "cec":    ("CECSOL", 1.0), "bdod": ("BLDFINE", 0.001),
    "bulkdensity": ("BLDFINE", 0.001),
}


def _finite(values) -> np.ndarray:
    v = np.ma.filled(np.ma.asarray(values, dtype=float), np.nan)
    return v[np.isfinite(v)]


def isric_cmap(code: str):
    """Continuous colormap interpolated through published ISRIC legend stops
    (piecewise-linear in RGB over class midpoints) + the legend's own span
    expressed in TRUE units (some ISRIC legends are in x10 units)."""
    stem, scale = _CODE2LEGEND.get(code.lower(), (code.upper(), 1.0))
    if code in _ISRIC_CACHE:
        return _ISRIC_CACHE[code]
    path = _DATA / f"{stem}.txt"
    if not path.exists():
        raise FileNotFoundError(path)
    xs, cols = [], []
    with open(path, newline="") as fh:
        for row in csv.DictReader(fh, delimiter="\t"):
            c = int(row["COLOR"])
            lo, hi = float(row["MINIMUM"]), float(row["MAXIMUM"])
            xs.append((lo + hi) / 2.0 * scale)
            cols.append(((c >> 16 & 255) / 255, (c >> 8 & 255) / 255, (c & 255) / 255))
    lo, hi = xs[0], xs[-1]
    cm = LinearSegmentedColormap.from_list(
        code, list(zip([(x - lo) / (hi - lo) for x in xs], cols)))
    _ISRIC_CACHE[code] = (cm, lo, hi)
    return _ISRIC_CACHE[code]


def soil_scale(code: str, values, domain: bool = False):
    """(cmap, norm, ticks) for a continuous soil property.

    ``code`` is an ISRIC legend stem (clay, soc, phh2o, cec, bdod, awch1k...).
    pH gets a diverging scale centered on 7.0; everything else the continuous
    ISRIC ramp stretched to P2-P98 (widened to cover the agronomic ticks so
    they are always visible on the colorbar).
    """
    v = _finite(values)
    if v.size == 0:
        return matplotlib.colormaps["viridis"], Normalize(0, 1), []
    if code in ("phh2o", "phcac2"):
        if domain:
            norm = TwoSlopeNorm(vcenter=PH_CENTER, vmin=4.0, vmax=8.5)
            ticks = [t for t in (AGRO_TICKS[code] or [])
                     if norm.vmin <= t <= norm.vmax]
            return matplotlib.colormaps["RdBu_r"], norm, ticks
        spread = max(np.percentile(v, 99) - PH_CENTER,
                     PH_CENTER - np.percentile(v, 1), 0.5)
        spread *= 1.05
        norm = TwoSlopeNorm(vcenter=PH_CENTER,
                            vmin=PH_CENTER - spread, vmax=PH_CENTER + spread)
        ticks = [t for t in (AGRO_TICKS[code] or [])
                 if norm.vmin <= t <= norm.vmax]
        return matplotlib.colormaps["RdBu_r"], norm, ticks
    try:
        cm, lo_lg, hi_lg = isric_cmap(code)
    except FileNotFoundError:
        lo, hi = np.percentile(v, [2, 98])
        return matplotlib.colormaps["viridis"], Normalize(lo, max(hi, lo + 1e-9)), []
    if domain:
        lo, hi = lo_lg, hi_lg
    else:
        lo, hi = np.percentile(v, [2, 98])
        if hi <= lo:
            lo, hi = float(v.min()), float(v.max()) + 1e-9
    ticks = [t for t in (AGRO_TICKS.get(code) or []) if lo_lg <= t <= hi_lg
             and lo * 0.9 <= t <= max(hi, lo * 1.02) * 1.1]
    # widen the window to include the agronomic anchors (clipped to the
    # legend span so colors stay in-family); cap window at the full legend
    lo = min(lo, max(min(ticks), lo_lg)) if ticks else lo
    hi = max(hi, min(max(ticks), hi_lg)) if ticks else hi
    return cm, Normalize(lo, max(hi, lo * 1.02)), ticks


def dem_scale(elev_values):
    """(cmap, norm, relief_m, label) for an elevation clip.

    Relief-adaptive per the adopted standard: ``terrain`` hypsometrics only
    make sense when there is orographic range to spend them on.
    """
    v = _finite(elev_values)
    if v.size == 0:
        return matplotlib.colormaps["cividis"], Normalize(0, 1), 0.0, "low"
    relief = float(np.percentile(v, 99) - np.percentile(v, 1))
    lo, hi = np.percentile(v, [2, 98])
    if hi <= lo:
        hi = lo + 1e-6
    if relief > 50:
        cm, klass = matplotlib.colormaps["terrain"], "high-relief"
    else:
        cm, klass = matplotlib.colormaps["cividis"], (
            "low-relief" if relief < 10 else "medium-relief")
    return cm, Normalize(lo, hi), relief, klass


def slope_scale(slope_pct):
    v = _finite(slope_pct)
    lo, hi = np.percentile(v, [2, 98]) if v.size else (0, 10)
    ticks = [t for t in _SLOPE_TICKS if lo <= t <= hi]
    return matplotlib.colormaps["YlOrBr"], Normalize(lo, max(hi, lo + 1e-9)), ticks


def twi_scale(twi):
    """TWI is resolution-dependent -> field-relative quantile ticks."""
    v = _finite(twi)
    if v.size < 8:
        return matplotlib.colormaps["YlGnBu"], Normalize(0, 1), []
    lo, hi = np.percentile(v, [2, 98])
    ticks = list(np.percentile(v, [25, 50, 80]))
    return matplotlib.colormaps["YlGnBu"], Normalize(lo, hi), ticks


def ndvi_scale(ndvi):
    """Fixed NASA EO phenology bands; luminance rises toward green so the
    red-green trap of RdYlGn is mitigated (yellow mid-band is a luminance
    peak). Pair with the cividis alternative flag in dense-legend figures."""
    v = _finite(ndvi)
    lo, hi = np.percentile(v, [2, 98]) if v.size else (0.0, 0.9)
    lo, hi = min(lo, 0.05), max(hi, 0.85)
    return matplotlib.colormaps["RdYlGn"], Normalize(lo, hi), list(_NDVI_BANDS)


def categorical(n: int):
    """Colour-blind-safe qualitative colors (Okabe-Ito); past 8 classes the
    caller should aggregate rare classes to 'Miscellaneous' (NRCS
    generalization practice) or switch to a Tol/ColorBrewer 12-16 set."""
    if n <= len(_OKABE_ITO):
        return _OKABE_ITO[:max(n, 1)]
    base = matplotlib.colormaps["tab20"].resampled(20)
    return [matplotlib.colors.to_hex(base(i)) for i in range(n)]
