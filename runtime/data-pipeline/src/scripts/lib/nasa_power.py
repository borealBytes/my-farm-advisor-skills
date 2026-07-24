# pyright: reportMissingImports=false
from __future__ import annotations

from typing import Any, cast

import pandas as pd
import requests

WEATHER_COLUMNS = [
    "T2M",
    "T2M_MAX",
    "T2M_MIN",
    "PRECTOTCORR",
    "ALLSKY_SFC_SW_DWN",
    "RH2M",
    "WS10M",
]
MERRA2_COLUMNS = ["T2M", "T2M_MAX", "T2M_MIN", "PRECTOTCORR", "RH2M", "WS10M"]
SYN1DEG_COLUMNS = ["ALLSKY_SFC_SW_DWN"]
ZARR_STORES = {
    "merra2": {
        "lst": "https://nasa-power.s3.us-west-2.amazonaws.com/merra2/temporal/power_merra2_daily_temporal_lst.zarr",
        "utc": "https://nasa-power.s3.us-west-2.amazonaws.com/merra2/temporal/power_merra2_daily_temporal_utc.zarr",
    },
    "syn1deg": {
        "lst": "https://nasa-power.s3.us-west-2.amazonaws.com/syn1deg/temporal/power_syn1deg_daily_temporal_lst.zarr",
        "utc": "https://nasa-power.s3.us-west-2.amazonaws.com/syn1deg/temporal/power_syn1deg_daily_temporal_utc.zarr",
    },
}


def assign_power_grid(
    points: pd.DataFrame,
    *,
    lat_column: str = "lat",
    lon_column: str = "lon",
) -> pd.DataFrame:
    lookup = points.copy()
    lookup["grid_lat"] = (lookup[lat_column] / 0.5).round() * 0.5
    lookup["grid_lon"] = (lookup[lon_column] / 0.625).round() * 0.625
    lookup["grid_key"] = (
        lookup["grid_lat"].map("{:.3f}".format)
        + ":"
        + lookup["grid_lon"].map("{:.3f}".format)
    )
    return cast(pd.DataFrame, lookup)


def import_zarr_stack() -> tuple[Any, Any]:
    try:
        import fsspec
        import xarray as xr
    except ImportError as exc:
        raise RuntimeError(
            "NASA POWER Zarr backend requires xarray, zarr, and fsspec[http]; "
            "rerun the data-pipeline installer to refresh dependencies or use "
            "--weather-backend api"
        ) from exc
    return fsspec, xr


def query_zarr_grid_weather(
    grid_lookup: pd.DataFrame,
    *,
    year: int,
    collection: str,
    parameters: list[str],
    time_standard: str,
) -> pd.DataFrame:
    if grid_lookup.empty:
        return pd.DataFrame()
    fsspec, xr = import_zarr_stack()
    store_url = ZARR_STORES[collection][time_standard]
    store = fsspec.get_mapper(store_url)
    ds = xr.open_zarr(store, consolidated=True, chunks=None)
    try:
        missing = [parameter for parameter in parameters if parameter not in ds.data_vars]
        if missing:
            raise RuntimeError(f"NASA POWER Zarr store missing variables: {missing}")
        grid_keys = grid_lookup["grid_key"].astype(str).to_numpy()
        lat_indexer = xr.DataArray(
            grid_lookup["grid_lat"].astype(float).to_numpy(),
            dims="grid",
            coords={"grid": grid_keys},
        )
        lon_indexer = xr.DataArray(
            grid_lookup["grid_lon"].astype(float).to_numpy(),
            dims="grid",
            coords={"grid": grid_keys},
        )
        subset = (
            ds[parameters]
            .sel(time=slice(f"{year}-01-01", f"{year}-12-31"))
            .sel(lat=lat_indexer, lon=lon_indexer, method="nearest")
            .load()
        )
        frame = cast(pd.DataFrame, subset.to_dataframe().reset_index())
    finally:
        ds.close()

    if frame.empty:
        return frame
    frame = cast(pd.DataFrame, frame.rename(columns={"time": "date", "grid": "grid_key"}))
    frame["grid_key"] = frame["grid_key"].astype(str)
    frame["date"] = pd.to_datetime(frame["date"])
    frame = frame.drop(columns=[column for column in ["lat", "lon"] if column in frame.columns])
    for parameter in parameters:
        if parameter in frame.columns:
            frame[parameter] = frame[parameter].replace(-999.0, pd.NA)
    return cast(pd.DataFrame, frame[["date", "grid_key", *parameters]].copy())


