import os
import sqlite3
from pathlib import Path

DB_ENV = "DB_PATH"
DEFAULT_DB_PATH = str(Path(__file__).resolve().parent / "db" / "shared.db")


def get_db_path() -> str:
    return os.environ.get(DB_ENV, DEFAULT_DB_PATH)


def connect(db_path: str | None = None) -> sqlite3.Connection:
    path = db_path or get_db_path()
    conn = sqlite3.connect(path, check_same_thread=False, timeout=5)
    # Use WAL for concurrent reads/writes across services.
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn


def init_db(db_path: str | None = None) -> None:
    path = db_path or get_db_path()
    schema_path = Path(__file__).resolve().parent / "db" / "schema.sql"
    if not Path(path).exists():
        # Create the database file and load schema + seed data.
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        conn = connect(path)
        with open(schema_path, "r", encoding="utf-8") as handle:
            conn.executescript(handle.read())
        conn.commit()
        conn.close()
        return
    conn = connect(path)
    # Apply schema updates idempotently for existing DBs.
    with open(schema_path, "r", encoding="utf-8") as handle:
        conn.executescript(handle.read())
    conn.commit()
    conn.close()
