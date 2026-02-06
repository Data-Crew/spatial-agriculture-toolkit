"""
Generate synthetic soil property data based on agronomic cycles.

This module creates realistic soil property observations within a defined region R
using predefined agronomic scenarios that simulate temporal cycles of fertility,
degradation, and recovery. Each scenario defines a sequence of phases that are
distributed across N user-defined realizations (frames).
"""

import numpy as np
import pandas as pd
import geopandas as gpd
from shapely.geometry import Polygon, Point
from typing import Tuple, Optional, List, Dict
import random


# =============================================================================
# INDIVIDUAL FERTILITY PHASES (building blocks for cycles)
# =============================================================================
FERTILITY_PHASES = {
    'alta_fertilidad': {
        'fertility_idx': 5, 'degradation_idx': 0,
        'pH': (6.0, 7.0), 'MO_pct': (3.0, 6.0),
        'CIC_cmol': (20, 30), 'SatBases_pct': (75, 95),
        'label': 'High Fertility',
        'description': 'Nutrient-rich soil, optimal for high-yield crops',
    },
    'buena_fertilidad': {
        'fertility_idx': 4, 'degradation_idx': 1,
        'pH': (5.5, 6.5), 'MO_pct': (2.0, 4.0),
        'CIC_cmol': (15, 22), 'SatBases_pct': (50, 70),
        'label': 'Good Fertility',
        'description': 'Productive soil, suitable for most crops',
    },
    'fertilidad_moderada': {
        'fertility_idx': 3, 'degradation_idx': 2,
        'pH': (5.5, 6.5), 'MO_pct': (2.0, 3.5),
        'CIC_cmol': (12, 18), 'SatBases_pct': (40, 60),
        'label': 'Moderate Fertility',
        'description': 'Average conditions, requires amendments',
    },
    'baja_fertilidad': {
        'fertility_idx': 2, 'degradation_idx': 3,
        'pH': (4.5, 5.5), 'MO_pct': (1.5, 3.0),
        'CIC_cmol': (8, 15), 'SatBases_pct': (20, 40),
        'label': 'Low Fertility',
        'description': 'Acidification and nutrient depletion',
    },
    'muy_baja_fertilidad': {
        'fertility_idx': 1, 'degradation_idx': 4,
        'pH': (4.5, 5.2), 'MO_pct': (2.0, 3.5),
        'CIC_cmol': (4, 8), 'SatBases_pct': (5, 15),
        'label': 'Very Low Fertility',
        'description': 'Severely degraded, very low productivity',
    },
    'salinizacion': {
        'fertility_idx': 2, 'degradation_idx': 4,
        'pH': (7.5, 8.5), 'MO_pct': (0.5, 1.5),
        'CIC_cmol': (8, 15), 'SatBases_pct': (90, 100),
        'label': 'Salinization',
        'description': 'Salt accumulation, toxic to roots',
    },
    'sodificacion': {
        'fertility_idx': 2, 'degradation_idx': 4,
        'pH': (8.0, 9.0), 'MO_pct': (1.0, 2.0),
        'CIC_cmol': (25, 40), 'SatBases_pct': (85, 95),
        'label': 'Sodification',
        'description': 'Sodium damage, structural collapse',
    },
}

# Keep backward compatibility
FERTILITY_SCENARIOS = FERTILITY_PHASES

