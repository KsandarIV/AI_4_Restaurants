"""The complete site (showcase/): served locally, pointed at the voice PC, safe against path tricks."""

from __future__ import annotations

import sys
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from showcase import launcher, serve  # noqa: E402


@pytest.fixture()
def site() -> str:
    server = ThreadingHTTPServer(("127.0.0.1", 0), serve.make_handler("http://10.0.0.7:8003"))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}"  # type: ignore[misc]
    server.shutdown()


def _get(url: str) -> tuple[int, str]:
    try:
        with urllib.request.urlopen(url, timeout=5) as resp:
            return resp.status, resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        return exc.code, ""


def test_index_is_pointed_at_the_voice_pc(site: str) -> None:
    status, html = _get(site + "/")
    assert status == 200
    assert 'window.VOICE_BASE = "http://10.0.0.7:8003"' in html
    assert html.index("VOICE_BASE") < html.index("/site-assets/app.js")  # set before the script runs
    assert 'href="http://10.0.0.7:8003/test-voice"' in html  # the footer link leaves for the voice PC


def test_assets_are_served_and_paths_cannot_escape(site: str) -> None:
    assert _get(site + "/site-assets/app.js")[0] == 200 and _get(site + "/site-assets/site.css")[0] == 200
    assert _get(site + "/health")[0] == 200
    assert _get(site + "/site-assets/../../../../../.env")[0] == 404
    assert _get(site + "/site-assets/%2e%2e/%2e%2e/server.py")[0] == 404
    assert _get(site + "/nothing")[0] == 404


def test_the_site_script_honours_the_voice_base() -> None:
    js = (ROOT / "voice/src/voicebot/pipeline/site/app.js").read_text(encoding="utf-8")
    assert "window.VOICE_BASE" in js and 'API.replace(/^http/, "ws")' in js
    assert js.count('API + "/site/') == 7  # menu, info, reservation, config + 3 chat calls: nothing hard-wired to same-origin


def test_addresses_are_the_easy_ones_and_every_role_opens_its_page() -> None:
    assert launcher.NAMES["solo-be"] == "http://solo-be.localhost:8080/"
    assert launcher.NAMES["completo"] == "http://completo.localhost:8090/"
    assert launcher.NAMES["chat"] == "http://chat.localhost:8080/"
    assert launcher.NAMES["voce"] == "http://voce.localhost:8003/test-voice"
    assert launcher.OPEN == {"be": ["solo-be", "completo"], "chat": ["chat"], "voice": ["voce"]}


def test_the_machine_setup_hook_exists_and_cannot_stop_a_component() -> None:
    text = (ROOT / "lan" / "machine_setup.py").read_text(encoding="utf-8")
    assert "from showcase.launcher import start_showcase" in text
    assert "showcase non avviato" in text  # failure is logged, the component still starts
