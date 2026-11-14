"""User marks and votes. Postgres when DATABASE_URL is set; in memory otherwise (local runs, tests)."""

from __future__ import annotations

from datetime import UTC, datetime
from threading import Lock

SCHEMA = """
CREATE TABLE IF NOT EXISTS marks (
    mark_id     BIGSERIAL PRIMARY KEY,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    field_id    TEXT NOT NULL,
    source_id   TEXT,
    ra          DOUBLE PRECISION NOT NULL,
    dec         DOUBLE PRECISION NOT NULL,
    epoch_mjd   DOUBLE PRECISION,
    user_label  TEXT NOT NULL,
    comment     TEXT NOT NULL DEFAULT '',
    client_id   TEXT NOT NULL DEFAULT 'anonymous'
);
CREATE INDEX IF NOT EXISTS marks_field_idx ON marks (field_id);
"""
COLUMNS = ("field_id", "source_id", "ra", "dec", "epoch_mjd", "user_label", "comment", "client_id")


class MemoryMarksRepo:
    storage = "memory"
    persistent = False  # lost when the instance restarts or sleeps

    def ping(self) -> bool:
        return True

    def __init__(self) -> None:
        self._rows: list[dict] = []
        self._lock = Lock()

    def add(self, mark: dict) -> dict:
        with self._lock:
            row = {**mark, "mark_id": len(self._rows) + 1, "created_at": datetime.now(UTC).isoformat()}
            self._rows.append(row)
            return row

    def list(self, field_id: str) -> list[dict]:
        return [r for r in self._rows if r["field_id"] == field_id]


class PostgresMarksRepo:
    """One short connection per call: enough for hackathon traffic, nothing to pool or leak."""

    storage = "postgres"
    persistent = True

    def ping(self) -> bool:
        try:
            with self._psycopg.connect(self._dsn, connect_timeout=3) as conn:
                conn.execute("SELECT 1")
            return True
        except Exception:  # noqa: BLE001 - health check: any failure means degraded
            return False

    def __init__(self, dsn: str) -> None:
        import psycopg

        self._psycopg = psycopg
        self._dsn = dsn
        with psycopg.connect(dsn) as conn:
            conn.execute(SCHEMA)

    def add(self, mark: dict) -> dict:
        placeholders = ", ".join(["%s"] * len(COLUMNS))
        sql = f"INSERT INTO marks ({', '.join(COLUMNS)}) VALUES ({placeholders}) RETURNING mark_id, created_at"
        with self._psycopg.connect(self._dsn) as conn:
            mark_id, created_at = conn.execute(sql, [mark.get(c) for c in COLUMNS]).fetchone()
        return {**mark, "mark_id": mark_id, "created_at": created_at.isoformat()}

    def list(self, field_id: str) -> list[dict]:
        sql = f"SELECT mark_id, created_at, {', '.join(COLUMNS)} FROM marks WHERE field_id = %s ORDER BY mark_id"
        with self._psycopg.connect(self._dsn) as conn:
            rows = conn.execute(sql, [field_id]).fetchall()
        keys = ("mark_id", "created_at") + COLUMNS
        return [{**dict(zip(keys, r, strict=True)), "created_at": r[1].isoformat()} for r in rows]


def make_marks_repo(database_url: str | None):
    return PostgresMarksRepo(database_url) if database_url else MemoryMarksRepo()
