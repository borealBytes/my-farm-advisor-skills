"""Tests for the weather dashboard generator."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

# Add scripts to path so imports work
_SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_SCRIPTS))
sys.path.insert(0, str(_SCRIPTS / "lib"))

from reporting.generate_weather_dashboard import (  # noqa: E402
    _color_for_index,
    _compute_weather_transforms,
    _group_by_year,
    _mercator_polygon,
    _mercator_x,
    _mercator_y,
    _read_weather_csv,
    _safe_float,
    _slugify,
    acquire_basemap,
    build_dashboard_html,
    read_farm_data,
    resolve_farm_dir,
)


def _make_weather_row(field_id: str, dt: str, t_min: float, t_max: float, precip: float) -> dict:
    return {
        "field_id": field_id,
        "date": dt,
        "T2M_MIN": str(t_min),
        "T2M_MAX": str(t_max),
        "PRECTOTCORR": str(precip),
    }


def _write_weather_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("field_id,date,T2M_MIN,T2M_MAX,PRECTOTCORR\n", encoding="utf-8")
        return
    headers = list(rows[0].keys())
    lines = [",".join(headers)]
    for r in rows:
        lines.append(",".join(str(r.get(h, "")) for h in headers))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _build_minimal_farm(temp_dir: Path, farm_slug: str = "test-farm") -> Path:
    """Create a minimal valid farm directory for testing."""
    farm_dir = temp_dir / "growers" / "test-grower" / "farms" / farm_slug
    boundary = farm_dir / "boundary"
    fields_root = farm_dir / "fields"
    boundary.mkdir(parents=True)
    fields_root.mkdir(parents=True)

    # farm.json
    (farm_dir / "farm.json").write_text(
        json.dumps({
            "grower_slug": "test-grower",
            "farm_slug": farm_slug,
            "display_name": "Test Farm",
        }),
        encoding="utf-8",
    )

    # field_boundaries.geojson with 2 fields
    geojson = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {"field_id": "field-001", "area_acres": 42.5},
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[
                        [-94.26, 43.31], [-94.26, 43.32],
                        [-94.25, 43.32], [-94.25, 43.31],
                        [-94.26, 43.31],
                    ]],
                },
            },
            {
                "type": "Feature",
                "properties": {"field_id": "field-002", "area_acres": 38.2},
                "geometry": {
                    "type": "MultiPolygon",
                    "coordinates": [[[
                        [-94.27, 43.30], [-94.27, 43.31],
                        [-94.26, 43.31], [-94.26, 43.30],
                        [-94.27, 43.30],
                    ]], [[
                        [-94.28, 43.30], [-94.28, 43.305],
                        [-94.275, 43.305], [-94.275, 43.30],
                        [-94.28, 43.30],
                    ]]],
                },
            },
        ],
    }
    (boundary / "field_boundaries.geojson").write_text(
        json.dumps(geojson), encoding="utf-8"
    )

    return farm_dir


def _setup_dummy_plotly_cache() -> str:
    """Create a dummy Plotly JS bundle for testing."""
    from reporting.generate_weather_dashboard import _plotly_cache_dir
    cache_dir = _plotly_cache_dir()
    cache_dir.mkdir(parents=True, exist_ok=True)
    dummy_js = "/* dummy plotly */"
    (cache_dir / "plotly-2.35.2.min.js").write_text(dummy_js, encoding="utf-8")
    return dummy_js


class TestSlugify(unittest.TestCase):
    def test_basic(self):
        self.assertEqual(_slugify("Hello World"), "hello-world")

    def test_special_chars(self):
        self.assertEqual(_slugify("Field #1!"), "field-1")


class TestColorForIndex(unittest.TestCase):
    def test_first_color(self):
        self.assertEqual(_color_for_index(0), "#1f77b4")

    def test_cycle(self):
        self.assertEqual(_color_for_index(10), "#1f77b4")
        self.assertEqual(_color_for_index(11), "#ff7f0e")


class TestMercatorHelpers(unittest.TestCase):
    def test_mercator_x_zero(self):
        self.assertAlmostEqual(_mercator_x(0), 0.0)

    def test_mercator_x_positive(self):
        self.assertGreater(_mercator_x(90), 0)

    def test_mercator_y_zero(self):
        self.assertAlmostEqual(_mercator_y(0), 0.0, delta=1)

    def test_mercator_polygon(self):
        geom = {
            "type": "Polygon",
            "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 0]]],
        }
        rings = _mercator_polygon(geom)
        self.assertEqual(len(rings), 1)
        self.assertEqual(len(rings[0]), 4)

    def test_mercator_multipolygon(self):
        geom = {
            "type": "MultiPolygon",
            "coordinates": [[[[0, 0], [1, 0], [1, 1], [0, 0]]]],
        }
        rings = _mercator_polygon(geom)
        self.assertEqual(len(rings), 1)


class TestSafeFloat(unittest.TestCase):
    def test_none(self):
        self.assertIsNone(_safe_float(None))

    def test_valid(self):
        self.assertEqual(_safe_float("3.14"), 3.14)

    def test_empty(self):
        self.assertIsNone(_safe_float(""))


class TestReadWeatherCSV(unittest.TestCase):
    def test_empty_file(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "weather.csv"
            path.write_text("field_id,date,T2M_MIN,T2M_MAX,PRECTOTCORR\n", encoding="utf-8")
            rows = _read_weather_csv(path, "field-001")
            self.assertEqual(len(rows), 0)

    def test_header_only(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "weather.csv"
            path.write_text("field_id,date,T2M_MIN,T2M_MAX,PRECTOTCORR\n", encoding="utf-8")
            result = _read_weather_csv(path, "field-001")
            self.assertEqual(result, [])


class TestGroupByYear(unittest.TestCase):
    def test_grouping(self):
        rows = [
            _make_weather_row("f1", "2025-04-19", -1.0, 10.0, 0.0),
            _make_weather_row("f1", "2025-06-01", 10.0, 25.0, 2.0),
            _make_weather_row("f1", "2024-05-01", 5.0, 20.0, 1.0),
        ]
        groups = _group_by_year(rows)
        self.assertEqual(set(groups.keys()), {2025, 2024})
        self.assertEqual(len(groups[2025]), 2)
        self.assertEqual(len(groups[2024]), 1)


class TestComputeWeatherTransforms(unittest.TestCase):
    def test_last_frost_before_july(self):
        rows = [
            _make_weather_row("f1", "2025-01-15", -5.0, -1.0, 0.0),
            _make_weather_row("f1", "2025-03-20", -2.0, 5.0, 1.0),
            _make_weather_row("f1", "2025-04-19", -1.0, 8.0, 0.5),
            _make_weather_row("f1", "2025-05-10", 8.0, 20.0, 2.0),
            _make_weather_row("f1", "2025-06-15", 15.0, 28.0, 3.0),
        ]
        result = _compute_weather_transforms(rows, 2025, "f1")
        self.assertIsNotNone(result)
        self.assertEqual(result["fieldId"], "f1")
        self.assertEqual(result["year"], 2025)
        # Last frost should be April 19 (latest <= 0 before July 1)
        self.assertEqual(result["lastFrostDate"], "2025-04-19")
        self.assertEqual(result["lastFrostDoy"], 109)
        # First daily record should start at last frost
        self.assertEqual(result["daily"][0]["date"], "2025-04-19")
        # Cumulative should increase
        self.assertGreater(result["daily"][-1]["cumulativeGdd"], 0)
        self.assertGreater(result["daily"][-1]["cumulativeRainfallIn"], 0)

    def test_no_frost_default_jan1(self):
        rows = [
            _make_weather_row("f1", "2025-01-01", 5.0, 10.0, 0.0),
            _make_weather_row("f1", "2025-06-15", 15.0, 28.0, 1.0),
        ]
        result = _compute_weather_transforms(rows, 2025, "f1")
        self.assertIsNotNone(result)
        self.assertEqual(result["lastFrostDate"], "2025-01-01")
        self.assertEqual(result["lastFrostDoy"], 1)

    def test_gdd_calculation(self):
        rows = [
            _make_weather_row("f1", "2025-04-19", -1.0, 8.0, 0.0),
            _make_weather_row("f1", "2025-05-01", 10.0, 25.0, 2.0),
        ]
        result = _compute_weather_transforms(rows, 2025, "f1")
        self.assertIsNotNone(result)
        # Day 1: GDD = max((8 + -1)/2 - 10, 0) = max(-6.5, 0) = 0
        self.assertEqual(result["daily"][0]["dailyGdd"], 0.0)
        # Day 2: GDD = max((25 + 10)/2 - 10, 0) = max(7.5, 0) = 7.5
        self.assertAlmostEqual(result["daily"][1]["dailyGdd"], 7.5, places=4)
        # Cumulative should be 0 + 7.5
        self.assertAlmostEqual(result["daily"][1]["cumulativeGdd"], 7.5, places=4)

    def test_rainfall_conversion(self):
        rows = [
            _make_weather_row("f1", "2025-05-01", 10.0, 20.0, 25.4),
        ]
        result = _compute_weather_transforms(rows, 2025, "f1")
        self.assertIsNotNone(result)
        # 25.4 mm * 0.0393701 = 1.0 inch
        self.assertAlmostEqual(result["daily"][0]["dailyRainfallIn"], 1.0, places=2)
        self.assertAlmostEqual(result["daily"][0]["cumulativeRainfallIn"], 1.0, places=2)

    def test_leap_year(self):
        rows = [
            _make_weather_row("f1", "2024-02-29", -2.0, 3.0, 0.0),
            _make_weather_row("f1", "2024-03-01", 1.0, 8.0, 0.5),
        ]
        result = _compute_weather_transforms(rows, 2024, "f1")
        self.assertIsNotNone(result)
        self.assertEqual(result["daily"][0]["date"], "2024-02-29")

    def test_empty_rows(self):
        result = _compute_weather_transforms([], 2025, "f1")
        self.assertIsNone(result)

    def test_missing_temps(self):
        rows = [{
            "field_id": "f1",
            "date": "2025-05-01",
            "T2M_MIN": "",
            "T2M_MAX": "",
            "PRECTOTCORR": "1.0",
        }]
        result = _compute_weather_transforms(rows, 2025, "f1")
        self.assertIsNotNone(result)
        # No valid temps -> GDD is 0
        self.assertEqual(result["daily"][0]["dailyGdd"], 0.0)
        # Precip still works
        self.assertGreater(result["daily"][0]["dailyRainfallIn"], 0)


class TestReadFarmData(unittest.TestCase):
    def test_basic_fields(self):
        with tempfile.TemporaryDirectory() as td:
            farm_dir = _build_minimal_farm(Path(td))
            meta, fields, weather = read_farm_data(farm_dir)
            self.assertEqual(meta["farmId"], "test-farm")
            self.assertEqual(len(fields), 2)
            # Ordered by inventory if available
            fids = [f["fieldId"] for f in fields]
            self.assertIn("field-001", fids)
            self.assertIn("field-002", fids)
            # Check MultiPolygon support
            f2 = next(f for f in fields if f["fieldId"] == "field-002")
            self.assertGreater(len(f2["mercatorPolygons"]), 0)

    def test_missing_field_json(self):
        with tempfile.TemporaryDirectory() as td:
            farm_dir = _build_minimal_farm(Path(td))
            # Remove field.json for field-001
            fjson = farm_dir / "fields" / "field-001" / "field.json"
            if fjson.exists():
                fjson.unlink()
            meta, fields, weather = read_farm_data(farm_dir)
            f1 = next(f for f in fields if f["fieldId"] == "field-001")
            self.assertEqual(f1["fieldName"], "field-001")

    def test_header_only_weather(self):
        with tempfile.TemporaryDirectory() as td:
            farm_dir = _build_minimal_farm(Path(td))
            # Add header-only weather CSV
            wcsv = farm_dir / "fields" / "field-001" / "weather" / "daily_weather.csv"
            wcsv.parent.mkdir(parents=True, exist_ok=True)
            wcsv.write_text("field_id,date,T2M_MIN,T2M_MAX,PRECTOTCORR\n", encoding="utf-8")
            meta, fields, weather = read_farm_data(farm_dir)
            f1 = next(f for f in fields if f["fieldId"] == "field-001")
            self.assertFalse(f1["hasWeatherData"])

    def test_with_weather_data(self):
        with tempfile.TemporaryDirectory() as td:
            farm_dir = _build_minimal_farm(Path(td))
            wrows = [
                _make_weather_row("field-001", "2025-04-19", -1.0, 8.0, 0.0),
                _make_weather_row("field-001", "2025-05-10", 10.0, 25.0, 2.0),
            ]
            _write_weather_csv(
                farm_dir / "fields" / "field-001" / "weather" / "daily_weather.csv",
                wrows,
            )
            meta, fields, weather = read_farm_data(farm_dir)
            f1 = next(f for f in fields if f["fieldId"] == "field-001")
            self.assertTrue(f1["hasWeatherData"])
            self.assertIn(2025, f1["availableYears"])
            self.assertGreater(len(weather), 0)
            wr = next(w for w in weather if w["fieldId"] == "field-001" and w["year"] == 2025)
            self.assertIsNotNone(wr)
            self.assertGreater(len(wr["daily"]), 0)


class TestResolveFarmDir(unittest.TestCase):
    def test_explicit_path(self):
        with tempfile.TemporaryDirectory() as td:
            farm_dir = _build_minimal_farm(Path(td))
            resolved = resolve_farm_dir(farm_dir=str(farm_dir))
            self.assertEqual(resolved, farm_dir)

    def test_invalid_path(self):
        with self.assertRaises(RuntimeError):
            resolve_farm_dir(farm_dir="/nonexistent/path")

    def test_ambiguous_discovery(self):
        """Discovery with multiple farms should fail."""
        with tempfile.TemporaryDirectory() as td:
            _build_minimal_farm(Path(td), farm_slug="farm-1")
            _build_minimal_farm(Path(td), farm_slug="farm-2")
            with self.assertRaises(RuntimeError) as ctx:
                resolve_farm_dir(growers_dir=str(Path(td)))
            self.assertIn("Multiple", str(ctx.exception))

    def test_single_discovery(self):
        with tempfile.TemporaryDirectory() as td:
            _build_minimal_farm(Path(td))
            resolved = resolve_farm_dir(growers_dir=str(Path(td)))
            self.assertTrue(resolved.exists())


class TestBuildDashboardHTML(unittest.TestCase):
    def test_output_is_single_html(self):
        html = build_dashboard_html(
            {"farmId": "test", "farmName": "Test"},
            [{"fieldId": "f1", "fieldSlug": "f1", "fieldName": "Field 1",
              "acres": 42.5, "color": "#1f77b4",
              "mercatorPolygons": [[[0, 0], [1, 0], [1, 1], [0, 0]]],
              "hasWeatherData": False, "availableYears": []}],
            [],
            "/* dummy plotly */",
            None,
            None,
        )
        self.assertIn("<!doctype html", html)
        self.assertIn("Grower Field Weather Dashboard", html)
        # No CDN URLs at runtime
        self.assertNotIn("cdn.plot.ly", html)
        self.assertNotIn("cdnjs.cloudflare.com", html)
        self.assertNotIn("fonts.googleapis.com", html)
        # Embedded Plotly
        self.assertIn("dummy plotly", html)
        # Embedded data
        self.assertIn("fieldId", html)
        self.assertIn("Field 1", html)
        # basemapAvailable flag reflects no basemap
        self.assertIn('"basemapAvailable": false', html)

    def test_no_external_refs(self):
        html = build_dashboard_html(
            {"farmId": "test", "farmName": "Test"},
            [],
            [],
            "/* plotly */",
            None,
            None,
        )
        # Check for external resource references in src/href attributes
        import re
        external_refs = re.findall(r'(?:src|href)=["\']https?://[^"\']+["\']', html)
        for ref in external_refs:
            print(f"Found external ref: {ref}")
        self.assertEqual(len(external_refs), 0, f"Found external references: {external_refs}")


class TestAcquireBasemap(unittest.TestCase):
    def test_no_basemap_flag(self):
        b64, bounds = acquire_basemap([], no_basemap=True)
        self.assertIsNone(b64)
        self.assertIsNone(bounds)

    def test_no_fields(self):
        b64, bounds = acquire_basemap([], no_basemap=False)
        self.assertIsNone(b64)
        self.assertIsNone(bounds)


class TestMercatorPolygonEdgeCases(unittest.TestCase):
    def test_non_polygon_geometry(self):
        geom = {"type": "Point", "coordinates": [0, 0]}
        rings = _mercator_polygon(geom)
        self.assertEqual(rings, [])

    def test_empty_geometry(self):
        rings = _mercator_polygon({})
        self.assertEqual(rings, [])


class TestFarmAggregateFallback(unittest.TestCase):
    def test_aggregate_weather_fallback(self):
        """When per-field weather is empty, try farm-level aggregate."""
        with tempfile.TemporaryDirectory() as td:
            farm_dir = _build_minimal_farm(Path(td))
            # No per-field weather, but add aggregate
            tables = farm_dir / "derived" / "tables"
            tables.mkdir(parents=True, exist_ok=True)
            agg = tables / "test_weather_2021_2025.csv"
            agg.write_text(
                "field_id,date,T2M_MIN,T2M_MAX,PRECTOTCORR\n"
                "field-001,2025-04-19,-1.0,8.0,0.0\n"
                "field-001,2025-05-10,10.0,25.0,2.0\n",
                encoding="utf-8",
            )
            meta, fields, weather = read_farm_data(farm_dir)
            f1 = next(f for f in fields if f["fieldId"] == "field-001")
            self.assertTrue(f1["hasWeatherData"])
            self.assertGreater(len(weather), 0)


if __name__ == "__main__":
    unittest.main()
