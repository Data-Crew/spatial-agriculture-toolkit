"""Generate synthetic test data for the Spatial Autocorrelation module.

Creates a tile GeoJSON and a matching props CSV so all 3 analysis modes
surface real indicators:
- Crop Frequency: freq_corn, freq_soybean
- Crop Coverage: crop_pct_2020, crop_pct_2021, crop_pct_2022
- Field Properties: area, flatness, perimeter

The layout is two clearly separated clusters so LISA with queen weights
produces at least some HH (top-right corner, corn monoculture + big, flat)
and LL (bottom-left, soybean + small, irregular) categories.
"""
import json
import os
import csv

DATA_DIR = os.path.join(os.path.dirname(__file__), '..', 'data')
os.makedirs(DATA_DIR, exist_ok=True)

TILE_NAME = '_demo_crop_fd_test_tile_v1.geojson'
CSV_NAME = 'props__fd_test_tile_v1.csv'

features = []
props_rows = []

GRID = 10  # 10x10 grid = 100 fields
STEP = 0.01  # ~1 km per cell

fid = 0
for i in range(GRID):
    for j in range(GRID):
        fid += 1
        lon0 = -90.0 + j * STEP
        lat0 = 40.0 + i * STEP
        # Polygons must share edges so queen contiguity finds real neighbors
        # (and LISA can compute spatial weights). Use full STEP width.
        poly = [[
            [lon0, lat0],
            [lon0 + STEP, lat0],
            [lon0 + STEP, lat0 + STEP],
            [lon0, lat0 + STEP],
            [lon0, lat0],
        ]]

        # High-value cluster in top-right (i>=6 and j>=6): corn monoculture,
        # large flat fields with high crop coverage.
        # Low-value cluster in bottom-left (i<=3 and j<=3): soybean,
        # small/irregular fields with low crop coverage.
        if i >= 6 and j >= 6:
            crops = ['corn'] * 15  # 2008-2022
            crop_pcts = [92.0] * 15
            area = 8.5
            flatness = 0.95
            perimeter = 1200.0
        elif i <= 3 and j <= 3:
            crops = ['soybean'] * 15
            crop_pcts = [35.0] * 15
            area = 1.2
            flatness = 0.4
            perimeter = 520.0
        else:
            # Mixed middle band: rotation of corn/soybean.
            crops = ['corn' if y % 2 else 'soybean' for y in range(15)]
            crop_pcts = [60.0] * 15
            area = 4.0
            flatness = 0.7
            perimeter = 800.0

        years = list(range(2008, 2023))
        crop_ids = [1 if c == 'corn' else 5 for c in crops]

        features.append({
            'type': 'Feature',
            'properties': {'id': str(fid)},
            'geometry': {'type': 'Polygon', 'coordinates': poly},
        })

        props_dict = {
            'area': area,
            'flatness': flatness,
            'perimeter': perimeter,
            'confidence': 0.9,
            'center_lat': lat0 + STEP * 0.45,
            'center_lng': lon0 + STEP * 0.45,
            'cdl_stats': {
                'year': years,
                'crops': crops,
                'crop_percentages': crop_pcts,
                'crop_ids': crop_ids,
            },
        }
        props_rows.append({'id': str(fid), 'props': repr(props_dict)})

geojson = {'type': 'FeatureCollection', 'features': features}
with open(os.path.join(DATA_DIR, TILE_NAME), 'w') as f:
    json.dump(geojson, f)

with open(os.path.join(DATA_DIR, CSV_NAME), 'w', newline='') as f:
    writer = csv.DictWriter(f, fieldnames=['id', 'props'])
    writer.writeheader()
    writer.writerows(props_rows)

print(f'Wrote {len(features)} features to {TILE_NAME}')
print(f'Wrote {len(props_rows)} props rows to {CSV_NAME}')
