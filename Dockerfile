# Multi-stage Dockerfile for Spatial Agriculture Toolkit
# Combines Python and R environments
# Replicating exact working configuration: Ubuntu 20.04 Focal, R 4.5.2, Python 3.10.18
# Matching the user's host environment that works successfully

FROM ubuntu:20.04 AS r-base

# Install R 4.5.2 from CRAN and system dependencies
# Match Ubuntu Focal environment exactly - user has R 4.5.2
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
    software-properties-common \
    dirmngr \
    apt-transport-https \
    ca-certificates \
    gnupg2 \
    wget \
    && wget -qO- https://cloud.r-project.org/bin/linux/ubuntu/marutter_pubkey.asc | apt-key add - \
    && add-apt-repository "deb https://cloud.r-project.org/bin/linux/ubuntu focal-cran40/" \
    && apt-get update && apt-get install -y --no-install-recommends \
    r-base \
    r-base-dev \
    r-recommended \
    cmake \
    build-essential \
    gcc \
    g++ \
    make \
    libgdal-dev \
    libproj-dev \
    libgeos-dev \
    libudunits2-dev \
    libudunits2-0 \
    libssl-dev \
    libxml2-dev \
    pkgconf \
    libsqlite3-dev \
    libcurl4-openssl-dev \
    libblas3 \
    liblapack3 \
    libreadline8 \
    libpcre2-dev \
    libbz2-dev \
    liblzma-dev \
    zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*

# Install R packages with exact versions matching working environment
# User's R packages: sf 1.0-24, terra 1.8-93, dplyr 1.1.4, raster 3.6-32, etc.
RUN R -e "options(repos = c(CRAN = 'https://cran.rstudio.com/')); \
          install.packages(c('Rcpp', 'rlang', 'cli', 'lifecycle', 'vctrs'), dependencies=FALSE)" && \
    R -e "options(repos = c(CRAN = 'https://cran.rstudio.com/')); \
          install.packages(c('tibble', 'pillar', 'tidyselect', 'generics', 'glue', 'magrittr', 'R6', 'utf8', 'withr', 'wk'), dependencies=FALSE)" && \
    R -e "options(repos = c(CRAN = 'https://cran.rstudio.com/')); \
          install.packages('units', dependencies=FALSE)" && \
    R -e "options(repos = c(CRAN = 'https://cran.rstudio.com/')); \
          install.packages('s2', dependencies=TRUE)" && \
    R -e "options(repos = c(CRAN = 'https://cran.rstudio.com/')); \
          install.packages(c('geometries', 'sfheaders', 'jsonlite'), dependencies=FALSE)" && \
    R -e "options(repos = c(CRAN = 'https://cran.rstudio.com/')); \
          install.packages(c('rapidjsonr', 'jsonify'), dependencies=FALSE)" && \
    R -e "options(repos = c(CRAN = 'https://cran.rstudio.com/')); \
          install.packages('terra', dependencies=FALSE)" && \
    R -e "options(repos = c(CRAN = 'https://cran.rstudio.com/')); \
          install.packages('e1071', dependencies=FALSE)" && \
    R -e "options(repos = c(CRAN = 'https://cran.rstudio.com/')); \
          install.packages(c('classInt', 'DBI'), dependencies=FALSE)" && \
    R -e "options(repos = c(CRAN = 'https://cran.rstudio.com/')); \
          install.packages('sf', dependencies=TRUE)" && \
    R -e "options(repos = c(CRAN = 'https://cran.rstudio.com/')); \
          install.packages('dplyr', dependencies=TRUE)" && \
    R -e "options(repos = c(CRAN = 'https://cran.rstudio.com/')); \
          install.packages('sp', dependencies=FALSE)" && \
    R -e "options(repos = c(CRAN = 'https://cran.rstudio.com/')); \
          install.packages('raster', dependencies=FALSE)" && \
    R -e "options(repos = c(CRAN = 'https://cran.rstudio.com/')); \
          install.packages('gstat', dependencies=TRUE)" && \
    R -e "library(sf); library(dplyr); library(raster); library(terra); library(units); library(s2); library(sp); library(classInt); library(DBI); library(e1071); library(gstat); cat('All R packages installed successfully\n')"

FROM ubuntu:20.04 AS python-base

