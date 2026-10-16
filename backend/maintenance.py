"""Maintenance commands, to run by hand or from a scheduler.

  python -m backend.maintenance staff-key            generate a secret for the staff area (to put in .env)
  python -m backend.maintenance backup               copy the database to backend/backups/ (keeps the last 14)
  python -m backend.maintenance purge --dry-run      show how many customers would be deleted
  python -m backend.maintenance purge --days 60      delete name and phone of old customers

Reservations are kept by `purge` (anonymous): only the contact data in the `customers` table is deleted.
"""
import argparse
import datetime
import secrets
import sqlite3
from pathlib import Path
from typing import Optional

from backend.config import settings
from backend.database import crud
from backend.database.connection import SessionLocal, engine


def backup_database(dest_dir: Optional[Path] = None, keep: int = 14) -> Path:
    """Consistent copy of the SQLite database (safe even while the server is running); keeps the newest `keep`."""
    source = engine.url.database
    if engine.dialect.name != "sqlite" or not source:
        raise RuntimeError("Il backup automatico funziona solo con SQLite.")
    dest_dir = Path(dest_dir) if dest_dir else Path(source).parent / "backups"
    dest_dir.mkdir(parents=True, exist_ok=True)
    target = dest_dir / f"restaurant_{datetime.datetime.now():%Y%m%d_%H%M%S}.db"
    src, dst = sqlite3.connect(source), sqlite3.connect(target)
    try:
        src.backup(dst)  # the official SQLite online backup: no half-written file
    finally:
        dst.close()
        src.close()
    for old in sorted(dest_dir.glob("restaurant_*.db"))[:-keep]:
        old.unlink()
    return target


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="python -m backend.maintenance", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("staff-key", help="print a new random STAFF_API_KEY line for the .env file")
    backup = sub.add_parser("backup", help="copy the database to backend/backups/")
    backup.add_argument("--keep", type=int, default=14, help="how many backups to keep (default 14)")
    purge = sub.add_parser("purge", help="delete name and phone of customers with no booking in the last N days")
    purge.add_argument("--days", type=int, default=settings.DATA_RETENTION_DAYS,
                       help=f"retention in days (default {settings.DATA_RETENTION_DAYS}, DATA_RETENTION_DAYS in .env)")
    purge.add_argument("--dry-run", action="store_true", help="only count, delete nothing")
    args = parser.parse_args(argv)

    if args.command == "staff-key":
        print("Aggiungi questa riga al file .env della macchina BE, poi riavvia il BE:\n")
        print(f"STAFF_API_KEY={secrets.token_urlsafe(24)}")
        print("\nÈ la password dell'area del ristoratore (http://<IP_BE>:8000/api/staff): non condividerla.")
        return 0

    crud.init_db()
    if args.command == "backup":
        print(f"Backup creato: {backup_database(keep=args.keep)}")
        return 0

    with SessionLocal() as db:
        count = crud.purge_old_customers(db, args.days, dry_run=args.dry_run)
    print(f"{count} clienti {'da cancellare (nessuna modifica fatta)' if args.dry_run else 'cancellati'} "
          f"(registrati da più di {args.days} giorni, senza prenotazioni recenti).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
