"""Voice v2 on-demand: tale e quale al chatbot, ma con voce in/out.

Niente streaming, niente WebSocket, niente barge-in: un turno = una domanda.
  microfono -> STT (testo) -> POST /api/chat al BE (come chat/app.py)
  -> risposta completa -> TTS (audio) -> altoparlante.

Uso:  .venv\\Scripts\\python -m voicebot.v2   (INVIO per parlare, 'q' per uscire)
"""

from __future__ import annotations

import asyncio
import io
import uuid
import wave
from typing import AsyncIterator

from .audio import rms_int16
from .backend import BackendClient
from .config import get_settings
from .interfaces import AbstractSTT, AbstractTTS
from .logging_json import get_logger, setup_logging
from .stt import build_stt
from .tts import build_tts

log = get_logger("v2")


def pcm_to_wav_bytes(pcm: bytes, sample_rate: int) -> bytes:
    """Incapsula PCM16 mono in un WAV (per playback/debug)."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm)
    return buf.getvalue()


def record_utterance(
    sample_rate: int = 16000,
    max_s: float = 15.0,
    silence_ms: int = 900,
    threshold: float = 500.0,
    block_ms: int = 100,
) -> bytes:
    """Registra dal microfono fino a `silence_ms` di silenzio (push-to-talk senza pulsante).

    Richiede `sounddevice` (nel venv condiviso). Ferma con Ctrl+C.
    """
    try:
        import sounddevice as sd  # type: ignore[import-not-found]
    except ImportError as exc:
        raise RuntimeError("sounddevice non installato: rilancia setup_env.py") from exc
    import numpy as np

    block = int(sample_rate * block_ms / 1000)
    silence_blocks = max(1, int(silence_ms / block_ms))
    max_blocks = int(max_s * 1000 / block_ms)
    chunks: list[bytes] = []
    quiet = 0
    started = False
    log.info("parla ora... (stop dopo %d ms di silenzio)", silence_ms)
    with sd.InputStream(samplerate=sample_rate, channels=1, dtype="int16", blocksize=block) as stream:
        for _ in range(max_blocks):
            data, _ = stream.read(block)
            pcm = bytes(data)
            chunks.append(pcm)
            if rms_int16(pcm) >= threshold:
                started, quiet = True, 0
            elif started:
                quiet += 1
                if quiet >= silence_blocks:
                    break
    return b"".join(chunks)


def play_audio(pcm: bytes, sample_rate: int) -> None:
    """Riproduce PCM16 mono: winsound su Windows, sounddevice altrove."""
    import platform

    if platform.system() == "Windows":
        import tempfile
        import winsound

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp.write(pcm_to_wav_bytes(pcm, sample_rate))
            path = tmp.name
        winsound.PlaySound(path, winsound.SND_FILENAME | winsound.SND_ASYNC)
        import time

        time.sleep(len(pcm) / 2 / sample_rate + 0.3)
    else:
        try:
            import sounddevice as sd  # type: ignore[import-not-found]
            import numpy as np
        except ImportError as exc:
            raise RuntimeError("playback non disponibile: installa sounddevice") from exc
        sd.play(np.frombuffer(pcm, dtype=np.int16), samplerate=sample_rate, blocking=True)


async def answer_once(
    pcm: bytes,
    sample_rate: int,
    stt: AbstractSTT,
    backend: BackendClient,
    tts: AbstractTTS,
    session_id: str,
    customer_id: str,
) -> tuple[str, str, bytes]:
    """Un turno on-demand: (testo_utente, risposta_BE, audio_risposta). Testabile senza mic."""

    async def _one(text: str) -> AsyncIterator[str]:
        yield text

    user_text = (await stt.transcribe(pcm, sample_rate)).strip()
    if not user_text:
        return "", "Non ho sentito bene, puoi ripetere?", b""
    reply = str((await backend.chat(user_text, session_id, customer_id))["reply"])
    audio = b"".join([chunk async for chunk in tts.synthesize_stream(_one(reply))])
    return user_text, reply, audio


async def amain() -> int:
    """Loop CLI: INVIO per parlare, q per uscire. Stessa sessione BE per tutta la run."""
    settings = get_settings()
    setup_logging(settings.log_level)
    stt = build_stt(
        settings.stt_backend, model=settings.stt_model, device=settings.stt_device,
        compute_type=settings.stt_compute_type, language=settings.stt_language,
    )
    tts = build_tts(
        settings.tts_backend, model_path=settings.piper_model_path,
        config_path=settings.piper_config_path, sample_rate=settings.tts_sample_rate,
    )
    backend = BackendClient(
        base_url=settings.backend_base_url, timeout_s=settings.backend_timeout_s,
        api_key=settings.backend_api_key,
    )
    session_id = f"voice_v2_{uuid.uuid4().hex[:8]}"
    customer_id = f"anon_{uuid.uuid4().hex[:8]}"
    print(f"[v2] BE: {settings.backend_base_url} | sessione: {session_id}")
    print("[v2] INVIO per parlare, q+INVIO per uscire.")
    try:
        while True:
            cmd = await asyncio.to_thread(input, "[v2] > ")
            if cmd.strip().lower() in ("q", "quit", "exit"):
                break
            try:
                pcm = await asyncio.to_thread(record_utterance, settings.sample_rate)
            except RuntimeError as exc:
                print(f"[v2] {exc}")
                break
            user_text, reply, audio = await answer_once(
                pcm, settings.sample_rate, stt, backend, tts, session_id, customer_id
            )
            print(f"[v2] tu: {user_text}")
            print(f"[v2] BE: {reply}")
            if audio:
                await asyncio.to_thread(play_audio, audio, tts.sample_rate)
    except (KeyboardInterrupt, EOFError):
        pass
    finally:
        await stt.aclose()
        await tts.aclose()
        await backend.aclose()
    return 0


def main() -> int:
    """Entrypoint sincrono per `python -m voicebot.v2`."""
    return asyncio.run(amain())


if __name__ == "__main__":
    raise SystemExit(main())
