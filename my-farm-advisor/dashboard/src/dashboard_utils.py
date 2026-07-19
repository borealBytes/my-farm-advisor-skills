import os
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import geopandas as gpd

DATA_PIPELINE_VENV = os.environ.get(
    "DATA_PIPELINE_VENV_DIR",
    str(Path(os.environ.get("DATA_PIPELINE_DATA_ROOT", "")) / "data-pipeline" / ".venv"),
)
_RUNTIME_SRC = Path(os.environ.get("DATA_PIPELINE_DATA_ROOT", "")) / "data-pipeline" / "src"
if str(_RUNTIME_SRC / "scripts" / "lib") not in sys.path and _RUNTIME_SRC.exists():
    sys.path.insert(0, str(_RUNTIME_SRC / "scripts" / "lib"))
try:
    from lib.paths import (
        GROWERS_ROOT,
        farm_dir,
        farm_derived_dir,
        farm_tables_dir,
        farm_boundary_path,
        farm_dashboards_dir,
        farm_manifest_dir,
        field_dir,
        field_boundary_dir,
        field_derived_dir,
        field_features_dir,
        field_tables_dir,
    )
    _HAVE_PATHS = True
except Exception:
    _HAVE_PATHS = False


class DashboardData:
    def __init__(self, data_root, grower_slug="iowa-grower", farm_slug="iowa-farm"):
        self.data_root = Path(data_root) / "data-pipeline"
        self.grower_slug = grower_slug
        self.farm_slug = farm_slug
        self.growers_root = self.data_root / "growers"
        self._resolve_farm_path()
        self._load_all()

    def _resolve_farm_path(self):
        base = self.growers_root / self.grower_slug
        direct = base / "farms" / self.farm_slug
        nested = base / self.grower_slug / "farms" / self.farm_slug
        if direct.exists():
            self.farm_path = direct
            self.nested = False
        else:
            self.farm_path = nested
            self.nested = True
        self.fields_root = self.farm_path / "fields"
        self.farm_tables = self.farm_path / "derived" / "tables"
        self.farm_dashboards = self.farm_path / "derived" / "dashboards"
        self.farm_boundary_dir = self.farm_path / "boundary"

    def _load_all(self):
        self.field_ids = self._load_field_inventory()
        self.field_geojson = self._load_field_boundaries()
        self.soil = self._load_soil_summary()
        self.weather = self._load_weather()
        self.cdl_composition = self._load_cdl_composition()
        self.crop_rotation = self._load_crop_rotation()
        self.ndvi = self._load_ndvi()
        self._compute_metrics()

    def _load_field_inventory(self):
        inv_path = self.farm_path / "manifests" / "field-inventory.csv"
        if inv_path.exists():
            inv = pd.read_csv(inv_path)
            return inv["field_id"].tolist()
        alt = self.farm_tables.parent.parent / "manifests" / "field-inventory.csv"
        if alt.exists():
            inv = pd.read_csv(alt)
            return inv["field_id"].tolist()
        dir_fields = []
        if self.fields_root.exists():
            dir_fields = sorted(d.name for d in self.fields_root.iterdir() if d.is_dir())
        return dir_fields

    def _field_path(self, field_id):
        p = self.fields_root / field_id
        if p.exists():
            return p
        alt = self.farm_path.parent / self.grower_slug / "farms" / self.farm_slug / "fields" / field_id
        if alt.exists():
            return alt
        return p

    def _load_field_boundaries(self):
        bdy_path = self.farm_boundary_dir / "field_boundaries.geojson"
        for path in [bdy_path]:
            if path.exists():
                gdf = gpd.read_file(path)
                if "area_acres" not in gdf.columns:
                    gdf = gdf.to_crs("EPSG:5070")
                    gdf["area_acres"] = gdf.geometry.area * 0.000247105
                    gdf = gdf.to_crs("EPSG:4326")
                return gdf
        if self.fields_root.exists():
            boundaries = []
            for fid in self.field_ids:
                bpath = self._field_path(fid) / "boundary" / "field_boundary.geojson"
                if bpath.exists():
                    g = gpd.read_file(bpath)
                    boundaries.append(g)
            if boundaries:
                return pd.concat(boundaries, ignore_index=True)
        return gpd.GeoDataFrame()

    def _load_soil_summary(self):
        patterns = [
            self.farm_tables / f"{self.farm_slug.replace('-farm', '')}_ssurgo_summary.csv",
            self.farm_tables / f"{self.farm_slug.split('-')[0]}_ssurgo_summary.csv",
        ]
        for p in patterns:
            if p.exists():
                df = pd.read_csv(p)
                df.columns = [c.strip().lower() for c in df.columns]
                return df
        for f in self.farm_tables.glob("*ssurgo_summary*.csv"):
            df = pd.read_csv(f)
            df.columns = [c.strip().lower() for c in df.columns]
            return df
        return pd.DataFrame()

    def _load_weather(self):
        patterns = [
            self.farm_tables / f"{self.farm_slug.replace('-farm', '')}_weather_2021_2025.csv",
            self.farm_tables / f"{self.farm_slug.split('-')[0]}_weather_2021_2025.csv",
        ]
        for p in patterns:
            if p.exists():
                df = pd.read_csv(p, parse_dates=["date"])
                df.columns = [c.strip().lower() for c in df.columns]
                return df
        for f in self.farm_tables.glob("*weather*.csv"):
            df = pd.read_csv(f, parse_dates=["date"])
            df.columns = [c.strip().lower() for c in df.columns]
            return df
        return pd.DataFrame()

    def _load_cdl_composition(self):
        patterns = [
            self.farm_tables / f"{self.farm_slug.replace('-farm', '')}_cdl_2021_2025_full_composition.csv",
            self.farm_tables / f"{self.farm_slug.split('-')[0]}_cdl_2021_2025_full_composition.csv",
        ]
        for p in patterns:
            if p.exists():
                return pd.read_csv(p)
        for f in self.farm_tables.glob("*cdl*composition*.csv"):
            return pd.read_csv(f)
        return pd.DataFrame()

    def _load_crop_rotation(self):
        patterns = [
            self.farm_tables / f"{self.farm_slug.replace('-farm', '')}_crop_rotation.csv",
            self.farm_tables / f"{self.farm_slug.split('-')[0]}_crop_rotation.csv",
        ]
        for p in patterns:
            if p.exists():
                return pd.read_csv(p)
        for f in self.farm_tables.glob("*crop_rotation*.csv"):
            return pd.read_csv(f)
        return pd.DataFrame()

    def _load_ndvi(self):
        records = []
        for fid in self.field_ids:
            ndvi_csv = self._field_path(fid) / "derived" / "tables" / "ndvi_year_crop_join.csv"
            if ndvi_csv.exists():
                df = pd.read_csv(ndvi_csv)
                records.append(df)
        if records:
            return pd.concat(records, ignore_index=True)
        return pd.DataFrame()

    def _compute_ndvi_from_tiff(self, tiff_rel_path):
        try:
            import rasterio
            full_path = self.data_root / tiff_rel_path
            if not full_path.exists():
                return None
            with rasterio.open(str(full_path)) as src:
                band = src.read(1)
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    if src.nodata is not None and not np.isnan(src.nodata):
                        band = band.astype(np.float32)
                        band[band == src.nodata] = np.nan
                    mean_val = float(np.nanmean(band))
                if np.isnan(mean_val) or mean_val <= 0:
                    return None
                return round(mean_val, 4)
        except Exception:
            return None

    def _compute_metrics(self):
        field_metrics = []
        for fid in self.field_ids:
            m = {"field_id": fid}
            ndvi_vals = []
            field_ndvi = self.ndvi[self.ndvi["field_id"] == fid] if not self.ndvi.empty else pd.DataFrame()
            if not field_ndvi.empty:
                for _, row in field_ndvi.iterrows():
                    val = self._compute_ndvi_from_tiff(row.get("composite_tif", ""))
                    if val is not None:
                        ndvi_vals.append(val)
            m["avg_ndvi"] = round(float(np.mean(ndvi_vals)), 4) if ndvi_vals else None
            m["max_ndvi"] = round(float(max(ndvi_vals)), 4) if ndvi_vals else None

            soil_row = self.soil[self.soil["field_id"] == fid] if not self.soil.empty else pd.DataFrame()
            if not soil_row.empty:
                r = soil_row.iloc[0]
                for col in ["avg_om_pct", "avg_ph", "total_aws_inches", "avg_cec",
                            "avg_clay_pct", "avg_sand_pct", "dominant_soil",
                            "drainage_class", "erosion_risk"]:
                    m[col] = r.get(col, None)

            w = self.weather[self.weather["field_id"] == fid] if not self.weather.empty else pd.DataFrame()
            if not w.empty:
                precip_col = "prectotcorr"
                if precip_col in w.columns:
                    yr_precip = w.groupby(w["date"].dt.year)[precip_col].sum()
                    m["avg_annual_rainfall_mm"] = round(float(yr_precip.mean()), 1) if len(yr_precip) > 0 else None
                else:
                    m["avg_annual_rainfall_mm"] = None
                temp_col = "t2m"
                if temp_col in w.columns:
                    m["avg_temp_c"] = round(float(w[temp_col].mean()), 1)

            rot = self.crop_rotation[self.crop_rotation["field_id"] == fid] if not self.crop_rotation.empty else pd.DataFrame()
            if not rot.empty:
                r = rot.iloc[0]
                m["crop_diversity"] = r.get("crop_diversity", 0)
                m["rotation_confidence"] = r.get("rotation_confidence", "")
                m["predicted_next_crop"] = r.get("predicted_next_crop", "")

            field_metrics.append(m)

        self.metrics = pd.DataFrame(field_metrics) if field_metrics else pd.DataFrame()

    def compute_soil_health_score(self):
        if self.metrics.empty:
            return self.metrics
        df = self.metrics.copy()
        scores = []
        for _, row in df.iterrows():
            score = 0.0
            om = row.get("avg_om_pct")
            if om is not None and om > 0:
                score += min(om / 5.0, 1.0) * 30
            ph = row.get("avg_ph")
            if ph is not None and ph > 0:
                ph_opt = 1.0 - abs(ph - 6.5) / 2.5
                score += max(0, min(ph_opt, 1.0)) * 25
            cec = row.get("avg_cec")
            if cec is not None and cec > 0:
                score += min(cec / 30.0, 1.0) * 25
            awc = row.get("total_aws_inches")
            if awc is not None and awc > 0:
                score += min(awc / 10.0, 1.0) * 20
            scores.append(round(score, 1))
        df["soil_health_score"] = scores
        return df

    def compute_sustainability_index(self):
        df = self.compute_soil_health_score()
        if df.empty:
            return df
        scores = []
        for _, row in df.iterrows():
            score = row.get("soil_health_score", 0) * 0.40
            div = row.get("crop_diversity", 0)
            if isinstance(div, (int, float)) and div > 0:
                score += min(div / 4.0, 1.0) * 30
            else:
                score += 15
            ndvi = row.get("avg_ndvi")
            if ndvi is not None and ndvi > 0:
                score += min(ndvi / 0.6, 1.0) * 30
            else:
                score += 15
            scores.append(round(score, 1))
        df["sustainability_index"] = scores
        return df

    def get_kpis(self):
        df = self.compute_sustainability_index()
        stats = {}
        stats["total_fields"] = len(self.field_ids)
        if not self.field_geojson.empty and "area_acres" in self.field_geojson.columns:
            stats["total_acreage"] = round(float(self.field_geojson["area_acres"].sum()), 1)
        else:
            stats["total_acreage"] = 0
        if not df.empty and "avg_ndvi" in df.columns:
            vals = df["avg_ndvi"].dropna()
            stats["avg_ndvi"] = round(float(vals.mean()), 3) if len(vals) > 0 else None
        else:
            stats["avg_ndvi"] = None
        if not self.weather.empty:
            precip_col = "prectotcorr"
            if precip_col in self.weather.columns:
                per_field_yr = self.weather.groupby(["field_id", self.weather["date"].dt.year])[precip_col].sum()
                per_field_avg = per_field_yr.groupby("field_id").mean()
                stats["avg_rainfall_mm"] = round(float(per_field_avg.mean()), 1) if len(per_field_avg) > 0 else None
            else:
                stats["avg_rainfall_mm"] = None
        else:
            stats["avg_rainfall_mm"] = None
        if not df.empty and "soil_health_score" in df.columns:
            vals = df["soil_health_score"].dropna()
            stats["avg_soil_health"] = round(float(vals.mean()), 1) if len(vals) > 0 else None
        else:
            stats["avg_soil_health"] = None
        if not df.empty and "sustainability_index" in df.columns:
            vals = df["sustainability_index"].dropna()
            stats["avg_sustainability"] = round(float(vals.mean()), 1) if len(vals) > 0 else None
        else:
            stats["avg_sustainability"] = None
        return stats


def main():
    data_root = os.environ.get("DATA_PIPELINE_DATA_ROOT")
    if not data_root:
        print("ERROR: Set DATA_PIPELINE_DATA_ROOT to the runtime root.")
        sys.exit(1)
    data = DashboardData(data_root, "iowa-grower", "iowa-farm")
    metrics = data.compute_sustainability_index()
    print(f"Fields: {len(data.field_ids)}")
    print(f"Soil: {list(data.soil.columns) if not data.soil.empty else 'empty'}")
    print(f"Weather: {list(data.weather.columns) if not data.weather.empty else 'empty'}")
    print(f"CDL: {list(data.cdl_composition.columns) if not data.cdl_composition.empty else 'empty'}")
    print(f"NDVI records: {len(data.ndvi)}")
    print(f"Metrics: {list(metrics.columns) if not metrics.empty else 'empty'}")
    print("KPIs:", data.get_kpis())
    if not metrics.empty:
        print(metrics[["field_id", "avg_ndvi", "soil_health_score", "sustainability_index"]].to_string())
    return data


if __name__ == "__main__":
    main()
