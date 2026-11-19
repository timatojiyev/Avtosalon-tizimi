"""Kichik DB adapter: lokal/testda SQLite, Docker'da PostgreSQL (psycopg 3).

SQL'da ``?`` belgisi ishlatiladi — PostgreSQL uchun avtomatik ``%s`` ga almashtiriladi.
Sxemada ``{pk}`` → ``INTEGER PRIMARY KEY AUTOINCREMENT`` (SQLite) yoki ``SERIAL PRIMARY KEY`` (PostgreSQL).
"""
from __future__ import annotations

import logging
import sqlite3
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Sequence

log = logging.getLogger("svc.db")


class Database:
    def __init__(self, url: str, connect_retries: int = 30, retry_delay: float = 1.0):
        self.url = url
        self.dialect = "postgresql" if url.startswith(("postgres://", "postgresql://")) else "sqlite"
        self._lock = threading.RLock()
        self._memory: sqlite3.Connection | None = None
        if self.dialect == "sqlite":
            path = url.removeprefix("sqlite:///") or ":memory:"
            self._path = path
            if path == ":memory:":
                self._memory = sqlite3.connect(":memory:", check_same_thread=False)
            else:
                Path(path).parent.mkdir(parents=True, exist_ok=True)
        else:
            import psycopg  # noqa: F401 — faqat PostgreSQL rejimida kerak
            self._wait_until_ready(connect_retries, retry_delay)

    # ------------------------------------------------------------------ #
    def _wait_until_ready(self, retries: int, delay: float) -> None:
        """Konteynerlar bir vaqtda ko'tariladi — DB tayyor bo'lguncha qayta urinish (depends_on'ga qo'shimcha)."""
        import psycopg
        for attempt in range(1, retries + 1):
            try:
                with psycopg.connect(self.url, connect_timeout=3) as conn:
                    conn.execute("SELECT 1")
                return
            except psycopg.OperationalError as exc:
                log.warning("DB tayyor emas (%s/%s): %s", attempt, retries, exc)
                time.sleep(delay)
        raise RuntimeError("Ma'lumotlar bazasiga ulanib bo'lmadi")

    def _sql(self, sql: str) -> str:
        return sql.replace("?", "%s") if self.dialect == "postgresql" else sql

    @contextmanager
    def connect(self) -> Iterator["Session"]:
        if self.dialect == "postgresql":
            import psycopg
            from psycopg.rows import dict_row
            with psycopg.connect(self.url, row_factory=dict_row) as conn:   # chiqishda commit / xatoda rollback
                yield Session(conn, self)
            return
        with self._lock:
            conn = self._memory or sqlite3.connect(self._path, timeout=10)
            conn.row_factory = sqlite3.Row
            try:
                yield Session(conn, self)
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                if self._memory is None:
                    conn.close()

    def init_schema(self, schema: str) -> None:
        pk = "SERIAL PRIMARY KEY" if self.dialect == "postgresql" else "INTEGER PRIMARY KEY AUTOINCREMENT"
        with self.connect() as s:
            for stmt in filter(None, (x.strip() for x in schema.format(pk=pk).split(";"))):
                s.execute(stmt)

    def ping(self) -> bool:
        try:
            with self.connect() as s:
                s.one("SELECT 1 AS ok")
            return True
        except Exception:  # noqa: BLE001
            return False


class Session:
    def __init__(self, conn: Any, db: Database):
        self._conn, self._db = conn, db

    def execute(self, sql: str, params: Sequence[Any] = ()) -> Any:
        return self._conn.execute(self._db._sql(sql), tuple(params))

    def all(self, sql: str, params: Sequence[Any] = ()) -> list[dict[str, Any]]:
        return [dict(r) for r in self.execute(sql, params).fetchall()]

    def one(self, sql: str, params: Sequence[Any] = ()) -> dict[str, Any] | None:
        row = self.execute(sql, params).fetchone()
        return dict(row) if row else None

    def scalar(self, sql: str, params: Sequence[Any] = ()) -> Any:
        row = self.execute(sql, params).fetchone()
        return None if row is None else list(dict(row).values())[0]