# =============================================================================
# PREDEFINED AGRONOMIC CYCLE SCENARIOS
# =============================================================================
CYCLE_SCENARIOS = {
    'degradation_by_intensive_use': {
        'name': 'Degradation by Intensive Use',
        'description': (
            'Simulates progressive soil degradation caused by intensive '
            'agricultural practices without adequate management. Starts from '
            'high fertility and gradually declines through nutrient extraction, '
            'loss of organic matter, and acidification.'
        ),
        'phases': [
            'alta_fertilidad',
            'buena_fertilidad',
            'fertilidad_moderada',
            'baja_fertilidad',
            'muy_baja_fertilidad',
        ],
    },
    'salinization_by_irrigation': {
        'name': 'Salinization by Irrigation',
        'description': (
            'Simulates soil salinization from poorly managed irrigation in '
            'arid/semi-arid zones. Fertility declines as salts accumulate '
            'in the root zone, eventually rendering the soil unproductive.'
        ),
        'phases': [
            'buena_fertilidad',
            'fertilidad_moderada',
            'baja_fertilidad',
            'salinizacion',
        ],
    },
    'sodification_process': {
        'name': 'Sodification Process',
        'description': (
            'Simulates progressive sodium accumulation that degrades soil '
            'structure. Common in irrigated areas with high-sodium water. '
            'Leads to impermeability and crop failure.'
        ),
        'phases': [
            'buena_fertilidad',
            'fertilidad_moderada',
            'baja_fertilidad',
            'sodificacion',
        ],
    },
    'recovery_with_management': {
        'name': 'Recovery with Management',
        'description': (
            'Simulates soil rehabilitation through good management practices: '
            'cover crops, crop rotation, organic amendments, and liming. '
            'A degraded soil gradually recovers productive capacity.'
        ),
        'phases': [
            'muy_baja_fertilidad',
            'baja_fertilidad',
            'fertilidad_moderada',
            'buena_fertilidad',
            'alta_fertilidad',
        ],
    },
    'annual_crop_cycle': {
        'name': 'Annual Crop Cycle',
        'description': (
            'Simulates a typical annual crop cycle: pre-planting fertility, '
            'nutrient consumption during growth, peak extraction at harvest, '
            'post-harvest decline, and partial recovery during fallow.'
        ),
        'phases': [
            'buena_fertilidad',       # pre-planting (after fertilization)
            'alta_fertilidad',        # early growth (nutrients available)
            'buena_fertilidad',       # mid growth (consumption)
            'fertilidad_moderada',    # peak extraction
            'baja_fertilidad',        # post-harvest
            'fertilidad_moderada',    # fallow recovery
        ],
    },
    'monoculture_decline': {
        'name': 'Monoculture Decline',
        'description': (
            'Simulates the gradual decline in soil health caused by continuous '
            'monoculture without rotation. Fertility drops steadily as specific '
            'nutrients are depleted and soil biology deteriorates.'
        ),
        'phases': [
            'alta_fertilidad',
            'buena_fertilidad',
            'buena_fertilidad',
            'fertilidad_moderada',
            'fertilidad_moderada',
            'baja_fertilidad',
            'baja_fertilidad',
            'muy_baja_fertilidad',
        ],
    },
    'stable_productive_field': {
        'name': 'Stable Productive Field',
        'description': (
            'Simulates a well-managed field that maintains stable fertility '
            'over time with minor seasonal fluctuations. Represents best-practice '
            'agriculture with rotation, cover crops, and nutrient management.'
        ),
        'phases': [
            'buena_fertilidad',
            'alta_fertilidad',
            'buena_fertilidad',
            'buena_fertilidad',
        ],
    },
}


# =============================================================================
# CORE FUNCTIONS
# =============================================================================

def _generate_single_realization(
    bbox: Tuple[float, float, float, float],
    n_samples: int,
    phase_name: str,
    seed: int,
    realization_id: int,
) -> pd.DataFrame:
    """Generate a single realization of points for a given fertility phase."""
    np.random.seed(seed)
    random.seed(seed)

    min_lon, min_lat, max_lon, max_lat = bbox
    phase = FERTILITY_PHASES[phase_name]
    fertility_idx = phase['fertility_idx']
    degradation_idx = phase['degradation_idx']

    # Random points
    lons = np.random.uniform(min_lon, max_lon, n_samples)
    lats = np.random.uniform(min_lat, max_lat, n_samples)

    # Normalized coords for spatial variation
    lon_n = (lons - min_lon) / max(max_lon - min_lon, 1e-9)
    lat_n = (lats - min_lat) / max(max_lat - min_lat, 1e-9)

    def _spatial(base_range, amplitude, freq_x, freq_y):
        base = np.random.uniform(base_range[0], base_range[1], n_samples)
        spatial = amplitude * np.sin(freq_x * np.pi * lon_n) * np.cos(freq_y * np.pi * lat_n)
        return base + spatial

    pH_vals = np.clip(_spatial(phase['pH'], 0.3, 2, 2), 4.0, 9.0)
    MO_vals = np.clip(_spatial(phase['MO_pct'], 0.5, 3, 3), 0.1, 50.0)
    CIC_vals = np.clip(_spatial(phase['CIC_cmol'], 2, 2, 2), 2, 100)
    SatB_vals = np.clip(_spatial(phase['SatBases_pct'], 5, 1, 1), 0, 100)

    # Use English label for event_type and phase columns
    phase_label = phase.get('label', phase_name)

    return pd.DataFrame({
        'longitude': lons,
        'latitude': lats,
        'realization': realization_id,
        'phase': phase_label,
        'event_type': phase_label,
        'fertility_index': fertility_idx,
        'degradation_index': degradation_idx,
        'pH': np.round(pH_vals, 2),
        'organic_matter_pct': np.round(MO_vals, 2),
        'CEC_cmol': np.round(CIC_vals, 1),
        'base_saturation_pct': np.round(SatB_vals, 1),
        'acidity_risk': (pH_vals < 5.5).astype(int),
        'salinity_risk': ((pH_vals > 7.5) & (SatB_vals > 90)).astype(int),
    })


