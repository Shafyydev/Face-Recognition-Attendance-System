"""
Response Cache Middleware
=========================
Provides in-memory TTL-based caching for Flask API responses.
No external dependencies — uses a simple dictionary with time-based expiry.

Usage:
    from middleware.cache import ResponseCache, cached

    cache = ResponseCache(app)

    @app.route('/api/stats')
    @cached(ttl=10)                  # cache for 10 seconds
    def get_stats():
        ...

Cache is automatically invalidated on write operations (POST/PUT/DELETE)
via the cache.invalidate() or invalidate_cache() helper.

Configuration (.env):
    CACHE_ENABLED=true
    CACHE_DEFAULT_TTL=10
"""

import os
import time
import hashlib
import threading
import functools
from flask import request, jsonify, g


class CacheEntry:
    """A single cached response with TTL."""

    __slots__ = ("data", "created_at", "ttl", "hits")

    def __init__(self, data, ttl: float):
        self.data = data
        self.created_at = time.time()
        self.ttl = ttl
        self.hits = 0

    @property
    def is_expired(self) -> bool:
        return (time.time() - self.created_at) > self.ttl

    @property
    def age(self) -> float:
        return time.time() - self.created_at


class ResponseCache:
    """
    In-memory response cache for Flask applications.

    Features:
    - TTL-based expiry
    - Automatic cache key generation from URL + query params
    - Thread-safe operations
    - Manual invalidation support
    - Cache statistics
    """

    def __init__(self, app=None, default_ttl: int = 10):
        self._store: dict[str, CacheEntry] = {}
        self._lock = threading.RLock()
        self._default_ttl = default_ttl
        self._stats = {"hits": 0, "misses": 0, "invalidations": 0}

        if app is not None:
            self.init_app(app)

    def init_app(self, app):
        """Register the cache with a Flask application."""
        app.extensions["response_cache"] = self

        @app.after_request
        def _add_cache_headers(response):
            if hasattr(g, "cache_hit"):
                response.headers["X-Cache"] = "HIT" if g.cache_hit else "MISS"
            if hasattr(g, "cache_age"):
                response.headers["X-Cache-Age"] = str(int(g.cache_age))
            return response

        print("[CACHE] Response cache initialized", flush=True)

    def _make_key(self, endpoint: str, args: dict) -> str:
        """Generate a unique cache key from endpoint + sorted query args."""
        sorted_args = "&".join(f"{k}={v}" for k, v in sorted(args.items()))
        raw = f"{endpoint}?{sorted_args}"
        return hashlib.md5(raw.encode()).hexdigest()

    def get(self, key: str) -> CacheEntry | None:
        """Retrieve a cache entry if it exists and is not expired."""
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                self._stats["misses"] += 1
                return None
            if entry.is_expired:
                del self._store[key]
                self._stats["misses"] += 1
                return None
            entry.hits += 1
            self._stats["hits"] += 1
            return entry

    def set(self, key: str, data, ttl: float = None):
        """Store a response in the cache."""
        with self._lock:
            self._store[key] = CacheEntry(data, ttl or self._default_ttl)

    def invalidate(self, pattern: str = None):
        """
        Invalidate cache entries.

        Args:
            pattern: If provided, only invalidate keys containing this pattern.
                     If None, invalidate ALL entries.
        """
        with self._lock:
            if pattern is None:
                count = len(self._store)
                self._store.clear()
            else:
                keys_to_delete = [k for k in self._store if pattern in k]
                count = len(keys_to_delete)
                for k in keys_to_delete:
                    del self._store[k]
            self._stats["invalidations"] += count
            if count > 0:
                print(f"[CACHE] Invalidated {count} entries", flush=True)

    def stats(self) -> dict:
        """Return cache statistics."""
        with self._lock:
            total = self._stats["hits"] + self._stats["misses"]
            hit_rate = (self._stats["hits"] / total * 100) if total > 0 else 0
            return {
                "entries": len(self._store),
                "hits": self._stats["hits"],
                "misses": self._stats["misses"],
                "invalidations": self._stats["invalidations"],
                "hit_rate_percent": round(hit_rate, 1),
            }

    def cleanup(self):
        """Remove all expired entries."""
        with self._lock:
            expired = [k for k, v in self._store.items() if v.is_expired]
            for k in expired:
                del self._store[k]


# Global cache instance
_cache = ResponseCache()


def get_cache() -> ResponseCache:
    """Return the global cache instance."""
    return _cache


def invalidate_cache(pattern: str = None):
    """Convenience function to invalidate the global cache."""
    _cache.invalidate(pattern)


def cached(ttl: int = 10, key_func=None, unless=None):
    """
    Decorator to cache Flask route responses.

    Args:
        ttl: Time-to-live in seconds (default: 10)
        key_func: Optional callable to generate a custom cache key
        unless: Optional callable; if it returns True, skip caching

    Example:
        @app.route('/api/stats')
        @cached(ttl=15)
        def get_stats():
            ...
    """
    def decorator(f):
        @functools.wraps(f)
        def wrapper(*args, **kwargs):
            # Check if caching is enabled
            enabled = os.getenv("CACHE_ENABLED", "true").strip().lower()
            if enabled not in ("true", "1", "yes", "on"):
                return f(*args, **kwargs)

            # Skip cache for non-GET requests
            if request.method != "GET":
                return f(*args, **kwargs)

            # Check unless condition
            if unless and unless():
                return f(*args, **kwargs)

            # Generate cache key
            if key_func:
                cache_key = key_func()
            else:
                cache_key = _cache._make_key(
                    request.endpoint or f.__name__,
                    dict(request.args)
                )

            # Try cache
            entry = _cache.get(cache_key)
            if entry is not None:
                g.cache_hit = True
                g.cache_age = entry.age
                return entry.data

            # Cache miss — execute the function
            g.cache_hit = False
            g.cache_age = 0
            result = f(*args, **kwargs)

            # Store in cache
            _cache.set(cache_key, result, ttl)
            return result

        return wrapper
    return decorator
