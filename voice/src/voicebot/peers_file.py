"""Where is the CHAT PC? Read lazily from the file the LAN launcher maintains (``AI4R_PEERS_FILE``).

``CHAT_SERVICE_URL`` pinned in the .env always wins. Otherwise the address is looked up at request time, so the voice
server can start before the CHAT PC exists, survive its address changing, and never ships a hard-coded example IP.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

CHAT_API_PORT = 8002


def chat_service_url(configured: str = "") -> str:
    """The CHAT service base URL: the configured one, else the verified peer from the peers file, else ''."""
    if configured:
        return configured.rstrip("/")
    path = os.environ.get("AI4R_PEERS_FILE", "")
    if not path:
        return ""
    try:
        host = str(json.loads(Path(path).read_text(encoding="utf-8")).get("chat", "")).strip()
    except (OSError, ValueError, AttributeError):
        return ""
    return f"http://{host}:{CHAT_API_PORT}" if host else ""
