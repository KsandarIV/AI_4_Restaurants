"""Maintenance commands, to run by hand or from a scheduler.

  python -m backend.maintenance purge --dry-run      show how many customers would be deleted
  python -m backend.maintenance purge --days 60      delete name and phone of old customers

Reservations are kept (anonymous): only the contact data in the `customers` table is deleted.
"""
import argparse

from backend.config import settings
from backend.database import crud
from backend.database.connection import SessionLocal


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="python -m backend.maintenance", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    purge = sub.add_parser("purge", help="delete name and phone of customers with no booking in the last N days")
    purge.add_argument("--days", type=int, default=settings.DATA_RETENTION_DAYS,
                       help=f"retention in days (default {settings.DATA_RETENTION_DAYS}, DATA_RETENTION_DAYS in .env)")
    purge.add_argument("--dry-run", action="store_true", help="only count, delete nothing")
    args = parser.parse_args(argv)

    crud.init_db()
    with SessionLocal() as db:
        count = crud.purge_old_customers(db, args.days, dry_run=args.dry_run)
    print(f"{count} clienti {'da cancellare (nessuna modifica fatta)' if args.dry_run else 'cancellati'} "
          f"(registrati da più di {args.days} giorni, senza prenotazioni recenti).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
