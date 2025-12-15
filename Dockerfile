FROM python:3.11-slim

WORKDIR /app

# Install system dependencies for osmnx/geopandas
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    libgdal-dev \
    libgeos-dev \
    libproj-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt gunicorn

# Copy application code
COPY app.py .
COPY rainy_road.py .
COPY templates/ templates/
COPY static/ static/

# Create directories
RUN mkdir -p generated_maps cache

# Expose port
EXPOSE 8000

# Default command (can be overridden in docker-compose)
CMD ["gunicorn", "-w", "4", "-b", "0.0.0.0:8000", "app:app"]
