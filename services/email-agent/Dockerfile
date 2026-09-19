FROM python:3.11-slim

WORKDIR /app

# Install dependencies first so this layer is cached unless pyproject.toml changes.
COPY pyproject.toml ./
COPY app ./app
RUN pip install --no-cache-dir .

RUN useradd --create-home --uid 1000 appuser \
    && mkdir -p /app/data \
    && chown -R appuser:appuser /app
USER appuser

ENTRYPOINT ["python", "-m", "app.main"]
