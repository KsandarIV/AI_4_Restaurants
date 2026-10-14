"""Test d'integrazione Voice <-> BE usando lo STUB locale (no rete, no LLM).

Esercitano il VERO BackendClient + BackendOrchestrator contro tests/stub_be.py,
che imita il contratto del BE (routes.py): health, chat/stream SSE, availability,
CRUD prenotazioni per booking_code, menu, info + verifica PII-scrub.
"""

from __future__ import annotations

import pytest

from tests.stub_be import make_stub
from voicebot.backend import BackendClient
from voicebot.orchestrator import BackendOrchestrator


@pytest.fixture()
def stub() -> tuple[str, object]:
    server, base_url, state = make_stub()
    yield base_url, state
    server.shutdown()


@pytest.fixture()
async def client(stub: tuple[str, object]) -> BackendClient:
    base_url, _ = stub
    cli = BackendClient(base_url=str(base_url), timeout_s=10.0)
    yield cli
    await cli.aclose()


async def test_health_ok(client: BackendClient) -> None:
    assert await client.health() is True


async def test_reservation_roundtrip(client: BackendClient) -> None:
    created = await client.create_reservation("2026-10-20", "20:00", 4, "Mario Rossi")
    code = str(created["booking_code"])
    assert code.startswith("RES-STUB")

    fetched = await client.get_reservation(code)
    assert fetched["guests"] == 4

    modified = await client.modify_reservation(code, new_time="21:00", new_party_size=2)
    assert modified["time"] == "21:00" and modified["guests"] == 2

    cancelled = await client.cancel_reservation(code)
    assert cancelled["success"] is True


async def test_stream_chat_tokens(client: BackendClient) -> None:
    tokens = [t async for t in client.stream_chat([{"role": "user", "content": "ciao"}])]
    assert len(tokens) > 1
    assert "".join(tokens).startswith("[Stub BE]")


async def test_orchestrator_menu_shortcut(stub: tuple[str, object]) -> None:
    base_url, _ = stub
    orch = BackendOrchestrator(
        backend=BackendClient(base_url=str(base_url), timeout_s=10.0), system_prompt="sys"
    )
    out = "".join([t async for t in orch.stream_reply("mostrami il menu")])
    assert "Bruschetta" in out


async def test_pii_scrubbed_before_send(stub: tuple[str, object]) -> None:
    base_url, state = stub
    orch = BackendOrchestrator(
        backend=BackendClient(base_url=str(base_url), timeout_s=10.0), system_prompt="sys"
    )
    # "menu" eviterebbe lo stream; usiamo testo neutro che va allo stream_chat.
    text = "vorrei info sul ristorante, scrivimi a mario.rossi@mail.it"
    _ = "".join([t async for t in orch.stream_reply(text)])
    payload = state.last_chat_payload  # type: ignore[union-attr]
    sent = " ".join(m["content"] for m in payload["messages"])
    assert "mario.rossi@mail.it" not in sent and "[EMAIL]" in sent
    assert payload["client_type"] == "voice" and payload["session_id"].startswith("voice_")


async def test_unknown_booking_returns_backend_error(client: BackendClient) -> None:
    from voicebot.backend import BackendError

    with pytest.raises(BackendError):
        await client.get_reservation("RES-INESISTENTE")
