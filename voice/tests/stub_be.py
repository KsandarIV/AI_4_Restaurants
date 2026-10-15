"""Stub BE for the voice tests. The implementation lives in the package (``voicebot.devtools``)
because ``python -m voicebot local`` needs it too; this file keeps the path used by docs/AGENTS.md.

Standalone: ``python voice/tests/stub_be.py [port]``.
"""

from __future__ import annotations

import sys
from pathlib import Path

try:
    from voicebot.devtools import stub_be as _impl
except ImportError:  # run as a script without the package installed: use ../src
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
    from voicebot.devtools import stub_be as _impl

INFO = _impl.INFO
MENU = _impl.MENU
Handler = _impl.Handler
StubState = _impl.StubState
make_stub = _impl.make_stub
main = _impl.main

if __name__ == "__main__":
    raise SystemExit(main())
