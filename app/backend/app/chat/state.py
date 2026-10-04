"""Pillar 2 — Session state.  Flag: CHAT_STATE

Pluggable session store behind a Protocol. Default is an in-memory dict with
TTL eviction. Swappable for Redis or a DB row by implementing SessionStore —
zero changes to any other module.

Imports: contracts only. No DB, no pillar internals.
"""
from __future__ import annotations

import threading
import time
from typing import Optional, Protocol, runtime_checkable

from .contracts import ChatSession

_TTL_SECONDS = 60 * 60  # 1 hour of inactivity expires a session


@runtime_checkable
class SessionStore(Protocol):
    def get(self, sid: str) -> Optional[ChatSession]: ...
    def put(self, sid: str, session: ChatSession) -> None: ...
    def delete(self, sid: str) -> None: ...


class InMemoryStore:
    """Thread-safe in-memory session store with TTL eviction.

    Suitable for a single-process server. For multi-instance deploys, swap
    this for a RedisStore implementing the same Protocol — no other code changes.
    """

    def __init__(self, ttl: int = _TTL_SECONDS) -> None:
        self._store: dict[str, tuple[ChatSession, float]] = {}
        self._lock = threading.Lock()
        self._ttl = ttl

    def get(self, sid: str) -> Optional[ChatSession]:
        with self._lock:
            entry = self._store.get(sid)
            if entry is None:
                return None
            session, ts = entry
            if time.monotonic() - ts > self._ttl:
                del self._store[sid]
                return None
            # Refresh TTL on access
            self._store[sid] = (session, time.monotonic())
            return session

    def put(self, sid: str, session: ChatSession) -> None:
        with self._lock:
            self._store[sid] = (session, time.monotonic())

    def delete(self, sid: str) -> None:
        with self._lock:
            self._store.pop(sid, None)

    def _evict_expired(self) -> None:
        now = time.monotonic()
        with self._lock:
            expired = [sid for sid, (_, ts) in self._store.items()
                       if now - ts > self._ttl]
            for sid in expired:
                del self._store[sid]


# Module-level singleton — one store per process.
_store: SessionStore = InMemoryStore()


def get_session(sid: Optional[str]) -> ChatSession:
    """Return the existing session for sid, or a fresh empty one."""
    if sid is None:
        return ChatSession()
    existing = _store.get(sid)
    return existing if existing is not None else ChatSession()


def save_session(sid: Optional[str], session: ChatSession) -> None:
    """Persist the session. No-op when sid is None (stateless fallback)."""
    if sid is not None:
        _store.put(sid, session)


def replace_store(new_store: SessionStore) -> None:
    """Swap the backing store — used in tests or to inject Redis in prod."""
    global _store
    _store = new_store
