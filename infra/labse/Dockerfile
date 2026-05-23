# LaBSE Multilingual Embedding Sidecar
# Purpose: Provides semantic similarity embeddings for Oracle Translation Quality Score Layer A
# Model: sentence-transformers/LaBSE (109 languages, ~1.8 GB weights)
# Endpoint: POST /embed for embedding generation, GET /health for readiness

FROM python:3.12-slim AS builder

# Install build dependencies
RUN pip install --no-cache-dir \
    sentence-transformers==3.0.1 \
    torch==2.3.1 \
    transformers==4.41.2

# Download LaBSE model weights at build time (baked into image — no runtime download)
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('sentence-transformers/LaBSE')"

# ============================================================================
# Runtime stage
# ============================================================================
FROM python:3.12-slim

WORKDIR /app

# Install runtime dependencies (torch, transformers, sentence-transformers, flask)
RUN pip install --no-cache-dir \
    sentence-transformers==3.0.1 \
    torch==2.3.1 \
    transformers==4.41.2 \
    flask==3.0.3 \
    gunicorn==22.0.0

# Copy model weights from builder stage
COPY --from=builder /root/.cache/huggingface /root/.cache/huggingface

# Copy application code
COPY infra/labse/app.py /app/app.py

# Expose port 8500 for embedding service
EXPOSE 8500

# Health check: /health endpoint returns 200 once model is loaded
HEALTHCHECK --interval=30s --timeout=10s --start-period=120s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8500/health').read()"

# Start the embedding service with gunicorn (1 worker to keep memory usage low)
CMD ["gunicorn", "--bind", "0.0.0.0:8500", "--workers", "1", "--timeout", "120", "--log-level", "info", "app:app"]
