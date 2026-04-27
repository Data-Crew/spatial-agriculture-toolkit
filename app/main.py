"""
Spatial Agriculture Toolkit - Main Streamlit Application

A toolkit for spatial analysis in precision agriculture, providing
interpolation and autocorrelation models for field-level decision making.
"""

import streamlit as st
from keplergl import KeplerGl
from streamlit_keplergl import keplergl_static

import pandas as pd
import geopandas as gpd
import json
from shapely.geometry import Polygon

import os
import sys

# Add app directory to path for imports
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

from app.spatial_interpolations import field_interpolation_predictor
from app.data_synthesis.field_loader import FieldLoader
from app.data_synthesis.soil_data_generator import (
    generate_soil_samples_in_region,
    generate_cycle_realizations,
    parse_bbox_from_geojson,
    CYCLE_SCENARIOS,
    FERTILITY_PHASES,
)
from app.spatial_autocorrelation import add_local_autocorrelation_labels, geopandas_to_h3

# Page configuration
st.set_page_config(
    page_title="Spatial Agriculture Toolkit",
    page_icon="🌾",
    layout='wide',
    initial_sidebar_state='expanded'
)

# Custom CSS for branding
st.markdown("""
    <style>
    .main-header {
        font-size: 2.5rem;
        font-weight: bold;
        color: #2E7D32;
        text-align: center;
        margin-bottom: 1rem;
    }
    .subtitle {
        font-size: 1.2rem;
        color: #666;
        text-align: center;
        margin-bottom: 2rem;
    }
    </style>
""", unsafe_allow_html=True)

# Header
st.markdown('<h1 class="main-header">🌾 Spatial Agriculture Toolkit</h1>', unsafe_allow_html=True)
st.markdown('<p class="subtitle">Spatial Analysis for Precision Agriculture</p>', unsafe_allow_html=True)

# Sidebar menu
menu_list = st.sidebar.radio(
    'Analysis Modules',
    ["Spatial Interpolations", "Spatial Autocorrelation"],
    help="Select the analysis module you want to use"
)

# ============================================================================
# SHARED SIDEBAR: Field Zone Manager (available for ALL modules)
# ============================================================================

# Initialize field loader (cached to avoid reinitialization)
@st.cache_resource
def get_field_loader():
    return FieldLoader()

field_loader = get_field_loader()

# Default values (ensure they exist even if no tile is selected)
selected_tile = None
gdf_fields = None
tile_center = None
max_fields = 2000

# Field Zone Manager
st.sidebar.markdown("### 🌍 Field Zone Manager")

# List available tiles (cached)
@st.cache_data(ttl=300)  # Cache for 5 minutes
def get_available_tiles():
    return field_loader.list_available_tiles()

available_tiles = get_available_tiles()

if not available_tiles:
    st.sidebar.error("No GeoJSON tiles found in data directory")
    st.sidebar.info(f"Expected path: {field_loader.base_dir}")
else:
    # Tile selector
    selected_tile = st.sidebar.selectbox(
        "Select Tile",
        available_tiles,
        help="Select a GeoJSON tile with delineated fields"
    )

    if selected_tile:
        # Get tile bounds (cached to avoid recalculating)
        @st.cache_data(ttl=3600)  # Cache for 1 hour
        def get_cached_tile_bounds(tile_name):
            return field_loader.get_tile_bounds(tile_name)

        try:
            tile_bounds = get_cached_tile_bounds(selected_tile)
            tile_center_lon = (tile_bounds[0] + tile_bounds[2]) / 2
            tile_center_lat = (tile_bounds[1] + tile_bounds[3]) / 2
            tile_center = (tile_center_lon, tile_center_lat)

            st.sidebar.info(f"Tile bounds:\n{tile_bounds}")

            # Max fields limit
            max_fields = st.sidebar.number_input(
                "Max Fields",
                min_value=100,
                max_value=10000,
                value=2000,
                step=100,
                help="Maximum number of fields to load (to avoid memory issues)"
            )

            # Check if we have cached fields for this tile
            if 'loaded_fields' in st.session_state and st.session_state.get('selected_tile') == selected_tile:
                gdf_fields = st.session_state['loaded_fields']
                tile_center = st.session_state.get('tile_center', tile_center)
            else:
                # Auto-load fields when tile is selected
                try:
                    with st.spinner(f"Loading fields from {selected_tile}..."):
                        gdf_fields = field_loader.load_fields(
                            selected_tile,
                            max_fields=max_fields
                        )

                    if len(gdf_fields) == 0:
                        st.sidebar.warning(f"No fields found in {selected_tile}")
                        st.session_state['loaded_fields'] = None
                        gdf_fields = None
                    elif len(gdf_fields) >= max_fields:
                        st.sidebar.warning(f"⚠️ Loaded {len(gdf_fields)} fields (limit reached). Consider increasing Max Fields.")
                        st.session_state['loaded_fields'] = gdf_fields
                        st.session_state['selected_tile'] = selected_tile
                        st.session_state['tile_center'] = tile_center
                    else:
                        st.session_state['loaded_fields'] = gdf_fields
                        st.session_state['selected_tile'] = selected_tile
                        st.session_state['tile_center'] = tile_center
                        st.sidebar.success(f"✅ Loaded {len(gdf_fields)} fields")
                except Exception as e:
                    st.sidebar.error(f"Error loading fields: {str(e)}")
                    st.sidebar.exception(e)
                    st.session_state['loaded_fields'] = None
                    gdf_fields = None
        except Exception as e:
            st.sidebar.error(f"Error getting tile info: {str(e)}")
            gdf_fields = None
            tile_center = None

