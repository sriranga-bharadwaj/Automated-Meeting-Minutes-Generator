"""Rate limiting, security headers, HTTPS redirect and input sanitising.

- AMG-SR-007: 100 requests per minute per signed-in user and 10 login attempts per minute per
  client address; over the limit the API answers HTTP 429 with a Retry-After header.
- AMG-SR-010: text is cleaned of HTML tags and control characters before it is stored, and every
  response carries security headers (CSP, nosniff, frame and referrer rules, HSTS over HTTPS).
- AMG-SR-001: with FORCE_HTTPS=true plain-HTTP requests are redirected to HTTPS.
Set RATE_LIMIT_ENABLED=false to switch rate limiting off.
"""
import os
import re
import threading
import time
from collections import defaultdict, deque
from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse, RedirectResponse
from starlette.middleware.base import BaseHTTPMiddleware

USER_LIMIT_PER_MIN = 100
LOGIN_LIMIT_PER_MIN = 10
WINDOW_SECONDS = 60


# ------------------------------------------------------------------ rate limiting
class RateLimiter:
    """Sliding window counter kept in memory (one process)."""

    def __init__(self) -> None:
        self._hits: dict[str, deque] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, key: str, limit: int, now: float | None = None) -> int:
        """0 when the request is allowed, else the number of seconds to wait."""
        now = time.monotonic() if now is None else now
        with self._lock:
            hits = self._hits[key]
            while hits and hits[0] <= now - WINDOW_SECONDS:
                hits.popleft()
            if len(hits) >= limit:
                return max(1, int(hits[0] + WINDOW_SECONDS - now) + 1)
            hits.append(now)
            return 0

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


limiter = RateLimiter()


def rate_limit_enabled() -> bool:
    return os.getenv("RATE_LIMIT_ENABLED", "true").strip().lower() not in {"0", "false", "no", "off"}


def too_many(wait: int) -> JSONResponse:
    message = f"Too many requests. Please wait {wait} second(s) and retry."
    return JSONResponse(
        status_code=429,
        content={"code": "RATE_LIMITED", "message": message, "detail": message},
        headers={"Retry-After": str(wait)},
    )


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


# ------------------------------------------------------------------ headers and HTTPS
CSP = "default-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
DOC_PATHS = ("/docs", "/redoc", "/openapi.json")


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if os.getenv("FORCE_HTTPS", "false").strip().lower() in {"1", "true", "yes", "on"}:
            if request.url.scheme != "https":
                return RedirectResponse(str(request.url.replace(scheme="https")), status_code=307)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = "geolocation=(), camera=(), microphone=(self)"
        if not request.url.path.startswith(DOC_PATHS):   # the API docs page loads its own scripts
            response.headers["Content-Security-Policy"] = CSP
        if request.url.scheme == "https":
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response


# ------------------------------------------------------------------ sanitising
_TAG = re.compile(r"<[^>]*>")
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def sanitize_text(value: str) -> str:
    """Remove HTML tags and control characters from text before it is stored."""
    return _CONTROL.sub("", _TAG.sub("", value))


def sanitize_obj(value: Any) -> Any:
    """sanitize_text applied to every string inside nested dicts and lists."""
    if isinstance(value, str):
        return sanitize_text(value)
    if isinstance(value, list):
        return [sanitize_obj(v) for v in value]
    if isinstance(value, dict):
        return {k: sanitize_obj(v) for k, v in value.items()}
    return value