def build_zarr_grid_weather(
    grid_lookup: pd.DataFrame,
    *,
    year: int,
    time_standard: str,
) -> pd.DataFrame:
    unique_grid_lookup = cast(
        pd.DataFrame,
        grid_lookup[["grid_key", "grid_lat", "grid_lon"]]
        .drop_duplicates()
        .reset_index(drop=True),
    )
    merra2_weather = query_zarr_grid_weather(
        unique_grid_lookup,
        year=year,
        collection="merra2",
        parameters=MERRA2_COLUMNS,
        time_standard=time_standard,
    )
    if merra2_weather.empty:
        return pd.DataFrame()

    syn1deg_weather = query_zarr_grid_weather(
        unique_grid_lookup,
        year=year,
        collection="syn1deg",
        parameters=SYN1DEG_COLUMNS,
        time_standard=time_standard,
    )
    if not syn1deg_weather.empty:
        solar_missing = bool(
            cast(pd.Series, syn1deg_weather["ALLSKY_SFC_SW_DWN"]).isna().any()
        )
        if solar_missing:
            alternate_time_standard = "utc" if time_standard == "lst" else "lst"
            alternate_solar = query_zarr_grid_weather(
                unique_grid_lookup,
                year=year,
                collection="syn1deg",
                parameters=SYN1DEG_COLUMNS,
                time_standard=alternate_time_standard,
            )
            if not alternate_solar.empty:
                alternate_solar = cast(
                    pd.DataFrame,
                    alternate_solar.rename(
                        columns={"ALLSKY_SFC_SW_DWN": "_ALLSKY_SFC_SW_DWN_FALLBACK"}
                    ),
                )
                syn1deg_weather = cast(
                    pd.DataFrame,
                    syn1deg_weather.merge(
                        alternate_solar[["date", "grid_key", "_ALLSKY_SFC_SW_DWN_FALLBACK"]],
                        on=["date", "grid_key"],
                        how="left",
                    ),
                )
                syn1deg_weather["ALLSKY_SFC_SW_DWN"] = syn1deg_weather[
                    "ALLSKY_SFC_SW_DWN"
                ].fillna(syn1deg_weather["_ALLSKY_SFC_SW_DWN_FALLBACK"])
                syn1deg_weather = cast(
                    pd.DataFrame,
                    syn1deg_weather.drop(columns=["_ALLSKY_SFC_SW_DWN_FALLBACK"]),
                )
        # The REST API returns daily shortwave radiation in MJ/m^2/day. The Zarr
        # source stores the same variable in W m-2, so convert for compatibility.
        solar_wm2 = cast(
            pd.Series,
            pd.to_numeric(syn1deg_weather["ALLSKY_SFC_SW_DWN"], errors="coerce"),
        )
        syn1deg_weather["ALLSKY_SFC_SW_DWN"] = solar_wm2 * 0.0864
        grid_weather = cast(
            pd.DataFrame,
            merra2_weather.merge(syn1deg_weather, on=["date", "grid_key"], how="left"),
        )
    else:
        grid_weather = merra2_weather.copy()
        grid_weather["ALLSKY_SFC_SW_DWN"] = pd.NA

    grid_weather = cast(
        pd.DataFrame,
        grid_weather.merge(unique_grid_lookup, on="grid_key", how="inner"),
    )
    grid_weather["year"] = grid_weather["date"].dt.year.astype(int)
    return cast(
        pd.DataFrame,
        grid_weather[
            [
                "date",
                "year",
                "grid_key",
                "grid_lat",
                "grid_lon",
                *WEATHER_COLUMNS,
            ]
        ].copy(),
    )


def query_api_point_weather(
    *,
    lat: float,
    lon: float,
    year: int,
    time_standard: str,
    timeout: int = 60,
    parameters: list[str] | None = None,
) -> pd.DataFrame:
    parameters = parameters or WEATHER_COLUMNS
    response = requests.get(
        "https://power.larc.nasa.gov/api/temporal/daily/point",
        params={
            "parameters": ",".join(parameters),
            "community": "AG",
            "longitude": lon,
            "latitude": lat,
            "start": f"{year}0101",
            "end": f"{year}1231",
            "time-standard": time_standard.upper(),
            "format": "JSON",
        },
        timeout=timeout,
    )
    response.raise_for_status()
    payload = response.json()
    parameter_data = payload.get("properties", {}).get("parameter", {})
    if not parameter_data:
        return pd.DataFrame()
    dates = list(parameter_data[parameters[0]].keys())
    records: list[dict[str, object]] = []
    for date_key in dates:
        record: dict[str, object] = {"date": pd.to_datetime(date_key, format="%Y%m%d")}
        for parameter in parameters:
            value = parameter_data.get(parameter, {}).get(date_key, -999.0)
            record[parameter] = None if value == -999.0 else value
        records.append(record)
    return pd.DataFrame(records)
