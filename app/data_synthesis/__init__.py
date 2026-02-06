"""
Data synthesis module for agricultural field data.

This module provides utilities for loading delineated field data,
generating synthetic soil observations based on agronomic cycle scenarios,
and fragmenting large GeoJSON tiles for performance.
"""

from app.data_synthesis.field_loader import FieldLoader

from app.data_synthesis.soil_data_generator import (
    generate_soil_samples_in_region,
    generate_cycle_realizations,
    parse_bbox_from_geojson,
    CYCLE_SCENARIOS,
    FERTILITY_PHASES,
)

from app.data_synthesis.tile_fragmenter import TileFragmenter

__all__ = [
    'FieldLoader',
    'TileFragmenter',
    'generate_soil_samples_in_region',
    'generate_cycle_realizations',
    'parse_bbox_from_geojson',
    'CYCLE_SCENARIOS',
    'FERTILITY_PHASES',
]
