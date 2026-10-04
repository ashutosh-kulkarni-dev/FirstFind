"""Custom middleware: request timing/logging + simple in-memory rate limiting."""
import json
import logging
import time
from collections import defaultdict, deque

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

logger = logging.getLogger("thriftfind")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


class TimingMiddleware(BaseHTTPMiddleware):
    """Logs every request with latency; adds X-Response-Time header."""

    async def dispatch(self, request: Request, call_next):
        start = time.perf_counter()
        response = await call_next(request)
        ms = (time.perf_counter() - start) * 1000
        response.headers["X-Response-Time"] = f"{ms:.1f}ms"
        logger.info("%s %s -> %s (%.1fms)", request.method, request.url.path,
                     response.status_code, ms)
        return response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Stamp common hardening headers on every response.

    Scope stays narrow on purpose: no CSP (would need per-page tuning and the
    frontend lives on a different origin anyway) and no HPKP (deprecated). Each
    header below either costs nothing or has already been considered against
    this app's needs.
    """

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        # 2 years + preload-eligible; Render terminates TLS so HSTS is safe.
        response.headers.setdefault(
            "Strict-Transport-Security",
            "max-age=63072000; includeSubDomains; preload",
        )
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault(
            "Permissions-Policy",
            "geolocation=(self), microphone=(), camera=(), payment=()",
        )
        return response


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Naive sliding-window rate limiter per client IP (in-memory, MVP-grade).

    Memory is bounded: an IP's entry is dropped as soon as its window empties,
    and a periodic sweep evicts any IP whose last request has aged out. Without
    this, `self.hits` grew one deque per unique IP forever (a slow leak). Still
    per-process — move to Redis when running more than one worker.
    """

    def __init__(self, app, max_requests: int = 120, window_seconds: int = 60):
        super().__init__(app)
        self.max_requests = max_requests
        self.window = window_seconds
        self.hits: dict[str, deque] = defaultdict(deque)
        self._last_sweep = 0.0

    def _sweep(self, now: float) -> None:
        """Evict IPs with no request inside the current window. Runs at most
        once per window so it's cheap even under heavy, high-cardinality load."""
        if now - self._last_sweep < self.window:
            return
        self._last_sweep = now
        stale = [ip for ip, q in self.hits.items()
                 if not q or now - q[-1] > self.window]
        for ip in stale:
            del self.hits[ip]

    async def dispatch(self, request: Request, call_next):
        ip = request.client.host if request.client else "unknown"
        now = time.time()
        self._sweep(now)
        q = self.hits[ip]
        while q and now - q[0] > self.window:
            q.popleft()
        if len(q) >= self.max_requests:
            # This IP is over the limit but still active; keep its deque.
            return JSONResponse(status_code=429,
                                content={"detail": "Rate limit exceeded. Slow down."})
        q.append(now)
        return await call_next(request)


class AuthRateLimitMiddleware(BaseHTTPMiddleware):
    """Stricter throttle for /api/auth/login + /api/auth/register.

    Keyed by (ip, email) rather than ip alone — a shared office NAT shouldn't
    lock everyone out when one person fat-fingers their password, but a single
    attacker spraying thousands of emails from one IP still trips the IP-wide
    limit above. Guest/empty-body requests fall back to IP-only.
    """

    PROTECTED_PATHS = {"/api/auth/login", "/api/auth/register", "/api/auth/google"}

    def __init__(self, app, max_requests: int = 10, window_seconds: int = 60):
        super().__init__(app)
        self.max_requests = max_requests
        self.window = window_seconds
        self.hits: dict[tuple[str, str], deque] = defaultdict(deque)
        self._last_sweep = 0.0

    def _sweep(self, now: float) -> None:
        if now - self._last_sweep < self.window:
            return
        self._last_sweep = now
        stale = [k for k, q in self.hits.items()
                 if not q or now - q[-1] > self.window]
        for k in stale:
            del self.hits[k]

    async def dispatch(self, request: Request, call_next):
        if request.url.path not in self.PROTECTED_PATHS:
            return await call_next(request)

        ip = request.client.host if request.client else "unknown"
        # Peek at the body to extract the identity key without consuming it —
        # Starlette caches the body so downstream handlers still read it fine.
        body = await request.body()
        identity = ""
        try:
            data = json.loads(body or b"{}")
            identity = (data.get("email") or data.get("credential") or "").strip().lower()[:120]
        except (ValueError, AttributeError):
            pass

        key = (ip, identity)
        now = time.time()
        self._sweep(now)
        q = self.hits[key]
        while q and now - q[0] > self.window:
            q.popleft()
        if len(q) >= self.max_requests:
            return JSONResponse(status_code=429,
                                content={"detail": "Too many auth attempts. Try again in a minute."})
        q.append(now)
        return await call_next(request)
