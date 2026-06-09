FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Copy the package first so the build backend can find it during install.
COPY pyproject.toml ./
COPY app ./app
COPY scripts ./scripts
RUN pip install --upgrade pip && pip install .

# data/ holds the SQLite DB; mounted as a volume in compose.
RUN mkdir -p /app/data

CMD ["python", "-m", "app.main"]
