# Moving from telegram-download-daemon

This page is for people running [alfem/telegram-download-daemon](https://github.com/alfem/telegram-download-daemon) who want to switch to Telegram Downloader. It maps every setting the daemon reads to ours, shows a before and after `docker-compose.yml`, and lists what works differently.

The daemon details below were checked against its source at commit [`cbc317f`](https://github.com/alfem/telegram-download-daemon/tree/cbc317fbc86d763c6eb4b877b6ee6c276351c0ca) (21 June 2023, `TDD_VERSION = "1.14"`), the latest commit on its default branch when this page was written.

## How the two work

The daemon listens to one channel you admin. You forward or send files to that channel, it replies with progress, and it saves each file as it arrives. You can also send it the commands `list`, `status`, `clean` and `queue`.

Telegram Downloader reads the message history of one or more channels, groups, forum topics or private chats you can access. It checks for new files every `TDL_DAEMON_CHECK_INTERVAL` seconds (300 by default, minimum 60). It never posts messages, so there are no replies and no chat commands. You can keep forwarding files to the same channel and point Telegram Downloader at it.

## Settings map

The daemon reads 8 environment variables. Its README lists 7 of them; `TELEGRAM_DAEMON_SESSION_PATH` is only in the source and the sample `docker-compose.yml`.

| telegram-download-daemon | Telegram Downloader | Notes |
|---|---|---|
| `TELEGRAM_DAEMON_API_ID` | `TDL_API_ID` | Same value. |
| `TELEGRAM_DAEMON_API_HASH` | `TDL_API_HASH` | Same value. |
| `TELEGRAM_DAEMON_CHANNEL` | `TDL_SOURCES_0_URL` | Use `https://t.me/c/<channel id>`, for example `TELEGRAM_DAEMON_CHANNEL=1234567890` becomes `TDL_SOURCES_0_URL=https://t.me/c/1234567890`. `TDL_SOURCES_0_CHAT_ID=-1001234567890` also works. Add more sources with `TDL_SOURCES_1_URL` and so on. |
| `TELEGRAM_DAEMON_DEST` | `TDL_DOWNLOAD_DIR` | Default `/downloads` (the daemon's is `/telegram-downloads`). Files go into one subfolder per source unless you set `TDL_FLAT_STRUCTURE=true`. |
| `TELEGRAM_DAEMON_TEMP` | None | No separate temp folder. A file in progress is written as `<name>.<message id>.partial` in its final folder and renamed when complete. |
| `TELEGRAM_DAEMON_DUPLICATES` | None | No setting, the behavior is fixed. A file with the same name and size is skipped. Same name with a different size is saved as `name_2.ext`, `name_3.ext` and so on. With `TDL_TRACK_DOWNLOADS=true` (the default) a file already downloaded once is skipped even after you move or rename it. There is no overwrite mode. |
| `TELEGRAM_DAEMON_WORKERS` | `TDL_MAX_CONCURRENT_DOWNLOADS` | 1 to 10, default 1. The daemon defaults to the number of CPU cores. |
| `TELEGRAM_DAEMON_SESSION_PATH` | `TDL_SESSION_DIR` | Default `/app/.sessions` in the image. Mount a volume there. |

The daemon also has `TELEGRAM_DAEMON_TEMP_SUFFIX`, but that is a fixed constant (`tdd`) in its code, not something it reads from the environment. Our in-progress files end in `.partial`.

## Before and after

Before, the daemon's own `docker-compose.yml` at `cbc317f`:

```yaml
version: '3.5'

services:
  telegram-download-daemon:
    #build: .
    image: alfem/telegram-download-daemon:latest
    container_name: telegram-download
    read_only: true
    environment:
      TELEGRAM_DAEMON_API_ID: "YOUR API ID HERE"
      TELEGRAM_DAEMON_API_HASH: "YOUR API HASH HERE"
      TELEGRAM_DAEMON_CHANNEL: "YOUR CHANNEL ID HERE"
      TELEGRAM_DAEMON_DEST: "/downloads"
      TELEGRAM_DAEMON_SESSION_PATH: "/session"
      #TELEGRAM_DAEMON_WORKERS: 2
    volumes:
       - downloads:/downloads
       - sessions:/session
    restart: unless-stopped

volumes:
    downloads:
    sessions:
```

After, the same setup with Telegram Downloader ([examples/migrate-from-telegram-download-daemon.yml](https://github.com/rfsbraz/telegram-downloader/blob/main/examples/migrate-from-telegram-download-daemon.yml)):

```yaml
--8<-- "examples/migrate-from-telegram-download-daemon.yml"
```

The example leaves out `read_only: true` because we have not tested the image with a read-only root filesystem.

## Switching over

1. Stop the daemon: `docker compose down`.
2. Write the new `docker-compose.yml` and fill in your API ID, API hash and phone number.
3. Log in once: `docker compose run --rm telegram-downloader`, then enter the code Telegram sends you.
4. Start it: `docker compose up -d`.

You have to log in again. The daemon keeps a Telethon session; Telegram Downloader uses Pyrogram and its own session file, so the old session is not reused.

## What is different

- **Existing files.** On its first check Telegram Downloader goes through the whole history of each source and downloads every file that passes the filters, not only new ones. If you point it at the daemon's folder with `TDL_FLAT_STRUCTURE=true`, a file already there with the same name and size is skipped. Names do not always match, though: we replace spaces, brackets and other punctuation except `.`, `_` and `-` with `_`, and the daemon names some videos after their caption, so expect some files to download again.
- **File types.** By default only `.pdf`, `.epub` and `.mobi` are downloaded. Set `TDL_GLOBAL_FILTERS_EXTENSIONS=` (empty) to download every file type, as the example does, or list the extensions you want.
- **Photos.** The daemon saves photos sent as photos. From channels, groups and private chats, Telegram Downloader picks up documents, audio, video, animations, voice messages and video notes, but not photos. Send pictures as files if you need them.
- **Folders.** Files go into one subfolder per source by default. `TDL_FLAT_STRUCTURE=true` puts everything in one folder, like the daemon.
- **Timing.** Files arrive on the next check, not the moment they are posted.
- **Which chats.** Any channel, group, forum topic or private chat your account can read, not only channels you admin.
- **No chat replies or commands.** Use `docker compose logs -f`, the container health check, or [notifications](configuration.md#notification-configuration) instead.

See the [configuration reference](configuration.md) for every other setting.
