# Production Deployment Guide

Best practices for deploying Telegram Downloader to production.

## Prerequisites

!!! info "Before You Begin"
    Ensure you have:

    - [x] Docker and Docker Compose installed
    - [x] Telegram API credentials from https://my.telegram.org/apps
    - [ ] Discord webhook URL (optional but recommended)
    - [x] Basic Linux administration knowledge

## Production Configuration

### 1. Environment Variables

!!! danger "Security: Never Hardcode Secrets!"
    **Always use `.env` file for secrets, never hardcode in docker-compose.yml!**

```bash
# Create .env file (not in version control!)
cat > .env <<EOF
TDL_API_ID=12345678
TDL_API_HASH=abcdef1234567890abcdef1234567890
TDL_PHONE_NUMBER=+1234567890
TDL_DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/123/abc
EOF

# Secure permissions
chmod 600 .env
```

Reference in docker-compose.yml:
```yaml
environment:
  - TDL_API_ID=${TDL_API_ID}
  - TDL_API_HASH=${TDL_API_HASH}
  # ...
```

### 2. Resource Limits

!!! warning "Always Set Resource Limits"
    Prevent runaway processes from consuming all system resources:

```yaml
deploy:
  resources:
    limits:
      cpus: '1.0'      # Max 1 CPU core
      memory: 512M     # Max 512MB RAM
    reservations:
      cpus: '0.25'     # Reserve 0.25 cores
      memory: 128M     # Reserve 128MB
```

**Guidelines:**
- **Light usage** (<5 sources, small files): 0.5 CPU, 256M RAM
- **Moderate usage** (5-10 sources, mixed files): 1.0 CPU, 512M RAM
- **Heavy usage** (10+ sources, large files): 2.0 CPU, 1G RAM

### 3. Logging Configuration

Prevent disk exhaustion from logs:

```yaml
logging:
  driver: "json-file"
  options:
    max-size: "10m"     # Max 10MB per log file
    max-file: "3"       # Keep 3 log files (30MB total)
```

### 4. Restart Policy

Automatic recovery from failures:

```yaml
restart: unless-stopped
```

**Options:**
- `unless-stopped`: Restart on failure, not on manual stop (recommended)
- `always`: Always restart, even after manual stop
- `on-failure`: Only restart on error exit code

### 5. Health Checks

Monitor daemon status:

```yaml
healthcheck:
  test: ["CMD", "python3", "/app/healthcheck.py"]
  interval: 2m        # Check every 2 minutes
  timeout: 10s        # 10 second timeout
  start_period: 1m    # 1 minute grace period on startup
  retries: 3          # 3 failures = unhealthy
```

## Backup Strategy

!!! warning "Critical: Back Up Session Files"
    Without session files, you'll need to re-authenticate with Telegram!

### What to Back Up

!!! info "Backup Priority List"
    1. **Session files** (`.sessions/`) - **CRITICAL**: Authentication state
    2. **Configuration** (`config.toml` or `.env`) - **IMPORTANT**: Settings and secrets
    3. **Download history** (optional) - **NICE TO HAVE**: Downloaded files

### Automated Backup Script

```bash
#!/bin/bash
# backup.sh - Run daily via cron

BACKUP_DIR="/backup/telegram-downloader"
DATE=$(date +%Y-%m-%d)

# Create backup directory
mkdir -p "$BACKUP_DIR/$DATE"

# Backup sessions (critical!)
cp -r ./sessions "$BACKUP_DIR/$DATE/"

# Backup config
cp .env "$BACKUP_DIR/$DATE/"

# Compress
tar -czf "$BACKUP_DIR/telegram-downloader-$DATE.tar.gz" \
  -C "$BACKUP_DIR" "$DATE"

# Clean up
rm -rf "$BACKUP_DIR/$DATE"

# Keep last 7 days
find "$BACKUP_DIR" -name "*.tar.gz" -mtime +7 -delete

echo "Backup complete: $BACKUP_DIR/telegram-downloader-$DATE.tar.gz"
```

Add to crontab:
```bash
# Run daily at 3 AM
0 3 * * * /path/to/backup.sh
```

## Monitoring

### 1. Health Check Integration

**Docker:**
```bash
# Check health status
docker compose ps

# Unhealthy containers shown in red
```

**External monitoring (Uptime Kuma, etc.):**
```bash
# Expose health check (not recommended, use Docker health)
# OR create monitoring script:

#!/bin/bash
STATUS=$(docker inspect --format='{{.State.Health.Status}}' telegram-downloader)
if [ "$STATUS" != "healthy" ]; then
  echo "Container unhealthy!"
  # Send alert (email, webhook, etc.)
fi
```

