"""Shim storico del membro VOICE (Traccia 3).

Il modulo e' stato promosso a package deploy-ready in ``src/voicebot``.
Questo file resta per retro-compatibilita': riesporta i simboli principali
e permette ``python voice/voice.py`` come smoke check (health + pipeline fake).
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from voicebot.pipeline.session import VoiceSession  # noqa: E402,F401
from voicebot.pipeline.server import build_app  # noqa: E402,F401


async def _smoke() -> None:
    from voicebot.orchestrator import BackendOrchestrator
    from voicebot.stt import FakeSTT
    from voicebot.tts import FakeTTS
    from voicebot.vad import EnergyVAD

    class _FakeBackend:
        async def stream_chat(self, messages, timeout_s=30.0):  # type: ignore[no-untyped-def]
            yield "Benvenuto al ristorante. "

    orch = BackendOrchestrator(backend=_FakeBackend(), system_prompt="sys")  # type: ignore[arg-type]
    session = VoiceSession(vad=EnergyVAD(), stt=FakeSTT(), llm=orch, tts=FakeTTS())
    run = asyncio.create_task(session.run())
    await session.text_q.put("vorrei prenotare")
    out = await asyncio.wait_for(session.audio_out_q.get(), timeout=10.0)
    print(f"smoke ok: received {len(out)} audio bytes")
    await session.close()
    run.cancel()


if __name__ == "__main__":
    asyncio.run(_smoke())
