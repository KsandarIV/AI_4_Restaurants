# BE del ristorante: FastAPI + LangGraph + SQLite (solo macchina BE).
# Ollama NON è in questa immagine: gira come servizio `ollama` (vedi docker-compose.yml)
# o su host, puntato da OLLAMA_BASE_URL.
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Dipendenze BE (base = comuni, be = LangGraph/Ollama/SQLAlchemy)
COPY setup/requirements/base.txt setup/requirements/be.txt ./setup/requirements/
RUN pip install --no-cache-dir -r setup/requirements/base.txt -r setup/requirements/be.txt

COPY backend/ ./backend/
COPY .env.example ./.env.example

# I dati (restaurant.db, conversations.db, backups) vivono nel volume /app/data:
# mai dentro l'immagine, altrimenti si perdono a ogni rebuild.
VOLUME ["/app/data"]
ENV DATABASE_URL=sqlite:////app/data/restaurant.db \
    CHECKPOINTS_DB_PATH=/app/data/conversations.db \
    HOST=0.0.0.0 \
    PORT=8000

EXPOSE 8000

# Il DB viene creato/aggiornato all'avvio da init_db() (lifespan in backend/main.py).
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
