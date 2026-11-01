FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# build tooling needed by numpy/scipy wheels on slim images
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY app ./app
COPY tests ./tests

# SQLite + ML artifacts live on mounted volumes
RUN mkdir -p /app/data /app/ml_artifacts

ENV GRIDS_DATABASE_URL=sqlite:////app/data/grids.db \
    GRIDS_ML_MODEL_PATH=/app/ml_artifacts/ml_correction.joblib \
    GRIDS_ML_DATASET_PATH=/app/ml_artifacts/eval_report.json

EXPOSE 8000

HEALTHCHECK --interval=20s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -fsS http://localhost:8000/api/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
