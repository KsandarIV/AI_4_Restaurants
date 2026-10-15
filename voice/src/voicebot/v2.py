"""Voice v2 - on-demand, exactly like the chat bot, with a microphone and a speaker.

No WebSocket, no streaming, no barge-in: one turn = one question. This sidesteps every
real-time problem of the live mode (echo, half-duplex audio, VAD tuning, browser mic
restrictions) because everything runs in the same process, on any PC:

    microphone -> STT (text) -> chat conversation -> complete reply -> TTS -> speaker

The "chat conversation" is the very same engine the live mode uses (registration phase,
anonymisation, ``POST /api/chat``). With ``CHAT_SERVICE_URL`` set it is the deployed CHAT
service instead, running invisibly underneath.

    python -m voicebot.v2                 # ENTER, speak, wait for the answer
    python -m voicebot.v2 --text          # type instead of speaking (no microphone needed)
    python -m voicebot.v2 --no-speaker    # print the replies, do not play them
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import tempfile
import time
from collections.abc import AsyncIterator

from .audio import pcm_duration_s, pcm_to_wav, rms_int16
from .backend import BackendClient
from .chat_service import ChatServiceOrchestrator
from .config import Settings, get_settings
from .interfaces import AbstractLLMOrchestrator, AbstractSTT, AbstractTTS
from .logging_json import get_logger, setup_logging
from .messages import say
from .orchestrator import BackendOrchestrator
from .stt import build_stt
from .tts import build_tts

log = get_logger("v2")


def record_utterance(
    sample_rate: int = 16000,
    max_s: float = 15.0,
    silence_ms: int = 900,
    threshold: float = 500.0,
    block_ms: int = 100,
    wait_s: float = 8.0,
) -> bytes:
    """Record from the microphone until ``silence_ms`` of silence follow some speech.

    Gives up (returns what it has) after ``wait_s`` without any speech. Needs ``sounddevice``.
    """
    try:
        import sounddevice as sd
    except ImportError as exc:
        raise RuntimeError("sounddevice is not installed: run python setup/setup_env.py") from exc

    block = int(sample_rate * block_ms / 1000)
    silence_blocks = max(1, int(silence_ms / block_ms))
    max_blocks = int(max_s * 1000 / block_ms)
    wait_blocks = int(wait_s * 1000 / block_ms)
    chunks: list[bytes] = []
    quiet, started = 0, False
    with sd.InputStream(samplerate=sample_rate, channels=1, dtype="int16", blocksize=block) as stream:
        for index in range(max_blocks):
            data, _ = stream.read(block)
            pcm = bytes(data)
            chunks.append(pcm)
            if rms_int16(pcm) >= threshold:
                started, quiet = True, 0
            elif started:
                quiet += 1
                if quiet >= silence_blocks:
                    break
            elif index >= wait_blocks:
                break
    return b"".join(chunks)


def play_audio(pcm: bytes, sample_rate: int) -> None:
    """Play PCM16 mono and wait until it has finished (winsound on Windows)."""
    if sys.platform == "win32":
        import winsound

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp.write(pcm_to_wav(pcm, sample_rate))
        winsound.PlaySound(tmp.name, winsound.SND_FILENAME)  # synchronous
        return
    try:
        import numpy as np
        import sounddevice as sd
    except ImportError as exc:
        raise RuntimeError("playback unavailable: install sounddevice") from exc
    sd.play(np.frombuffer(pcm, dtype=np.int16), samplerate=sample_rate, blocking=True)
    time.sleep(0.1)


async def synthesize(tts: AbstractTTS, text: str) -> bytes:
    """Complete audio for ``text`` (sentence by sentence, concatenated)."""

    async def _one() -> AsyncIterator[str]:
        yield text

    return b"".join([chunk async for chunk in tts.synthesize_stream(_one())])


async def hear_and_reply(
    pcm: bytes,
    sample_rate: int,
    stt: AbstractSTT,
    conversation: AbstractLLMOrchestrator,
    language: str = "it",
) -> tuple[str, str]:
    """STT + conversation, no audio out: ``(what_was_heard, reply_text)``."""
    heard = (await stt.transcribe(pcm, sample_rate)).strip()
    if not heard:
        return "", say(language, "didnt_hear")
    return heard, await conversation.reply(heard)


async def answer_once(
    pcm: bytes,
    sample_rate: int,
    stt: AbstractSTT,
    conversation: AbstractLLMOrchestrator,
    tts: AbstractTTS,
    language: str = "it",
) -> tuple[str, str, bytes]:
    """One complete on-demand turn: ``(what_was_heard, reply_text, reply_audio)``."""
    heard, reply = await hear_and_reply(pcm, sample_rate, stt, conversation, language)
    return heard, reply, await synthesize(tts, reply)


def build_conversation(settings: Settings) -> AbstractLLMOrchestrator:
    """The chat conversation: via the CHAT service when configured, else straight to the BE."""
    if settings.chat_service_url:
        return ChatServiceOrchestrator(
            settings.chat_service_url, language=settings.voice_language,
            timeout_s=settings.backend_chat_timeout_s,
        )
    backend = BackendClient(
        base_url=settings.backend_base_url,
        timeout_s=settings.backend_timeout_s,
        api_key=settings.backend_api_key,
        chat_timeout_s=settings.backend_chat_timeout_s,
    )
    return BackendOrchestrator(
        backend=backend,
        system_prompt=settings.llm_system_prompt,
        max_history=settings.llm_max_history,
        language=settings.voice_language,
        require_registration=settings.require_registration,
    )


async def amain(args: argparse.Namespace) -> int:
    """Interactive loop. ENTER to speak, ``q`` to quit."""
    settings = get_settings()
    setup_logging("WARNING" if not args.verbose else settings.log_level)
    stt = build_stt(
        settings.stt_backend, model=settings.stt_model, device=settings.stt_device,
        compute_type=settings.stt_compute_type, language=settings.effective_stt_language,
        initial_prompt=settings.effective_stt_prompt,
    )
    tts = build_tts(
        settings.tts_backend, model_path=settings.piper_model_path,
        config_path=settings.piper_config_path, sample_rate=settings.tts_sample_rate,
    )
    conversation = build_conversation(settings)
    via = f"chat service {settings.chat_service_url}" if settings.chat_service_url else settings.backend_base_url
    print(f"[v2] talking to: {via} | language: {settings.voice_language}")
    print("[v2] loading models..." if not args.text else "[v2] text mode")

    async def say_aloud(text: str) -> None:
        print(f"[v2] bot: {text}")
        if args.no_speaker:
            return
        audio = await synthesize(tts, text)
        if audio:
            await asyncio.to_thread(play_audio, audio, tts.sample_rate)

    try:
        if not args.text:
            await stt.warmup()
        await tts.warmup()
        await say_aloud(await conversation.opening())
        prompt = "[v2] type your message (q to quit) > " if args.text else "[v2] ENTER to speak (q to quit) > "
        while True:
            command = await asyncio.to_thread(input, prompt)
            if command.strip().lower() in ("q", "quit", "exit"):
                break
            if args.text:
                heard, reply = command.strip(), ""
                if not heard:
                    continue
                reply = await conversation.reply(heard)
                await say_aloud(reply)
                continue
            print("[v2] listening...")
            pcm = await asyncio.to_thread(
                record_utterance, settings.sample_rate, 15.0, 900, settings.vad_energy_threshold
            )
            print(f"[v2] captured {pcm_duration_s(pcm, settings.sample_rate):.1f}s, thinking...")
            heard, reply = await hear_and_reply(
                pcm, settings.sample_rate, stt, conversation, settings.voice_language
            )
            print(f"[v2] you: {heard or '(nothing heard)'}")
            await say_aloud(reply)
    except (KeyboardInterrupt, EOFError):
        pass
    except RuntimeError as exc:
        print(f"[v2] {exc}")
        return 1
    finally:
        await conversation.aclose()
        await stt.aclose()
        await tts.aclose()
    return 0


def main(argv: list[str] | None = None) -> int:
    """Entry point for ``python -m voicebot.v2``."""
    parser = argparse.ArgumentParser(prog="voicebot.v2", description="On-demand voice chat")
    parser.add_argument("--text", action="store_true", help="type instead of speaking")
    parser.add_argument("--no-speaker", action="store_true", help="do not play the replies")
    parser.add_argument("--verbose", action="store_true", help="show JSON logs")
    return asyncio.run(amain(parser.parse_args(argv)))


if __name__ == "__main__":
    raise SystemExit(main())
