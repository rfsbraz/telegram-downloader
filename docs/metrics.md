# Metrics

Telegram Media Downloader can expose a Prometheus `/metrics` endpoint. It is off by default.

## Enable

Set the following, and publish the port if you run in Docker:

```yaml
- TDL_METRICS_ENABLED=true
- TDL_METRICS_PORT=9184
```

The same settings in a config file:

```yaml
metrics:
  enabled: true
  port: 9184
```

The endpoint is unauthenticated. Only expose it on a private network or behind a scrape proxy.

## Scrape config

```yaml
scrape_configs:
  - job_name: telegram-downloader
    static_configs:
      - targets: ['telegram-downloader:9184']
```

Replace the target with the hostname or container name Prometheus uses to reach the downloader. If you change `TDL_METRICS_PORT`, change the target port to match.

## Metrics

| Name | Type | Labels | Description |
|------|------|--------|-------------|
| `telegram_downloader_files_downloaded_total` | counter | `source` | Files downloaded successfully |
| `telegram_downloader_bytes_downloaded_total` | counter | `source` | Bytes downloaded successfully |
| `telegram_downloader_files_failed_total` | counter | `source` | Files that failed to download |
| `telegram_downloader_files_skipped_total` | counter | `source`, `reason` | Files skipped. `reason` is `duplicate`, `tracked`, `error`, or `filter` |
| `telegram_downloader_pending_queue_size` | gauge | `source` | Messages waiting in the pending queue |
| `telegram_downloader_last_check_timestamp_seconds` | gauge | | Unix time of the last completed check |
| `telegram_downloader_check_duration_seconds` | histogram | | Duration of each download check |
| `telegram_downloader_floodwait_seconds_total` | counter | | Seconds of FloodWait requested by Telegram |
| `telegram_downloader_up` | gauge | | `1` while the metrics endpoint is running |

`source` is the source `name` from the config when set, otherwise the display name used in logs.

These counters follow the same events as the run summary. A dry-run still records check duration and last-check time, but it does not increment download, skip, or failure counters.

Labeled counters appear on the scrape after the first event for that label set.

## Grafana dashboard

A starter dashboard is in [`docs/grafana/telegram-downloader.json`](https://github.com/rfsbraz/telegram-downloader/blob/main/docs/grafana/telegram-downloader.json). Import it in Grafana (Dashboards, Import) and point it at your Prometheus datasource.