# ============================================================================
# SPATIAL INTERPOLATIONS MODULE
# ============================================================================
if menu_list == "Spatial Interpolations":
    st.header("Field-Level Spatial Interpolation")
    st.markdown("""
    Predict occurrence probabilities of agricultural events or properties across 
    your field using spatial interpolation models. This tool helps identify 
    spatial patterns and risk zones for better field management decisions.
    """)

    map_col = st.container(border=True)
    
    with map_col:
        # Load Kepler config
        config_path = os.path.join(os.path.dirname(__file__), 'spatial_interpolations', 'kepler_config.json')
        with open(config_path) as config_file:
            config = json.load(config_file)
        
        # Center map on tile center if available
        if tile_center:
            config['config']['mapState']['latitude'] = tile_center[1]
            config['config']['mapState']['longitude'] = tile_center[0]
            config['config']['mapState']['zoom'] = 11
        
        sim_frame_map = KeplerGl(height=800, config=config)
        landing_map = sim_frame_map
        
        # Add fields to map if loaded
        if gdf_fields is not None and len(gdf_fields) > 0:
            sim_frame_map.add_data(data=gdf_fields, name="delineated_fields")
            st.info(f"📊 {len(gdf_fields)} fields loaded and displayed on map")
        
        # Add PPP dataset (all realizations combined) to map as a single layer
        if 'ppp_data' in st.session_state and st.session_state['ppp_data'] is not None:
            gdf_ppp = st.session_state['ppp_data']
            sim_frame_map.add_data(data=gdf_ppp, name="point_pattern")
            st.info(
                f"📊 Point pattern loaded: **{len(gdf_ppp)} points** across "
                f"**{gdf_ppp['realization'].nunique()} realizations**. "
                f"Use the `realization` column in Kepler filters to explore individual frames."
            )

        with st.expander("**Define Analysis Region**"):
            st.markdown("""
            **Define the 2D region ℛ for spatial interpolation:**
            
            Copy a GeoJSON Polygon directly from the Kepler map viewport (draw a polygon, 
            click on it, and copy from the feature panel), then paste it below to define 
            your bounded analysis region.
            """)
            
            # Region bbox input
            region_bbox_input = st.text_area(
                "Region ℛ (GeoJSON Polygon)",
                value="",
                help="Paste GeoJSON Polygon from Kepler to define the bounded analysis region",
                height=100
            )
            
            region_bbox = None
            if region_bbox_input.strip():
                region_bbox = parse_bbox_from_geojson(region_bbox_input.strip())
                if region_bbox:
                    st.success(f"✅ Region ℛ defined: [{region_bbox[0]:.6f}, {region_bbox[1]:.6f}, {region_bbox[2]:.6f}, {region_bbox[3]:.6f}]")
                    st.session_state['region_bbox'] = region_bbox
                else:
                    st.error("Could not parse GeoJSON Polygon. Please check the format.")
                    st.session_state['region_bbox'] = None
            else:
                st.session_state['region_bbox'] = None
        
        with st.expander("**Set Up Field Events**"):
            st.markdown("""
            **Planar Point Pattern (PPP):**  
            
            Simulate where events occur across your field by setting a set of random point 
            locations within region ℛ. Generate multiple realizations automatically 
            using agronomic cycle scenarios (e.g., degradation, recovery), or upload 
            your own field observations as CSV.
            
            All points are loaded as a single dataset with a `realization` column—use 
            Kepler's filter panel to explore individual frames.
            """)

            # --- Show current PPP status ---
            if 'ppp_data' in st.session_state and st.session_state['ppp_data'] is not None:
                gdf_ppp = st.session_state['ppp_data']
                n_real = gdf_ppp['realization'].nunique()
                n_pts = len(gdf_ppp)
                source = st.session_state.get('ppp_source', 'unknown')
                cycle_label = st.session_state.get('ppp_cycle_label', '')

                st.success(
                    f"**Current PPP:** {n_real} realizations, {n_pts} total points "
                    f"({source}){' — ' + cycle_label if cycle_label else ''}"
                )

                # Phase breakdown with descriptions
                if 'phase' in gdf_ppp.columns:
                    # Build label→description lookup from FERTILITY_PHASES
                    _label_to_desc = {
                        v['label']: v.get('description', '')
                        for v in FERTILITY_PHASES.values()
                    }

                    phase_summary = (
                        gdf_ppp.groupby('realization')['phase']
                        .first()
                        .reset_index()
                        .rename(columns={'phase': 'Phase'})
                    )
                    phase_summary['Description'] = phase_summary['Phase'].map(
                        lambda p: _label_to_desc.get(p, '')
                    )
                    st.dataframe(
                        phase_summary[['realization', 'Phase', 'Description']].rename(
                            columns={'realization': 'Realization'}
                        ),
                        use_container_width=True,
                        hide_index=True,
                    )

                if st.button("Clear Point Pattern", key="clear_ppp"):
                    st.session_state['ppp_data'] = None
                    st.session_state.pop('ppp_source', None)
                    st.session_state.pop('ppp_cycle_label', None)
                    # Also clear old-style realizations if any
                    st.session_state.pop('realizations', None)
                    st.rerun()

            st.markdown("---")

            # --- Two tabs: Generate / Upload ---
            tab_gen, tab_upload = st.tabs(["Generate Cycle Scenario", "Upload CSV"])

            # ====== TAB: Generate Cycle Scenario ======
            with tab_gen:
                has_region = (
                    'region_bbox' in st.session_state
                    and st.session_state['region_bbox'] is not None
                )

                if not has_region:
                    st.warning("Define Region ℛ above before generating synthetic realizations.")
                else:
                    # Cycle selector
                    cycle_keys = list(CYCLE_SCENARIOS.keys())
                    cycle_labels = [CYCLE_SCENARIOS[k]['name'] for k in cycle_keys]

                    selected_cycle_idx = st.selectbox(
                        "Agronomic Cycle Scenario",
                        range(len(cycle_keys)),
                        format_func=lambda i: cycle_labels[i],
                        key="cycle_selector",
                        help="Choose a predefined scenario that simulates a temporal cycle",
                    )
                    selected_cycle = cycle_keys[selected_cycle_idx]
                    cycle_info = CYCLE_SCENARIOS[selected_cycle]

                    # Description
                    st.caption(cycle_info['description'])

                    # Show phase sequence
                    phase_seq = " → ".join(
                        FERTILITY_PHASES[p]['label'] for p in cycle_info['phases']
                    )
                    st.markdown(f"**Phase sequence:** {phase_seq}")

                    col_a, col_b, col_c = st.columns(3)
                    with col_a:
                        n_realizations = st.number_input(
                            "Number of Realizations",
                            min_value=2,
                            max_value=120,
                            value=12,
                            step=1,
                            key="n_realizations",
                            help=(
                                "How many frames to generate. The cycle phases "
                                "are distributed evenly across these frames."
                            ),
                        )
                    with col_b:
                        n_samples = st.number_input(
                            "Points per Realization",
                            min_value=10,
                            max_value=500,
                            value=50,
                            step=10,
                            key="n_samples_cycle",
                            help="Number of sample points in each realization",
                        )
                    with col_c:
                        seed = st.number_input(
                            "Random Seed",
                            min_value=0,
                            max_value=99999,
                            value=42,
                            key="seed_cycle",
                            help="Seed for reproducibility",
                        )

                    if st.button(
                        f"Generate {n_realizations} Realizations",
                        type="primary",
                        key="generate_cycle",
                        use_container_width=True,
                    ):
                        with st.spinner(
                            f"Generating {n_realizations} realizations "
                            f"({n_samples} pts each) — {cycle_info['name']}..."
                        ):
                            try:
                                gdf_ppp = generate_cycle_realizations(
                                    bbox=st.session_state['region_bbox'],
                                    cycle_name=selected_cycle,
                                    n_realizations=n_realizations,
                                    n_samples_per_realization=n_samples,
                                    seed=seed,
                                )
                                st.session_state['ppp_data'] = gdf_ppp
                                st.session_state['ppp_source'] = 'synthetic'
                                st.session_state['ppp_cycle_label'] = cycle_info['name']
                                # Clear old-style realizations
                                st.session_state.pop('realizations', None)

                                st.success(
                                    f"Generated {len(gdf_ppp)} points across "
                                    f"{n_realizations} realizations"
                                )
                                st.rerun()
                            except Exception as e:
                                st.error(f"Error generating cycle: {e}")
                                import traceback
                                st.exception(e)

            # ====== TAB: Upload CSV ======
            with tab_upload:
                st.markdown("""
                **Expected CSV format:**  
                `longitude`, `latitude`, `realization` (integer), and optionally
                `event_type`, `phase`, `pH`, `organic_matter_pct`, etc.  
                Each unique `realization` value becomes a separate frame.
                """)

                uploaded_file = st.file_uploader(
                    "Upload Point Pattern CSV",
                    type=['csv'],
                    key="upload_ppp",
                    help="CSV with longitude, latitude, and realization columns",
                )

                if uploaded_file:
                    if st.button("Load CSV", type="primary", key="load_csv_ppp"):
                        try:
                            df = pd.read_csv(uploaded_file)
                            required = ['longitude', 'latitude']
                            missing = [c for c in required if c not in df.columns]
                            if missing:
                                st.error(f"Missing required columns: {missing}")
                            else:
                                # Create realization column if missing
                                if 'realization' not in df.columns:
                                    if 'occurrence_date' in df.columns:
                                        dates_sorted = sorted(df['occurrence_date'].unique())
                                        date_to_idx = {d: i + 1 for i, d in enumerate(dates_sorted)}
                                        df['realization'] = df['occurrence_date'].map(date_to_idx)
                                    else:
                                        df['realization'] = 1

                                # Create event_type if missing
                                if 'event_type' not in df.columns:
                                    if 'fertility_index' in df.columns:
                                        fert_map = {
                                            5: 'High Fertility',
                                            4: 'Good Fertility',
                                            3: 'Moderate Fertility',
                                            2: 'Low Fertility',
                                            1: 'Very Low Fertility',
                                        }
                                        df['event_type'] = df['fertility_index'].map(fert_map).fillna('Moderate Fertility')
                                    elif 'phase' in df.columns:
                                        df['event_type'] = df['phase']
                                    elif 'scenario' in df.columns:
                                        df['event_type'] = df['scenario']
                                    else:
                                        df['event_type'] = 'unknown'

                                gdf_ppp = gpd.GeoDataFrame(
                                    df,
                                    geometry=gpd.points_from_xy(df['longitude'], df['latitude']),
                                    crs='EPSG:4326',
                                )
                                st.session_state['ppp_data'] = gdf_ppp
                                st.session_state['ppp_source'] = 'uploaded'
                                st.session_state['ppp_cycle_label'] = ''
                                # Clear old-style realizations
                                st.session_state.pop('realizations', None)

                                n_real = gdf_ppp['realization'].nunique()
                                st.success(
                                    f"Loaded {len(gdf_ppp)} points across "
                                    f"{n_real} realizations"
                                )
                                st.rerun()
                        except Exception as e:
                            st.error(f"Error loading CSV: {e}")
                            import traceback
                            st.exception(e)
        
        with st.expander("**Configure Interpolation Model**"):
            col1, col2, col3 = st.columns([0.33, 0.33, 0.34])

            with col1:
                st.subheader("Model Selection")
                prediction_method = st.selectbox(
                    "Interpolation Method",
                    ("linear", "orthogonal", "splines", "gam", "kriging"),
                    index=3,
                    help=(
                        "Linear: simple linear trend | "
                        "Orthogonal: polynomial trends (3rd order) | "
                        "Splines: B-spline basis with interaction | "
                        "GAM: 2D thin-plate smooth with automatic penalty (recommended) | "
                        "Kriging: Indicator Kriging with variogram-based spatial autocorrelation"
                    ),
                )

                # Target event selector — restricted to cycle phases
                target_event = None
                ppp_data = st.session_state.get('ppp_data')
                if ppp_data is not None and 'event_type' in ppp_data.columns:
                    cycle_label = st.session_state.get('ppp_cycle_label', '')

                    # Build label→description lookup
                    _label_to_desc = {
                        v['label']: v.get('description', '')
                        for v in FERTILITY_PHASES.values()
                    }

                    # Build ordered, deduplicated list of event labels
                    # from the cycle's phase sequence
                    event_types = None
                    if cycle_label:
                        cycle_key = None
                        for key, info in CYCLE_SCENARIOS.items():
                            if info['name'] == cycle_label:
                                cycle_key = key
                                break
                        if cycle_key:
                            # Map internal keys → English labels, in cycle order
                            seen = set()
                            event_types = []
                            for phase_key in CYCLE_SCENARIOS[cycle_key]['phases']:
                                lbl = FERTILITY_PHASES.get(
                                    phase_key, {}
                                ).get('label', phase_key)
                                if lbl not in seen:
                                    event_types.append(lbl)
                                    seen.add(lbl)

                    # Fallback for uploaded data: use what's in the data
                    if event_types is None:
                        event_types = sorted(
                            set(ppp_data['event_type'].unique().tolist())
                        )

                    # Display: label + short description
                    event_options = [
                        f"{ev} — {_label_to_desc[ev]}"
                        if ev in _label_to_desc else ev
                        for ev in event_types
                    ]

                    st.markdown("**Target Event to Predict:**")
                    selected_idx = st.selectbox(
                        "Select event type to predict",
                        range(len(event_options)),
                        index=len(event_options) - 1,
                        format_func=lambda x: event_options[x],
                        key="target_event_selector",
                        help="Select which event type to predict probability of occurrence",
                    )
                    target_event = event_types[selected_idx]
                    st.session_state['selected_target_event'] = target_event
                    st.success(f"Predicting: {target_event}")

            with col2:
                st.subheader("Data Status")
                if ppp_data is not None:
                    n_real = ppp_data['realization'].nunique()
                    st.success(f"{n_real} realizations, {len(ppp_data)} points")
                else:
                    st.warning("No point pattern loaded")

                if st.session_state.get('region_bbox') is not None:
                    bbox = st.session_state['region_bbox']
                    st.info(
                        f"Region ℛ: [{bbox[0]:.4f}, {bbox[1]:.4f}, "
                        f"{bbox[2]:.4f}, {bbox[3]:.4f}]"
                    )
                else:
                    st.warning("Region ℛ not defined")

            with col3:
                st.subheader("Run Analysis")
                if st.button("Run Interpolation", type="primary", use_container_width=True):
                    if st.session_state.get('region_bbox') is None:
                        st.warning("Please define Region ℛ first!")
                    elif ppp_data is None:
                        st.warning("Please generate or upload a point pattern first!")
                    elif len(ppp_data) < 10:
                        st.warning(
                            "Total sample size is too small for robust "
                            "interpolation. Need at least 10 points."
                        )
                    elif 'event_type' not in ppp_data.columns:
                        st.warning(
                            "Point data must contain an 'event_type' column."
                        )
                    else:
                        combined_points = ppp_data
                        n_real = combined_points['realization'].nunique()

                        with st.spinner(
                            f"Running spatial interpolation on "
                            f"{len(combined_points)} points from "
                            f"{n_real} realizations..."
                        ):
                            try:
                                points_df = pd.DataFrame(
                                    combined_points.drop(columns="geometry")
                                )

                                output_dir = os.path.join(
                                    os.path.dirname(os.path.dirname(__file__)),
                                    'output',
                                )
                                os.makedirs(output_dir, exist_ok=True)
                                output_path = os.path.join(
                                    output_dir, 'interpolation_result.tif'
                                )

                                target_event_selected = st.session_state.get(
                                    'selected_target_event'
                                )
                                if target_event_selected is None:
                                    ev_sorted = sorted(
                                        combined_points['event_type'].unique().tolist()
                                    )
                                    target_event_selected = (
                                        ev_sorted[-1] if ev_sorted else None
                                    )

                                gdf_pred = field_interpolation_predictor(
                                    df=points_df,
                                    geom=combined_points,
                                    prediction_method=prediction_method,
                                    output_path=output_path,
                                    target_event=target_event_selected,
                                )

                                st.session_state['interpolation_results'] = gdf_pred
                                st.session_state['combined_points'] = combined_points

                                sim_frame_map.add_data(
                                    data=gdf_pred,
                                    name="interpolation_results",
                                )

                                st.success("Interpolation completed successfully!")

                                actual_target = (
                                    target_event_selected
                                    or 'unknown'
                                )
                                st.session_state['last_predicted_event'] = actual_target

                                st.markdown(f"""
**How to interpret the results:**

The model predicts the **probability of occurrence** of **"{actual_target}"**.
High values (0.7-1.0) indicate strong spatial evidence; low values (0.0-0.4) suggest other conditions are more likely.
Based on **{n_real} realizations** with **{len(combined_points)}** total points.
                                """)

                                col_m1, col_m2, col_m3 = st.columns(3)
                                col_m1.metric(
                                    "Mean Probability",
                                    f"{gdf_pred['probability'].mean():.3f}",
                                )
                                col_m2.metric(
                                    "Max Probability",
                                    f"{gdf_pred['probability'].max():.3f}",
                                )
                                col_m3.metric(
                                    "Total Points Used",
                                    len(combined_points),
                                )
                            except Exception as e:
                                st.error(f"Error running interpolation: {e}")
                                import traceback
                                st.exception(e)
        
        # Display map
        keplergl_static(landing_map, center_map=True)
        
        # Show results if available
        if 'interpolation_results' in st.session_state:
            with st.expander("📊 Interpolation Results Summary"):
                results = st.session_state['interpolation_results']
                st.dataframe(
                    results[['probability']].describe(),
                    use_container_width=True
                )

