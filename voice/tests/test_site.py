"""The voice site (same kind of site as the chat bot's), its /site/* proxy and the one-command local mode."""

from __future__ import annotations

import re
import socket
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
import pytest

from tests.helpers import stub_be
from voicebot.__main__ import main as cli_main
from voicebot.config import Settings
from voicebot.local import local_settings, pick_port
from voicebot.pipeline.server import create_app

SITE = Path(__file__).parent.parent / "src" / "voicebot" / "pipeline" / "site"


@asynccontextmanager
async def site_client(be_url: str, **overrides: object) -> AsyncIterator[httpx.AsyncClient]:
    settings = Settings(backend_base_url=be_url, **overrides)  # type: ignore[arg-type]
    app = create_app(settings)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://voice.test") as client:
        yield client


async def test_the_site_is_served_with_its_assets() -> None:
    async with stub_be() as (url, _), site_client(url) as client:
        page = await client.get("/")
        assert page.status_code == 200 and "Trattoria Bella Napoli" in page.text
        for element in ('id="menu-list"', 'id="res-list"', 'id="lookup-code"', 'id="orb"', 'id="chat-panel"'):
            assert element in page.text
        assert "/site-assets/app.js" in page.text and "/site-assets/site.css" in page.text
        for asset in ("app.js", "site.css"):
            assert (await client.get(f"/site-assets/{asset}")).status_code == 200
        assert (await client.get("/test-voice")).status_code == 200  # the test page


async def test_site_config_tells_the_page_language_and_mode() -> None:
    async with stub_be() as (url, _), site_client(url, voice_language="en", mode="local") as client:
        assert (await client.get("/site/config")).json() == {
            "language": "en", "mode": "local", "require_registration": True}


async def test_menu_and_info_come_through_this_server() -> None:
    async with stub_be() as (url, _), site_client(url) as client:
        menu = (await client.get("/site/menu")).json()
        assert {"category", "name", "price", "allergens", "is_vegetarian"} <= set(menu[0])
        assert (await client.get("/site/info")).json()["phone"].startswith("+39")


async def test_reservation_lookup_is_limited_to_its_owner() -> None:
    async with stub_be() as (url, state), site_client(url) as client:
        state.reservations["RES-STUB01"] = {
            "booking_code": "RES-STUB01", "customer_id": "cust_a", "status": "CONFIRMED", "table_number": 3,
            "table_location": "terrazza", "date": "2026-10-16", "time": "20:30", "guests_count": 4}
        mine = await client.get("/site/reservation/res-stub01", params={"customer_id": "cust_a"})
        assert mine.status_code == 200 and mine.json()["guests_count"] == 4 and mine.json()["status"] == "CONFIRMED"
        assert (await client.get("/site/reservation/RES-STUB01", params={"customer_id": "cust_b"})).status_code == 404
        assert (await client.get("/site/reservation/RES-STUB01")).status_code == 400  # no customer id
        assert (await client.get("/site/reservation/not%20a%20code!", params={"customer_id": "x"})).status_code in (400, 404)
        state.reservations["RES-STUB01"]["status"] = "CANCELLED"  # the site shows the up-to-date status
        assert (await client.get("/site/reservation/RES-STUB01", params={"customer_id": "cust_a"})).json()["status"] == "CANCELLED"


async def test_site_endpoints_answer_502_when_the_be_is_down() -> None:
    async with site_client("http://127.0.0.1:9") as client:
        for path in ("/site/menu", "/site/info", "/site/reservation/RES-ABC123?customer_id=c"):
            assert (await client.get(path)).status_code == 502  # the page then shows its fallback text


def _keys(block: str) -> set[str]:
    return set(re.findall(r"\b([a-z0-9_]+):\s*\"", block))


def test_the_site_has_the_same_texts_in_both_languages() -> None:
    js = (SITE / "app.js").read_text(encoding="utf-8")
    it_block = js[js.index("    it: {"): js.index("    en: {")]
    en_block = js[js.index("    en: {"): js.index("  let LANG")]
    assert _keys(it_block) == _keys(en_block) and len(_keys(it_block)) > 60
    used = set(re.findall(r"data-i18n(?:-placeholder|-aria)?=\"([a-z0-9_]+)\"", (SITE / "index.html").read_text(encoding="utf-8")))
    assert used <= _keys(it_block), used - _keys(it_block)  # every label in the HTML has a translation


def test_the_site_assistant_has_the_same_liquid_orb_as_the_test_page() -> None:
    js = (SITE / "app.js").read_text(encoding="utf-8")
    for needle in ("liquid orb", "createRadialGradient", "ripples", "flashRed", "const CX = 260", "wave(th, t, amp)"):
        assert needle in js, needle


async def test_the_test_page_is_test_voice_and_the_old_addresses_redirect() -> None:
    async with stub_be() as (url, _):
        for app in (create_app(local_settings(url, 8013, fake=True)), create_app(Settings(backend_base_url=url))):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://v") as client:
                page = await client.get("/test-voice")
                assert page.status_code == 200 and "VOICE / TESTS" in page.text and url in page.text
                for old in ("/prova-vocale", "/prova-vocale-test"):
                    moved = await client.get(old)
                    assert moved.status_code in (302, 307) and moved.headers["location"] == "/test-voice"


def test_the_voice_button_turns_into_the_orb_without_a_panel() -> None:
    html = (SITE / "index.html").read_text(encoding="utf-8")
    js = (SITE / "app.js").read_text(encoding="utf-8")
    assert 'id="assistant"' not in html and 'id="hangup"' not in html and 'id="chat-log"' not in html
    assert 'id="orb"' in html and 'id="chat-fab"' in html and "function showOrb" in js and "function startCall" in js
    assert 'logLine(' not in js  # no transcript on the site: it lives on /test-voice


