from sqlalchemy import create_engine, event
from sqlalchemy.orm import declarative_base, sessionmaker
from backend.config import settings

connect_args = {"check_same_thread": False, "timeout": 10} if "sqlite" in settings.DATABASE_URL else {}

engine = create_engine(settings.DATABASE_URL, connect_args=connect_args)

if "sqlite" in settings.DATABASE_URL:
    @event.listens_for(engine, "connect")
    def _set_sqlite_pragmas(dbapi_connection, _connection_record):
        """WAL + busy timeout + FK enforcement on every SQLite connection.

        - journal_mode=WAL: readers never block writers (LAN clients reading menu/info
          while a booking is committed) and vice versa.
        - busy_timeout=5000: a concurrent writer waits 5s instead of failing with SQLITE_BUSY.
        - synchronous=NORMAL: safe with WAL, faster commits.
        - foreign_keys=ON: SQLite does not enforce FKs by default.
        Single-file SQLite + single uvicorn worker: together with the
        BEGIN IMMEDIATE write transactions in crud.py this prevents overbooking.
        """
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL;")
        cursor.execute("PRAGMA busy_timeout=5000;")
        cursor.execute("PRAGMA synchronous=NORMAL;")
        cursor.execute("PRAGMA foreign_keys=ON;")
        cursor.close()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    """FastAPI dependency for database sessions."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
