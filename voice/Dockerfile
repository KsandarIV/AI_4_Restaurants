# ---------- builder ----------
FROM python:3.11-slim AS builder
ENV PIP_NO_CACHE_DIR=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends build-essential && rm -rf /var/lib/apt/lists/*
COPY pyproject.toml ./
RUN pip install --upgrade pip && pip wheel --wheel-dir /wheels -e . 2>/dev/null || pip download --dest /wheels faster-whisper webrtcvad piper-tts onnxruntime fastapi "uvicorn[standard]" websockets httpx pydantic pydantic-settings numpy || true
COPY src ./src

# ---------- runtime (modelli locali) ----------
FROM python:3.11-slim AS runtime
ENV PIP_NO_CACHE_DIR=1 PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/app/src
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg libsndfile1 espeak-ng && rm -rf /var/lib/apt/lists/* \
    && useradd -m -u 10001 voicebot
COPY pyproject.toml ./
RUN pip install --upgrade pip && pip install fastapi "uvicorn[standard]" websockets httpx pydantic pydantic-settings numpy faster-whisper webrtcvad piper-tts onnxruntime
COPY src ./src
# I pesi dei modelli locali vanno montati come volume (mai baked con dati personali)
# Es: -v ./models:/app/models
COPY .env.example ./.env.example
USER voicebot
EXPOSE 8003
HEALTHCHECK --interval=30s --timeout=5s --retries=3 CMD python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8003/health',timeout=4).read()" || exit 1
CMD ["uvicorn", "voicebot.pipeline.server:app", "--host", "0.0.0.0", "--port", "8003"]
