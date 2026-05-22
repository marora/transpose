# Dockerfile for Transpose
# Multi-stage build for production-ready container

# Stage 1: Build stage
FROM python:3.12-slim AS builder

WORKDIR /build

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy project files
COPY pyproject.toml ./
COPY src ./src
COPY web ./web
COPY README.md ./

# Install Python dependencies
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir .

# Stage 2: Runtime stage
FROM python:3.12-slim

WORKDIR /app

# Install runtime system dependencies for WeasyPrint (PDF generation)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpango-1.0-0 \
    libpangoft2-1.0-0 \
    libcairo2 \
    libgdk-pixbuf-2.0-0 \
    libffi-dev \
    shared-mime-info \
    fontconfig \
    && rm -rf /var/lib/apt/lists/*

# Install Devanagari and Gurmukhi fonts for Indic script PDF rendering
COPY fonts/ /usr/local/share/fonts/transpose/
RUN fc-cache -f

# Copy installed packages from builder
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application source
COPY --from=builder /build/src /app/src
COPY --from=builder /build/web /app/web

ENV TRANSPOSE_WEB_ROOT=/app/web

# Create non-root user
RUN useradd -m -u 1000 transpose && \
    chown -R transpose:transpose /app

USER transpose

# Health check endpoint
EXPOSE 8000

# Run the HTTP API server
CMD ["python", "-m", "transpose.api"]
