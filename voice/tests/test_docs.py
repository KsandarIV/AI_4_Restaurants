"""Tech page + documentazione: la pagina /tech esiste e cita i punti chiave."""

from __future__ import annotations

from pathlib import Path


def test_tech_page_content() -> None:
    html = (Path(__file__).parent.parent / "src" / "voicebot" / "pipeline" / "tech.html").read_text(
        encoding="utf-8"
    )
    for expected in ("barge-in", "gemma4:12b", "Piper", "faster-whisper",
                     "/api/chat/stream", "Stampa / Salva PDF", "window.print"):
        assert expected in html


def test_documentazione_exists() -> None:
    doc = (Path(__file__).parent.parent / "documentazione.md").read_text(encoding="utf-8")
    for expected in ("Checklist test incrociati", "Punti di forza", "gemma4:12b",
                     "BACKEND_BASE_URL", "booking_code"):
        assert expected in doc


def test_voice_test_page() -> None:
    html = (Path(__file__).parent.parent / "src" / "voicebot" / "pipeline" / "voice_test.html").read_text(
        encoding="utf-8"
    )
    for expected in ("/ws/voice", "getUserMedia", "AudioContext", "prova-vocale", "localhost",
                     "isSecureContext", "interrompere"):
        assert expected in html
