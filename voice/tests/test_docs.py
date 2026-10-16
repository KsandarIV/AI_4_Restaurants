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


def _readme() -> str:
    return (VOICE / "README_VOICE.md").read_text(encoding="utf-8")


def test_every_setting_named_in_the_readme_exists() -> None:
    """The configuration table is written from the code: a renamed or removed setting must fail here."""
    import re

    from voicebot.config import Settings

    section = _readme().split("## Configuration", 1)[1].split("## Files", 1)[0]
    first_cells = [line.split("|")[1] for line in section.splitlines() if line.startswith("| `")]  # the variable names only
    named = {n for cell in first_cells for n in re.findall(r"`([A-Z][A-Z0-9_]{3,})`", cell)}
    fields = {name.upper() for name in Settings.model_fields}
    missing = {n for n in named if n not in fields and not n.startswith("VAD_")}  # "VAD_*" stands for a family
    assert len(named) >= 20 and not missing, missing


def test_every_event_in_the_readme_is_emitted_by_the_code() -> None:
    import re

    src = "".join((VOICE / "src" / "voicebot" / p).read_text(encoding="utf-8")
                  for p in ("pipeline/session.py", "orchestrator.py", "pipeline/server.py"))
    table = _readme().split("## WebSocket protocol", 1)[1].split("## BE contract", 1)[0]
    events = set(re.findall(r"`([a-z_]+)`", table)) & {
        "loading", "ready", "heard", "transcript", "thinking", "reply", "barge_in", "registered", "reservation",
        "reservation_confirmed", "call_ended", "error"}
    assert len(events) == 12
    for event in events:
        assert f'"{event}"' in src, event


def test_files_and_pages_named_in_the_readme_exist() -> None:
    import re

    readme = _readme()
    tree = readme.split("## Files", 1)[1].split("## The complete site", 1)[0]
    base = VOICE / "src" / "voicebot"
    for name in re.findall(r"\b([a-z_]+\.py)\b", tree):
        assert any(base.rglob(name)) or (VOICE / name).exists(), name
    for name in ("voice.bat", "test.bat", "Dockerfile", ".dockerignore", "pyproject.toml"):
        assert (VOICE / name).is_file(), name
    pages = readme.split("## Pages served", 1)[1].split("## The conversation", 1)[0]
    from voicebot.config import Settings
    from voicebot.pipeline.server import create_app

    routes = {getattr(r, "path", "") for r in create_app(Settings()).routes}
    for page in ("/health", "/ready", "/diag", "/test-voice", "/ws/voice", "/site/config", "/site/menu", "/site/info",
                 "/site/reservation/{code}", "/site/chat/session", "/site/chat/message", "/tech", "/tech-codice", "/tech-idea"):
        assert page in pages and page in routes, page
