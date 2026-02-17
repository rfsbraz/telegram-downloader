# Troubleshooting Guide

Solutions for common errors and issues.

## Table of Contents

1. [Telegram Errors](#telegram-errors)
2. [Docker Issues](#docker-issues)
3. [Health Check Problems](#health-check-problems)
4. [Notification Failures](#notification-failures)
5. [Performance Issues](#performance-issues)

## Telegram Errors

### FloodWait Error

!!! warning "FloodWait - Telegram Rate Limiting"
    **Symptom:** Logs show "FloodWait" error with wait time.

    **Cause:** Telegram rate limiting (too many API requests).

    **Automatic Handling:** Daemon retries automatically after wait time with exponential backoff.

!!! tip "Reduce FloodWait Frequency"
    If FloodWait errors are persistent:

    ```yaml
    - TDL_DAEMON_CHECK_INTERVAL=600  # Check every 10 minutes instead of 5
    ```

    **Prevention:** Don't check too frequently (minimum 60 seconds recommended).

!!! danger "When to Worry"
    FloodWait >60 seconds triggers notification. If persistent, you're checking too often or have too many sources.

### PEER_ID_INVALID Error

!!! danger "PEER_ID_INVALID - Source Access Error"
    **Symptom:** "PEER_ID_INVALID" error when accessing source.

    **Common Causes:**

    1. Invalid source URL format
    2. Bot/user doesn't have access to source
    3. Source deleted or banned

!!! success "Solutions"
    1. Verify URL format matches [configuration guide](configuration.md)
    2. Test access in Telegram app first
    3. For private channels: Ensure you're a member
    4. For forum topics: Verify topic ID is correct

### USER_NOT_PARTICIPANT Error

!!! bug "USER_NOT_PARTICIPANT - Membership Required"
    **Symptom:** "USER_NOT_PARTICIPANT" error.

    **Cause:** You're not a member of the channel/group.

    **Fix:**

    1. Open Telegram app
    2. Join the channel/group
    3. Restart downloader: `docker compose restart`

### CHAT_FORBIDDEN Error

!!! danger "CHAT_FORBIDDEN - Access Denied"
    **Symptom:** "CHAT_FORBIDDEN" error.

    **Possible Causes:**

    - You were banned from the source
    - Source set to private/invite-only
    - Source was deleted

    **Resolution:**

    - Check source access in Telegram app
    - Contact source admin for access
    - Remove source from configuration if no longer accessible

### Authentication Failed

!!! failure "Authentication Failed"
    **Symptom:** "Authentication failed" or "Invalid phone number".

    **Step-by-step Fix:**

    1. Verify `TDL_API_ID` and `TDL_API_HASH` are correct
    2. Check phone number includes country code: `+1234567890`
    3. Delete session files and re-authenticate:

    ```bash
    docker compose down
    rm -rf sessions/*
    docker compose up -d
    docker compose logs -f  # Follow authentication prompts
    ```

## Docker Issues

### Container Won't Start

!!! bug "Container Exits Immediately"
    **Symptom:** `docker compose up` fails or container exits immediately.

    **Diagnosis Commands:**

    ```bash
    # Check logs
    docker compose logs

    # Check container status
    docker compose ps
    ```

!!! warning "Common Causes"
    1. Missing required env vars (`TDL_API_ID`, `TDL_API_HASH`, `TDL_PHONE_NUMBER`)
    2. Invalid configuration syntax
    3. Port conflicts (rare - this app doesn't expose ports)

!!! success "Solutions"
    **1. Verify all required environment variables:**

    ```bash
    docker compose config | grep TDL_API
    ```

    **2. Validate compose file syntax:**

    ```bash
    docker compose config
    ```

    **3. Check error messages in logs:**

    ```bash
    docker compose logs --tail=50
    ```

### Permission Denied Errors

!!! danger "Permission Denied - File Write Errors"
    **Symptom:** "Permission denied" errors in logs when writing files.

    **Cause:** Volume mount permission mismatch (host UID ≠ container UID).

!!! success "Fix Permissions"
    Container runs as UID 1000. Set correct permissions on host:

    ```bash
    sudo chown -R 1000:1000 ./downloads ./sessions
    ```

!!! tip "Alternative: Use Named Volumes"
    Instead of bind mounts, use named volumes (Docker manages permissions automatically):

    ```yaml
    volumes:
      - downloads:/downloads
      - sessions:/app/.sessions

    volumes:
      downloads:
      sessions:
    ```

### Health Check Failing

!!! bug "Unhealthy Status"
    **Symptom:** `docker compose ps` shows "unhealthy" status.

    **Diagnosis Commands:**

    ```bash
    # Check health file contents
    docker compose exec telegram-downloader cat /app/health_status.txt

    # Run health check manually
    docker compose exec telegram-downloader python3 /app/healthcheck.py
    echo $?  # 0 = healthy, 1 = unhealthy
    ```

!!! warning "Common Causes"
    1. Daemon not enabled (`TDL_DAEMON_ENABLED=false`)
    2. Daemon crashed (check logs)
    3. Health file stale (daemon stuck)

!!! success "Solutions"
    **1. Enable daemon mode:**

    ```yaml
    - TDL_DAEMON_ENABLED=true
    ```

    **2. Check logs and restart:**

    ```bash
    docker compose logs --tail=100
    docker compose restart
    ```

    **3. If persistent, increase start period:**

    ```yaml
    healthcheck:
      start_period: 2m  # Give more time to start
    ```

### Slow Multi-Platform Builds

**Symptom:** Docker builds take >20 minutes.

**Cause:** QEMU emulation overhead for ARM64.

**Solutions:**
1. Use build cache (GitHub Actions does this automatically):
   ```bash
   docker buildx build --cache-from type=local,src=/tmp/cache ...
   ```
2. Build only for your platform locally:
   ```bash
   docker build --platform linux/amd64 .
   ```
3. Use native ARM64 runners in CI (costs money)

## Health Check Problems

### Status Always "starting"

**Symptom:** Health check shows "starting" status even after start period.

**Cause:** Daemon not updating health file.

**Solution:**
1. Check daemon is enabled
2. Verify health file path matches config
3. Check for permission errors in logs

### Status "error" But Daemon Running

**Symptom:** Health check shows "error" but logs look normal.

**Cause:** Last check iteration failed but daemon recovered.

**Solution:**
- This is normal after transient errors (FloodWait, network issues)
- Wait for next check cycle (health updates every check interval)
- If persistent, check logs for recurring errors

## Notification Failures

### Discord Notifications Not Received

**Symptom:** No Discord messages despite `TDL_NOTIFICATIONS_ENABLED=true`.

**Diagnosis:**
```bash
# Check logs for notification attempts
docker compose logs | grep notification
```

**Common causes:**
1. Invalid webhook URL
2. Webhook deleted in Discord
3. Notifications throttled (too frequent)

**Solutions:**
1. Test webhook URL manually:
   ```bash
   curl -X POST "YOUR_WEBHOOK_URL" \
     -H "Content-Type: application/json" \
     -d '{"content": "Test message"}'
   ```
2. Regenerate webhook in Discord if invalid
3. Check throttle settings: `TDL_NOTIFICATIONS_THROTTLE_SECONDS`

### Too Many Notifications (Spam)

**Symptom:** Flooded with notifications during bulk downloads.

**Cause:** Notification throttling too aggressive or disabled.

**Solution:**
Increase throttle period:
```yaml
- TDL_NOTIFICATIONS_THROTTLE_SECONDS=300  # 5 minutes between notifications
```

Or reduce detail level:
```yaml
- TDL_NOTIFICATIONS_DETAIL_LEVEL=minimal  # Status only
```

## Performance Issues

### High Memory Usage

**Symptom:** Container using >512MB RAM.

**Diagnosis:**
```bash
docker stats telegram-downloader
```

**Causes:**
1. Large file downloads
2. Many concurrent sources
3. Memory leak (rare)

**Solutions:**
1. Increase memory limit in docker-compose.yml:
   ```yaml
   deploy:
     resources:
       limits:
         memory: 1G
   ```
2. Reduce concurrent downloads (add to future config)
3. Restart container periodically if memory leak suspected

### Slow Downloads

**Symptom:** Downloads slower than expected.

**Causes:**
1. Network throttling (ISP or Telegram)
2. Large files
3. Distant Telegram data center

**Solutions:**
1. Check network speed: `docker compose exec telegram-downloader curl -o /dev/null https://speed.cloudflare.com/__down?bytes=100000000`
2. Verify no FloodWait errors (Telegram rate limiting)
3. Consider VPS in different region if persistent

### High CPU Usage

**Symptom:** Container using >50% CPU consistently.

**Diagnosis:**
```bash
docker stats telegram-downloader
```

**Causes:**
1. Active download/upload
2. Many sources being checked
3. Inefficient filtering (rare)

**Solutions:**
1. Reduce check frequency: `TDL_DAEMON_CHECK_INTERVAL=600`
2. Limit CPU usage in docker-compose.yml:
   ```yaml
   deploy:
     resources:
       limits:
         cpus: '0.5'
   ```

## Download Tracking

### Files Re-Downloaded After Moving

**Symptom:** Files you've already downloaded are being downloaded again after you move or rename them.

**Cause:** Download tracking may be disabled, or the state database was deleted.

**Solutions:**

1. Ensure download tracking is enabled (it's on by default):
   ```yaml
   - TDL_TRACK_DOWNLOADS=true
   ```
2. Make sure the sessions volume is persisted — the download history lives in `state.db` alongside cursor data:
   ```yaml
   volumes:
     - ./sessions:/app/.sessions
   ```

### Want to Re-Download Everything

**Symptom:** You want to force re-download of all files (e.g., after a corrupted download).

**Solutions:**

1. Temporarily disable tracking:
   ```yaml
   - TDL_TRACK_DOWNLOADS=false
   ```
2. Or delete the state database to reset both cursors and download history:
   ```bash
   rm ./sessions/state.db
   ```

## Getting Help

!!! question "Still Stuck? Open an Issue"
    Follow these steps for the best support experience:

    **1. Gather diagnostic information:**

    ```bash
    # Docker version
    docker --version
    docker compose version

    # Container logs
    docker compose logs > logs.txt

    # Configuration (REDACT API CREDENTIALS!)
    docker compose config > config.txt
    ```

    **2. Create GitHub issue with:**

    - **Title:** Brief, descriptive summary
    - **Description:** What you tried, what happened, expected behavior
    - **Attachments:** Logs and config (redact sensitive info!)

    **3. Response time:** Usually within 24-48 hours

!!! tip "Before Opening an Issue"
    **Most issues are authentication or configuration problems.**

    Double-check the [Configuration Reference](configuration.md) first!

!!! warning "Redact Sensitive Information"
    **Always remove before sharing:**

    - API credentials (`TDL_API_ID`, `TDL_API_HASH`)
    - Phone numbers
    - Webhook URLs
    - Session files
