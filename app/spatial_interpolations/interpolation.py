"""
Spatial interpolation module for agricultural field analysis.

This module provides spatial interpolation capabilities using R-based models
to predict occurrence probabilities of agricultural events or properties
across field areas.
"""

# Initialize R interface and load base packages before importing robjects
import rpy2.rinterface as rinterface
rinterface.initr()

# Now import robjects - base packages should be available
from rpy2 import robjects as ro
from rpy2.robjects import pandas2ri
from rpy2.robjects import conversion, default_converter

# Ensure base packages are loaded
ro.r("""
if (!"package:utils" %in% search()) {
    library(utils)
}
if (!"package:stats" %in% search()) {
    library(stats)
}
""")

import geopandas as gpd
import rasterio
from rasterio.features import shapes
import pandas as pd
from typing import Optional


# =============================================================================
# R functions for spatial interpolation.
#
# The code is organized as a set of small, focused functions:
#   prepare_point_data  – raw data → clean data.frame with binary target
#   resolve_target      – pick the target event to model
#   make_grid           – uniform prediction grid over the data extent
#   fit_*               – one per method, returns a prediction vector
#   predictions_to_raster – prediction vector → GeoTIFF on disk
#   Spatial_Interpolation – public entry point that orchestrates everything
# =============================================================================

R_INTERPOLATION_FUNCTION = """
# ── Load libraries once ──────────────────────────────────────────────────────
suppressPackageStartupMessages({
    library(sf)
    library(dplyr)
    library(splines)
    library(raster)
})

# ── Data preparation ─────────────────────────────────────────────────────────

prepare_point_data <- function(raw_data, target_label) {
    # Convert raw points to a data.frame with lon, lat, and binary target.
    coords <- raw_data %>%
        st_as_sf(coords = c("longitude", "latitude"), crs = 4326) %>%
        st_coordinates()

    data.frame(
        lon    = coords[, "X"],
        lat    = coords[, "Y"],
        event  = as.factor(raw_data$event_type),
        target = as.numeric(raw_data$event_type == target_label)
    )
}

resolve_target <- function(event_types, requested = NULL) {
    # Return a validated target label.
    levels_vec <- levels(as.factor(event_types))
    if (is.null(requested) || requested == "") {
        label <- tail(levels_vec, 1)
        message("[target] auto-selected: ", label)
    } else if (requested %in% levels_vec) {
        label <- requested
        message("[target] user-selected: ", label)
    } else {
        warning("Target '", requested, "' not in data. ",
                "Available: ", paste(levels_vec, collapse = ", "))
        label <- tail(levels_vec, 1)
        message("[target] falling back to: ", label)
    }
    label
}

# ── Prediction grid ──────────────────────────────────────────────────────────

make_grid <- function(ppp, resolution = 100) {
    expand.grid(
        lon = seq(min(ppp$lon), max(ppp$lon), length.out = resolution),
        lat = seq(min(ppp$lat), max(ppp$lat), length.out = resolution)
    )
}

# ── Model fitting (one function per method) ──────────────────────────────────
# Each fit_* function receives ppp (data.frame) and grid (data.frame)
# and returns a numeric vector of predicted probabilities (length = nrow(grid)).

fit_linear <- function(ppp, grid) {
    model <- glm(target ~ lon + lat, data = ppp, family = binomial())
    predict(model, newdata = grid, type = "response")
}

fit_orthogonal <- function(ppp, grid) {
    model <- glm(target ~ poly(lon, 3) * poly(lat, 3),
                  data = ppp, family = binomial())
    predict(model, newdata = grid, type = "response")
}

fit_splines <- function(ppp, grid) {
    model <- glm(target ~ bs(lon, 4) * bs(lat, 4),
                  data = ppp, family = binomial())
    predict(model, newdata = grid, type = "response")
}

fit_gam <- function(ppp, grid) {
    suppressPackageStartupMessages(library(mgcv))
    k_val <- min(max(20, floor(nrow(ppp) / 3)), 100)
    model <- gam(target ~ s(lon, lat, k = k_val, bs = "tp"),
                  data = ppp, family = binomial(), method = "REML")
    message("[gam] edf = ", round(summary(model)$s.table[, "edf"], 1),
            ", deviance explained = ",
            round(summary(model)$dev.expl * 100, 1), "%")
    predict(model, newdata = grid, type = "response")
}

fit_kriging <- function(ppp, grid) {
    suppressPackageStartupMessages({ library(gstat); library(sp) })

    # Build SpatialPointsDataFrame
    sp_pts <- ppp[, c("lon", "lat", "target")]
    coordinates(sp_pts) <- ~ lon + lat

    # Fit variogram: empirical → theoretical (auto-select best model)
    emp   <- variogram(target ~ 1, data = sp_pts)
    vmodel <- fit.variogram(emp, vgm(c("Sph", "Exp", "Gau")))
    message("[kriging] variogram: ", vmodel$model[2],
            ", range = ", round(vmodel$range[2], 6),
            ", sill = ", round(vmodel$psill[2], 4))

    # Build SpatialPixels grid for krige()
    sp_grid <- grid
    coordinates(sp_grid) <- ~ lon + lat
    gridded(sp_grid) <- TRUE

    result <- krige(target ~ 1, locations = sp_pts,
                    newdata = sp_grid, model = vmodel)

    # Clip to [0, 1] — kriging can extrapolate beyond indicator bounds
    pmin(pmax(result$var1.pred, 0), 1)
}

# ── Rasterization ────────────────────────────────────────────────────────────

predictions_to_raster <- function(predictions, ppp, grid, resolution, path) {
    r <- raster(nrows = resolution, ncols = resolution,
                xmn = min(ppp$lon), xmx = max(ppp$lon),
                ymn = min(ppp$lat), ymx = max(ppp$lat))

    # predictions follow expand.grid order (lon varies fastest).
    # Convert to matrix (rows = lat, cols = lon) and flip so row 1 = north.
    m <- matrix(predictions, nrow = resolution, ncol = resolution, byrow = FALSE)
    values(r) <- as.vector(t(m[nrow(m):1, ]))

    writeRaster(r, path, format = "GTiff", overwrite = TRUE)
    invisible(r)
}

# ── Public entry point ───────────────────────────────────────────────────────

Spatial_Interpolation <- function(points_data, prediction_method,
                                  output_path, target_event = NULL) {
    resolution <- 100

    target_label <- resolve_target(points_data$event_type, target_event)
    ppp          <- prepare_point_data(points_data, target_label)
    grid         <- make_grid(ppp, resolution)

    # Dispatch to the appropriate fitter
    predictions <- switch(prediction_method,
        linear     = fit_linear(ppp, grid),
        orthogonal = fit_orthogonal(ppp, grid),
        splines    = fit_splines(ppp, grid),
        gam        = fit_gam(ppp, grid),
        kriging    = fit_kriging(ppp, grid),
        stop(paste("Unknown method:", prediction_method))
    )

    predictions_to_raster(predictions, ppp, grid, resolution, output_path)

    list(target_label = target_label, grid_resolution = resolution)
}
"""


