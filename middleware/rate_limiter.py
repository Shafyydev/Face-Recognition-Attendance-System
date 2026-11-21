"""
Rate Limiter Middleware
=======================
Provides in-memory, sliding-window rate limiting for Flask API endpoints.
Uses a token-bucket-inspired algorithm — no external dependencies required.

Usage:
    from middleware.rate_limiter import RateLimiter, rate_limit

    limiter = RateLimiter(app)        # attach to Flask app

    @app.route('/api/register', methods=['POST'])
    @rate_limit("5/minute")           # 5 requests per minute per IP
    def register_student():
        ...

Configuration (.env):
    RATE_LIMIT_ENABLED=true
    RATE_LIMIT_DEFAULT=60/minute
    RATE_LIMIT_STORAGE=memory
"""

import os
import time
import threading
import functools
from collections import defaultdict
from flask import request, jsonify, g


class _SlidingWindow:
    """Thread-safe sliding window counter for a single key."""

    __slots__ = ("_timestamps", "_lock")

    def __init__(self):
        self._timestamps: list[float] = []
        self._lock = threading.Lock()

    def hit(self, now: float, window_seconds: float, max_hits: int) -> bool:
        """Record a hit. Return True if the request is ALLOWED."""
        with self._lock:
            cutoff = now - window_seconds
            self._timestamps = [t for t in self._timestamps if t > cutoff]
            if len(self._timestamps) >= max_hits:
                return False
            self._timestamps.append(now)
            return True

    def remaining(self, now: float, window_seconds: float, max_hits: int) -> int:
        with self._lock:
            cutoff = now - window_seconds
            active = [t for t in self._timestamps if t > cutoff]
            return max(0, max_hits - len(active))

    def reset_time(self, now: float, window_seconds: float) -> float:
        with self._lock:
            cutoff = now - window_seconds
            active = [t for t in self._timestamps if t > cutoff]
            if active:
                return active[0] + window_seconds
            return now + window_seconds


class RateLimiterStorage:
    """In-memory rate limit storage with automatic cleanup."""

    def __init__(self):
        self._windows: dict[str, _SlidingWindow] = defaultdict(_SlidingWindow)
        self._lock = threading.Lock()
        self._cleanup_interval = 300  # cleanup every 5 minutes
        self._last_cleanup = time.time()

    def get_window(self, key: str) -> _SlidingWindow:
        with self._lock:
            now = time.time()
            if now - self._last_cleanup > self._cleanup_interval:
                self._cleanup(now)
                self._last_cleanup = now
            return self._windows[key]

    def _cleanup(self, now: float):
        """Remove stale entries older than 10 minutes."""
        stale_keys = []
        for key, window in self._windows.items():
            if window.remaining(now, 600, 1) == 1:  # no hits in last 10 min
                stale_keys.append(key)
        for key in stale_keys:
            del self._windows[key]


def _parse_rate(rate_string: str) -> tuple:
    """Parse rate string like '60/minute' into (max_hits, window_seconds)."""
    rate_string = rate_string.strip().lower()

    unit_map = {
        "second": 1, "sec": 1, "s": 1,
        "minute": 60, "min": 60, "m": 60,
        "hour": 3600, "hr": 3600, "h": 3600,
        "day": 86400, "d": 86400,
    }

    parts = rate_string.split("/")
    if len(parts) != 2:
        raise ValueError(f"Invalid rate format: '{rate_string}'. Use 'N/unit' (e.g. '60/minute')")

    max_hits = int(parts[0].strip())
    unit = parts[1].strip()

    if unit not in unit_map:
        raise ValueError(f"Unknown time unit: '{unit}'. Use: second, minute, hour, day")

    return max_hits, unit_map[unit]


# Global storage instance
_storage = RateLimiterStorage()


def _get_client_key() -> str:
    """Get a unique key for the current client (IP-based)."""
    # Support reverse proxy headers
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.remote_addr or "unknown"


def rate_limit(limit_string: str, key_func=None, error_message=None):
    """
    Decorator to apply rate limiting to a Flask route.

    Args:
        limit_string: Rate limit in 'N/unit' format (e.g., '10/minute', '100/hour')
        key_func: Optional callable returning a custom rate limit key
        error_message: Optional custom error message when rate limited

    Example:
        @app.route('/api/register', methods=['POST'])
        @rate_limit("5/minute")
        def register():
            ...
    """
    max_hits, window_seconds = _parse_rate(limit_string)

    def decorator(f):
        @functools.wraps(f)
        def wrapper(*args, **kwargs):
            # Check if rate limiting is enabled
            enabled = os.getenv("RATE_LIMIT_ENABLED", "true").strip().lower()
            if enabled not in ("true", "1", "yes", "on"):
                return f(*args, **kwargs)

            # Build rate limit key
            if key_func:
                client_key = key_func()
            else:
                client_key = _get_client_key()

            rate_key = f"{request.endpoint}:{client_key}"
            now = time.time()

            window = _storage.get_window(rate_key)
            allowed = window.hit(now, window_seconds, max_hits)

            # Always set rate limit headers
            remaining = window.remaining(now, window_seconds, max_hits)
            reset_at = window.reset_time(now, window_seconds)

            g.rate_limit_limit = max_hits
            g.rate_limit_remaining = remaining
            g.rate_limit_reset = int(reset_at)

            if not allowed:
                msg = error_message or "Rate limit exceeded. Please try again later."
                response = jsonify({
                    "error": msg,
                    "retry_after": int(reset_at - now) + 1,
                })
                response.status_code = 429
                response.headers["Retry-After"] = str(int(reset_at - now) + 1)
                response.headers["X-RateLimit-Limit"] = str(max_hits)
                response.headers["X-RateLimit-Remaining"] = "0"
                response.headers["X-RateLimit-Reset"] = str(int(reset_at))
                return response

            return f(*args, **kwargs)

        return wrapper
    return decorator


class RateLimiter:
    """
    Flask extension for rate limiting.

    Usage:
        limiter = RateLimiter(app, default_limit="60/minute")
    """

    def __init__(self, app=None, default_limit="60/minute"):
        self.default_limit = default_limit
        if app is not None:
            self.init_app(app)

    def init_app(self, app):
        """Attach rate limit headers to all responses."""
        @app.after_request
        def _add_rate_limit_headers(response):
            if hasattr(g, "rate_limit_limit"):
                response.headers["X-RateLimit-Limit"] = str(g.rate_limit_limit)
                response.headers["X-RateLimit-Remaining"] = str(g.rate_limit_remaining)
                response.headers["X-RateLimit-Reset"] = str(g.rate_limit_reset)
            return response

        app.extensions["rate_limiter"] = self
        print("[RATE LIMITER] Initialized", flush=True)
