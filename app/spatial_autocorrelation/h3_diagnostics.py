"""
H3 hexgrid diagnostics and recommendation utilities.

Implements the operational guidance from the H3 resolution effects notebook:
- Auto-recommend resolution based on field size
- Cardinality classification for indicators
- Replication factor monitoring
- Compute-on-fields, render-on-hexes mode
"""

from typing import Tuple

import geopandas as gpd
import pandas as pd
import pyproj
from shapely.ops import transform

from .geo_utils import geopandas_to_h3
from .moran import add_local_autocorrelation_labels


# H3 hex cell areas (km²) by resolution — exact nominal values from h3-py v3.7.7.
# Used as fallback if dynamic area lookup fails at runtime.
H3_CELL_AREA_KM2 = {
    0: 4_250_547.847,
    1: 609_788.441,
    2: 86_801.780,
    3: 12_393.434,
    4: 1_770.347,
    5: 252.903,
    6: 36.129,
    7: 5.161,
    8: 0.737,
    9: 0.105,
    10: 0.015,
    11: 0.00214,
    12: 0.000305,
    13: 0.0000436,
    14: 0.00000623,
    15: 0.00000089,
}


def _h3_cell_area_km2(lat: float, lon: float, resolution: int) -> float:
    """Return the actual cell area (km²) for a cell near (lat, lon)."""
    try:
        import h3
        cell = h3.geo_to_h3(lat, lon, resolution)
        return h3.cell_area(cell, unit="km^2")
    except Exception:
        return H3_CELL_AREA_KM2.get(resolution, 0.0)


def _compute_median_field_area_km2(gdf: gpd.GeoDataFrame) -> float:
    """Compute the median area of fields in km² using a local UTM projection."""
    if gdf.crs is None:
        gdf = gdf.set_crs("EPSG:4326")

    centroid = gdf.unary_union.centroid
    lon, lat = centroid.x, centroid.y

    utm_zone = int((lon + 180) / 6) + 1
    hemisphere = 32600 if lat >= 0 else 32700
    epsg = hemisphere + utm_zone
    utm_crs = pyproj.CRS.from_epsg(epsg)

    transformer = pyproj.Transformer.from_crs(gdf.crs, utm_crs, always_xy=True)
    gdf_proj = gdf.copy()
    gdf_proj.geometry = gdf_proj.geometry.apply(
        lambda geom: transform(transformer.transform, geom)
    )
    gdf_proj = gdf_proj.set_crs(utm_crs, allow_override=True)
    return gdf_proj.geometry.area.median() / 1e6


def recommend_h3_resolution(
    gdf: gpd.GeoDataFrame,
    target_replication: float = 1.25,
    min_res: int = 4,
    max_res: int = 12,
) -> Tuple[int, float]:
    """
    Recommend an H3 resolution so that the average field resolves to
    roughly one hex (replication factor ≈ target_replication).

    Parameters
    ----------
    gdf : geopandas.GeoDataFrame
        Field geometries (EPSG:4326).
    target_replication : float, default 1.25
        Desired ratio of median field area to H3 cell area.
    min_res, max_res : int
        Resolution search bounds.

    Returns
    -------
    (recommended_resolution, expected_replication)
    """
    median_area = _compute_median_field_area_km2(gdf)
    centroid = gdf.unary_union.centroid
    lat, lon = centroid.y, centroid.x

    candidates = []
    for res in range(min_res, max_res + 1):
        cell_area = _h3_cell_area_km2(lat, lon, res)
        if cell_area <= 0:
            continue
        replication = median_area / cell_area
        candidates.append((res, replication))

    # Prefer resolutions where the hex is at most the size of a field
    # (replication >= 1.0) and closest to the target.
    valid = [(res, rep) for res, rep in candidates if rep >= 1.0]
    if valid:
        best_res, best_rep = min(valid, key=lambda x: abs(x[1] - target_replication))
    else:
        # All resolutions too coarse → pick the finest one available.
        best_res, best_rep = candidates[-1] if candidates else (min_res, 0.0)

    return int(best_res), float(best_rep)


def cardinality_class(n_unique: int) -> Tuple[str, str, str]:
    """
    Classify an indicator by its empirical cardinality.

    Returns
    -------
    (level, emoji, css_color) — e.g. ('High', '🟢', '#28a745')
    """
    if n_unique > 20:
        return "High", "🟢", "#28a745"
    if n_unique >= 5:
        return "Medium", "🟡", "#ffc107"
    return "Low", "🔴", "#dc3545"


def compute_replication_factor(gdf_fields: gpd.GeoDataFrame, gdf_h3: gpd.GeoDataFrame) -> float:
    """Return the replication factor: n_hexes / n_fields."""
    return len(gdf_h3) / max(1, len(gdf_fields))


def lisa_on_fields_render_on_hexes(
    gdf_fields: gpd.GeoDataFrame,
    indicator: str,
    resolution: int,
    p_value: float = 0.05,
    weights: str = "queen",
    knn_k: int = 5,
) -> gpd.GeoDataFrame:
    """
    Compute LISA on the original field geometries, then project the
    labels onto an H3 hexgrid for rendering.

    This avoids the four inflation mechanisms described in the notebook:
    1. Pseudo p-value inflation from large N
    2. Polyfill pseudo-replicates
    3. Sibling-dominated queen neighbourhoods
    4. Cardinality collapse

    Parameters
    ----------
    gdf_fields : geopandas.GeoDataFrame
        Original field-level geometries (EPSG:4326).
    indicator : str
        Column name to analyze.
    resolution : int
        H3 resolution for rendering.
    p_value, weights, knn_k
        Passed to ``add_local_autocorrelation_labels``.

    Returns
    -------
    geopandas.GeoDataFrame
        Hexgrid GeoDataFrame with ``lbl_autocorr`` and ``lbl_autocorr_col``
        inherited from the parent field labels.
    """
    # 1. Compute LISA on field geometry
    gdf_fields_labeled = add_local_autocorrelation_labels(
        gdf=gdf_fields.copy(),
        indicator=indicator,
        p_value=p_value,
        weights=weights,
        knn_k=knn_k,
    )

    # 2. Hexify the original fields (without label columns).
    #    polyfill_resample drops string columns, so we hexify the raw
    #    fields first and join labels back afterwards.
    gdf_h3 = geopandas_to_h3(gdf_fields.copy(), resolution=resolution, resample=True)

    # 3. Spatial join: each hex gets the label of the field whose
    #    polygon contains the hex centroid.
    hex_centroids = gdf_h3.copy()
    hex_centroids.geometry = hex_centroids.geometry.centroid

    joined = gpd.sjoin(
        hex_centroids,
        gdf_fields_labeled[["lbl_autocorr", "lbl_autocorr_col", "geometry"]],
        how="left",
        predicate="within",
    )

    # Copy labels back to the hex grid (preserve left order)
    gdf_h3["lbl_autocorr"] = joined["lbl_autocorr"].values
    gdf_h3["lbl_autocorr_col"] = joined["lbl_autocorr_col"].values

    return gdf_h3