def field_interpolation_predictor(
    df: pd.DataFrame,
    geom: gpd.GeoDataFrame,
    prediction_method: str,
    output_path: str,
    target_event: Optional[str] = None
) -> gpd.GeoDataFrame:
    """
    Python wrapper for R-based spatial interpolation predictor.
    
    Predicts occurrence probability of agricultural events or properties
    across a field area using spatial models.
    
    Parameters
    ----------
    df : pd.DataFrame
        DataFrame containing point observations with columns:
        - longitude: longitude coordinates
        - latitude: latitude coordinates
        - event_type: categorical event/property type
    geom : gpd.GeoDataFrame
        GeoDataFrame containing point geometries (for clipping)
    prediction_method : str
        Interpolation method:
        - "linear": logistic regression with linear lon+lat trend
        - "orthogonal": logistic regression with 3rd-order orthogonal polynomials
        - "splines": logistic regression with B-spline basis functions
        - "gam": Generalized Additive Model with 2D thin-plate smooth (recommended)
        - "kriging": Indicator Kriging with automatic variogram fitting
    output_path : str
        Path where the output raster will be saved
    target_event : str, optional
        Event type to predict. If None, last alphabetically is used.
        
    Returns
    -------
    gpd.GeoDataFrame
        GeoDataFrame with polygonized raster predictions clipped to
        the convex hull of input geometries
        
    Raises
    ------
    RuntimeError
        If required R packages are not installed
    ValueError
        If prediction_method is not one of the supported methods
    """
    # Validate prediction method
    valid_methods = ["linear", "orthogonal", "splines", "gam", "kriging"]
    if prediction_method not in valid_methods:
        raise ValueError(
            f"prediction_method must be one of {valid_methods}, "
            f"got '{prediction_method}'"
        )
    
    # Check if required R packages are installed
    check_packages = """
    required_packages <- c('sf', 'dplyr', 'raster', 'splines', 'mgcv', 'gstat', 'sp')
    missing_packages <- required_packages[!(required_packages %in% installed.packages()[,'Package'])]
    if(length(missing_packages) > 0) {
        stop(paste('Missing R packages:', paste(missing_packages, collapse=', '), 
                   '\nPlease install them in the Docker container.'))
    }
    """
    
    try:
        ro.r(check_packages)
    except Exception as e:
        error_msg = str(e)
        if "Missing R packages" in error_msg:
            raise RuntimeError(
                f"Error: {error_msg}\n\n"
                "Required R packages must be installed in the Docker container."
            ) from e
        raise
    
    # Convert pandas DataFrame to R object
    with conversion.localconverter(default_converter):
        with (ro.default_converter + pandas2ri.converter).context():
            r_df = ro.conversion.get_conversion().py2rpy(df)
        
        # Load R function
        ro.r(R_INTERPOLATION_FUNCTION)
        spatial_interpolation = ro.globalenv["Spatial_Interpolation"]
        
        # Convert target_event to R NULL if not provided
        if target_event is None:
            r_target_event = ro.NULL
        else:
            r_target_event = target_event
        
        # Run interpolation
        result = spatial_interpolation(r_df, prediction_method, output_path, r_target_event)
    
    # Convert raster to GeoDataFrame
    mask = None
    with rasterio.Env():
        with rasterio.open(output_path) as src:
            image = src.read(1)  # Read first band
            results = (
                {"properties": {"probability": v}, "geometry": s}
                for i, (s, v) in enumerate(
                    shapes(image, mask=mask, transform=src.transform)
                )
            )
    
    # Create GeoDataFrame from raster shapes
    gdf_polygonized = gpd.GeoDataFrame.from_features(list(results))
    gdf_polygonized = gdf_polygonized.set_crs("epsg:4326")
    
    # Clip to convex hull of input geometries
    area_mask = geom.to_crs(4326).unary_union.convex_hull
    gdf_polygonized = gdf_polygonized.clip(area_mask)
    
    # Round probability values
    gdf_polygonized['probability'] = gdf_polygonized['probability'].round(3)
    
    return gdf_polygonized