def generate_cycle_realizations(
    bbox: Tuple[float, float, float, float],
    cycle_name: str,
    n_realizations: int = 12,
    n_samples_per_realization: int = 50,
    seed: int = 42,
) -> gpd.GeoDataFrame:
    """
    Generate all realizations for a predefined agronomic cycle.

    The cycle's phases are evenly distributed across the requested number
    of realizations.  For example, a cycle with 5 phases and 12 realizations
    will interpolate the phases so that the transition is gradual.

    Parameters
    ----------
    bbox : tuple
        (min_lon, min_lat, max_lon, max_lat)
    cycle_name : str
        Key from CYCLE_SCENARIOS.
    n_realizations : int
        Number of frames / realizations to generate.
    n_samples_per_realization : int
        Points per realization.
    seed : int
        Base random seed (each realization uses seed + i).

    Returns
    -------
    gpd.GeoDataFrame
        Single GeoDataFrame with all realizations.  Contains a
        ``realization`` column (1‥N) that can be used to filter
        in Kepler.
    """
    if cycle_name not in CYCLE_SCENARIOS:
        raise ValueError(
            f"Unknown cycle: '{cycle_name}'. "
            f"Available: {list(CYCLE_SCENARIOS.keys())}"
        )

    phases = CYCLE_SCENARIOS[cycle_name]['phases']

    # Map each realization index to a phase using linear interpolation
    phase_indices = np.linspace(0, len(phases) - 1, n_realizations)
    assigned_phases = [phases[int(round(idx))] for idx in phase_indices]

    all_frames: List[pd.DataFrame] = []
    for i, phase_name in enumerate(assigned_phases):
        df = _generate_single_realization(
            bbox=bbox,
            n_samples=n_samples_per_realization,
            phase_name=phase_name,
            seed=seed + i,
            realization_id=i + 1,
        )
        all_frames.append(df)

    combined = pd.concat(all_frames, ignore_index=True)

    gdf = gpd.GeoDataFrame(
        combined,
        geometry=gpd.points_from_xy(combined['longitude'], combined['latitude']),
        crs='EPSG:4326',
    )
    return gdf


# Keep the old single-realization function for backward compatibility
def generate_soil_samples_in_region(
    bbox: Tuple[float, float, float, float],
    n_samples: int = 50,
    scenario: Optional[str] = None,
    seed: Optional[int] = None,
    occurrence_date: Optional[str] = None,
) -> gpd.GeoDataFrame:
    """Generate a single realization (backward compatible wrapper)."""
    phase_name = scenario if scenario and scenario in FERTILITY_PHASES else 'fertilidad_moderada'
    df = _generate_single_realization(
        bbox=bbox,
        n_samples=n_samples,
        phase_name=phase_name,
        seed=seed or 42,
        realization_id=1,
    )
    if occurrence_date:
        df['occurrence_date'] = occurrence_date

    gdf = gpd.GeoDataFrame(
        df, geometry=gpd.points_from_xy(df['longitude'], df['latitude']),
        crs='EPSG:4326',
    )
    return gdf


def parse_bbox_from_geojson(geojson_str: str) -> Optional[Tuple[float, float, float, float]]:
    """Parse bounding box from GeoJSON Polygon string."""
    try:
        import json
        geojson_data = json.loads(geojson_str.strip())

        if isinstance(geojson_data, dict):
            if geojson_data.get('type') == 'Polygon':
                coords = geojson_data.get('coordinates', [])
                if coords and len(coords) > 0:
                    ring = coords[0]
                    lons = [c[0] for c in ring]
                    lats = [c[1] for c in ring]
                    return (min(lons), min(lats), max(lons), max(lats))
            elif (geojson_data.get('type') == 'Feature'
                  and geojson_data.get('geometry', {}).get('type') == 'Polygon'):
                coords = geojson_data['geometry'].get('coordinates', [])
                if coords and len(coords) > 0:
                    ring = coords[0]
                    lons = [c[0] for c in ring]
                    lats = [c[1] for c in ring]
                    return (min(lons), min(lats), max(lons), max(lats))

        return None
    except Exception:
        return None
