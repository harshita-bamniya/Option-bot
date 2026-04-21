"""Simple migration runner — executes SQL files under /sql in order.

For production scale-out, swap to Alembic. This is deliberately minimal
so the first-time developer can get a working DB with one command.
"""
from __future__ import annotations

from pathlib import Path

from sqlalchemy import text

from app.db.session import engine
from app.utils.logging import get_logger, setup_logging

log = get_logger(__name__)

SQL_DIR = Path(__file__).resolve().parent.parent.parent / "sql"


def main() -> None:
    setup_logging()
    files = sorted(SQL_DIR.glob("*.sql"))
    if not files:
        log.warning("no_sql_files_found", path=str(SQL_DIR))
        return

    with engine.begin() as conn:
        for f in files:
            log.info("applying_migration", file=f.name)
            sql = f.read_text(encoding="utf-8")
            # Execute as a single script (Postgres supports multi-statement)
            conn.exec_driver_sql(sql)
    log.info("migrations_complete", count=len(files))


if __name__ == "__main__":
    main()
