import json
import os
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import norm


class DashboardData:
    def __init__(self, data_root, grower_slug="iowa-grower", farm_slug="iowa-farm"):
        self.data_root = Path(data_root) / "data-pipeline"
        self.grower_slug = grower_slug
        self.farm_slug = farm_slug
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

        weather_records = pkg.get("weather_monthly", [])
        if weather_records:
            wdf = pd.DataFrame(weather_records)
            wdf["date"] = pd.to_datetime(wdf["year"].astype(str) + "-" + wdf["month"].astype(str) + "-01")
            self.weather = wdf.rename(columns={"precip": "prectotcorr", "temp": "t2m",
                                                "tmin": "t2m_min", "tmax": "t2m_max"})
            self.weather["field_id"] = self.field_ids[0] if self.field_ids else "unknown"
        else:
            self.weather = pd.DataFrame()

        cdl = pkg.get("cdl_composition", [])
        self.cdl_composition = pd.DataFrame(cdl) if cdl else pd.DataFrame()

        rot = pkg.get("crop_rotation", [])
        self.crop_rotation = pd.DataFrame(rot) if rot else pd.DataFrame()

        ndvi_records = pkg.get("ndvi_annual", [])
        self.ndvi_list = ndvi_records
        ndvi_df = pd.DataFrame(ndvi_records) if ndvi_records else pd.DataFrame()
        if not ndvi_df.empty and "ndvi" in ndvi_df.columns:
            ndvi_df = ndvi_df.dropna(subset=["ndvi"])
        self.ndvi = ndvi_df

        wdaily = pkg.get("weather_daily", [])
        if wdaily:
            wdf = pd.DataFrame(wdaily)
            wdf["date"] = pd.to_datetime(wdf["year"].astype(str) + "-"
                                          + wdf["month"].astype(str).str.zfill(2) + "-"
                                          + wdf["day"].astype(str).str.zfill(2))
            wdf = wdf.rename(columns={"precip": "prectotcorr", "temp": "t2m",
                                       "tmin": "t2m_min", "tmax": "t2m_max"})
            self.weather_daily = wdf
        else:
            self.weather_daily = pd.DataFrame()

        scenes = pkg.get("ndvi_scenes", [])
        if scenes:
            sdf = pd.DataFrame(scenes)
            sdf["date"] = pd.to_datetime(sdf["date"], format="%Y%m%d", errors="coerce")
            self.ndvi_scenes = sdf
        else:
            self.ndvi_scenes = pd.DataFrame()

        gdd = pkg.get("gdd_daily", [])
        if gdd:
            gdf = pd.DataFrame(gdd)
            gdf["date"] = pd.to_datetime(gdf["year"].astype(str) + "-"
                                          + gdf["month"].astype(str).str.zfill(2) + "-"
                                          + gdf["day"].astype(str).str.zfill(2))
            self.gdd_daily = gdf
        else:
            self.gdd_daily = pd.DataFrame()

        spi_records = pkg.get("spi_monthly", [])
        if spi_records:
            self.spi = pd.DataFrame(spi_records)
        else:
            self.spi = pd.DataFrame()

        self._compute_from_json(pkg)
        return self

    def _compute_from_json(self, pkg):
        self.kpis_cache = pkg.get("kpis", {})
        if not self.metrics.empty:
            self.metrics["soil_health_score"] = self.metrics.get("soil_health_score", None)
            self.metrics["sustainability_index"] = self.metrics.get("sustainability_index", None)
            if "soil_health_score" not in self.metrics.columns or self.metrics["soil_health_score"].isna().all():
                df = self.compute_soil_health_score(force=True)
                self.metrics["soil_health_score"] = df["soil_health_score"]
            if "sustainability_index" not in self.metrics.columns or self.metrics["sustainability_index"].isna().all():
                df = self.compute_sustainability_index(force=True)
                self.metrics["sustainability_index"] = df["sustainability_index"]

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
        self.ndvi_scenes = self._load_ndvi_scenes()
        self.weather_daily = self._load_weather_daily()
        self.gdd_daily = self._compute_gdd_daily()
        self.spi = self._compute_spi()
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

    def _load_ndvi_scenes(self):
        records = []
        for fid in self.field_ids:
            field_path = self._field_path(fid)
            sat_base = field_path / "satellite"
            for src in ("sentinel", "landsat"):
                sat_dir = sat_base / src
                if not sat_dir.exists():
                    continue
                for yr_dir in sorted(sat_dir.iterdir()):
                    if not yr_dir.is_dir():
                        continue
                    for scene_dir in sorted(yr_dir.iterdir()):
                        if not scene_dir.is_dir():
                            continue
                        ndvi_tif = scene_dir / f"{scene_dir.name}_ndvi.tif"
                        if not ndvi_tif.exists():
                            continue
                        try:
                            import rasterio
                            with rasterio.open(str(ndvi_tif)) as src_rio:
                                band = src_rio.read(1)
                                with warnings.catch_warnings():
                                    warnings.simplefilter("ignore")
                                    if src_rio.nodata is not None and not np.isnan(src_rio.nodata):
                                        band = band.astype(np.float32)
                                        band[band == src_rio.nodata] = np.nan
                                    mean_val = float(np.nanmean(band))
                                if np.isnan(mean_val) or mean_val <= 0:
                                    continue
                            prefix = f"{src}_"
                            scene_date = scene_dir.name.replace(prefix, "")
                            records.append({
                                "field_id": fid,
                                "year": int(yr_dir.name),
                                "date": scene_date,
                                "ndvi": round(mean_val, 4),
                                "source": src,
                            })
                        except Exception:
                            continue
                if any(r["field_id"] == fid for r in records):
                    break
        return pd.DataFrame(records) if records else pd.DataFrame()

    def _load_weather_daily(self):
        if self.weather.empty:
            return pd.DataFrame()
        if "date" in self.weather.columns and self.weather["date"].dtype == "object":
            self.weather["date"] = pd.to_datetime(self.weather["date"])
        return self.weather.copy()

    def _gdd_value(self, tmax, tmin, base=10, cap=30):
        if pd.isna(tmax) or pd.isna(tmin):
            return 0.0
        avg = (tmax + tmin) / 2
        return max(0.0, min(avg, cap) - base)

    def _compute_gdd_daily(self, base=10, cap=30, planting_doy=121):
        if self.weather.empty:
            return pd.DataFrame()
        w = self.weather.copy()
        if "date" in w.columns and w["date"].dtype == "object":
            w["date"] = pd.to_datetime(w["date"])
        w = w.sort_values("date")
        if "field_id" not in w.columns:
            w["field_id"] = self.field_ids[0] if self.field_ids else "unknown"
        rows = []
        for fid in w["field_id"].unique():
            fw = w[w["field_id"] == fid].copy()
            fw = fw.sort_values("date")
            cum_gdd = 0.0
            prev_yr = None
            for _, r in fw.iterrows():
                yr = r["date"].year
                doy = r["date"].timetuple().tm_yday
                if prev_yr is not None and yr != prev_yr:
                    cum_gdd = 0.0
                prev_yr = yr
                gdd_val = self._gdd_value(r.get("t2m_max"), r.get("t2m_min"), base, cap)
                if doy >= planting_doy:
                    cum_gdd += gdd_val
                else:
                    cum_gdd = 0.0
                rows.append({
                    "field_id": fid,
                    "date": r["date"],
                    "year": yr,
                    "gdd": round(gdd_val, 2),
                    "cumulative_gdd": round(cum_gdd, 2),
                })
        return pd.DataFrame(rows) if rows else pd.DataFrame()

    def get_field_crop_sequence(self, field_id):
        if not self.ndvi.empty:
            nd = self.ndvi[self.ndvi["field_id"] == field_id].sort_values("year")
            if not nd.empty:
                return dict(zip(nd["year"].astype(int), nd["crop_name"]))
        return {}

    def _compute_spi(self, windows=(1, 3, 6, 12)):
        w = self.weather_daily if not self.weather_daily.empty else self.weather
        if w.empty:
            return pd.DataFrame()
        if "field_id" not in w.columns:
            w["field_id"] = self.field_ids[0] if self.field_ids else "unknown"
        if "date" in w.columns and w["date"].dtype == "object":
            w["date"] = pd.to_datetime(w["date"])
        w["year"] = w["date"].dt.year
        w["month"] = w["date"].dt.month
        precip_col = "prectotcorr"
        monthly = w.groupby(["field_id", "year", "month"], as_index=False)[precip_col].sum()
        monthly = monthly.sort_values(["field_id", "year", "month"])
        all_spi = []
        for fid in monthly["field_id"].unique():
            fw = monthly[monthly["field_id"] == fid].copy()
            for win in windows:
                col = f"precip_{win}m"
                fw[col] = fw[precip_col].rolling(win, min_periods=1).sum()
            spi_df = fw[["field_id", "year", "month"]].copy()
            for win in windows:
                col = f"precip_{win}m"
                vals = fw[col].dropna()
                if len(vals) < 3:
                    spi_df[f"spi{win}"] = None
                    continue
                ranks = vals.rank(method="average")
                n = len(vals)
                prob = (ranks - 0.44) / (n + 1 - 2 * 0.44)
                prob = prob.clip(0.001, 0.999)
                spi_series = norm.ppf(prob)
                spi_df[f"spi{win}"] = spi_series
            all_spi.append(spi_df)
        return pd.concat(all_spi, ignore_index=True) if all_spi else pd.DataFrame()

    def get_spi_for_field(self, field_id):
        if self.spi.empty:
            return pd.DataFrame()
        return self.spi[self.spi["field_id"] == field_id].sort_values(["year", "month"])

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

    def get_maturity_strategy(self):
        return {
            "county": "Cerro Gordo County",
            "state": "IA",
            "corn_rm": 94,
            "corn_rm_range": "90 - 100",
            "corn_rm_band": 90,
            "corn_planting_window": "Apr 25 - May 20",
            "soybean_mg": 2.8,
            "soybean_mg_range": "2.4 - 3.2",
            "soybean_mg_band": "3.0",
            "soybean_planting_window": "Apr 25 - Jun 1",
            "annual_gdd": 1884,
            "source": "USDA NASS CDL / NASA POWER GDD",
        }


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
