import logging
import threading
from contextlib import asynccontextmanager
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.config import settings
from backend.database.crud import init_db
from backend.llm_provider import warm_up
from backend.api.routes import router as api_router
from backend.api.staff import router as staff_router

# Configure logging
logging.basicConfig(
    level=logging.INFO if settings.DEBUG else logging.WARNING,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("backend")
logger.setLevel(logging.INFO)  # startup messages of the backend are always shown, even with DEBUG off

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle hook for startup and shutdown."""
    logger.info("Inizializzazione database SQLite e seed iniziale...")
    init_db()
    if not settings.STAFF_API_KEY:
        logger.warning("Area staff DISABILITATA. Per attivarla: python -m backend.maintenance staff-key e copia la riga nel .env")
    if not settings.REQUIRE_CUSTOMER_REGISTRATION:
        logger.warning("Registrazione clienti SPENTA: nessun controllo sul proprietario delle prenotazioni.")
    if settings.LLM_PROVIDER != "mock":
        threading.Thread(target=warm_up, daemon=True, name="warm-up-modello").start()  # does not delay the server
    logger.info(f"Server pronto su http://{settings.HOST}:{settings.PORT}")
    logger.info(f"Documentazione Swagger UI attiva su http://localhost:{settings.PORT}/docs")
    yield
    logger.info("Arresto del server Backend...")

app = FastAPI(
    title=f"Backend AI Prenotazione Ristorante - {settings.RESTAURANT_NAME}",
    description=(
        "Backend Python con LangGraph, LangChain e SQLite per la gestione intelligente "
        "delle prenotazioni, modifiche, cancellazioni, consultazione menu e info ristorante. "
        "Esposto su rete locale per client CHAT (bot testuale) e VOICE (bot vocale)."
    ),
    version="1.0.0",
    lifespan=lifespan
)

# Enable CORS for LAN access across different devices
# No cookies are used, so credentials stay off ("*" with credentials is not valid CORS anyway).
# Restrict the origins with CORS_ORIGINS=http://host1,http://host2 when the web page is on a known address.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API router at /api and root aliases for VoiceBot compatibility
app.include_router(api_router, prefix="/api")
app.include_router(api_router, prefix="", include_in_schema=False)  # same routes without /api, hidden from Swagger
app.include_router(staff_router, prefix="/api")  # restaurant owner area, protected by STAFF_API_KEY

@app.get("/health", summary="Root healthcheck alias")
def root_health():
    from backend.api.routes import health_endpoint
    return health_endpoint()

@app.get("/", summary="Root endpoint")
def root():
    return {
        "status": "online",
        "service": "AI Restaurant Reservation Backend",
        "restaurant": settings.RESTAURANT_NAME,
        "docs_url": "/docs",
        "endpoints": {
            "chat": "/api/chat",
            "menu": "/api/menu",
            "info": "/api/info",
            "reservations": "/api/reservations",
            "health": "/api/health"
        }
    }

if __name__ == "__main__":
    uvicorn.run(
        "backend.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG
    )
