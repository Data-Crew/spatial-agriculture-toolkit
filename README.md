# 🌾 Spatial Agriculture Toolkit

A precision agriculture toolkit for spatial analysis in field-level decision making.

## Documentation

Full project documentation is available in the [`docs/`](docs/) directory.

## Overview

The Spatial Agriculture Toolkit helps agricultural professionals and researchers
analyze spatial patterns in field data. It provides:

- **Spatial Interpolation**: Predict occurrence probabilities of soil fertility
  events across a bounded region using multiple model strategies (GLM, GAM,
  Indicator Kriging).
- **Spatial Autocorrelation**: Identify hotspots, coldspots, and spatial
  outliers using Local Indicators of Spatial Association (LISA).

## Features

- Dockerized environment with Python 3.10 and R 4.5
- Five interpolation methods: linear, orthogonal polynomials, B-splines, GAM,
  and Indicator Kriging
- Predefined agronomic cycle scenarios for synthetic data generation
- Interactive Kepler.gl maps with filterable realization layers
- Spatial autocorrelation with optional H3 hexgrid transformation

## Architecture

The toolkit combines:
- **Python**: Main application framework (Streamlit) and geospatial processing
- **R**: Statistical models for spatial interpolation (logistic regression with spatial trends)
- **Docker**: Containerized development and deployment environment

## Quick Start

### Prerequisites

- Docker and Docker Compose installed
- Git (for cloning the repository)

### Installation

1. Clone the repository:
```bash
git clone <repository-url>
cd spatial-agriculture-toolkit
```

2. Build and run with Docker Compose:
```bash
docker compose build 
docker compose up -d
```

3. Access the application:
   - Open your browser at `http://localhost:8501`


The application code is mounted as a volume, so changes will be reflected immediately.

### Accessing the Container Shell

To access the bash console of the container (useful for debugging, installing packages, or running commands):

**When to use each command:**

** `make shell` or `docker compose exec`**
- **Use this when:** The container is already running (e.g., when Streamlit is active at `http://localhost:8501`)
- **Advantage:** You access the same container where your application is running, you can see active processes
- **How to use:**
  ```bash
  # First start the container
  docker compose up -d
  
  # Then access the shell
  make shell
  # Or directly:
  docker compose exec -it app bash
  ```

** `make shell-temp` or `docker compose run`**if you're not sure if it's running**
- **Use this when:** The container is NOT running, or you want an independent temporary container
- **Advantage:** Always works, even if the main container is not running. Creates a new container that is removed when you exit
- **How to use:**
  ```bash
  make shell-temp
  # Or directly:
  docker compose run --rm app bash
  ```

**Using Docker directly**
- **Use this when:** You know the container name and it's running
- **How to use:**
  ```bash
  docker exec -it spatial-agriculture-toolkit bash
  ```

**Practical summary:**
- If Streamlit is running → use `make shell` or `docker compose exec -it app bash`
- If you're not sure or the container is not running → use `make shell-temp` or `docker compose run --rm app bash`

Once inside the container, you can:
- Install Python packages: `pip install <package-name>`
- Install R packages: `R -e "install.packages('<package-name>')"`
- Run Python scripts: `python <script.py>`
- Run R scripts: `Rscript <script.R>`
- Inspect files: `ls`, `cat`, `head`, etc.
- Access the application directory: `cd /app`

### Rebuild the Docker image from scratch

```bash
docker compose down
docker compose build --no-cache
docker compose up -d
```

## Project Structure

```
spatial-agriculture-toolkit/
├── app/
│   ├── main.py                            # Streamlit application
│   ├── spatial_interpolations/
│   │   ├── interpolation.py               # R-based models (GLM, GAM, Kriging)
│   │   └── kepler_config.json
│   ├── spatial_autocorrelation/
│   │   ├── moran.py                       # LISA / Moran's I
│   │   ├── geo_utils.py
│   │   └── kepler_config.json
│   └── data_synthesis/
│       ├── field_loader.py                # Load fragmented GeoJSON tiles
│       ├── soil_data_generator.py         # Agronomic cycle scenarios
│       └── tile_fragmenter.py             # Split large GeoJSON into fragments
├── data/                                   # Input tiles and field data
├── output/                                 # Generated rasters and results
├── scripts/
│   ├── fragment_tile.py                   # CLI for tile fragmentation
│   └── check_fragmentation_progress.sh
├── .streamlit/config.toml
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── Makefile
└── README.md
```

## Usage

### 1. Load Delineated Fields

