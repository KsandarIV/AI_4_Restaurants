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
        for element in ('id="menu-list"', 'id="res-list"', 'id="lookup-code"', 'id="orb"', 'id="chat-log"'):
            assert element in page.text
        assert "/site-assets/app.js" in page.text and "/site-assets/site.css" in page.text
        for asset in ("app.js", "site.css"):
            assert (await client.get(f"/site-assets/{asset}")).status_code == 200
        assert (await client.get("/prova-vocale")).status_code == 200  # the diagnostic page is still there


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


def test_the_site_talks_to_this_server_only_and_handles_every_event() -> None:
    js = (SITE / "app.js").read_text(encoding="utf-8")
    for needle in ("/site/menu", "/site/info", "/site/reservation/", "/site/config", "/ws/voice", "localStorage",
                   "customer_id", "setTimeout(connect", "Math.min(500 * 2 ** retry"):
        assert needle in js
    for event in ("ready", "loading", "heard", "transcript", "thinking", "reply", "barge_in",
                  "registered", "reservation", "error"):
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
