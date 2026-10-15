"""The doctor must turn every broken setup into a readable report with a fix."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.helpers import stub_be
from voicebot import doctor
from voicebot.config import Settings
from voicebot.diagnostics import collect_diagnostics, local_checks


def _by_name(report: dict[str, object]) -> dict[str, dict[str, str]]:
    return {c["name"]: c for c in report["checks"]}  # type: ignore[attr-defined]


async def test_healthy_setup_has_no_failures() -> None:
    async with stub_be() as (url, _):
        report = await collect_diagnostics(Settings(backend_base_url=url))
        checks = _by_name(report)
        assert checks["backend"]["status"] == "ok" and checks["registration"]["status"] == "ok"
        assert report["be"]["ok"] is True  # type: ignore[index]
        assert report["overall"] in ("ok", "warn")  # warn: fake STT/TTS in the test settings


async def test_unreachable_be_explains_what_to_check() -> None:
    report = await collect_diagnostics(Settings(backend_base_url="http://127.0.0.1:9"))
    backend = _by_name(report)["backend"]
    assert backend["status"] == "fail" and report["overall"] == "fail"
    for clue in ("running", "BACKEND_BASE_URL", "firewall"):
        assert clue in backend["hint"]


async def test_degraded_be_points_at_ollama() -> None:
    async with stub_be() as (url, state):
        state_ok = state  # the stub always reports online: swap the handler's answer
        import tests.stub_be as stub

        original = stub.Handler.do_GET

        def degraded(self: stub.Handler) -> None:
            if self.path.startswith(("/api/health", "/health")):
                self._json(200, {"status": "degraded", "llm_reachable": False, "llm_model_available": False})
            else:
                original(self)

        stub.Handler.do_GET = degraded  # type: ignore[method-assign]
        try:
            report = await collect_diagnostics(Settings(backend_base_url=url))
        finally:
            stub.Handler.do_GET = original  # type: ignore[method-assign]
        backend = _by_name(report)["backend"]
        assert state_ok is state and backend["status"] == "warn" and "ollama" in backend["hint"].lower()


async def test_old_be_without_registration_is_detected() -> None:
    import tests.stub_be as stub

    async with stub_be() as (url, _):
        original = stub.Handler.do_POST

        def no_customers(self: stub.Handler) -> None:
            if self.path.startswith("/api/customers"):
                self._json(404, {"detail": "Not Found"})
            else:
                original(self)

        stub.Handler.do_POST = no_customers  # type: ignore[method-assign]
        try:
            report = await collect_diagnostics(Settings(backend_base_url=url))
        finally:
            stub.Handler.do_POST = original  # type: ignore[method-assign]
        registration = _by_name(report)["registration"]
        assert registration["status"] == "fail" and "customers" in registration["hint"]


def test_missing_piper_model_is_a_failure_with_the_fix(tmp_path: Path) -> None:
    checks = {c["name"]: c for c in local_checks(Settings(tts_backend="piper", piper_model_path=str(tmp_path / "x.onnx")))}
    assert checks["tts"]["status"] == "fail" and "setup_env" in checks["tts"]["hint"]


def test_fake_backends_are_flagged_as_not_real() -> None:
    checks = {c["name"]: c for c in local_checks(Settings())}
    assert checks["stt"]["status"] == "warn" and checks["tts"]["status"] == "warn"


def test_cli_exit_codes_and_json(capsys: pytest.CaptureFixture[str]) -> None:
    assert doctor.main(["--be-url", "http://127.0.0.1:9", "--json"]) == 1  # BE down -> fail
    report = json.loads(capsys.readouterr().out)
    assert report["overall"] == "fail" and {"name", "status", "detail", "hint"} <= set(report["checks"][0])


async def test_cli_text_report_on_a_working_setup(capsys: pytest.CaptureFixture[str]) -> None:
    async with stub_be() as (url, _):
        report = await doctor.run(Settings(backend_base_url=url), load_models=True)
        names = _by_name(report)
        assert names["model_load"]["status"] == "ok"  # fake models load instantly
        assert {"voice_port", "audio_devices", "backend", "registration"} <= set(names)