Select a tile from the sidebar. Fields are loaded automatically and displayed
on the Kepler map.  If you have a large GeoJSON tile, fragment it first (see
[Fragmenting Large Tiles](#fragmenting-large-tiles) below).

### 2. Define Analysis Region ℛ

Expand **Define Analysis Region** and paste a GeoJSON Polygon copied from the
Kepler map. This defines the bounded 2D region where the interpolation model
will operate.

### 3. Generate or Upload Point Patterns

Expand **Define your Planar Point Patterns**.

**Option A — Synthetic cycle scenario:**

1. Select an agronomic cycle (e.g., *Degradation by Intensive Use*,
   *Recovery with Management*).
2. Choose the number of realizations (frames) and points per realization.
3. Click **Generate N Realizations**.

All points are loaded as a single dataset. Use the `realization` column in
Kepler's filter panel to browse individual frames.

**Option B — Upload CSV:**

Provide a CSV with columns `longitude`, `latitude`, and `realization` (integer).
Optionally include `event_type`, `phase`, `pH`, `organic_matter_pct`, etc.

#### Agronomic Cycle Scenarios

The toolkit includes seven predefined scenarios that simulate realistic soil
fertility evolution over time. Each scenario defines a sequence of phases
distributed across your chosen number of realizations:

| Scenario | Description |
|----------|-------------|
| **Degradation by Intensive Use** | Progressive soil degradation from intensive agriculture without adequate management. Starts from high fertility and declines through nutrient extraction, loss of organic matter, and acidification. |
| **Salinization by Irrigation** | Soil salinization from poorly managed irrigation in arid/semi-arid zones. Fertility declines as salts accumulate in the root zone, eventually rendering the soil unproductive. |
| **Sodification Process** | Progressive sodium accumulation that degrades soil structure. Common in irrigated areas with high-sodium water. Leads to impermeability and crop failure. |
| **Recovery with Management** | Soil rehabilitation through good management practices: cover crops, crop rotation, organic amendments, and liming. A degraded soil gradually recovers productive capacity. |
| **Annual Crop Cycle** | Typical annual crop cycle: pre-planting fertility, nutrient consumption during growth, peak extraction at harvest, post-harvest decline, and partial recovery during fallow. |
| **Monoculture Decline** | Gradual decline in soil health caused by continuous monoculture without rotation. Fertility drops steadily as specific nutrients are depleted and soil biology deteriorates. |
| **Stable Productive Field** | Well-managed field that maintains stable fertility over time with minor seasonal fluctuations. Represents best-practice agriculture with rotation, cover crops, and nutrient management. |

Each scenario generates spatially correlated soil properties (pH, organic matter,
CEC, base saturation) consistent with the fertility phase, creating realistic
point patterns for interpolation modeling.

### 4. Configure and Run Interpolation

Expand **Configure Interpolation Model**.

| Method         | Description |
|----------------|-------------|
| **linear**     | Logistic regression with linear lon + lat trend |
| **orthogonal** | Logistic regression with 3rd-order orthogonal polynomials |
| **splines**    | Logistic regression with B-spline basis functions |
| **gam**        | Generalized Additive Model with 2D thin-plate smooth (recommended) |
| **kriging**    | Indicator Kriging with automatic variogram fitting |

Select the **Target Event to Predict** (only phases from the active cycle are
shown), then click **Run Interpolation**.

### 5. Spatial Autocorrelation

Switch to the *Spatial Autocorrelation* module from the sidebar.

1. Upload a GeoJSON file with numeric indicator columns.
2. Optionally enable H3 hexgrid transformation.
3. Select an indicator column and click **Run Autocorrelation**.

The result shows LISA clusters: HH (hotspot), LL (coldspot), HL/LH (outliers).


## Fragmenting Large Tiles

If your delineated-fields GeoJSON is too large for Streamlit (> 200 MB), split
it into smaller fragments using the provided script.

```bash
# Fragment into an 8×8 grid (64 fragments)
python scripts/fragment_tile.py _demo_crop_fd_16tgk_10091004_v1.geojson 8
```

The script reads the tile from `data/`, creates a subdirectory named after the
tile ID (e.g., `data/16tgk/`), and writes one GeoJSON fragment per grid cell.
Only cells that contain field centroids produce a file.

**Monitor progress** (in a second terminal):

```bash
bash scripts/check_fragmentation_progress.sh
```

After fragmentation, the tile selector in Streamlit will list the individual
fragments instead of the original large file.

## Technical Details

### R Packages

Installed automatically in Docker:

| Package   | Purpose |
|-----------|---------|
| `sf`      | Spatial data handling |
| `dplyr`   | Data manipulation |
| `raster`  | Raster operations |
| `splines` | B-spline basis functions |
| `mgcv`    | Generalized Additive Models |
| `gstat`   | Variogram fitting and Kriging |
| `sp`      | Legacy spatial classes (for gstat) |

### Key Python Packages

| Package          | Purpose |
|------------------|---------|
| `streamlit`      | Web application framework |
| `geopandas`      | Geospatial data processing |
| `rpy2`           | Python ↔ R interface |
| `keplergl`       | Interactive mapping |
| `fiona`          | Efficient GeoJSON I/O with bbox filtering |
| `esda` / `libpysal` | Spatial autocorrelation |

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Submit a pull request

## 📄 License

MIT License - see LICENSE

## 👥 Author

Developed by Data Crew Consulting
