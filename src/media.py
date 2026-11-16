"""Helpers for choosing downloadable media on a Telegram message.

File attachments (document, audio, video, animation, voice, video_note)
are always considered. Compressed photos are opt-in because photo-heavy
chats can be huge (issue #59).
"""
from __future__ import annotations

from typing import Any

FILE_MEDIA_ATTRS = (
    "document",
    "audio",
    "video",
    "animation",
    "voice",
    "video_note",
)


def get_file_media(message: Any) -> Any | None:
    """Return the first file-attachment object, or None."""
    for attr in FILE_MEDIA_ATTRS:
        obj = getattr(message, attr, None)
        if obj:
            return obj
    return None


def is_photo_only(message: Any) -> bool:
    """True when the message has a compressed photo and no file attachment."""
    return get_file_media(message) is None and getattr(message, "photo", None) is not None


def largest_photo(message: Any) -> Any | None:
    """Return the largest size of a compressed photo, or None.

    kurigram already exposes Message.photo as the largest size. If a sizes
    list is present (raw photo objects or tests), pick the biggest by
    file size, then by pixel area.
    """
    photo = getattr(message, "photo", None)
    if not photo:
        return None
    sizes = getattr(photo, "sizes", None)
    if sizes:
        def size_key(item: Any) -> tuple[int, int]:
            file_size = getattr(item, "file_size", None) or getattr(item, "size", None) or 0
            width = getattr(item, "width", None) or getattr(item, "w", None) or 0
            height = getattr(item, "height", None) or getattr(item, "h", None) or 0
            return (file_size, width * height)

        return max(sizes, key=size_key)
    return photo


def get_media(message: Any, include_photos: bool = False) -> Any | None:
    """Return the media object to download, or None."""
    media = get_file_media(message)
    if media:
        return media
    if include_photos:
        return largest_photo(message)
    return None


def has_source_media(message: Any) -> bool:
    """True if the source iterator should yield this message."""
    return get_media(message, include_photos=True) is not None


def _photo_name_token(message: Any) -> str:
    """Return a stable photo-name token that is not chat-local message id alone.

    file_unique_id identifies the photo across chats. When it is missing,
    the chat id is included because message ids collide in a shared folder.
    """
    photo = largest_photo(message) or getattr(message, "photo", None)
    unique = getattr(photo, "file_unique_id", None) if photo is not None else None
    if unique:
        return str(unique)
    chat = getattr(message, "chat", None)
    chat_id = getattr(chat, "id", None) if chat is not None else getattr(message, "chat_id", None)
    if chat_id is not None:
        return f"{chat_id}_{message.id}"
    return str(message.id)


def photo_filename(message: Any) -> str:
    """Generate photo_<YYYY-MM-DD>_<identity>.jpg from date and a stable id."""
    date = getattr(message, "date", None)
    date_str = date.strftime("%Y-%m-%d") if date is not None and hasattr(date, "strftime") else "unknown"
    return f"photo_{date_str}_{_photo_name_token(message)}.jpg"


def media_filename(message: Any, media: Any) -> str:
    """Return the media file name, generating one for photos that have none."""
    fname = getattr(media, "file_name", None)
    if fname:
        return fname
    if is_photo_only(message):
        return photo_filename(message)
    return f"message_{message.id}"


async def collect_matching_ids(source: Any, last_seen_id: int, composite_filter: Any, log: Any) -> list[int]:
    """Collect message IDs that pass the filter, logging skipped photos.

    Photo messages are counted and omitted when include_photos is off so
    users can discover the option from a DEBUG log.
    """
    ids: list[int] = []
    skipped_photos = 0
    include_photos = getattr(composite_filter, "include_photos", False)
    async for msg in source.iterate_new_media(last_seen_id):
        if is_photo_only(msg) and not include_photos:
            skipped_photos += 1
            continue
        if await composite_filter.matches(msg):
            ids.append(msg.id)
    if skipped_photos:
        log.debug(
            "Skipped %s photo(s). Set TDL_GLOBAL_FILTERS_INCLUDE_PHOTOS=true "
            "or TDL_SOURCES_N_FILTERS_INCLUDE_PHOTOS=true to download them.",
            skipped_photos,
        )
    return ids
