# Telegram Downloader - Production Multi-Stage Build
# Optimized for size and security with separate build and runtime stages

# Build stage - includes build tools and compilers
FROM python:3.14-slim AS builder

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
FROM python:3.14-slim

WORKDIR /app

# Install runtime dependencies only
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Copy Python packages from builder stage to a shared location
COPY --from=builder /root/.local /usr/local

# Copy application code
COPY src/ ./src/
COPY healthcheck.py .

# Create directories for runtime data
RUN mkdir -p /downloads /.sessions && \
    chmod 700 /.sessions

# Environment variables
ENV PYTHONUNBUFFERED=1 \
    TDL_DOWNLOAD_DIR=/downloads \
    TDL_DAEMON_HEALTH_FILE=/app/health_status.txt

# Health check configuration for Docker orchestration
# Validates daemon is running and updating health file
# Interval: 2 minutes (check every 2min)
# Timeout: 10 seconds (healthcheck.py should complete quickly)
# Start period: 1 minute (allow startup validation time)
# Retries: 3 (fail after 3 consecutive unhealthy checks)
HEALTHCHECK --interval=2m \
            --timeout=10s \
            --start-period=1m \
            --retries=3 \
            CMD python3 /app/healthcheck.py

# Run as non-root user for security
RUN useradd -m -u 1000 appuser && \
    chown -R appuser:appuser /app /downloads /.sessions
USER appuser

# Default command - runs main.py
CMD ["python3", "-m", "src.main"]
