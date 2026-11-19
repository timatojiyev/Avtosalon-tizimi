"""Autentifikatsiya, rollar asosidagi ruxsatlar (RBAC) va audit jurnali — BFF (web) qatlamida.

Biznes-servislar ichki tarmoqda (``backend``) yopiq turadi, foydalanuvchi faqat web orqali kiradi,
shuning uchun kirish nazorati bitta joyda — shu modulda (ADR-0010).
"""
from __future__ import annotations

import os
import threading
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from werkzeug.security import check_password_hash, generate_password_hash

ROLES: dict[str, dict[str, Any]] = {
    "admin": {"title": "Administrator", "perms": {"*"}},
    "menejer": {"title": "Sotuv menejeri", "perms": {"dashboard", "cars:read", "cars:write", "customers:read", "customers:write",
                                                      "sales:read", "sales:write", "financing:read", "reports", "docs"}},
    "kredit": {"title": "Kredit mutaxassisi", "perms": {"dashboard", "customers:read", "sales:read", "financing:read",
                                                        "reports", "docs"}},
}

# Demo foydalanuvchilar. Production'da parollar muhit o'zgaruvchilaridan olinadi (WEB_<LOGIN>_PASSWORD).
DEFAULT_USERS = [("admin", "Administrator", "admin", "admin123"),
                 ("menejer", "Dilshod Ergashev", "menejer", "menejer123"),
                 ("kredit", "Nodira Saidova", "kredit", "kredit123")]


@dataclass(frozen=True)
class User:
    login: str
    name: str
    role: str
    password_hash: str

    @property
    def role_title(self) -> str:
        return ROLES[self.role]["title"]

    def can(self, perm: str) -> bool:
        perms = ROLES[self.role]["perms"]
        return "*" in perms or perm in perms


def load_users(production: bool | None = None) -> dict[str, User]:
    """Production'da demo parollar ishlatilmaydi: WEB_<LOGIN>_PASSWORD berilmagan foydalanuvchi yaratilmaydi."""
    if production is None:
        production = os.getenv("APP_ENV", "development") == "production"
    users = {}
    for login, name, role, default_pw in DEFAULT_USERS:
        pw = os.getenv(f"WEB_{login.upper()}_PASSWORD") or ("" if production else default_pw)
        if pw:
            users[login] = User(login, name, role, generate_password_hash(pw))
    return users


class LoginThrottle:
    """Parolni terib topishdan himoya: IP+login bo'yicha 5 ta xato → 5 daqiqa blok."""

    def __init__(self, max_failures: int = 5, window_s: int = 300):
        self.max_failures, self.window_s = max_failures, window_s
        self._fails: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def _recent(self, key: str) -> list[float]:
        now = time.time()
        items = [t for t in self._fails.get(key, []) if now - t < self.window_s]
        self._fails[key] = items
        return items

    def blocked_for(self, key: str) -> int:
        with self._lock:
            items = self._recent(key)
            if len(items) < self.max_failures:
                return 0
            return int(self.window_s - (time.time() - items[0])) + 1

    def fail(self, key: str) -> None:
        with self._lock:
            self._recent(key).append(time.time())

    def reset(self, key: str) -> None:
        with self._lock:
            self._fails.pop(key, None)


def verify(users: dict[str, User], login: str, password: str) -> User | None:
    user = users.get(login.strip().lower())
    # Login topilmasa ham hash tekshiruvi bajariladi — javob vaqti bo'yicha loginni aniqlab bo'lmasin.
    ok = check_password_hash(user.password_hash if user else _DUMMY_HASH, password)
    return user if user and ok else None


_DUMMY_HASH = generate_password_hash("dummy-password")


class AuditLog:
    """Kim, qachon, nima qildi. Xotirada (oxirgi 500 yozuv) + ixtiyoriy JSONL fayl (AUDIT_LOG_PATH)."""

    def __init__(self, path: str | None = None, capacity: int = 500):
        self._items: deque[dict[str, Any]] = deque(maxlen=capacity)
        self._lock = threading.Lock()
        self.path = path

    def write(self, user: str, action: str, detail: str = "", ok: bool = True, request_id: str = "", ip: str = "") -> None:
        item = {"at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "user": user, "action": action,
                "detail": detail[:300], "ok": ok, "request_id": request_id, "ip": ip}
        with self._lock:
            self._items.append(item)
            if self.path:
                try:
                    import json
                    with open(self.path, "a", encoding="utf-8") as f:
                        f.write(json.dumps(item, ensure_ascii=False) + "\n")
                except OSError:
                    pass

    def recent(self, limit: int = 200) -> list[dict[str, Any]]:
        with self._lock:
            return list(self._items)[-limit:][::-1]
