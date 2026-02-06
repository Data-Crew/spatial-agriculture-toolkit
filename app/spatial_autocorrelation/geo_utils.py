"""
Geospatial utilities for spatial autocorrelation analysis.
"""

from copy import deepcopy

import libpysal
import geopandas as gpd
import h3pandas


def geopandas_to_h3(
    gdf: gpd.GeoDataFrame,
    resolution: int = 8,
    resample: bool = True,
) -> gpd.GeoDataFrame:
    """
    Convert GeoDataFrame to H3 hexgrid representation.
    
    This function takes a geopandas GeoDataFrame and returns a geopandas 
    GeoDataFrame with the h3 index for the given resolution.
    
    Parameters
    ----------
    gdf : geopandas.GeoDataFrame
        GeoDataFrame with geometries
    resolution : int, default=8
        H3 resolution level (1-15)
    resample : bool, default=True
        If True, resample the geometries to the h3 resolution

    Returns
    -------
    geopandas.GeoDataFrame
        GeoDataFrame with the hexgrid as geometries
    """
    gdf = deepcopy(gdf)
    if resample:
        return gdf.h3.polyfill_resample(resolution=resolution)
    else:
        return gdf.h3.polyfill(resolution=resolution)


def compute_weights(
    gdf: gpd.GeoDataFrame, 
    weights: str = "queen", 
    knn_k: int = 5
):
    """
    Compute spatial weights matrix.
    
    This function takes a geopandas GeoDataFrame and returns a libpysal 
    weights object for spatial analysis.
    
    Parameters
    ----------
    gdf : geopandas.GeoDataFrame
        GeoDataFrame with geometries
    weights : str, default="queen"
        Spatial weights type. Options: "queen", "knn"
    knn_k : int, default=5
        Number of neighbors for KNN weights

    Returns
    -------
    libpysal.weights
        libpysal weights object
    """
    match weights:
        case "queen":
            w = libpysal.weights.Queen.from_dataframe(gdf)
        case "knn":
            w = libpysal.weights.KNN.from_dataframe(gdf, k=knn_k)
        case _:
            raise ValueError(f"Invalid weights type: {weights}")
    return w
