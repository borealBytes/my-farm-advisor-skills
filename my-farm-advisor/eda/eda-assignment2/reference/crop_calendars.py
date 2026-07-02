"""Estimated planting and harvest windows by state and crop.

Sourced from USDA NASS Typical Crop Progress dates (Midwest region).
Values represent typical start-of-planting and end-of-harvest windows.
Used as estimates when observed field-level dates are unavailable.

Return format per entry:
    (plant_month, plant_day, harvest_month, harvest_day)
"""

from __future__ import annotations

# Key: (state_fips, crop_name_lower)
# Value: (plant_mm, plant_dd, harvest_mm, harvest_dd)
#
# Sources:
#   - USDA NASS Crop Progress & Condition (IL, IA, NE)
#   - University of Illinois Extension planting date recommendations
#   - Iowa State University Extension corn/soybean planting guides
#   - University of Nebraska-Lincoln CropWatch

CROP_CALENDARS: dict[tuple[str, str], tuple[int, int, int, int]] = {
    # Illinois — Corn: mid-Apr to late-Oct
    ("17", "corn"): (4, 15, 10, 25),
    # Illinois — Soybeans: early-May to late-Oct
    ("17", "soybeans"): (5, 1, 10, 20),
    # Iowa — Corn: late-Apr to late-Oct
    ("19", "corn"): (4, 20, 10, 25),
    # Iowa — Soybeans: early-May to late-Oct
    ("19", "soybeans"): (5, 1, 10, 20),
    # Nebraska — Corn: late-Apr to late-Oct
    ("31", "corn"): (4, 20, 10, 20),
    # Nebraska — Soybeans: early-May to late-Oct
    ("31", "soybeans"): (5, 5, 10, 15),
}

# Fallback for any unrecognised (state, crop) combination
DEFAULT_CALENDAR: tuple[int, int, int, int] = (5, 1, 10, 15)


def lookup(state_fips: str, crop: str) -> tuple[int, int, int, int]:
    """Return (plant_mm, plant_dd, harvest_mm, harvest_dd) for a state and crop.

    Args:
        state_fips: Two-digit state FIPS code as string, e.g. "17".
        crop: Lowercase crop name from CDL, e.g. "corn" or "soybeans".

    Returns:
        Tuple of (plant_month, plant_day, harvest_month, harvest_day).
    """
    crop_lower = crop.strip().lower()
    key = (state_fips.zfill(2), crop_lower)
    return CROP_CALENDARS.get(key, DEFAULT_CALENDAR)