### 2. Log Monitoring

Watch for errors:
```bash
# Real-time error monitoring
docker compose logs -f | grep -i error

# Count errors in last hour
docker compose logs --since 1h | grep -i error | wc -l
```

### 3. Resource Monitoring

Track resource usage:
```bash
# Live stats
docker stats telegram-downloader

# Historical trends (requires monitoring system)
# Prometheus, Grafana, etc.
```

## Security Hardening

!!! success "Built-in Security Features"
    The container is already configured with security best practices.

### 1. Non-Root User

!!! tip "Verify Non-Root Execution"
    Container already runs as UID 1000 (non-root). Verify:
```bash
docker compose exec telegram-downloader whoami
# Should output: appuser
```

### 2. Read-Only Config

Mount config as read-only:
```yaml
volumes:
  - ./config.toml:/app/config.toml:ro  # :ro = read-only
```

### 3. Network Isolation

No exposed ports needed (daemon only makes outbound connections):
```yaml
# No ports section in docker-compose.yml
# If you need debugging access, use docker exec instead
```

### 4. Secrets Management

**Production-grade secrets:**
- Use Docker Secrets (Swarm mode)
- OR environment variables from secrets manager (AWS Secrets Manager, HashiCorp Vault)
- Never commit secrets to version control

### 5. Regular Updates

```bash
# Update to latest image
docker compose pull
docker compose up -d

# Verify health after update
docker compose ps
```

## Disaster Recovery

### Recovery from Backup

```bash
# Stop service
docker compose down

# Restore session files
tar -xzf backup/telegram-downloader-YYYY-MM-DD.tar.gz
cp -r telegram-downloader-YYYY-MM-DD/sessions ./

# Restore config
cp telegram-downloader-YYYY-MM-DD/.env ./

# Start service
docker compose up -d

# Verify
docker compose logs -f
```

### Complete Rebuild

```bash
# Stop and remove everything
docker compose down -v

# Re-authenticate (will request phone code)
docker compose up -d
docker compose logs -f
# Enter verification code when prompted
```

## High Availability (Optional)

For mission-critical deployments:

1. **Multiple instances:** Run on different hosts with different sources
2. **Shared storage:** Use network volumes (NFS, S3) for downloads
3. **Load balancing:** Not applicable (no incoming requests)
4. **Failover:** Use Docker Swarm or Kubernetes for automatic restart

**Note:** Single instance is sufficient for most use cases.

## Performance Tuning

### 1. Check Interval

Balance between responsiveness and API usage:
```yaml
- TDL_DAEMON_CHECK_INTERVAL=300  # 5 minutes (balanced)
# OR
- TDL_DAEMON_CHECK_INTERVAL=600  # 10 minutes (light API usage)
# OR
- TDL_DAEMON_CHECK_INTERVAL=60   # 1 minute (maximum responsiveness, risk of rate limiting)
```

### 2. Notification Throttling

Prevent notification spam:
```yaml
- TDL_NOTIFICATIONS_THROTTLE_SECONDS=300  # 5 minutes between notifications
```

### 3. Retry Configuration

Adjust retry behavior for reliability:
```yaml
- TDL_RETRY_MAX_RETRIES=3      # More retries for flaky networks
- TDL_RETRY_BASE_DELAY=2       # Seconds between retries
- TDL_RETRY_MAX_DELAY=120      # Max backoff delay
```

## Production Checklist

!!! note "Pre-Deployment Checklist"
    **Complete these tasks before deploying to production:**

    - [ ] Secrets in `.env` file (not hardcoded)
    - [ ] `.env` file has 600 permissions (`chmod 600 .env`)
    - [ ] Resource limits configured
    - [ ] Logging limits configured
    - [ ] Health check enabled
    - [ ] Restart policy set to `unless-stopped`
    - [ ] Backup script configured and tested
    - [ ] Monitoring alerts set up
    - [ ] Config mounted read-only (optional)
    - [ ] Documentation reviewed

!!! success "Post-Deployment Verification"
    **Verify these after deployment:**

    - [ ] Service starts successfully (`docker compose ps`)
    - [ ] Health check passes (status shows "healthy")
    - [ ] Authentication works (check logs)
    - [ ] Downloads completing successfully
    - [ ] Notifications received (if enabled)
    - [ ] Resource usage within limits (`docker stats`)
    - [ ] Logs readable and not growing unbounded
    - [ ] Backup script running daily (check cron)

!!! question "Need Help?"
    See [Troubleshooting Guide](troubleshooting.md) or [open an issue on GitHub](https://github.com/rfsbraz/telegram-downloader/issues).
