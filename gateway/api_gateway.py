"""
API Gateway Module
==================
Lightweight API Gateway pattern for the Face Recognition Attendance System.

Provides:
- Centralized request validation and authentication
- API versioning support
- Request/response logging
- CORS and security headers
- Health check endpoint

Usage:
    from gateway.api_gateway import APIGateway

    gateway = APIGateway(app)
"""

import os
import time
import uuid
import functools
from flask import request, jsonify, g


class APIGateway:
    """
    Lightweight API Gateway for Flask applications.

    Features:
    - Request ID tracking for distributed tracing
    - Security headers (HSTS, X-Content-Type-Options, etc.)
    - Request timing
    - API key authentication (optional)
    - Health check endpoint
    """

    def __init__(self, app=None):
        self.app = app
        if app is not None:
            self.init_app(app)

    def init_app(self, app):
        """Attach gateway middleware to a Flask application."""
        self.app = app

        @app.before_request
        def _gateway_before():
            # Assign unique request ID for tracing
            g.request_id = request.headers.get(
                "X-Request-ID",
                str(uuid.uuid4())[:8]
            )
            g.request_start = time.time()

            # Optional API key authentication for external access
            api_key = os.getenv("API_GATEWAY_KEY", "").strip()
            if api_key and request.path.startswith("/api/"):
                # Allow health/status endpoints without auth
                public_endpoints = {"/api/status", "/api/health"}
                if request.path not in public_endpoints:
                    provided_key = (
                        request.headers.get("X-API-Key", "")
                        or request.args.get("api_key", "")
                    )
                    if provided_key != api_key:
                        # Only enforce if API_GATEWAY_AUTH_REQUIRED is set
                        if os.getenv("API_GATEWAY_AUTH_REQUIRED", "false").lower() in ("true", "1"):
                            return jsonify({
                                "error": "Unauthorized",
                                "message": "Valid API key required",
                                "request_id": g.request_id,
                            }), 401

        @app.after_request
        def _gateway_after(response):
            # Request timing
            if hasattr(g, "request_start"):
                elapsed_ms = (time.time() - g.request_start) * 1000
                response.headers["X-Response-Time"] = f"{elapsed_ms:.1f}ms"

            # Request ID for tracing
            if hasattr(g, "request_id"):
                response.headers["X-Request-ID"] = g.request_id

            # Security headers
            response.headers["X-Content-Type-Options"] = "nosniff"
            response.headers["X-Frame-Options"] = "SAMEORIGIN"
            response.headers["X-XSS-Protection"] = "1; mode=block"
            response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

            # API version
            response.headers["X-API-Version"] = "1.0"

            return response

        # Register health check endpoint
        @app.route("/api/health")
        def _health_check():
            """
            Comprehensive health check endpoint.

            Returns system status including database, camera, recognition,
            and notification service health.
            """
            from database.models import get_session

            health = {
                "status": "healthy",
                "version": "1.0.0",
                "timestamp": time.time(),
                "request_id": getattr(g, "request_id", "N/A"),
                "checks": {},
            }

            # Database check
            try:
                session = get_session()
                session.execute(
                    __import__("sqlalchemy").text("SELECT 1")
                )
                session.close()
                health["checks"]["database"] = {"status": "up"}
            except Exception as exc:
                health["checks"]["database"] = {
                    "status": "down",
                    "error": str(exc),
                }
                health["status"] = "degraded"

            # Camera check (from app module globals)
            try:
                import app as app_module
                cam_ok = getattr(app_module, "camera_info", {}).get("ok", False)
                health["checks"]["camera"] = {
                    "status": "up" if cam_ok else "down",
                    "message": getattr(app_module, "camera_info", {}).get("message", ""),
                }
            except Exception:
                health["checks"]["camera"] = {"status": "unknown"}

            # SMS Gateway check (circuit breaker state)
            try:
                from middleware.circuit_breaker import sms_circuit_breaker
                cb_stats = sms_circuit_breaker.stats()
                health["checks"]["sms_gateway"] = {
                    "status": "up" if cb_stats["state"] == "closed" else cb_stats["state"],
                    "circuit_state": cb_stats["state"],
                    "failure_count": cb_stats["failure_count"],
                }
            except Exception:
                health["checks"]["sms_gateway"] = {"status": "unknown"}

            # Cache stats
            try:
                from middleware.cache import get_cache
                cache_stats = get_cache().stats()
                health["checks"]["cache"] = {
                    "status": "up",
                    "entries": cache_stats["entries"],
                    "hit_rate": cache_stats["hit_rate_percent"],
                }
            except Exception:
                health["checks"]["cache"] = {"status": "unknown"}

            status_code = 200 if health["status"] == "healthy" else 503
            return jsonify(health), status_code

        app.extensions["api_gateway"] = self
        print("[API GATEWAY] Initialized with request tracking and security headers", flush=True)
