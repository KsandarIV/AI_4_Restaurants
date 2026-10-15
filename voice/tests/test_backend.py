"""BackendClient: retries, error mapping, SSE parsing (httpx MockTransport, no network)."""

from __future__ import annotations

import json

import httpx
import pytest

from voicebot.backend import BackendClient, BackendError


def _client(handler: httpx.MockTransport, **kwargs: object) -> BackendClient:
    return BackendClient(base_url="http://be.test", transport=handler, max_retries=3, **kwargs)  # type: ignore[arg-type]


@pytest.fixture(autouse=True)
def _fast_backoff(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("voicebot.backend._backoff", lambda attempt: 0.0)


async def test_get_retries_on_5xx_then_succeeds() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(503) if calls["n"] < 3 else httpx.Response(200, json={"status": "online"})

    client = _client(httpx.MockTransport(handler))
    assert (await client.health_info())["status"] == "online"
    assert calls["n"] == 3


async def test_health_falls_back_to_root_path() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404) if request.url.path == "/api/health" else httpx.Response(200, json={"status": "online"})

    assert await _client(httpx.MockTransport(handler)).health() is True


async def test_post_chat_is_not_retried_after_a_read_timeout() -> None:
    """A retry could make the LLM book the same table twice."""
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        raise httpx.ReadTimeout("slow", request=request)

    with pytest.raises(BackendError) as info:
        await _client(httpx.MockTransport(handler)).chat("ciao", "s", "c")
    assert info.value.kind == "timeout" and calls["n"] == 1


async def test_connection_refused_is_retried_then_reported() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        raise httpx.ConnectError("refused", request=request)

    with pytest.raises(BackendError) as info:
        await _client(httpx.MockTransport(handler)).chat("ciao", "s", "c")
    assert info.value.kind == "unreachable" and calls["n"] == 3


async def test_chat_sends_the_chat_contract_and_scrubs_pii() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(json.loads(request.content))
        return httpx.Response(200, json={"reply": "ok"})

    out = await _client(httpx.MockTransport(handler)).chat("scrivimi a a@b.it", "sess1", "cust1")
    assert out["reply"] == "ok"
    assert seen == {"message": "scrivimi a [EMAIL_1]", "session_id": "sess1",
                    "customer_id": "cust1", "client_type": "voice"}


async def test_register_customer_returns_the_anonymous_id() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert body == {"name": "Mario Rossi", "phone": "+393331234567", "consent": True}
        return httpx.Response(200, json={"customer_id": "cust_abc"})

    assert await _client(httpx.MockTransport(handler)).register_customer("Mario Rossi", "+393331234567") == "cust_abc"


async def test_register_customer_rejection_carries_the_status() -> None:
    client = _client(httpx.MockTransport(lambda r: httpx.Response(422, json={"detail": "bad"})))
    with pytest.raises(BackendError) as info:
        await client.register_customer("x", "+393331234567")
    assert info.value.status == 422


async def test_stream_parses_sse_and_sends_only_the_last_message() -> None:
    seen: dict[str, object] = {}
    sse = 'data: {"token": "Ciao "}\n\ndata: {"token": "mondo"}\n\ndata: [DONE]\n\n'

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(json.loads(request.content))
        return httpx.Response(200, text=sse, headers={"content-type": "text/event-stream"})

    tokens = [t async for t in _client(httpx.MockTransport(handler)).stream_chat(
        "ciao", "s", "c", system_prompt="be brief")]
    assert tokens == ["Ciao ", "mondo"]
    assert seen["session_id"] == "s" and seen["client_type"] == "voice"
    assert [m["role"] for m in seen["messages"]] == ["system", "user"]  # type: ignore[index]


async def test_stream_reconnects_once_before_the_first_token() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            raise httpx.ConnectError("blip", request=request)
        return httpx.Response(200, text='data: {"token": "ok"}\n\ndata: [DONE]\n\n')

    assert [t async for t in _client(httpx.MockTransport(handler)).stream_chat("x", "s", "c")] == ["ok"]
    assert calls["n"] == 2


async def test_stream_http_error_maps_to_backend_error() -> None:
    client = _client(httpx.MockTransport(lambda r: httpx.Response(503, text="llm down")))
    with pytest.raises(BackendError) as info:
        [t async for t in client.stream_chat("x", "s", "c")]
    assert info.value.status == 503