# ============================================================================
# SPATIAL AUTOCORRELATION MODULE
# ============================================================================
if menu_list == "Spatial Autocorrelation":
    st.header("Spatial Autocorrelation Analysis")
    st.markdown("""
    Analyze spatial patterns and clustering in your field data using Local 
    Indicators of Spatial Association (LISA). Identify hotspots, coldspots, 
    and spatial outliers in your agricultural data.
    """)

    # --- Load enriched fields if tile is selected ---
    # Uses gdf_fields and selected_tile from the shared sidebar
    if selected_tile and gdf_fields is not None:
        # Load enriched data with CDL properties (cached in session_state)
        if ('autocorr_enriched_gdf' not in st.session_state
                or st.session_state.get('autocorr_selected_tile') != selected_tile):
            try:
                with st.spinner("Loading field properties from CSV..."):
                    gdf_enriched = field_loader.load_fields_with_properties(
                        selected_tile, max_fields=max_fields
                    )
                st.session_state['autocorr_enriched_gdf'] = gdf_enriched
                st.session_state['autocorr_selected_tile'] = selected_tile
            except Exception as e:
                st.warning(f"Could not load properties: {e}. Using basic fields.")
                st.session_state['autocorr_enriched_gdf'] = gdf_fields
                st.session_state['autocorr_selected_tile'] = selected_tile

        gdf_enriched = st.session_state['autocorr_enriched_gdf']
    else:
        gdf_enriched = None

    # --- Analysis Mode definitions ---
    ANALYSIS_MODES = {
        "Crop Frequency": {
            "description": "How consistently a crop dominates each field across all years",
            "help": (
                "Measures the proportion of years (2008-2022) where a specific crop was the "
                "dominant land cover. A value of 0.73 means the crop was dominant in 73% of years. "
                "Moran I identifies spatial clusters of persistent monoculture (HH) vs. "
                "crop rotation zones (LL)."
            ),
            "legend": {
                "HH": "Cluster where {detail} dominates consistently (high frequency near high frequency)",
                "LL": "Cluster where {detail} rarely appears (low frequency near low frequency)",
                "HL": "Field with high {detail} frequency surrounded by low frequency (spatial outlier)",
                "LH": "Field with low {detail} frequency surrounded by high frequency (spatial outlier)",
                "ns": "No statistically significant spatial pattern",
            },
        },
        "Crop Coverage": {
            "description": "Percentage of field area covered by the dominant crop in a specific year",
            "help": (
                "Uses the crop_percentage value for a selected year — the share of the field's area "
                "covered by its dominant crop. High values indicate strong single-crop dominance; "
                "low values suggest mixed land use. Moran I reveals spatial patterns of crop "
                "homogeneity (HH) vs. fragmentation (LL)."
            ),
            "legend": {
                "HH": "Cluster of high crop coverage in {detail} (homogeneous near homogeneous)",
                "LL": "Cluster of low crop coverage in {detail} (fragmented near fragmented)",
                "HL": "Homogeneous field surrounded by fragmented fields (spatial outlier)",
                "LH": "Fragmented field surrounded by homogeneous fields (spatial outlier)",
                "ns": "No statistically significant spatial pattern",
            },
        },
        "Field Properties": {
            "description": "Physical field characteristics (area, flatness, perimeter, etc.)",
            "help": (
                "Analyzes spatial clustering of physical field characteristics. Useful for detecting "
                "structural patterns in field delineation — e.g., clusters of large fields (HH) vs. "
                "small parcels (LL), or clusters of flat vs. irregular terrain."
            ),
            "legend": {
                "HH": "Cluster of high {detail} values (high near high)",
                "LL": "Cluster of low {detail} values (low near low)",
                "HL": "High {detail} surrounded by low values (spatial outlier)",
                "LH": "Low {detail} surrounded by high values (spatial outlier)",
                "ns": "No statistically significant spatial pattern",
            },
        },
    }

    map_col = st.container(border=True)

    with map_col:
        # Load Kepler config BEFORE constructing the map so the same pattern
        # used by the Spatial Interpolations module (which renders the
        # satellite basemap + layer styling correctly) also works here.
        config_path = os.path.join(os.path.dirname(__file__), 'spatial_autocorrelation', 'kepler_config.json')
        with open(config_path) as config_file:
            config = json.load(config_file)

        # Center map on tile if available
        if tile_center:
            config['config']['mapState']['latitude'] = tile_center[1]
            config['config']['mapState']['longitude'] = tile_center[0]
            config['config']['mapState']['zoom'] = 11

        sim_frame_map = KeplerGl(height=800, config=config)
        landing_map = sim_frame_map

        # Show fields on map if loaded
        if gdf_enriched is not None and len(gdf_enriched) > 0:
            sim_frame_map.add_data(data=gdf_enriched, name="delineated_fields")
            st.info(f"📊 {len(gdf_enriched)} enriched fields loaded and displayed on map")

        with st.expander("**Configure Autocorrelation Analysis**", expanded=True):
            col1, col2, col3, col4 = st.columns([0.3, 0.2, 0.2, 0.3])

            # --- Col1: Analysis Mode ---
            with col1:
                st.subheader("Analysis Mode")
                selected_mode = st.selectbox(
                    "Select Analysis Mode",
                    list(ANALYSIS_MODES.keys()),
                    format_func=lambda m: f"{m} — {ANALYSIS_MODES[m]['description']}",
                    key="autocorr_mode",
                    help="Choose what aspect of the data to analyze for spatial clustering",
                )
                st.caption(ANALYSIS_MODES[selected_mode]["help"])

            # --- Col2: Hexgrid ---
            with col2:
                st.subheader("Hexgrid")
                activate_hexgrid = st.toggle(
                    "Use H3 Hexgrid",
                    value=False,
                    help="Transform data to H3 hexagonal grid",
                )
                if activate_hexgrid:
                    h3_res = st.number_input(
                        "H3 Resolution",
                        min_value=1, max_value=15, step=1, value=6,
                        help="Higher resolution = smaller hexagons",
                    )

            # --- Col3: Indicator (contextual based on mode) ---
            with col3:
                st.subheader("Indicator")
                indicator = None
                indicator_detail = ""

                if gdf_enriched is None:
                    st.warning("Select a tile in the sidebar to load data")
                else:
                    if selected_mode == "Crop Frequency":
                        freq_cols = [c for c in gdf_enriched.columns if c.startswith('freq_')]
                        if freq_cols:
                            crop_names = [c.replace('freq_', '').replace('_', ' ') for c in freq_cols]
                            selected_crop = st.selectbox(
                                "Select Crop", crop_names,
                                help="Crop to analyze frequency clustering for",
                            )
                            indicator = f"freq_{selected_crop.replace(' ', '_')}"
                            indicator_detail = selected_crop
                            if indicator in gdf_enriched.columns:
                                st.metric("Mean frequency", f"{gdf_enriched[indicator].mean():.2%}")
                        else:
                            st.warning("No crop frequency columns found. Check CSV properties.")

                    elif selected_mode == "Crop Coverage":
                        pct_cols = [c for c in gdf_enriched.columns if c.startswith('crop_pct_')]
                        if pct_cols:
                            years = sorted([int(c.replace('crop_pct_', '')) for c in pct_cols])
                            selected_year = st.selectbox(
                                "Select Year", years,
                                index=len(years) - 1,
                                help="Year to analyze crop coverage for",
                            )
                            indicator = f"crop_pct_{selected_year}"
                            indicator_detail = str(selected_year)
                            if indicator in gdf_enriched.columns:
                                st.metric("Mean coverage", f"{gdf_enriched[indicator].mean():.1f}%")
                        else:
                            st.warning("No crop coverage columns found. Check CSV properties.")

                    elif selected_mode == "Field Properties":
                        exclude_prefixes = ('freq_', 'crop_pct_', 'crop_id_', 'crop_')
                        exclude_exact = {'id', 'geometry', 'index'}
                        numeric_cols = gdf_enriched.select_dtypes(include=['number']).columns.tolist()
                        property_cols = [
                            c for c in numeric_cols
                            if c not in exclude_exact and not any(c.startswith(p) for p in exclude_prefixes)
                        ]
                        if property_cols:
                            selected_prop = st.selectbox(
                                "Select Property", property_cols,
                                help="Field property to analyze",
                            )
                            indicator = selected_prop
                            indicator_detail = selected_prop
                            if indicator in gdf_enriched.columns:
                                st.metric(f"Mean {selected_prop}", f"{gdf_enriched[indicator].mean():.2f}")
                        else:
                            st.warning("No numeric property columns found")

            # --- Col4: Run ---
            with col4:
                st.subheader("Model Parameters")
                weights_type = st.selectbox(
                    "Spatial Weights", ["queen", "knn"],
                    help="Queen: shared edges/vertices | KNN: k nearest neighbors",
                )
                if weights_type == "knn":
                    knn_k = st.number_input("K neighbors", min_value=1, max_value=20, value=5)
                else:
                    knn_k = 5
                p_value = st.number_input(
                    "P-value threshold",
                    min_value=0.01, max_value=0.10, value=0.05, step=0.01,
                )

                if st.button("Run Autocorrelation", type="primary", use_container_width=True):
                    if gdf_enriched is None:
                        st.warning("Please select a tile in the sidebar first!")
                    elif indicator is None:
                        st.warning("Please select an indicator!")
                    else:
                        with st.spinner("Computing spatial autocorrelation..."):
                            try:
                                gdf = gdf_enriched.copy()

                                if activate_hexgrid:
                                    gdf = geopandas_to_h3(gdf, resolution=h3_res)

                                gdf_labeled = add_local_autocorrelation_labels(
                                    gdf=gdf, indicator=indicator,
                                    p_value=p_value, weights=weights_type, knn_k=knn_k,
                                )

                                st.session_state['autocorr_results'] = gdf_labeled
                                st.session_state['autocorr_mode_used'] = selected_mode
                                st.session_state['autocorr_detail'] = indicator_detail

                                plot_columns = ['id', 'lbl_autocorr', 'lbl_autocorr_col', 'geometry']
                                if 'id' not in gdf_labeled.columns:
                                    gdf_labeled['id'] = range(len(gdf_labeled))

                                # Sort so categories are fed to kepler in the
                                # canonical LISA order (matches colorDomain).
                                label_order = {'HH': 0, 'HL': 1, 'LH': 2, 'LL': 3, 'ns': 4}
                                gdf_plot = gdf_labeled[plot_columns].copy()
                                gdf_plot['_sort'] = gdf_plot['lbl_autocorr'].map(label_order)
                                gdf_plot = (
                                    gdf_plot
                                    .sort_values('_sort')
                                    .drop(columns=['_sort'])
                                )

                                # Clear previous layers and add results
                                if "delineated_fields" in sim_frame_map.data:
                                    sim_frame_map.data = {}

                                sim_frame_map.add_data(data=gdf_plot, name="spatial_autocorr")

                                # When the analysis is run on an H3 hexgrid the
                                # original parcel geometry is no longer rendered
                                # by the spatial_autocorr layer. Add the parcel
                                # outlines as a separate reference layer so the
                                # user keeps visual context.
                                if activate_hexgrid:
                                    field_boundaries = gdf_enriched[['id', 'geometry']].copy()
                                    sim_frame_map.add_data(
                                        data=field_boundaries,
                                        name="field_boundaries",
                                    )

                                # Diagnostic warning for degenerate indicators
                                # post-resampling (e.g. freq_* on H3 res >= 8
                                # collapses to a near-binary distribution and
                                # any "significance" reported by Moran_Local is
                                # mostly an artifact of the inflated sample
                                # size, not a real spatial pattern).
                                values = gdf[indicator].dropna()
                                n_unique = values.nunique()
                                if activate_hexgrid and n_unique < 5:
                                    st.warning(
                                        f"Indicator `{indicator}` only has "
                                        f"{n_unique} unique values after H3 "
                                        f"resampling at resolution {h3_res}. "
                                        "LISA significance at high resolutions "
                                        "may be artifactual — try a lower "
                                        "resolution or a continuous indicator "
                                        "(e.g. crop_pct_*, area)."
                                    )

                                st.success(
                                    f"Autocorrelation completed! Mode: {selected_mode}, "
                                    f"Indicator: {indicator}"
                                )
                                label_counts = gdf_labeled['lbl_autocorr'].value_counts()
                                st.dataframe(label_counts, use_container_width=True)

                            except Exception as e:
                                st.error(f"Error: {str(e)}")
                                st.exception(e)

        # Display map
        keplergl_static(landing_map, center_map=True)

        # Contextual legend based on mode used
        if 'autocorr_results' in st.session_state:
            mode_used = st.session_state.get('autocorr_mode_used', 'Field Properties')
            detail = st.session_state.get('autocorr_detail', '')
            legend_templates = ANALYSIS_MODES[mode_used]["legend"]

            st.markdown("**LISA Results Interpretation:**")
            emojis = {'HH': '🔴', 'HL': '🟠', 'LH': '🔵', 'LL': '🔷', 'ns': '⚪'}
            for label in ['HH', 'HL', 'LH', 'LL', 'ns']:
                desc = legend_templates[label].format(detail=detail)
                st.markdown(f"- {emojis[label]} **{label}**: {desc}")

# Footer
st.markdown("---")
st.markdown(
    "<div style='text-align: center; color: #666;'>"
    "Spatial Agriculture Toolkit - Precision Agriculture Spatial Analysis"
    "</div>",
    unsafe_allow_html=True
)
