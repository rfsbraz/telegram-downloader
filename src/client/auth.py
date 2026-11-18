"""One-shot login helper behind `python -m src.main auth`.

Runs the normal interactive login (phone, code, 2FA), then prints the exported
session string so it can go into TDL_SESSION_STRING. The string is the account
session: it goes to stdout only, and the warning to stderr.
"""

import sys
import tempfile
from typing import TextIO

from src.client.factory import create_client
from src.config.schema import Config

WARNING = (
    "Copy the session string above into TDL_SESSION_STRING.\n"
    "It gives full access to your Telegram account: treat it like a password."
)


async def run_auth(config: Config, out: TextIO | None = None, err: TextIO | None = None) -> None:
    """Log in interactively and print the session string.

    The login is always fresh: a configured TDL_SESSION_STRING is ignored, and the
    session lives in a throwaway directory, so the runtime session file is neither
    reused nor changed. Dry-run is off for the same reason.
    """
    out = out or sys.stdout
    err = err or sys.stderr
    with tempfile.TemporaryDirectory(prefix="tdl-auth-session-") as session_dir:
        fresh = config.model_copy(
            update={"session_string": None, "session_dir": session_dir, "dry_run": False}
        )
        client = create_client(fresh)
        async with client:
            session_string = await client.export_session_string()
    print(session_string, file=out)
    print(WARNING, file=err)
