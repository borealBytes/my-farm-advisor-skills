FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gdal-bin libgdal-dev g++ \
    && rm -rf /var/lib/apt/lists/*

COPY requirements-dashboard.txt .

RUN pip install --no-cache-dir -r requirements-dashboard.txt

COPY . .

ENV DATA_PIPELINE_DATA_ROOT=/app
ENV AG_WEATHER_START_YEAR=2021
ENV AG_WEATHER_END_YEAR=2025

EXPOSE 8501

HEALTHCHECK --interval=30s --timeout=10s --start-period=15s \
    CMD curl --fail http://localhost:8501/_stcore/health || exit 1

CMD ["streamlit", "run", "src/scripts/dashboard/build_rowcrop_dashboard.py", \
     "--server.port=8501", "--server.address=0.0.0.0", \
     "--server.headless=true", "--browser.gatherUsageStats=false"]
