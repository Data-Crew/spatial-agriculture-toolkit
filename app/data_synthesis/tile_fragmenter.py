"""
Fragment large GeoJSON tiles into smaller files for better performance.

This module splits large tile files into smaller fragments based on a grid,
making it easier to load and work with large datasets in Streamlit.
"""

import os
import json
import geopandas as gpd
from shapely.geometry import box, shape
from typing import Tuple, List
import math


class TileFragmenter:
    """
    Fragment large GeoJSON tiles into smaller files.
    """
    
    def __init__(self, data_dir: str = None):
        """
        Initialize the fragmenter.
        
        Parameters
        ----------
        data_dir : str, optional
            Directory containing tiles. If None, uses default.
        """
        if data_dir is None:
            import os
            current_file = os.path.abspath(__file__)
            project_root = os.path.dirname(os.path.dirname(os.path.dirname(current_file)))
            self.data_dir = os.path.join(project_root, 'data')
        else:
            self.data_dir = data_dir
    
    def fragment_tile(
        self,
        tile_name: str,
        grid_size: int = 4,
        output_subdir: str = None
    ) -> List[str]:
        """
        Fragment a tile into smaller files based on a grid.
        
        Parameters
        ----------
        tile_name : str
            Name of the GeoJSON file to fragment
        grid_size : int
            Number of fragments per side (e.g., 4 = 4x4 = 16 fragments)
        output_subdir : str, optional
            Subdirectory name for fragments. If None, uses tile name without extension.
        
        Returns
        -------
        list of str
            List of fragment filenames created
        """
        filepath = os.path.join(self.data_dir, tile_name)
        
        if not os.path.exists(filepath):
            raise FileNotFoundError(f"Tile file not found: {filepath}")
        
        # Determine output directory
        if output_subdir is None:
            base_name = tile_name.replace('.geojson', '').replace('_demo_crop_fd_', '')
            output_subdir = base_name.split('_')[0] if '_' in base_name else base_name
        
        fragment_dir = os.path.join(self.data_dir, output_subdir)
        os.makedirs(fragment_dir, exist_ok=True)
        
        # Get tile bounds and schema
        import fiona
        with fiona.open(filepath) as src:
            bounds = src.bounds
            crs = src.crs
            schema = src.schema  # Get schema from original file
        
        min_lon, min_lat, max_lon, max_lat = bounds
        
        # Calculate grid cell size
        lon_range = max_lon - min_lon
        lat_range = max_lat - min_lat
        cell_lon_size = lon_range / grid_size
        cell_lat_size = lat_range / grid_size
        
        fragment_files = []
        
        # Process each grid cell
        for row in range(grid_size):
            for col in range(grid_size):
                # Calculate cell bounds
                cell_min_lon = min_lon + col * cell_lon_size
                cell_max_lon = min_lon + (col + 1) * cell_lon_size
                cell_min_lat = min_lat + row * cell_lat_size
                cell_max_lat = min_lat + (row + 1) * cell_lat_size
                
                cell_bbox = (cell_min_lon, cell_min_lat, cell_max_lon, cell_max_lat)
                
                # Load features within this cell using bbox filter
                # Strategy: Assign features to the cell that contains their centroid
                # This avoids duplicating features across multiple fragments
                features = []
                cell_geom = box(cell_min_lon, cell_min_lat, cell_max_lon, cell_max_lat)
                
                with fiona.open(filepath, bbox=cell_bbox) as src_bbox:
                    for feature in src_bbox:
                        # Parse geometry and check if centroid is within the cell
                        try:
                            geom = shape(feature['geometry'])
                            # Use centroid to assign feature to a single cell
                            centroid = geom.centroid
                            if cell_geom.contains(centroid):
                                features.append(feature)
                        except Exception as e:
                            # If geometry parsing fails, skip this feature
                            # (better to skip than include incorrectly)
                            continue
                
                if features:
                    # Create fragment filename
                    fragment_name = f"{output_subdir}_fragment_{row:02d}_{col:02d}.geojson"
                    fragment_path = os.path.join(fragment_dir, fragment_name)
                    
                    # Write fragment using the schema from original file
                    with fiona.open(
                        fragment_path,
                        'w',
                        driver='GeoJSON',
                        crs=crs,
                        schema=schema
                    ) as dst:
                        dst.writerecords(features)
                    
                    fragment_files.append(fragment_name)
                    print(f"Created fragment: {fragment_name} with {len(features)} features")
        
        return fragment_files
    
    def list_fragments(self, tile_base_name: str) -> List[str]:
        """
        List available fragments for a tile.
        
        Parameters
        ----------
        tile_base_name : str
            Base name of the tile (e.g., "16tgk")
        
        Returns
        -------
        list of str
            List of fragment filenames
        """
        fragment_dir = os.path.join(self.data_dir, tile_base_name)
        
        if not os.path.exists(fragment_dir):
            return []
        
        fragments = [
            f for f in os.listdir(fragment_dir)
            if f.endswith('.geojson') and 'fragment' in f
        ]
        
        return sorted(fragments)
    
    def get_fragment_bounds(self, fragment_name: str, tile_base_name: str) -> Tuple[float, float, float, float]:
        """
        Get bounds of a fragment.
        
        Parameters
        ----------
        fragment_name : str
            Name of fragment file
        tile_base_name : str
            Base name of tile (subdirectory)
        
        Returns
        -------
        tuple
            (min_lon, min_lat, max_lon, max_lat)
        """
        fragment_path = os.path.join(self.data_dir, tile_base_name, fragment_name)
        
        import fiona
        with fiona.open(fragment_path) as src:
            return src.bounds


if __name__ == "__main__":
    # Example usage
    fragmenter = TileFragmenter()
    
    # Fragment a tile
    tile_name = "_demo_crop_fd_16tgk_10091004_v1.geojson"
    print(f"Fragmenting {tile_name}...")
    
    fragments = fragmenter.fragment_tile(tile_name, grid_size=4)
    print(f"Created {len(fragments)} fragments")
