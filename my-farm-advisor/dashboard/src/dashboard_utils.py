import json
import os
import re
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd


GDD_BASE_TEMP = 10
GDD_CAP_TEMP = 30
PLANTING_DOY = 121


class DashboardData:
    def __init__(self, data_root, grower_slug="iowa-grower", farm_slug="iowa-farm",
                 field_id=None):
        self.data_root = Path(data_root) / "data-pipeline"
        self.grower_slug = grower_slug
        self.farm_slug = farm_slug
        self.field_id = field_id
        self.growers_root = self.data_root / "growers"
        self._resolve_farm_path()
        self._load_all()

    @classmethod
    def from_json(cls, json_path):
        self = cls.__new__(cls)
        with open(json_path) as f:
            pkg = json.load(f)

        self.grower_slug = pkg["grower_slug"]
        self.farm_slug = pkg["farm_slug"]
        self.field_ids = pkg["field_ids"]
        self.field_id = pkg.get("field_id")
        self.data_root = None

        bdy = pkg.get("field_boundaries", [])
        geo_features = []
        for fb in bdy:
            geom_type = "MultiPolygon" if len(fb["coordinates"]) > 1 else "Polygon"
            if geom_type == "Polygon":
                geometry = {"type": "Polygon", "coordinates": fb["coordinates"]}
            else:
                geometry = {"type": "MultiPolygon", "coordinates": fb["coordinates"]}
            geo_features.append({
                "type": "Feature",
                "geometry": geometry,
                "properties": {
                    "field_id": fb["field_id"],
                    "area_acres": fb["area_acres"],
                },
            })
        import geopandas as gpd
        self.field_geojson = gpd.GeoDataFrame.from_features(
            geo_features, crs="EPSG:4326"
        ) if geo_features else gpd.GeoDataFrame()

        fm = pkg.get("field_metrics", [])
        self.metrics = pd.DataFrame(fm) if fm else pd.DataFrame()

        self.soil = self.metrics[["field_id", "avg_om_pct", "avg_ph", "total_aws_inches",
                                  "avg_cec", "avg_clay_pct", "avg_sand_pct",
                                  "dominant_soil", "drainage_class", "erosion_risk"]].copy() if not self.metrics.empty else pd.DataFrame()

        weather_daily = pkg.get("weather_daily", [])
        if weather_daily:
            wdf = pd.DataFrame(weather_daily)
            wdf["date"] = pd.to_datetime(wdf["date"])
            self.weather = wdf
        else:
            weather_records = pkg.get("weather_monthly", [])
            if weather_records:
                wdf = pd.DataFrame(weather_records)
                wdf["date"] = pd.to_datetime(wdf["year"].astype(str) + "-" + wdf["month"].astype(str) + "-01")
                self.weather = wdf.rename(columns={"precip": "prectotcorr", "temp": "t2m",
                                                    "tmin": "t2m_min", "tmax": "t2m_max"})
            else:
                self.weather = pd.DataFrame()

        cdl = pkg.get("cdl_composition", [])
        self.cdl_composition = pd.DataFrame(cdl) if cdl else pd.DataFrame()

        rot = pkg.get("crop_rotation", [])
        self.crop_rotation = pd.DataFrame(rot) if rot else pd.DataFrame()

        ndvi_records = pkg.get("ndvi_scenes", [])
        if ndvi_records:
            ndf = pd.DataFrame(ndvi_records)
            if "date" in ndf.columns:
                ndf["date"] = pd.to_datetime(ndf["date"])
            self.ndvi_scenes = ndf
        else:
            ndvi_records = pkg.get("ndvi_annual", [])
            self.ndvi_scenes = pd.DataFrame(ndvi_records) if ndvi_records else pd.DataFrame()

        gdd_records = pkg.get("gdd_daily", [])
        if gdd_records:
            gdf = pd.DataFrame(gdd_records)
            if "date" in gdf.columns:
                gdf["date"] = pd.to_datetime(gdf["date"])
            self.gdd_daily = gdf
        else:
            self.gdd_daily = pd.DataFrame()

        self.kpis_cache = pkg.get("kpis", {})
        if not self.metrics.empty:
            self.metrics["soil_health_score"] = self.metrics.get("soil_health_score", None)
            self.metrics["sustainability_index"] = self.metrics.get("sustainability_index", None)
        return self

    def _resolve_farm_path(self):
        import geopandas as gpd
        self._gpd = gpd
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
        self.farm_boundary_dir = self.farm_path / "boundary"

    def _load_all(self):
        self.field_ids = self._load_field_inventory()
        if self.field_id and self.field_id in self.field_ids:
            self.field_ids = [self.field_id]
        elif self.field_id:
            self.field_ids = self.field_ids[:1] if self.field_ids else []
        self.field_geojson = self._load_field_boundaries()
        self.soil = self._load_soil_summary()
        self.weather = self._load_weather()
        self.cdl_composition = self._load_cdl_composition()
        self.crop_rotation = self._load_crop_rotation()
        self.ndvi_scenes = self._load_ndvi_scenes()
        self.gdd_daily = self._compute_gdd()
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
        gpd = self._gpd
        bdy_path = self.farm_boundary_dir / "field_boundaries.geojson"
        for path in [bdy_path]:
            if path.exists():
                gdf = gpd.read_file(path)
                if self.field_id:
                    gdf = gdf[gdf["field_id"] == self.field_id].copy()
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
                if self.field_id:
                    df = df[df["field_id"] == self.field_id].copy()
                return df
        for f in self.farm_tables.glob("*ssurgo_summary*.csv"):
            df = pd.read_csv(f)
            df.columns = [c.strip().lower() for c in df.columns]
            if self.field_id:
                df = df[df["field_id"] == self.field_id].copy()
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
                if self.field_id:
                    df = df[df["field_id"] == self.field_id].copy()
                return df
        for f in self.farm_tables.glob("*weather*.csv"):
            df = pd.read_csv(f, parse_dates=["date"])
            df.columns = [c.strip().lower() for c in df.columns]
            if self.field_id:
                df = df[df["field_id"] == self.field_id].copy()
            return df
        return pd.DataFrame()

    def _load_cdl_composition(self):
        patterns = [
            self.farm_tables / f"{self.farm_slug.replace('-farm', '')}_cdl_2021_2025_full_composition.csv",
            self.farm_tables / f"{self.farm_slug.split('-')[0]}_cdl_2021_2025_full_composition.csv",
        ]
        for p in patterns:
            if p.exists():
                df = pd.read_csv(p)
                if self.field_id:
                    df = df[df["field_id"] == self.field_id].copy()
                return df
        for f in self.farm_tables.glob("*cdl*composition*.csv"):
            df = pd.read_csv(f)
            if self.field_id:
                df = df[df["field_id"] == self.field_id].copy()
            return df
        return pd.DataFrame()

    def _load_crop_rotation(self):
        patterns = [
            self.farm_tables / f"{self.farm_slug.replace('-farm', '')}_crop_rotation.csv",
            self.farm_tables / f"{self.farm_slug.split('-')[0]}_crop_rotation.csv",
        ]
        for p in patterns:
            if p.exists():
                df = pd.read_csv(p)
                if self.field_id:
                    df = df[df["field_id"] == self.field_id].copy()
                return df
        for f in self.farm_tables.glob("*crop_rotation*.csv"):
            df = pd.read_csv(f)
            if self.field_id:
                df = df[df["field_id"] == self.field_id].copy()
            return df
        return pd.DataFrame()

    def _load_ndvi_scenes(self):
        records = []
        for fid in self.field_ids:
            scene_dir = self._field_path(fid) / "satellite" / "sentinel"
            if not scene_dir.exists():
                continue
            for year_dir in sorted(scene_dir.iterdir()):
                if not year_dir.is_dir() or not year_dir.name.isdigit():
                    continue
                year = int(year_dir.name)
                for scene_dir2 in sorted(year_dir.iterdir()):
                    ndvi_path = scene_dir2 / f"{scene_dir2.name}_ndvi.tif"
                    if ndvi_path.exists():
                        mean_val = self._read_tiff_mean(ndvi_path)
                        scene_date_str = ndvi_path.name.replace("sentinel_", "").replace("_ndvi.tif", "")
                        try:
                            scene_date = pd.Timestamp(f"{year}{scene_date_str[:4]}")
                        except Exception:
                            scene_date = pd.Timestamp(f"{year}-01-01")
                        records.append({
                            "field_id": fid,
                            "year": year,
                            "date": scene_date,
                            "ndvi": mean_val,
                            "source": "sentinel",
                            "scene": scene_dir2.name,
                        })
        df = pd.DataFrame(records) if records else pd.DataFrame()
        if not df.empty:
            df = df.sort_values("date").reset_index(drop=True)
        return df

    def _read_tiff_mean(self, tiff_path):
        try:
            import rasterio
            with rasterio.open(str(tiff_path)) as src:
                band = src.read(1).astype(np.float32)
                if src.nodata is not None and not np.isnan(src.nodata):
                    band[band == src.nodata] = np.nan
                mean_val = float(np.nanmean(band))
                if np.isnan(mean_val) or mean_val <= 0:
                    return None
                return round(mean_val, 4)
        except Exception:
            return None

    def _compute_gdd(self):
        if self.weather.empty:
            return pd.DataFrame()
        w = self.weather.copy()
        required = ["t2m_max", "t2m_min", "date"]
        if not all(c in w.columns for c in required):
            return pd.DataFrame()
        w["tmax_cap"] = w["t2m_max"].clip(upper=GDD_CAP_TEMP)
        w["tmin_cap"] = w["t2m_min"].clip(lower=GDD_BASE_TEMP)
        w["gdd"] = ((w["tmax_cap"] + w["tmin_cap"]) / 2) - GDD_BASE_TEMP
        w["gdd"] = w["gdd"].clip(lower=0)
        w["doy"] = w["date"].dt.dayofyear
        w["season_gdd"] = 0.0
        for yr in w["date"].dt.year.unique():
            mask = (w["date"].dt.year == yr) & (w["doy"] >= PLANTING_DOY)
            w.loc[mask, "season_gdd"] = w.loc[mask, "gdd"].cumsum()
        return w[["date", "doy", "gdd", "season_gdd", "t2m_max", "t2m_min", "t2m", "prectotcorr"]]

    def get_field_crop_year(self, field_id, year):
        if self.cdl_composition.empty:
            return None
        sub = self.cdl_composition[
            (self.cdl_composition["field_id"] == field_id) &
            (self.cdl_composition["year"] == year)
        ]
        if sub.empty:
            return None
        sub = sub.sort_values("pct", ascending=False)
        return sub.iloc[0].get("crop_name", "Unknown")

    def get_field_crop_sequence(self, field_id):
        if self.cdl_composition.empty:
            return {}
        sub = self.cdl_composition[self.cdl_composition["field_id"] == field_id]
        if sub.empty:
            return {}
        result = {}
        for _, row in sub.iterrows():
            yr = int(row["year"])
            if yr not in result or row.get("pct", 0) > result[yr].get("pct", 0):
                result[yr] = {"crop_name": row["crop_name"], "pct": row.get("pct", 0)}
        return result

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

            scene_df = self.ndvi_scenes[self.ndvi_scenes["field_id"] == fid] if not self.ndvi_scenes.empty else pd.DataFrame()
            if not scene_df.empty and "ndvi" in scene_df.columns:
                vals = scene_df["ndvi"].dropna()
                m["avg_ndvi"] = round(float(vals.mean()), 4) if len(vals) > 0 else None
                m["max_ndvi"] = round(float(vals.max()), 4) if len(vals) > 0 else None
            else:
                m["avg_ndvi"] = None
                m["max_ndvi"] = None

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

    def compute_soil_health_score(self, force=False):
        if self.metrics.empty:
            return self.metrics
        df = self.metrics.copy()
        if not force and "soil_health_score" in df.columns and df["soil_health_score"].notna().any():
            return df
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

    def compute_sustainability_index(self, force=False):
        df = self.compute_soil_health_score(force=force)
        if df.empty:
            return df
        if not force and "sustainability_index" in df.columns and df["sustainability_index"].notna().any():
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
        if hasattr(self, "kpis_cache") and self.kpis_cache:
            return self.kpis_cache
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
                if self.weather["date"].dtype == "object":
                    self.weather["date"] = pd.to_datetime(self.weather["date"])
                if "field_id" in self.weather.columns:
                    per_field_yr = self.weather.groupby(["field_id", self.weather["date"].dt.year])[precip_col].sum()
                    per_field_avg = per_field_yr.groupby("field_id").mean()
                    stats["avg_rainfall_mm"] = round(float(per_field_avg.mean()), 1) if len(per_field_avg) > 0 else None
                else:
                    stats["avg_rainfall_mm"] = round(float(self.weather[precip_col].mean()), 1)
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
        self.kpis_cache = stats
        return stats

    def get_single_field_summary(self, field_id):
        crop_seq = self.get_field_crop_sequence(field_id)
        scene_df = self.ndvi_scenes[self.ndvi_scenes["field_id"] == field_id] if not self.ndvi_scenes.empty else pd.DataFrame()
        ndvi_by_year = scene_df.groupby("year")["ndvi"].agg(["mean", "max", "count"]).to_dict("index") if not scene_df.empty else {}
        weather_by_year = {}
        if not self.weather.empty:
            w = self.weather.copy()
            w["year"] = w["date"].dt.year
            weather_by_year = w.groupby("year").agg(
                precip_total=("prectotcorr", "sum"),
                temp_avg=("t2m", "mean"),
                tmax_avg=("t2m_max", "mean"),
                tmin_avg=("t2m_min", "mean"),
            ).to_dict("index")
        return {
            "field_id": field_id,
            "crop_sequence": {str(yr): info["crop_name"] for yr, info in sorted(crop_seq.items())},
            "ndvi_by_year": {str(k): v for k, v in sorted(ndvi_by_year.items())},
            "weather_by_year": {str(k): v for k, v in sorted(weather_by_year.items())},
        }


def main():
    data_root = os.environ.get("DATA_PIPELINE_DATA_ROOT")
    if not data_root:
        print("ERROR: Set DATA_PIPELINE_DATA_ROOT to the runtime root.")
        sys.exit(1)
    data = DashboardData(data_root, "iowa-grower", "iowa-farm", field_id="osm-1219926116")
    print(f"Fields: {data.field_ids}")
    print(f"NDVI scenes: {len(data.ndvi_scenes)}")
    if not data.ndvi_scenes.empty:
        print(data.ndvi_scenes[["date", "ndvi", "source"]].to_string())
    print(f"\nGDD records: {len(data.gdd_daily)}")
    if not data.gdd_daily.empty:
        print(data.gdd_daily[["date", "gdd", "season_gdd"]].tail(10).to_string())
    print(f"\nCrop sequence: {data.get_field_crop_sequence('osm-1219926116')}")
    print(f"KPIs: {data.get_kpis()}")


if __name__ == "__main__":
    main()
