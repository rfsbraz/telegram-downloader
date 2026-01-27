# Telegram Downloader - Production Multi-Stage Build
# Optimized for size and security with separate build and runtime stages

# Python version sourced from .python-version via build arg
ARG PYTHON_VERSION=3.12

# Build stage - includes build tools and compilers
FROM python:${PYTHON_VERSION}-slim AS builder

WORKDIR /build

# Install build dependencies (needed for cryptography and tgcrypto)
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        gcc \
        libc-dev \
        libffi-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# Runtime stage - minimal dependencies only
FROM python:${PYTHON_VERSION}-slim

WORKDIR /app

# Install runtime dependencies (gosu for entrypoint privilege drop)
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        ca-certificates \
        gosu \
    && rm -rf /var/lib/apt/lists/*

# Copy Python packages from builder stage to a shared location
COPY --from=builder /root/.local /usr/local

# Copy application code
COPY src/ ./src/
COPY healthcheck.py .
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Create non-root user and runtime directories
RUN useradd -m -u 1000 appuser && \
    mkdir -p /downloads /app/.sessions && \
    chown -R appuser:appuser /app /downloads

# Environment variables
ENV PYTHONUNBUFFERED=1 \
    TDL_DOWNLOAD_DIR=/downloads \
    TDL_SESSION_DIR=/app/.sessions \
    TDL_DAEMON_HEALTH_FILE=/app/health_status.txt

# Health check configuration for Docker orchestration
HEALTHCHECK --interval=2m \
            --timeout=10s \
            --start-period=1m \
            --retries=3 \
            CMD gosu appuser python3 /app/healthcheck.py

# Entrypoint fixes bind-mount permissions then drops to appuser
ENTRYPOINT ["/entrypoint.sh"]
CMD ["python3", "-m", "src.main"]
