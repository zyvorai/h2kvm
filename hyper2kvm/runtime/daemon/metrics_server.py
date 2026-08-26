# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# hyper2kvm/daemon/metrics_server.py
"""
Prometheus metrics HTTP server.

Exposes metrics on HTTP endpoint for Prometheus scraping.
Uses stdlib http.server - no optional dependencies needed!
"""

from __future__ import annotations

import logging
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

from ...core.metrics import PROMETHEUS_AVAILABLE, get_metrics

logger = logging.getLogger(__name__)

# Content type for Prometheus metrics
CONTENT_TYPE_LATEST = "text/plain; version=0.0.4; charset=utf-8"


class MetricsHandler(BaseHTTPRequestHandler):
    """HTTP handler for Prometheus metrics endpoint."""

    def do_GET(self):
        """Handle GET requests."""
        if self.path == "/metrics":
            self._serve_metrics()
        elif self.path == "/health":
            self._serve_health()
        elif self.path == "/":
            self._serve_index()
        else:
            self.send_error(404, "Not Found")

    def _serve_metrics(self):
        """Serve Prometheus metrics."""
        try:
            metrics = get_metrics()

            self.send_response(200)
            self.send_header("Content-Type", CONTENT_TYPE_LATEST)
            self.send_header("Content-Length", str(len(metrics)))
            self.end_headers()
            self.wfile.write(metrics)

        except Exception as e:
            logger.exception(f"Error serving metrics: {e}")
            self.send_error(500, "Internal Server Error")

    def _serve_health(self):
        """Serve health check endpoint."""
        health_status = "OK" if PROMETHEUS_AVAILABLE else "Metrics Disabled"

        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(health_status.encode("utf-8"))

    def _serve_index(self):
        """Serve index page with links."""
        html = """
<!DOCTYPE html>
<html>
<head>
    <title>hyper2kvm Metrics</title>
    <style>
        body {{ font-family: sans-serif; margin: 40px; }}
        h1 {{ color: #333; }}
        .links {{ margin-top: 20px; }}
        .links a {{ display: block; margin: 10px 0; color: #0366d6; }}
        .status {{ margin: 20px 0; padding: 10px; background: #f6f8fa; border-radius: 3px; }}
    </style>
</head>
<body>
    <h1>hyper2kvm Metrics Server</h1>
    <div class="status">
        <strong>Status:</strong> Running<br>
        <strong>Metrics:</strong> {}
    </div>
    <div class="links">
        <h2>Endpoints:</h2>
        <a href="/metrics">/metrics</a> - Prometheus metrics (text format)
        <a href="/health">/health</a> - Health check
    </div>
</body>
</html>
        """.format("Enabled" if PROMETHEUS_AVAILABLE else "Disabled (prometheus_client not installed)")

        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(html.encode("utf-8"))

    def log_message(self, format, *args):
        """Override to use our logger."""
        logger.debug(f"{self.client_address[0]} - {format % args}")


class MetricsServer:
    """
    Prometheus metrics HTTP server.

    Runs in background thread and exposes metrics on HTTP endpoint.
    """

    def __init__(self, port: int = 9090, host: str = "0.0.0.0"):
        """
        Initialize metrics server.

        Args:
            port: Port to listen on (default: 9090)
            host: Host to bind to (default: 0.0.0.0 - all interfaces)
        """
        self.port = port
        self.host = host
        self.server: HTTPServer | None = None
        self.thread: threading.Thread | None = None
        self._running = False

    def start(self):
        """Start the metrics server in background thread."""
        if self._running:
            logger.warning("Metrics server already running")
            return

        try:
            self.server = HTTPServer((self.host, self.port), MetricsHandler)
            self._running = True

            # Start in background thread
            self.thread = threading.Thread(target=self._serve_forever, daemon=True)
            self.thread.start()

            logger.info(f"Metrics server started on http://{self.host}:{self.port}/metrics")

            if not PROMETHEUS_AVAILABLE:
                logger.warning(
                    "Prometheus client not available - metrics will be disabled. "
                    "Install with: pip install prometheus-client"
                )

        except OSError as e:
            logger.exception(f"Failed to start metrics server on port {self.port}: {e}")
            raise

    def _serve_forever(self):
        """Serve requests forever (runs in thread)."""
        if self.server:
            self.server.serve_forever()

    def stop(self):
        """Stop the metrics server."""
        if not self._running:
            return

        logger.info("Stopping metrics server")

        if self.server:
            self.server.shutdown()
            self.server.server_close()

        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=5)

        self._running = False
        logger.info("Metrics server stopped")

    def is_running(self) -> bool:
        """Check if server is running."""
        return self._running


# Global server instance (singleton)
_metrics_server: MetricsServer | None = None


def start_metrics_server(port: int = 9090, host: str = "0.0.0.0") -> MetricsServer:
    """
    Start global metrics server.

    Args:
        port: Port to listen on (default: 9090)
        host: Host to bind to (default: 0.0.0.0)

    Returns:
        MetricsServer instance

    Example:
        >>> from .metrics_server import start_metrics_server
        >>> server = start_metrics_server(port=9090)
        >>> # Server runs in background
        >>> # Metrics available at http://localhost:9090/metrics
    """
    global _metrics_server

    if _metrics_server is not None and _metrics_server.is_running():
        logger.warning("Metrics server already running")
        return _metrics_server

    _metrics_server = MetricsServer(port=port, host=host)
    _metrics_server.start()

    return _metrics_server


def stop_metrics_server():
    """Stop global metrics server."""
    global _metrics_server

    if _metrics_server:
        _metrics_server.stop()
        _metrics_server = None


def get_metrics_server() -> MetricsServer | None:
    """Get global metrics server instance."""
    return _metrics_server
