#!/usr/bin/env python3
"""
Fragment a large GeoJSON tile into smaller files.

Usage:
    python scripts/fragment_tile.py [tile_name] [grid_size]

Example:
    python scripts/fragment_tile.py _demo_crop_fd_16tgk_10091004_v1.geojson 4
"""

import os
import sys

# Add project root to path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from app.data_synthesis.tile_fragmenter import TileFragmenter


def main():
    """Fragment a tile."""
    if len(sys.argv) < 2:
        print("Usage: python scripts/fragment_tile.py <tile_name> [grid_size]")
        print("\nExample:")
        print("  python scripts/fragment_tile.py _demo_crop_fd_16tgk_10091004_v1.geojson 4")
        sys.exit(1)
    
    tile_name = sys.argv[1]
    grid_size = int(sys.argv[2]) if len(sys.argv) > 2 else 4
    
    print(f"Fragmenting tile: {tile_name}")
    print(f"Grid size: {grid_size}x{grid_size} = {grid_size * grid_size} fragments")
    
    fragmenter = TileFragmenter()
    
    try:
        fragments = fragmenter.fragment_tile(tile_name, grid_size=grid_size)
        print(f"\n✅ Successfully created {len(fragments)} fragments")
        print(f"Fragments saved in: {os.path.join(fragmenter.data_dir, tile_name.replace('.geojson', '').split('_')[0])}")
    except Exception as e:
        print(f"\n❌ Error: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
