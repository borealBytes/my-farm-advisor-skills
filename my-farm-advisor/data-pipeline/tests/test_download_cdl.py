from __future__ import annotations

import importlib.util
import io
import os
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch


SKILL_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = (
    SKILL_ROOT / "data-pipeline" / "src" / "scripts" / "ingest" / "download_cdl.py"
)


class FakeResponse:
    def __init__(self, payload: bytes) -> None:
        self.payload = payload

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False

    def raise_for_status(self) -> None:
        return None

    def iter_content(self, chunk_size: int):
        for idx in range(0, len(self.payload), chunk_size):
            yield self.payload[idx : idx + chunk_size]


def _zip_payload(member_name: str, payload: bytes) -> bytes:
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        archive.writestr(member_name, payload)
    return stream.getvalue()


def _load_download_cdl(runtime_root: Path):
    os.environ["DATA_PIPELINE_DATA_ROOT"] = str(runtime_root)
    os.environ["MY_FARM_ADVISOR_SKILL_ROOT"] = str(SKILL_ROOT)
    for name in (
        "download_cdl_under_test",
        "paths",
        "reporting_bootstrap",
        "runtime_paths",
        "lib.runtime_paths",
        "cdl_reporting",
    ):
        sys.modules.pop(name, None)
    spec = importlib.util.spec_from_file_location("download_cdl_under_test", SCRIPT_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load {SCRIPT_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules["download_cdl_under_test"] = module
    spec.loader.exec_module(module)
    return module


class DownloadCdlTests(unittest.TestCase):
    def test_state_scope_keeps_byfips_download_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            module = _load_download_cdl(Path(tmp))
            requested_urls: list[str] = []

            def fake_get(url: str, *args, **kwargs) -> FakeResponse:
                requested_urls.append(url)
                return FakeResponse(b"state-cdl")

            with patch.object(module.requests, "get", side_effect=fake_get):
                paths = module.prepare_shared_cdl_rasters(
                    scope="state",
                    years=[2025],
                    state_fips_values=["19"],
                    force=True,
                )

            self.assertEqual(
                requested_urls,
                ["https://nassgeodata.gmu.edu/nass_data_cache/byfips/CDL_2025_19.tif"],
            )
            self.assertEqual(len(paths), 1)
            self.assertEqual(paths[0].name, "CDL_2025_19.tif")
            self.assertEqual(paths[0].read_bytes(), b"state-cdl")

    def test_conus_scope_downloads_national_zip_and_extracts_tif(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            module = _load_download_cdl(Path(tmp))
            requested_urls: list[str] = []
            payload = _zip_payload("2025_30m_cdls.tif", b"conus-cdl")

            def fake_get(url: str, *args, **kwargs) -> FakeResponse:
                requested_urls.append(url)
                return FakeResponse(payload)

            with patch.object(module.requests, "get", side_effect=fake_get):
                paths = module.prepare_shared_cdl_rasters(
                    scope="conus",
                    years=[2025],
                    force=True,
                )

            self.assertEqual(
                requested_urls,
                [
                    "https://www.nass.usda.gov/Research_and_Science/Cropland/Release/"
                    "datasets/2025_30m_cdls.zip"
                ],
            )
            self.assertEqual(len(paths), 1)
            self.assertEqual(paths[0].name, "CDL_2025_CONUS.tif")
            self.assertEqual(paths[0].read_bytes(), b"conus-cdl")

    @unittest.skipUnless(
        os.environ.get("RUN_LIVE_CDL_DOWNLOAD") == "1",
        "set RUN_LIVE_CDL_DOWNLOAD=1 to download and validate the 2025 CONUS CDL",
    )
    def test_live_2025_conus_download_opens_with_rasterio(self) -> None:
        import rasterio

        with tempfile.TemporaryDirectory() as tmp:
            module = _load_download_cdl(Path(tmp))
            paths = module.prepare_shared_cdl_rasters(
                scope="conus",
                years=[2025],
                force=True,
            )
            self.assertEqual(len(paths), 1)
            path = paths[0]
            self.assertEqual(path.name, "CDL_2025_CONUS.tif")
            self.assertGreater(path.stat().st_size, 1_000_000_000)
            with rasterio.open(path) as dataset:
                self.assertGreater(dataset.width, 100_000)
                self.assertGreater(dataset.height, 50_000)
                self.assertGreaterEqual(dataset.count, 1)
                self.assertIsNotNone(dataset.crs)


if __name__ == "__main__":
    unittest.main()
