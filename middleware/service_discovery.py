"""
Service Discovery Module
=========================
Formalizes the service discovery pattern for the Face Recognition Attendance System.

Implements:
- Service registry for internal and external services
- Health check probing for registered services
- Auto-discovery of LAN services (SMS Gateway)
- Service status monitoring with periodic health checks

Usage:
    from middleware.service_discovery import ServiceRegistry, service_registry

    # Register a service
    service_registry.register("sms_gateway", "http://192.168.1.100:8080")

    # Discover and use
    url = service_registry.get_url("sms_gateway")
"""

import time
import socket
import threading
from dataclasses import dataclass, field
from enum import Enum


class ServiceStatus(Enum):
    """Service health status."""
    UP = "up"
    DOWN = "down"
    UNKNOWN = "unknown"
    DEGRADED = "degraded"


@dataclass
class ServiceInfo:
    """Information about a registered service."""
    name: str
    url: str
    status: ServiceStatus = ServiceStatus.UNKNOWN
    last_check: float = 0.0
    last_success: float = 0.0
    failure_count: int = 0
    metadata: dict = field(default_factory=dict)


class ServiceRegistry:
    """
    Thread-safe service registry with health checking.

    Features:
    - Register/deregister services
    - Periodic health checks
    - Auto-discovery for LAN services
    - Service URL resolution
    """

    def __init__(self, health_check_interval: float = 60.0):
        self._services: dict[str, ServiceInfo] = {}
        self._lock = threading.RLock()
        self._health_check_interval = health_check_interval
        self._monitor_thread: threading.Thread | None = None
        self._running = False

    def register(self, name: str, url: str, metadata: dict = None):
        """Register a service with the registry."""
        with self._lock:
            self._services[name] = ServiceInfo(
                name=name,
                url=url,
                metadata=metadata or {},
            )
            print(f"[SERVICE DISCOVERY] Registered: {name} -> {url}", flush=True)

    def deregister(self, name: str):
        """Remove a service from the registry."""
        with self._lock:
            if name in self._services:
                del self._services[name]
                print(f"[SERVICE DISCOVERY] Deregistered: {name}", flush=True)

    def get_service(self, name: str) -> ServiceInfo | None:
        """Get service info by name."""
        with self._lock:
            return self._services.get(name)

    def get_url(self, name: str) -> str:
        """Get the URL of a registered service."""
        with self._lock:
            svc = self._services.get(name)
            return svc.url if svc else ""

    def is_healthy(self, name: str) -> bool:
        """Check if a service is healthy."""
        with self._lock:
            svc = self._services.get(name)
            if svc is None:
                return False
            return svc.status in (ServiceStatus.UP, ServiceStatus.UNKNOWN)

    def list_services(self) -> list[dict]:
        """Return info about all registered services."""
        with self._lock:
            return [
                {
                    "name": svc.name,
                    "url": svc.url,
                    "status": svc.status.value,
                    "last_check": svc.last_check,
                    "last_success": svc.last_success,
                    "failure_count": svc.failure_count,
                    "metadata": svc.metadata,
                }
                for svc in self._services.values()
            ]

    def check_health(self, name: str) -> ServiceStatus:
        """Probe a service's health using TCP connection check."""
        with self._lock:
            svc = self._services.get(name)
            if svc is None:
                return ServiceStatus.UNKNOWN

        # Parse URL to get host and port
        from urllib.parse import urlparse
        parsed = urlparse(svc.url)
        host = parsed.hostname or "localhost"
        port = parsed.port or (443 if parsed.scheme == "https" else 80)

        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(2.0)
            result = sock.connect_ex((host, port))
            sock.close()

            with self._lock:
                svc.last_check = time.time()
                if result == 0:
                    svc.status = ServiceStatus.UP
                    svc.last_success = time.time()
                    svc.failure_count = 0
                else:
                    svc.failure_count += 1
                    svc.status = ServiceStatus.DOWN if svc.failure_count >= 3 else ServiceStatus.DEGRADED

            return svc.status

        except Exception:
            with self._lock:
                svc.last_check = time.time()
                svc.failure_count += 1
                svc.status = ServiceStatus.DOWN
            return ServiceStatus.DOWN

    def _monitor_loop(self):
        """Background thread for periodic health checks."""
        while self._running:
            with self._lock:
                service_names = list(self._services.keys())

            for name in service_names:
                if not self._running:
                    break
                try:
                    self.check_health(name)
                except Exception:
                    pass

            time.sleep(self._health_check_interval)

    def start_monitoring(self):
        """Start periodic health check monitoring."""
        if self._monitor_thread and self._monitor_thread.is_alive():
            return

        self._running = True
        self._monitor_thread = threading.Thread(
            target=self._monitor_loop,
            daemon=True,
            name="ServiceHealthMonitor",
        )
        self._monitor_thread.start()
        print("[SERVICE DISCOVERY] Health monitoring started", flush=True)

    def stop_monitoring(self):
        """Stop health check monitoring."""
        self._running = False


def auto_discover_sms_gateway() -> str:
    """
    Auto-discover SMS Gateway on the local network.

    Wraps the existing discover_gateway() from notification_service
    into the service registry pattern.
    """
    try:
        from notification_service import discover_gateway
        ip = discover_gateway(force=True)
        if ip:
            service_registry.register(
                "sms_gateway",
                f"http://{ip}:8080",
                metadata={"type": "android_sms_gate", "auto_discovered": True},
            )
            return ip
    except Exception as exc:
        print(f"[SERVICE DISCOVERY] SMS Gateway auto-discovery failed: {exc}", flush=True)
    return ""


# Global service registry instance
service_registry = ServiceRegistry(health_check_interval=60.0)
