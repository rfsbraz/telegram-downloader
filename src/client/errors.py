"""Telegram error groups shared by startup and the daemon loop."""

from pyrogram.errors import AuthKeyDuplicated, Unauthorized

# Telegram errors that mean the session is dead and a human must re-auth
# (AUTH_KEY_UNREGISTERED, SESSION_REVOKED, USER_DEACTIVATED, ...). Retrying
# them never helps, see issue #78.
AUTH_ERRORS = (Unauthorized, AuthKeyDuplicated)
