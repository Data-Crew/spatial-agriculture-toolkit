"""
Load delineated field data with bbox filtering.

This module loads GeoJSON files with delineated fields and allows filtering
by bounding box to handle large datasets efficiently.
"""

import ast
import os
import re
import geopandas as gpd
import pandas as pd
from shapely.geometry import box
from typing import Optional, Tuple, Dict, List
import json


class FieldLoader:
    """
    Loader for delineated field data with bbox filtering.
    
    Allows loading GeoJSON files with filtering by bounding box,
    enabling users to work with large datasets by focusing on
    specific geographic areas.
    """
    
    def __init__(self, base_dir: str = None):
        """
        Initialize the loader.
        
        Parameters
        ----------
        base_dir : str, optional
            Base directory containing delin_fields. If None, uses default path.
        """
        if base_dir is None:
            # Default to the project data directory
            import os
            # Get project root (assuming this file is in app/data_synthesis/)
            current_file = os.path.abspath(__file__)
            project_root = os.path.dirname(os.path.dirname(os.path.dirname(current_file)))
            self.base_dir = os.path.join(project_root, 'data')
        else:
            self.base_dir = base_dir
    
    def list_available_tiles(self) -> List[str]:
        """
        List available GeoJSON files (tiles) in the directory.
        
        Returns
        -------
        list of str
            List of available tile filenames
        """
        if not os.path.exists(self.base_dir):
            return []
        
        # List top-level GeoJSON files (non-fragmented tiles)
        geojson_files = [
            f for f in os.listdir(self.base_dir)
            if f.endswith('.geojson') and not f.startswith('.') and 'fragment' not in f
        ]
        
        # Also list fragment directories (subdirectories with fragments)
        fragment_dirs = [
            d for d in os.listdir(self.base_dir)
            if os.path.isdir(os.path.join(self.base_dir, d)) and not d.startswith('.')
        ]
        
        # For fragment directories, list fragments
        for frag_dir in fragment_dirs:
            frag_path = os.path.join(self.base_dir, frag_dir)
            fragments = [
                os.path.join(frag_dir, f) for f in os.listdir(frag_path)
                if f.endswith('.geojson') and 'fragment' in f
            ]
            if fragments:
                # Add fragments as options
                geojson_files.extend(sorted(fragments))
        
        return sorted(geojson_files)
    
    def load_fields_bbox(
        self,
        tile_name: str,
        bbox: Tuple[float, float, float, float],
        crs: str = 'EPSG:4326',
        max_fields: int = 5000
    ) -> gpd.GeoDataFrame:
        """
        Load fields from a tile filtered by bounding box.
        
        Parameters
        ----------
        tile_name : str
            Name of the GeoJSON file (tile) to load
        bbox : tuple
            Bounding box as (min_lon, min_lat, max_lon, max_lat)
        crs : str
            CRS for the bbox coordinates
        
        Returns
        -------
        gpd.GeoDataFrame
            Filtered GeoDataFrame with fields within the bbox
        """
        # Handle fragment paths (subdirectory/fragment_name.geojson)
        if '/' in tile_name:
            filepath = os.path.join(self.base_dir, tile_name)
        else:
            filepath = os.path.join(self.base_dir, tile_name)
        
        if not os.path.exists(filepath):
            raise FileNotFoundError(f"Tile file not found: {filepath}")
        
        # Create bbox geometry
        min_lon, min_lat, max_lon, max_lat = bbox
        bbox_geom = box(min_lon, min_lat, max_lon, max_lat)
        
        # Load GeoJSON with bbox filter using geopandas
        # Note: geopandas doesn't directly support bbox filtering in read_file,
        # so we'll load and filter manually
        # For very large files, we can use fiona with bbox parameter
        try:
            # Try using fiona's bbox parameter for efficient filtering
            import fiona
            
            # Read with bbox filter using fiona
            # Note: fiona bbox expects (minx, miny, maxx, maxy)
            # Limit the number of features to avoid memory issues
            features = []
            feature_count = 0
            
            with fiona.open(filepath, bbox=bbox) as src:
                for feature in src:
                    features.append(feature)
                    feature_count += 1
                    # Stop if we exceed max_fields to avoid memory issues
                    if feature_count >= max_fields:
                        break
            
            if not features:
                # Return empty GeoDataFrame with correct schema
                return gpd.GeoDataFrame()
            
            # Convert to GeoDataFrame
            gdf = gpd.GeoDataFrame.from_features(features, crs=src.crs)
            
            # Ensure CRS match
            if gdf.crs != crs:
                gdf = gdf.to_crs(crs)
            
            # If we hit the limit, warn (but return what we have)
            if feature_count >= max_fields:
                import warnings
                warnings.warn(f"Loaded {max_fields} fields (limit reached). Consider using a smaller bbox or higher zoom level.")
            
        except Exception as e:
            # Fallback: load full file and filter (slower but works)
            # This is necessary for very large files or when fiona bbox doesn't work
            import warnings
            warnings.warn(f"Could not use bbox filter efficiently: {e}. Loading full file and filtering...")
            
            # For very large files, we need to be careful
            # Try to read in chunks or use spatial index
            gdf = gpd.read_file(filepath)
            
            # Ensure CRS match
            if gdf.crs != crs:
                gdf = gdf.to_crs(crs)
            
            # Filter by bbox using spatial index for efficiency
            if len(gdf) > 0:
                # Create bbox geometry for filtering
                bbox_gdf = gpd.GeoDataFrame([1], geometry=[bbox_geom], crs=crs)
                # Use spatial index if available
                if hasattr(gdf, 'sindex') and gdf.sindex is not None:
                    # Use spatial index for faster filtering
                    possible_matches_index = list(gdf.sindex.intersection(bbox_geom.bounds))
                    gdf_filtered = gdf.iloc[possible_matches_index]
                    # Final intersection check
                    gdf = gdf_filtered[gdf_filtered.intersects(bbox_gdf.geometry.iloc[0])]
                else:
                    # Fallback to simple intersection
                    gdf = gdf[gdf.intersects(bbox_gdf.geometry.iloc[0])]
                
                # Limit to max_fields to avoid memory issues
                if len(gdf) > max_fields:
                    gdf = gdf.head(max_fields)
                    import warnings
                    warnings.warn(f"Limited to {max_fields} fields. Consider using a smaller bbox or higher zoom level.")
            else:
                gdf = gpd.GeoDataFrame()
        
        return gdf
    
    def load_fields_zoom_level(
        self,
        tile_name: str,
        center_lon: float,
        center_lat: float,
        zoom_level: int = 10,
        max_fields: int = 5000
    ) -> gpd.GeoDataFrame:
        """
        Load fields for a specific zoom level around a center point.
        
        Parameters
        ----------
        tile_name : str
            Name of the GeoJSON file (tile) to load
        center_lon : float
            Center longitude
        center_lat : float
            Center latitude
        zoom_level : int
            Zoom level (higher = more zoomed in = smaller area)
            Typical values: 8-12 for field-level views
        
        Returns
        -------
        gpd.GeoDataFrame
            Filtered GeoDataFrame
        """
        # Calculate bbox size based on zoom level
        # At zoom level 10, approximately 0.1 degrees per tile
        # This is approximate and can be adjusted
        zoom_to_deg = {
            8: 1.0,   # Very wide view
            9: 0.5,   # Wide view
            10: 0.25, # Medium view
            11: 0.1,  # Close view
            12: 0.05, # Very close view
            13: 0.025 # Extremely close view
        }
        
        deg_size = zoom_to_deg.get(zoom_level, 0.25)
        half_size = deg_size / 2
        
        bbox = (
            center_lon - half_size,
            center_lat - half_size,
            center_lon + half_size,
            center_lat + half_size
        )
        
        # Load fields with the calculated bbox
        gdf = self.load_fields_bbox(tile_name, bbox, max_fields=max_fields)
        
        # If no fields found, try with a slightly larger area (fallback)
        # But only if we haven't hit the limit
        if len(gdf) == 0 and zoom_level >= 10 and len(gdf) < max_fields:
            # Try with 2x the area
            larger_half_size = half_size * 2
            larger_bbox = (
                center_lon - larger_half_size,
                center_lat - larger_half_size,
                center_lon + larger_half_size,
                center_lat + larger_half_size
            )
            gdf = self.load_fields_bbox(tile_name, larger_bbox, max_fields=max_fields)
        
        return gdf
    
    def load_fields(
        self,
        tile_name: str,
        max_fields: int = 5000
    ) -> gpd.GeoDataFrame:
        """
        Load fields from a tile without any filtering.
        
        Parameters
        ----------
        tile_name : str
            Name of the GeoJSON file (tile) to load
        max_fields : int
            Maximum number of fields to load (to avoid memory issues)
        
        Returns
        -------
        gpd.GeoDataFrame
            GeoDataFrame with fields
        """
        # Handle fragment paths (subdirectory/fragment_name.geojson)
        if '/' in tile_name:
            filepath = os.path.join(self.base_dir, tile_name)
        else:
            filepath = os.path.join(self.base_dir, tile_name)
        
        if not os.path.exists(filepath):
            raise FileNotFoundError(f"Tile file not found: {filepath}")
        
        # Load GeoJSON file
        try:
            # Try using fiona for efficient reading with limit
            import fiona
            
            features = []
            feature_count = 0
            
            with fiona.open(filepath) as src:
                for feature in src:
                    features.append(feature)
                    feature_count += 1
                    # Stop if we exceed max_fields to avoid memory issues
                    if feature_count >= max_fields:
                        break
            
            if not features:
                return gpd.GeoDataFrame()
            
            # Convert to GeoDataFrame
            gdf = gpd.GeoDataFrame.from_features(features, crs=src.crs)
            
            # Ensure CRS is set
            if gdf.crs is None:
                gdf.set_crs('EPSG:4326', inplace=True)
            
        except Exception as e:
            # Fallback: use geopandas directly
            import warnings
            warnings.warn(f"Could not use fiona efficiently: {e}. Loading with geopandas...")
            
            gdf = gpd.read_file(filepath)
            
            # Limit to max_fields if needed
            if len(gdf) > max_fields:
                gdf = gdf.head(max_fields)
                import warnings
                warnings.warn(f"Limited to {max_fields} fields.")
        
        return gdf
    
    def _find_props_csv_path(self, tile_name: str) -> Optional[str]:
        """Resolve the properties CSV path for a tile or fragment."""
        if not tile_name or not os.path.exists(self.base_dir):
            return None

        base_name = tile_name.replace('.geojson', '')

        # Fragmented tile: 16tgk/16tgk_fragment_00_00.geojson -> props__fd_16tgk_*.csv
        if '/' in base_name:
            tile_key = base_name.split('/')[0]
            matches = sorted(
                f for f in os.listdir(self.base_dir)
                if f.endswith('.csv') and f.startswith(f'props__fd_{tile_key}_')
            )
            if matches:
                return os.path.join(self.base_dir, matches[0])
            return None

        if base_name.startswith('_demo_crop_fd_'):
            base_name = base_name.replace('_demo_crop_fd_', '')

        csv_patterns = [
            f'props__fd_{base_name}.csv',
            f'props_{base_name}.csv',
        ]
        if '_' in base_name:
            parts = base_name.split('_')
            if len(parts) >= 2:
                csv_patterns.insert(0, f'props__fd_{parts[0]}_{parts[-1]}.csv')

        for pattern in csv_patterns:
            potential_path = os.path.join(self.base_dir, pattern)
            if os.path.exists(potential_path):
                return potential_path
        return None

    def load_properties_csv(self, tile_name: str = None) -> pd.DataFrame:
        """
        Load properties CSV file for a tile.
        
        Parameters
        ----------
        tile_name : str, optional
            Name of the GeoJSON file (tile). If None, tries to find any CSV.
        
        Returns
        -------
        pd.DataFrame
            DataFrame with field properties
        """
        if tile_name:
            csv_path = self._find_props_csv_path(tile_name)
        else:
            csv_path = None

        if csv_path is None:
            if tile_name:
                return pd.DataFrame()
            csv_files = sorted(
                f for f in os.listdir(self.base_dir) if f.endswith('.csv')
            )
            if not csv_files:
                return pd.DataFrame()
            csv_path = os.path.join(self.base_dir, csv_files[0])
        
        # Load CSV
        df = pd.read_csv(csv_path)
        
        # Parse the 'props' column if it's a string representation of dict.
        # Prefer ast.literal_eval because the CSV stores Python-style dicts
        # (single quotes); fall back to json.loads for JSON-compliant strings.
        if 'props' in df.columns:
            try:
                df['props'] = df['props'].apply(
                    lambda x: ast.literal_eval(x) if isinstance(x, str) else x
                )
            except Exception:
                try:
                    df['props'] = df['props'].apply(
                        lambda x: json.loads(x) if isinstance(x, str) else x
                    )
                except Exception:
                    pass  # Keep as is if parsing fails

        return df

    def expand_props_dict(self, props: dict) -> dict:
        """Expand one field ``props`` dict into flat analysis columns."""
        from collections import Counter

        record: Dict = {}
        if not isinstance(props, dict):
            return record

        for key in ('area', 'flatness', 'perimeter', 'confidence',
                    'center_lat', 'center_lng'):
            if key in props:
                record[key] = props[key]

        cdl = props.get('cdl_stats', {})
        if cdl and 'year' in cdl and 'crops' in cdl:
            years = cdl['year']
            crops = cdl['crops']
            crop_pcts = cdl.get('crop_percentages', [None] * len(years))
            crop_ids = cdl.get('crop_ids', [None] * len(years))

            for y, crop, pct, cid in zip(years, crops, crop_pcts, crop_ids):
                record[f'crop_{y}'] = crop
                record[f'crop_pct_{y}'] = pct
                record[f'crop_id_{y}'] = cid

            crop_counts = Counter(crops)
            total_years = len(years)
            if total_years:
                for crop_name, count in crop_counts.items():
                    col_name = f'freq_{str(crop_name).replace(" ", "_")}'
                    record[col_name] = round(count / total_years, 4)
            return record

        # GeoJSON inline format: crops_2008, crop_percentage_2008, crops_ids_2008
        years = sorted({
            int(match.group(1))
            for key in props
            if (match := re.match(r'crops_(\d{4})$', key))
        })
        crops = []
        for year in years:
            crop = props.get(f'crops_{year}')
            record[f'crop_{year}'] = crop
            if f'crop_percentage_{year}' in props:
                record[f'crop_pct_{year}'] = props[f'crop_percentage_{year}']
            if f'crops_ids_{year}' in props:
                record[f'crop_id_{year}'] = props[f'crops_ids_{year}']
            if crop is not None:
                crops.append(crop)

        if crops:
            crop_counts = Counter(crops)
            total_years = len(crops)
            for crop_name, count in crop_counts.items():
                col_name = f'freq_{str(crop_name).replace(" ", "_")}'
                record[col_name] = round(count / total_years, 4)

        return record

    def expand_cdl_properties(self, props_df: pd.DataFrame) -> pd.DataFrame:
        """Expand the ``props`` column into individual analysis-ready columns.

        The CSV stores a nested ``props`` dict per field with scalar attributes
        (area, flatness, ...) and a ``cdl_stats`` sub-dict with per-year crops.
        GeoJSON tiles may instead embed a flat ``props`` dict on each feature.
        This flattens either format into columns suitable for Moran I analysis:

        - ``area``, ``flatness``, ``perimeter``, ``confidence``, ``center_lat``,
          ``center_lng`` (when present)
        - ``crop_{year}``, ``crop_pct_{year}``, ``crop_id_{year}`` for each year
        - ``freq_{crop_name}`` = fraction of years that crop was dominant
        """
        records = []
        for _, row in props_df.iterrows():
            record = {'id': row['id']}
            record.update(self.expand_props_dict(row.get('props')))
            records.append(record)

        return pd.DataFrame(records)

    @staticmethod
    def _is_enriched(gdf: gpd.GeoDataFrame) -> bool:
        """True when scalar + crop indicator columns are present."""
        if gdf is None or gdf.empty:
            return False
        has_scalars = any(c in gdf.columns for c in ('area', 'flatness'))
        has_crop_metrics = any(
            c.startswith('freq_') or c.startswith('crop_pct_')
            for c in gdf.columns
        )
        return has_scalars and has_crop_metrics

    def _expand_gdf_inline_props(self, gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
        """Expand embedded GeoJSON ``props`` dicts into top-level columns."""
        if 'props' not in gdf.columns:
            return gdf

        records = []
        for _, row in gdf.iterrows():
            record = {'id': str(row['id'])}
            record.update(self.expand_props_dict(row.get('props')))
            records.append(record)

        if not records:
            return gdf.drop(columns=['props'], errors='ignore')

        expanded = pd.DataFrame(records)
        expanded['id'] = expanded['id'].astype(str)
        gdf = gdf.drop(columns=['props'], errors='ignore')
        gdf['id'] = gdf['id'].astype(str)

        overlap = set(gdf.columns) & set(expanded.columns) - {'id'}
        if overlap:
            gdf = gdf.drop(columns=list(overlap))

        return gdf.merge(expanded, on='id', how='left')

    def load_fields_with_properties(
        self,
        tile_name: str,
        max_fields: int = 5000,
    ) -> gpd.GeoDataFrame:
        """Load fields GeoJSON and merge with expanded CDL properties from CSV.

        Falls back to the base fields when no properties CSV can be resolved.
        """
        gdf = self.load_fields(tile_name, max_fields=max_fields)
        if gdf.empty:
            return gdf

        props_df = self.load_properties_csv(tile_name)

        if not props_df.empty and 'props' in props_df.columns:
            try:
                gdf['id'] = gdf['id'].astype(str)
                props_df = props_df.copy()
                props_df['id'] = props_df['id'].astype(str)
                field_ids = set(gdf['id'])
                props_df = props_df[props_df['id'].isin(field_ids)]
                expanded = self.expand_cdl_properties(props_df)
                expanded['id'] = expanded['id'].astype(str)
                overlap = set(gdf.columns) & set(expanded.columns) - {'id', 'geometry'}
                if overlap:
                    gdf = gdf.drop(columns=list(overlap))
                gdf = gdf.merge(expanded, on='id', how='left')
            except Exception as e:
                import warnings
                warnings.warn(f"Could not merge properties: {e}")

        if not self._is_enriched(gdf):
            gdf = self._expand_gdf_inline_props(gdf)
        else:
            gdf = gdf.drop(columns=['props'], errors='ignore')

        return gdf
    
    def get_tile_bounds(self, tile_name: str) -> Tuple[float, float, float, float]:
        """
        Get the bounding box of a tile without loading all data.
        
        Parameters
        ----------
        tile_name : str
            Name of the GeoJSON file
        
        Returns
        -------
        tuple
            (min_lon, min_lat, max_lon, max_lat)
        """
        filepath = os.path.join(self.base_dir, tile_name)
        
        # Use fiona to get bounds without loading all features
        import fiona
        with fiona.open(filepath) as src:
            bounds = src.bounds
        
        return bounds  # (minx, miny, maxx, maxy)


if __name__ == "__main__":
    # Test the loader
    loader = FieldLoader()
    
    print("Available tiles:")
    tiles = loader.list_available_tiles()
    for tile in tiles:
        print(f"  - {tile}")
    
    if tiles:
        tile_name = tiles[0]
        print(f"\nLoading sample from: {tile_name}")
        
        # Get tile bounds
        bounds = loader.get_tile_bounds(tile_name)
        print(f"Tile bounds: {bounds}")
        
        # Load a small sample around center
        center_lon = (bounds[0] + bounds[2]) / 2
        center_lat = (bounds[1] + bounds[3]) / 2
        
        print(f"\nLoading fields around center ({center_lon}, {center_lat}) at zoom 11...")
        gdf = loader.load_fields_zoom_level(tile_name, center_lon, center_lat, zoom_level=11)
        print(f"Loaded {len(gdf)} fields")
        print(f"Columns: {list(gdf.columns)}")
