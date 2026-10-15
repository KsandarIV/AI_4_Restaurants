import os
from pathlib import Path
from typing import Optional
from pydantic import BaseModel
from dotenv import load_dotenv

# Load .env if present
load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

class Settings(BaseModel):
    # Base directory
    BASE_DIR: Path = BASE_DIR

    # Server settings
    HOST: str = os.getenv("HOST", "0.0.0.0")
    PORT: int = int(os.getenv("PORT", "8000"))
    DEBUG: bool = os.getenv("DEBUG", "true").lower() in ("true", "1", "yes")

    # Database settings
    DB_PATH: Path = BASE_DIR / "backend" / "restaurant.db"
    CHECKPOINTS_DB_PATH: Path = BASE_DIR / "backend" / "conversations.db"
    DATABASE_URL: str = os.getenv("DATABASE_URL", f"sqlite:///{DB_PATH}")

    # LLM Settings (Local Environment)
    LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "ollama")  # "ollama" or "mock"
    OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "llama3.2")
    LLM_TEMPERATURE: float = float(os.getenv("LLM_TEMPERATURE", "0.1"))
    # "thinking" of reasoning models (e.g. gemma4): true/false to force it, empty = model default.
    # Turning it off makes answers much faster; only set it for models that support thinking.
    OLLAMA_REASONING: Optional[bool] = (
        os.getenv("OLLAMA_REASONING", "").strip().lower() in ("true", "1", "yes")
        if os.getenv("OLLAMA_REASONING", "").strip() else None
    )

    # Restaurant metadata & business shifts
    RESTAURANT_NAME: str = "Trattoria Bella Napoli"
    LUNCH_START: str = "12:00"
    LUNCH_END: str = "15:00"
    LUNCH_LAST_BOOKING: str = "14:00"

    DINNER_START: str = "19:00"
    DINNER_END: str = "23:30"
    DINNER_LAST_BOOKING: str = "22:00"

    RESERVATION_DURATION_MINUTES: int = 90

    # Customer registration. CHAT/VOICE collect name and phone *before* the conversation and send
    # them only to POST /api/customers; the LLM sees just the anonymous customer_id.
    # When enabled: bookings need a registered customer, and only the customer who made a booking
    # can read, modify or cancel it. Set to false to keep the legacy behaviour (e.g. until VOICE is adapted).
    REQUIRE_CUSTOMER_REGISTRATION: bool = os.getenv("REQUIRE_CUSTOMER_REGISTRATION", "true").lower() in ("true", "1", "yes")

settings = Settings()
