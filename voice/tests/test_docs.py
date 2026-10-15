"""Pages and docs: they exist, are in English and mention what the code really does."""

from __future__ import annotations

from pathlib import Path

PAGES = Path(__file__).parent.parent / "src" / "voicebot" / "pipeline"
VOICE = Path(__file__).parent.parent


def test_tech_pages_content() -> None:
    tech = (PAGES / "tech.html").read_text(encoding="utf-8")
    for expected in ("barge-in", "gemma4:12b", "Piper", "faster-whisper", "/api/chat/stream",
                     "POST /api/customers", "Print / Save PDF", "window.print", "voicebot.doctor"):
        assert expected in tech
    code = (PAGES / "tech_codice.html").read_text(encoding="utf-8")
    for expected in ("session.py", "vad.py", "stt.py", "orchestrator.py", "tts.py", "anonymizer.py",
                     "audio_in_q", "barge-in", "Print / Save PDF"):
        assert expected in code
    idea = (PAGES / "tech_idea.html").read_text(encoding="utf-8").lower()
    for expected in ("ears", "translator", "brain", "res", "stopped"):
        assert expected in idea


def test_pages_do_not_claim_removed_features() -> None:
    """The old shortcuts and the old PII tags are gone: the docs must not advertise them."""
    for name in ("tech.html", "tech_codice.html", "tech_idea.html"):
        text = (PAGES / name).read_text(encoding="utf-8")
        assert "tool shortcut" not in text.lower() and "[EMAIL]" not in text


def test_voice_test_page_keeps_the_orb_and_both_drawers() -> None:
    """The original test page (liquid orb, TECNICA + STATO drawers) is what v1 is tested with: keep it."""
    html = (PAGES / "voice_test.html").read_text(encoding="utf-8")
    for expected in ("orb liquido", "ripples", "flashRed", "flash", "requestAnimationFrame", "createRadialGradient",
                     "ⓘ TECNICA", "◉ STATO", "drawer2", "mouseleave", "evlog", "pollDiag", "/tech-codice", "/tech-idea"):
        assert expected in html, expected


def test_voice_test_page_has_what_the_flow_needs() -> None:
    html = (PAGES / "voice_test.html").read_text(encoding="utf-8")
    for expected in ("/ws/voice", "getUserMedia", "isSecureContext", "tts_sample_rate", "echoCancellation",
                     "transcript", "reply", "barge_in", "thinking", "heard", "loading", "registered", "reservation",
                     "setTimeout(connect", "Math.min(500 * 2 ** retry", "stopPlayback", 'id="checks"'):
        assert expected in html, expected


def test_voice_pages_live_vs_test() -> None:
    """The live and the TEST page differ in title; only the TEST one has the BE banner."""
    from voicebot.pipeline.server import _page

    live = _page("voice_test.html", test=False, be_url="http://be-live:8000")
    test = _page("voice_test.html", test=True, be_url="http://localhost:8000")
    assert "{{TITLE_SUFFIX}}" not in live and "{{TEST_BANNER}}" not in live
    assert "VOICE / TESTS" in test and "http://localhost:8000" in test
    assert "VOICE / TESTS" not in live
    assert "Bella Napoli · Voce</a>" in live


def test_documentation_matches_the_code() -> None:
    doc = (VOICE / "documentazione.md").read_text(encoding="utf-8")
    for expected in ("voicebot.doctor", "voicebot.v2", "voicebot.live_client", "/api/customers",
                     "BACKEND_BASE_URL", "Cross-test checklist", "barge-in", "CHAT_SERVICE_URL",
                     "VOICE_LANGUAGE", "REQUIRE_REGISTRATION"):
        assert expected in doc
    readme = (VOICE / "README_VOICE.md").read_text(encoding="utf-8")
    for expected in ("orchestrator.py", "contacts.py", "anonymizer.py", "diagnostics.py", "Dockerfile"):
        assert expected in readme


def test_prompt_defines_role_and_actions() -> None:
    from voicebot.prompts import VOICE_AGENT_PROMPT, build_system_prompt

    for section in ("# RUOLO", "# LINGUA E STILE", "# COSA PUOI FARE", "# CONFERMA", "# DATI PERSONALI", "# ALLERGIE"):
        assert section in VOICE_AGENT_PROMPT
    assert build_system_prompt("") == VOICE_AGENT_PROMPT
    assert "Rispondi in italiano di default" in VOICE_AGENT_PROMPT and "ambiente specifico" in VOICE_AGENT_PROMPT
    assert build_system_prompt("  custom  ") == "custom"
