# syntax=docker/dockerfile:1
#
# Voice bot (live server). Multi-stage: wheels are built in a throwaway stage, the runtime image
# only gets the installed packages (no compiler, no pip cache), runs as a non-root user and has a
# healthcheck. Models are NOT baked in: mount the Piper voice and (optionally) a Hugging Face cache.
#
#   docker build -t voicebot voice
#   docker run --rm -p 8003:8003 --env-file .env \
#       -v "$PWD/voice/models:/app/models:ro" -v voicebot-hf:/home/voice/.cache voicebot
#
# BACKEND_BASE_URL must be the BE machine's LAN address (not localhost). The container has no audio
# device: use the browser page or `python -m voicebot.live_client` from a PC with a microphone.

ARG PYTHON_VERSION=3.12

# ---------- stage 1: build wheels ----------
FROM python:${PYTHON_VERSION}-slim AS builder
ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /build
COPY pyproject.toml ./
COPY src ./src
RUN pip wheel --wheel-dir /wheels ".[local-models]"

# ---------- stage 2: runtime ----------
FROM python:${PYTHON_VERSION}-slim AS runtime
# libgomp1: OpenMP runtime needed by onnxruntime / ctranslate2 (faster-whisper)
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*
ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 \
    VOICE_HOST=0.0.0.0 VOICE_PORT=8003 \
    VOICE_SETUP_SKIP=1 \
    PIPER_MODEL_PATH=/app/models/it_IT-riccardo-x_low.onnx

COPY --from=builder /wheels /wheels
RUN pip install --no-index --find-links=/wheels "voicebot[local-models]" \
    && rm -rf /wheels

# Optional extra PII safety net (spaCy NER): docker build --build-arg WITH_NER=1 ...
ARG WITH_NER=0
RUN if [ "$WITH_NER" = "1" ]; then \
        pip install spacy && python -m spacy download it_core_news_md; \
    fi

RUN useradd --create-home --shell /usr/sbin/nologin voice
WORKDIR /app
RUN mkdir -p /app/models && chown -R voice:voice /app /home/voice
USER voice

EXPOSE 8003
HEALTHCHECK --interval=15s --timeout=4s --start-period=60s --retries=3 \
    CMD python -c "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:%s/health' % os.environ.get('VOICE_PORT', '8003'), timeout=3)"

# `python -m voicebot` handles SIGTERM with a graceful shutdown (uvicorn, 10 s).
CMD ["python", "-m", "voicebot"]
