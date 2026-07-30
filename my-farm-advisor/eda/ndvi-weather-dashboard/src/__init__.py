from __future__ import annotations

GDD_BASE_TEMP = 10.0
GDD_CAP_TEMP = 30.0
GDD_START_DOY = 60

HEAVY_RAIN_THRESHOLD_MM = 25.0
HOT_DAY_THRESHOLD_C = 30.0
MAX_CLOUD_COVER_PCT = 70.0
NDVI_SURGE_DELTA = 0.10

CROP_STAGES: dict[str, list[dict[str, float | str]]] = {
    "Corn": [
        {"name": "VE", "gdd": 120},
        {"name": "V6", "gdd": 250},
        {"name": "V12", "gdd": 550},
        {"name": "R1 (Silk)", "gdd": 1100},
        {"name": "R3 (Dough)", "gdd": 1700},
        {"name": "R6 (Maturity)", "gdd": 2500},
    ],
    "Soybeans": [
        {"name": "VE", "gdd": 130},
        {"name": "V6", "gdd": 350},
        {"name": "R1 (Bloom)", "gdd": 750},
        {"name": "R5 (Seed)", "gdd": 1400},
        {"name": "R8 (Maturity)", "gdd": 2100},
    ],
}

WARNING_LEVELS = {"info": "#3b82f6", "warning": "#eab308", "error": "#ef4444"}
