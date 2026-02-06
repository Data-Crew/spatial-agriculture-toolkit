"""
Spatial autocorrelation analysis using Moran's I.

This module provides functions for computing local and global spatial
autocorrelation statistics for agricultural field analysis.
"""

import geopandas as gpd
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.patches import Patch

import esda
from splot import esda as esdaplot

from esda.moran import (
    Moran, 
    Moran_Local, 
    Moran_BV, 
    Moran_Local_BV
)

from .geo_utils import compute_weights

# Mapping from value to name (as a dict)
MORAN_LABELS = {
    0: "Non-Significant",
    1: "HH",
    2: "LH",
    3: "LL",
    4: "HL",
}


def lisa(
    gdf: gpd.GeoDataFrame,
    indicators: list[str],
    weights: str = "queen",
    knn_k: int = 5,
    local: bool = True
):
    """
    Compute Local Indicators of Spatial Association (LISA).
    
    This function takes a geopandas GeoDataFrame and estimates the 
    spatial autocorrelation between the observations of the same group 
    and their surroundings.
    
    Parameters
    ----------
    gdf : geopandas.GeoDataFrame
        GeoDataFrame with geometries
    indicators : list[str]
        List of indicators to compute LISA for
    weights : str, default="queen"
        Spatial weights type. Options: "queen", "knn"
    knn_k : int, default=5
        Number of neighbors for KNN weights
    local : bool, default=True
        Whether to return local or global Moran statistics

    Returns
    -------
    list
        List of esda.Moran or esda.Moran_Local objects
    """
    w = compute_weights(gdf, weights=weights, knn_k=knn_k)
    
    if local:
        return [Moran_Local(gdf[indicator], w) for indicator in indicators]
    else:
        # global
        return [Moran(gdf[indicator].values, w) for indicator in indicators]


def lisa_bv(
    gdf: gpd.GeoDataFrame,
    target_attr: str,
    reference_attr: str,
    weights: str = "queen",
    knn_k: int = 5,
    local: bool = True,
):
    """
    Compute bivariate Local Indicators of Spatial Association (LISA).
    
    This function estimates spatial autocorrelation between a group of 
    observations and neighbors of a different group.
    
    Parameters
    ----------
    gdf : geopandas.GeoDataFrame
        GeoDataFrame with geometries
    target_attr : str
        Name of the column with target observations
    reference_attr : str
        Name of the column representing neighbor reference
    weights : str, default="queen"
        Spatial weights type. Options: "queen", "knn"
    knn_k : int, default=5
        Number of neighbors for KNN weights
    local : bool, default=True
        Whether to return local or global statistic

    Returns
    -------
    esda.Moran_BV or esda.Moran_Local_BV
        Bivariate spatial autocorrelation object
    """
    w = compute_weights(gdf, weights=weights, knn_k=knn_k)
    
    if local:
        return Moran_Local_BV(gdf[target_attr], gdf[reference_attr], w)
    else:
        # global
        return Moran_BV(gdf[target_attr], gdf[reference_attr], w)


def plot_local_autocorrelation(
    gdf: gpd.GeoDataFrame,
    indicators: list[str],
    p_value: float = 0.05,
    weights: str = "queen",
    knn_k: int = 5,
    figsize: tuple[int, int] = (20, 7),
    cmap: str = "viridis",
    **kwargs,
):
    """
    Plot local autocorrelation for each indicator in the list.

    Parameters
    ----------
    gdf : gpd.GeoDataFrame
        GeoDataFrame with the data
    indicators : list[str]
        List of indicators to plot
    p_value : float, default=0.05
        P-value threshold for significance
    weights : str, default="queen"
        Spatial weights type
    knn_k : int, default=5
        Number of neighbors for KNN weights
    figsize : tuple[int, int], default=(20, 7)
        Figure size
    cmap : str, default="viridis"
        Colormap to use

    Returns
    -------
    matplotlib.figure.Figure
        Figure with the plots
    """
    for indicator in indicators:
        w = compute_weights(gdf, weights=weights, knn_k=knn_k)
        lisa = esda.Moran_Local(gdf[indicator], w)
        fig, subplots = esdaplot.plot_local_autocorrelation(
            lisa,
            gdf,
            indicator,
            p=p_value,
            figsize=figsize,
            cmap=cmap,
            **kwargs,
        )
        fig.suptitle(f"{indicator.capitalize()} - Local Autocorrelation")


def add_local_autocorrelation_labels(
    gdf: gpd.GeoDataFrame,
    indicator: str,
    p_value: float = 0.05,
    weights: str = "queen",
    knn_k: int = 5
):
    """
    Add local autocorrelation labels to GeoDataFrame.

    Parameters
    ----------
    gdf : gpd.GeoDataFrame
        GeoDataFrame with the data
    indicator : str
        Indicator column name to analyze
    p_value : float, default=0.05
        P-value threshold for significance
    weights : str, default="queen"
        Spatial weights type
    knn_k : int, default=5
        Number of neighbors for KNN weights

    Returns
    -------
    gpd.GeoDataFrame
        Updated GeoDataFrame with columns:
        - lbl_autocorr: autocorrelation labels (HH, HL, LH, LL, ns)
        - lbl_autocorr_col: color codes for visualization
    """
    w = compute_weights(gdf, weights=weights, knn_k=knn_k)
    lisa = esda.Moran_Local(gdf[indicator], w)
    sig = lisa.p_sim < p_value
    hot = lisa.q == 1
    cold = lisa.q == 3
    doughnut = lisa.q == 2
    diamond = lisa.q == 4

    labels = pd.Series(['ns']*len(gdf), index=gdf.index)
    labels[(sig) & (hot)] = 'HH'
    labels[(sig) & (doughnut)] = 'HL'
    labels[(sig) & (diamond)] = 'LH'
    labels[(sig) & (cold)] = 'LL'

    gdf['lbl_autocorr'] = labels

    colors = {
        'HH': '#FF0000',  # Red
        'HL': '#FFD580',  # Light Orange
        'LH': '#87CEEB',  # Sky Blue
        'LL': '#0074D9',  # Darker Blue
        'ns': '#D3D3D3'  # Light Grey
    }

    gdf['lbl_autocorr_col'] = gdf['lbl_autocorr'].map(colors)

    return gdf


def plot_autocorrelation_labels(
        gdf: gpd.GeoDataFrame, 
        title: str, 
        tuple_size: tuple[int, int]):
    """
    Plot a GeoDataFrame with autocorrelation labels.

    Parameters
    ----------
    gdf : gpd.GeoDataFrame
        GeoDataFrame with the 'lbl_autocorr' column
    title : str
        Plot title
    tuple_size : tuple[int, int]
        Figure size
    """
    # Set up the color map and legend
    legend_labels = {
        'HH': 'High-High', 
        'HL': 'High-Low', 
        'LH': 'Low-High', 
        'LL': 'Low-Low', 
        'ns': 'Not significant'
    }
    colors = {
        'HH': '#FF0000',  # Red
        'HL': '#FFD580',  # Light Orange
        'LH': '#87CEEB',  # Sky Blue
        'LL': '#0074D9',  # Darker Blue
        'ns': '#D3D3D3'  # Light Grey
    }
    
    fig, ax = plt.subplots(1, 1, figsize=tuple_size)
    for label, group in gdf.groupby('lbl_autocorr'):
        color = colors[label]
        group.plot(ax=ax, color=color)

    # Creating legend handles manually
    legend_handles = [Patch(color=color, label=label) for label, color in colors.items()]

    ax.set_title(title)
    ax.set_axis_off()
    ax.legend(handles=legend_handles, title='Quadrants') 

    plt.show()