async def test_the_chat_window_is_not_connected_without_a_chat_service_and_proxies_when_it_is() -> None:
    import json
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    class FakeChat(BaseHTTPRequestHandler):
        def log_message(self, *args: object) -> None:
            pass

        def do_POST(self) -> None:  # noqa: N802
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
            out = ({"session_id": "s1", "reply": "Buongiorno dal chat bot"} if self.path == "/chat/session"
                   else {"reply": "eco: " + body["text"]})
            raw = json.dumps(out).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

    chat = ThreadingHTTPServer(("127.0.0.1", 0), FakeChat)
    threading.Thread(target=chat.serve_forever, daemon=True).start()
    try:
        async with stub_be() as (url, _):
            async with site_client(url) as client:  # no CHAT_SERVICE_URL
                refused = await client.post("/site/chat/session")
                assert refused.status_code == 503 and "non è collegato" in refused.json()["detail"]
            async with site_client(url, chat_service_url=f"http://127.0.0.1:{chat.server_port}") as client:
                assert (await client.post("/site/chat/session")).json()["session_id"] == "s1"
                reply = await client.post("/site/chat/message", json={"session_id": "s1", "text": "ciao"})
                assert reply.json()["reply"] == "eco: ciao"
                assert (await client.post("/site/chat/message", json={"session_id": "s1", "text": " "})).status_code == 400
    finally:
        chat.shutdown()


def test_the_site_talks_to_this_server_only_and_handles_every_event() -> None:
    js = (SITE / "app.js").read_text(encoding="utf-8")
    for needle in ("/site/menu", "/site/info", "/site/reservation/", "/site/config", "/ws/voice", "localStorage",
                   "customer_id", "setTimeout(connect", "Math.min(500 * 2 ** retry"):
        assert needle in js
    for event in ("ready", "loading", "heard", "thinking", "reply", "barge_in", "registered", "reservation",
                  "reservation_confirmed", "call_ended", "error"):
        assert f'case "{event}"' in js
    assert "10.10." not in js and "192.168." not in js  # no hard-coded machine addresses


# ---------------- one-command local mode ----------------


def test_pick_port_skips_ports_in_use() -> None:
    with socket.socket() as busy:
        busy.bind(("127.0.0.1", 0))
        busy.listen()
        taken = busy.getsockname()[1]
        assert pick_port(taken) != taken


def test_local_settings_point_at_the_stub_and_can_go_fake() -> None:
    real = local_settings("http://127.0.0.1:8001", 8013, fake=False)
    assert (real.backend_base_url, real.voice_port, real.mode, real.voice_host) == (
        "http://127.0.0.1:8001", 8013, "local", "127.0.0.1")
    fake = local_settings("http://127.0.0.1:8001", 8013, fake=True)
    assert (fake.stt_backend, fake.tts_backend) == ("fake", "fake")


async def test_a_full_local_session_works_through_the_site_endpoints() -> None:
    """What `voicebot local` wires: stub BE + app in local mode; menu/info/config all answer."""
    async with stub_be() as (url, _):
        settings = local_settings(url, 8013, fake=True)
        app = create_app(settings)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://voice.test") as client:
            assert (await client.get("/site/config")).json()["mode"] == "local"
            assert len((await client.get("/site/menu")).json()) >= 4
            assert (await client.get("/health")).json() == {"status": "ok"}


def test_cli_help_and_dispatch(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exit_info:
        cli_main(["--help"])
    assert exit_info.value.code == 0
    out = capsys.readouterr().out
    for command in ("local", "real", "doctor", "v2", "live"):
        assert command in out
    assert cli_main(["doctor", "--be-url", "http://127.0.0.1:9", "--json"]) == 1  # sub-commands parse their own options


def test_the_windows_launcher_lists_the_simple_commands() -> None:
    bat = (Path(__file__).parent.parent / "voice.bat").read_text(encoding="utf-8")
    for command in ("local", "real", "doctor", "v2", "live", "test", "avvia.py"):
        assert command in bat


def test_orb_has_no_halo_or_hint_text_has_the_golden_ring_and_the_popup_closes_by_voice_only() -> None:
    js = (SITE / "app.js").read_text(encoding="utf-8")
    css = (SITE / "site.css").read_text(encoding="utf-8")
    html = (SITE / "index.html").read_text(encoding="utf-8")
    assert "createRadialGradient(CX, CY, R * 0.4" not in js and "anello morbido" not in js  # no translucent red circle
    assert "function drawRing" in js and "#f6dd8f" in js and "preparingSince" in js  # golden ring, driven by the bot's state
    assert ".state-line { position: absolute" in css  # the state text is only for screen readers
    assert "TOAST_MS = 4000" in js and 'case "reservation_confirmed"' in js
    assert 'id="toast"' in html and "<button" not in html.split('id="toast"')[1].split("</aside>")[0]  # no way to click it away
    assert ".dock #orb" in css  # the orb sits where the voice button was


def test_the_test_page_has_the_same_golden_ring_and_popup() -> None:
    page = (SITE.parent / "voice_test.html").read_text(encoding="utf-8")
    assert "function drawRing" in page and "createRadialGradient(CX, CY, R * 0.4" not in page and "anello morbido" not in page
    assert "TOAST_MS = 4000" in page and "reservation_confirmed" in page and 'id="toast"' in page
    assert ".state { position: absolute" in page  # no hint text under the orb