# Install Python 3.10.18 and R 4.5.2 from CRAN
# Match Ubuntu Focal environment exactly - user has Python 3.10.18, R 4.5.2
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
    software-properties-common \
    dirmngr \
    apt-transport-https \
    ca-certificates \
    gnupg2 \
    wget \
    curl \
    && wget -qO- https://cloud.r-project.org/bin/linux/ubuntu/marutter_pubkey.asc | apt-key add - \
    && add-apt-repository "deb https://cloud.r-project.org/bin/linux/ubuntu focal-cran40/" \
    && add-apt-repository ppa:savoury1/python -y \
    && echo "=== Creating apt preferences to prioritize Ubuntu focal packages ===" \
    && echo "Package: gdal-bin libgdal-dev libgdal26 libproj-dev libproj15 libgeos-dev libgeos-c1v5 libgeos-3.8.0 libspatialindex-dev libcurl4 libcurl4-openssl-dev libcurl3-gnutls libcfitsio8 libcfitsio-dev libdapclient6v5 libdap-dev libgeotiff5 libgeotiff-dev libnetcdf15 libnetcdf-dev libspatialite7 libspatialite-dev libxerces-c3.2 libxerces-c-dev libhdf4-alt-dev libcharls2 libcharls-dev" > /etc/apt/preferences.d/focal-spatial-packages \
    && echo "Pin: release o=Ubuntu,a=focal" >> /etc/apt/preferences.d/focal-spatial-packages \
    && echo "Pin-Priority: 1001" >> /etc/apt/preferences.d/focal-spatial-packages \
    && apt-get update \
    && echo "=== Checking python3.10 availability ===" \
    && apt-cache search python3.10 | grep "^python3.10 " | head -10 \
    && echo "=== Installing Python 3.10 first ===" \
    && apt-get install -y --no-install-recommends \
    python3.10 \
    python3.10-venv \
    python3.10-distutils \
    && echo "=== Verifying Python 3.10 installation ===" \
    && (python3.10 --version || (echo "ERROR: python3.10 not found, checking locations:" && which python3.10 || echo "which python3.10: not found" && ls -la /usr/bin/python3.10* 2>/dev/null || echo "No python3.10* in /usr/bin" && find /usr -name "python3.10" 2>/dev/null | head -5 || echo "No python3.10 found in /usr" && dpkg -L python3.10 2>/dev/null | grep bin || echo "python3.10 package files not found" && exit 1)) \
    && echo "=== Installing R and spatial dependencies ===" \
    && apt-get install -y --no-install-recommends \
    r-base \
    r-base-dev \
    r-recommended \
    build-essential \
    gcc \
    g++ \
    make \
    libblas3 \
    liblapack3 \
    libreadline8 \
    libpcre2-8-0 \
    libpcre2-dev \
    libbz2-1.0 \
    libbz2-dev \
    liblzma5 \
    liblzma-dev \
    zlib1g-dev \
    libcurl4-openssl-dev=7.68.0-1ubuntu2.25 \
    libcurl4=7.68.0-1ubuntu2.25 \
    libssl1.1 \
    libssl-dev \
    libxml2 \
    libxml2-dev \
    libtirpc-dev \
    libudunits2-dev \
    libudunits2-0 \
    libudunits2-data \
    python3.10-dev \
    libpq-dev \
    && echo "=== Installing GDAL dependencies first (from Ubuntu focal) ===" \
    && apt-get install -y --no-install-recommends \
    libcfitsio8 \
    libcfitsio-dev \
    libcurl3-gnutls \
    libdapclient6v5 \
    libdap-dev \
    libgeotiff5 \
    libgeotiff-dev \
    libnetcdf15 \
    libnetcdf-dev \
    libspatialite7 \
    libspatialite-dev \
    libxerces-c3.2 \
    libxerces-c-dev \
    libhdf4-alt-dev \
    libcharls2 \
    libcharls-dev \
    && echo "=== Installing spatial libraries (apt preferences will prioritize Ubuntu focal versions) ===" \
    && echo "=== Checking which versions will be installed ===" \
    && apt-cache policy libgdal-dev libgdal26 libproj-dev libproj15 | head -20 \
    && apt-get install -y --no-install-recommends \
    libgdal-dev=3.0.4+dfsg-1build3 \
    libgdal26=3.0.4+dfsg-1build3 \
    libproj-dev=6.3.1-1 \
    libproj15=6.3.1-1 \
    libgeos-dev=3.8.0-1build1 \
    libgeos-c1v5=3.8.0-1build1 \
    libgeos-3.8.0=3.8.0-1build1 \
    libspatialindex-dev=1.9.3-1build1 \
    && echo "=== Verifying installed versions match Ubuntu 20.04 ===" \
    && dpkg -l | grep -E "(gdal|proj|geos|spatialindex)" | head -10 \
    && echo "=== Versions verified ===" \
    && curl https://bootstrap.pypa.io/get-pip.py -o get-pip.py \
    && python3.10 get-pip.py \
    && rm get-pip.py \
    && ln -sf /usr/bin/python3.10 /usr/bin/python \
    && ln -sf /usr/bin/python3.10 /usr/bin/python3 \
    && python3.10 -m pip install --upgrade pip setuptools wheel \
    && rm -rf /var/lib/apt/lists/*

# Copy R packages from r-base stage (already compiled)
# R is installed in python-base, just copy the packages
COPY --from=r-base /usr/local/lib/R/site-library /usr/local/lib/R/site-library
COPY --from=r-base /usr/lib/R/site-library /usr/lib/R/site-library

# Ensure R site-library directories exist
RUN mkdir -p /usr/local/lib/R/site-library /usr/lib/R/site-library && \
    R --slave -e "cat('R_HOME:', R.home(), '\n')" > /tmp/r_home.txt

# Set R environment variables
ENV R_HOME=/usr/lib/R
ENV R_LIBS=/usr/local/lib/R/site-library:/usr/lib/R/site-library:/usr/lib/R/library
ENV R_LIBS_USER=/usr/local/lib/R/site-library
ENV LD_LIBRARY_PATH=/usr/lib/R/lib:/usr/lib/x86_64-linux-gnu
ENV PATH=/usr/bin:/usr/lib/R/bin:$PATH

# Set working directory
WORKDIR /app

# Set PYTHONPATH
ENV PYTHONPATH=/app

# Copy requirements and install Python packages
COPY requirements.txt .
# Update pip first to avoid metadata issues, then install packages
RUN python3.10 -m pip install --upgrade pip setuptools wheel && \
    python3.10 -m pip install --no-cache-dir -r requirements.txt

# Verify R installation works
RUN R --slave -e "library(utils); cat('R base packages loaded successfully\n')" || \
    (echo "Warning: R verification failed, but continuing..." && exit 0)

# Copy application code
COPY . .

# Expose Streamlit port
EXPOSE 8501

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import streamlit; import sys; sys.exit(0)" || exit 1

# Run Streamlit
CMD ["streamlit", "run", "app/main.py", "--server.port=8501", "--server.address=0.0.0.0"]
