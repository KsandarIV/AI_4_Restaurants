"""Tech page + documentazione: la pagina /tech esiste e cita i punti chiave."""

from __future__ import annotations

from pathlib import Path


def test_tech_page_content() -> None:
    base = Path(__file__).parent.parent / "src" / "voicebot" / "pipeline"
    html = (base / "tech.html").read_text(encoding="utf-8")
    for expected in ("barge-in", "gemma4:12b", "Piper", "faster-whisper",
                     "/api/chat/stream", "Stampa / Salva PDF", "window.print"):
        assert expected in html
    codice = (base / "tech_codice.html").read_text(encoding="utf-8")
    for expected in ("session.py", "vad.py", "stt.py", "orchestrator.py", "tts.py",
                     "audio_in_q", "barge-in", "Stampa / Salva PDF"):
        assert expected in codice
    idea = (base / "tech_idea.html").read_text(encoding="utf-8")
    for expected in ("orecchie", "traduttore", "cervello", "res-", "fermato"):
        assert expected in idea.lower()


async def test_diag_endpoint_shape() -> None:
    """GET /diag risponde sempre con la forma attesa (BE irraggiungibile = ok:false)."""
    from voicebot.config import Settings
    from voicebot.pipeline.server import build_app

    settings = Settings(
        stt_backend="fake", tts_backend="fake", backend_base_url="http://127.0.0.1:9",
    )
    import asyncio

    app = build_app(settings)
    scope = {"type": "http", "http_version": "1.1", "method": "GET", "path": "/diag",
             "headers": [], "query_string": b""}

    async def receive() -> dict[str, object]:
        return {"type": "http.request", "body": b"", "more_body": False}

    messages: list[dict[str, object]] = []

    async def send(message: dict[str, object]) -> None:
        messages.append(message)

    await app(scope, receive, send)
    assert messages[0].get("status") == 200
    import json as _json

    body = _json.loads(messages[1]["body"])
    assert body["voice"] == "ok"
    assert set(body["be"].keys()) == {"ok", "detail", "model"}
    assert body["be"]["ok"] is False
    assert body["stt_backend"] == "fake"


def test_documentazione_exists() -> None:
    doc = (Path(__file__).parent.parent / "documentazione.md").read_text(encoding="utf-8")
    for expected in ("Checklist test incrociati", "Punti di forza", "gemma4:12b",
                     "BACKEND_BASE_URL", "booking_code"):
        assert expected in doc


def test_voice_test_page() -> None:
    html = (Path(__file__).parent.parent / "src" / "voicebot" / "pipeline" / "voice_test.html").read_text(
        encoding="utf-8"
    )
    for expected in ("/ws/voice", "getUserMedia", "prova-vocale", "localhost",
                     "isSecureContext", "interromp", "Bella Napoli", "Come funziona",
                     "tts_sample_rate", "Schede complete", "/tech-codice", "/tech-idea",
                     "termina", "drawer", "drawer2", "canvas", "mouseleave",
                     "echoCancellation", "requestAnimationFrame",
                     "heard", "thinking", "ripples", "flashRed", "evlog", "pollDiag"):
        assert expected in html
    for absent in ("Versioni", ">v0.3<", ">v0.4<", "<footer"):
        assert absent not in html


def test_voice_pages_live_vs_test() -> None:
    """VOICE (live) e VOICE/TESTS (locale) hanno titoli diversi; solo la TEST ha il banner."""
    from voicebot.config import Settings
    from voicebot.pipeline.server import _voice_page, build_app  # noqa: F401

    base = Path(__file__).parent.parent / "src" / "voicebot" / "pipeline" / "voice_test.html"
    live = _voice_page(base, test=False, be_url="http://be-live:8000")
    tst = _voice_page(base, test=True, be_url="http://localhost:8000")
    assert "{{TITLE_SUFFIX}}" not in live and "{{TEST_BANNER}}" not in live
    assert "VOICE / TESTS" in tst and "http://localhost:8000" in tst
    assert "VOICE / TESTS" not in live
    assert "Bella Napoli · Voce</a>" in live
