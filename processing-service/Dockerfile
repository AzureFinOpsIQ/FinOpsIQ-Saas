FROM python:3.11-slim-bookworm AS builder
WORKDIR /build
# Rebuild marker: refresh service image without changing runtime behavior.
COPY base.txt ./base.txt
COPY shared-lib/ ./shared-lib/
COPY requirements.txt ./requirements.txt
RUN pip install --no-cache-dir --prefix=/install ./shared-lib -r requirements.txt

FROM python:3.11-slim-bookworm AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

RUN pip install --no-cache-dir --upgrade pip setuptools wheel jaraco.context

WORKDIR /app
COPY --from=builder /install /usr/local
COPY src/src/ ./src/
RUN useradd --create-home --uid 1000 appuser && chown -R appuser:appuser /app
USER 1000
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health/live')" || exit 1
CMD ["uvicorn", "src.microservices.processing_service:app", "--host", "0.0.0.0", "--port", "8000"]

