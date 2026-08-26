# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""
Systemd Socket Activation Integration
======================================

Unix domain socket server for on-demand VM repair operations.
Enables socket-activated service for efficient resource usage.
"""

import json
import logging
import socket
import struct
import threading
import time
from dataclasses import asdict, dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Optional

try:
    import systemd.daemon

    SYSTEMD_AVAILABLE = True
except ImportError:
    SYSTEMD_AVAILABLE = False


class RequestType(Enum):
    """Types of repair requests"""

    REPAIR_VM = "repair_vm"
    STATUS = "status"
    LIST_VMS = "list_vms"
    CANCEL = "cancel"
    HEALTH_CHECK = "health_check"


class ResponseStatus(Enum):
    """Response status codes"""

    SUCCESS = "success"
    ERROR = "error"
    IN_PROGRESS = "in_progress"
    NOT_FOUND = "not_found"


@dataclass
class RepairRequest:
    """Repair operation request"""

    request_type: str
    vm_image_path: Optional[str] = None
    output_dir: Optional[str] = None
    options: Optional[dict[str, Any]] = None
    request_id: Optional[str] = None

    def to_dict(self) -> dict:
        """Convert to dictionary"""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "RepairRequest":
        """Create from dictionary"""
        return cls(**data)


@dataclass
class RepairResponse:
    """Repair operation response"""

    status: str
    message: str
    request_id: Optional[str] = None
    data: Optional[dict[str, Any]] = None
    error: Optional[str] = None

    def to_dict(self) -> dict:
        """Convert to dictionary"""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "RepairResponse":
        """Create from dictionary"""
        return cls(**data)


class RepairSocketServer:
    """Unix domain socket server for VM repair requests"""

    def __init__(self, socket_path: str = "/run/hyper2kvm/repair.sock", handler: Optional[Callable] = None):
        """
        Args:
            socket_path: Path to Unix domain socket
            handler: Optional request handler function
        """
        self.socket_path = Path(socket_path)
        self.handler = handler or self._default_handler
        self.logger = logging.getLogger(__name__)
        self.server_socket = None
        self.running = False
        self.server_thread = None
        self.active_requests: dict[str, dict] = {}

    def start(self):
        """Start the socket server"""
        # Clean up old socket if it exists
        if self.socket_path.exists():
            try:
                self.socket_path.unlink()
            except Exception as e:
                self.logger.exception(f"Failed to remove old socket: {e}")

        # Create directory if needed
        self.socket_path.parent.mkdir(parents=True, exist_ok=True)

        # Check if socket was passed by systemd
        if SYSTEMD_AVAILABLE:
            fds = systemd.daemon.listen_fds()
            if fds > 0:
                self.logger.info("Using socket passed by systemd")
                self.server_socket = socket.fromfd(
                    systemd.daemon.LISTEN_FDS_START, socket.AF_UNIX, socket.SOCK_STREAM
                )
                self._run_server()
                return

        # Create socket manually
        try:
            self.server_socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            self.server_socket.bind(str(self.socket_path))
            self.socket_path.chmod(0o666)  # Allow all users to connect
            self.server_socket.listen(5)

            self.logger.info(f"Socket server listening on {self.socket_path}")

            # Notify systemd we're ready
            if SYSTEMD_AVAILABLE:
                systemd.daemon.notify("READY=1")

            self._run_server()

        except Exception as e:
            self.logger.exception(f"Failed to start socket server: {e}")
            raise

    def start_background(self):
        """Start socket server in background thread"""
        self.server_thread = threading.Thread(target=self.start, daemon=True)
        self.server_thread.start()
        self.logger.info("Socket server started in background")

    def _run_server(self):
        """Main server loop"""
        self.running = True

        while self.running:
            try:
                client_socket, _ = self.server_socket.accept()
                # Handle each connection in a separate thread
                client_thread = threading.Thread(
                    target=self._handle_client, args=(client_socket,), daemon=True
                )
                client_thread.start()

            except Exception as e:
                if self.running:
                    self.logger.exception(f"Error accepting connection: {e}")

    def _handle_client(self, client_socket: socket.socket):
        """Handle individual client connection"""
        try:
            # Receive message length (4 bytes)
            length_data = self._recv_exact(client_socket, 4)
            if not length_data:
                return

            msg_length = struct.unpack("!I", length_data)[0]

            # Receive message
            msg_data = self._recv_exact(client_socket, msg_length)
            if not msg_data:
                return

            # Parse request
            request_dict = json.loads(msg_data.decode("utf-8"))
            request = RepairRequest.from_dict(request_dict)

            self.logger.info(f"Received request: {request.request_type}")

            # Process request
            response = self.handler(request)

            # Send response
            self._send_response(client_socket, response)

        except Exception as e:
            self.logger.exception(f"Error handling client: {e}")
            error_response = RepairResponse(
                status=ResponseStatus.ERROR.value, message="Internal server error", error=str(e)
            )
            try:
                self._send_response(client_socket, error_response)
            except Exception:
                # Ignore errors during error response - connection may be closed
                pass

        finally:
            client_socket.close()

    def _recv_exact(self, sock: socket.socket, length: int) -> Optional[bytes]:
        """Receive exact number of bytes from socket"""
        data = b""
        while len(data) < length:
            chunk = sock.recv(length - len(data))
            if not chunk:
                return None
            data += chunk
        return data

    def _send_response(self, sock: socket.socket, response: RepairResponse):
        """Send response to client"""
        response_data = json.dumps(response.to_dict()).encode("utf-8")
        length = struct.pack("!I", len(response_data))
        sock.sendall(length + response_data)

    def _default_handler(self, request: RepairRequest) -> RepairResponse:
        """Default request handler"""
        try:
            if request.request_type == RequestType.REPAIR_VM.value:
                return self._handle_repair_vm(request)
            if request.request_type == RequestType.STATUS.value:
                return self._handle_status(request)
            if request.request_type == RequestType.LIST_VMS.value:
                return self._handle_list_vms(request)
            if request.request_type == RequestType.HEALTH_CHECK.value:
                return self._handle_health_check(request)
            return RepairResponse(
                status=ResponseStatus.ERROR.value,
                message=f"Unknown request type: {request.request_type}",
            )

        except Exception as e:
            self.logger.exception(f"Error handling request: {e}")
            return RepairResponse(
                status=ResponseStatus.ERROR.value, message="Request handler failed", error=str(e)
            )

    def _handle_repair_vm(self, request: RepairRequest) -> RepairResponse:
        """Handle VM repair request"""
        if not request.vm_image_path:
            return RepairResponse(status=ResponseStatus.ERROR.value, message="vm_image_path is required")

        # This would integrate with actual repair logic
        # For now, return a mock response
        self.logger.info(f"Repair request for VM: {request.vm_image_path}")

        # Store active request
        if request.request_id:
            self.active_requests[request.request_id] = {
                "vm_image_path": request.vm_image_path,
                "status": "in_progress",
                "started_at": time.time(),
            }

        return RepairResponse(
            status=ResponseStatus.SUCCESS.value,
            message="Repair operation started",
            request_id=request.request_id,
            data={
                "vm_image_path": request.vm_image_path,
                "output_dir": request.output_dir or "/var/lib/libvirt/images",
            },
        )

    def _handle_status(self, request: RepairRequest) -> RepairResponse:
        """Handle status request"""
        if not request.request_id:
            return RepairResponse(status=ResponseStatus.ERROR.value, message="request_id is required")

        if request.request_id in self.active_requests:
            req_info = self.active_requests[request.request_id]
            return RepairResponse(
                status=ResponseStatus.SUCCESS.value,
                message="Request found",
                request_id=request.request_id,
                data=req_info,
            )
        return RepairResponse(
            status=ResponseStatus.NOT_FOUND.value,
            message="Request not found",
            request_id=request.request_id,
        )

    def _handle_list_vms(self, request: RepairRequest) -> RepairResponse:
        """Handle list VMs request"""
        # This would integrate with actual VM discovery
        return RepairResponse(
            status=ResponseStatus.SUCCESS.value,
            message="Active requests listed",
            data={"active_requests": list(self.active_requests.keys()), "count": len(self.active_requests)},
        )

    def _handle_health_check(self, request: RepairRequest) -> RepairResponse:
        """Handle health check request"""
        return RepairResponse(
            status=ResponseStatus.SUCCESS.value,
            message="Server is healthy",
            data={
                "active_requests": len(self.active_requests),
                "uptime": "unknown",  # Could track actual uptime
            },
        )

    def stop(self):
        """Stop the socket server"""
        self.running = False

        if self.server_socket:
            try:
                self.server_socket.close()
            except OSError:
                # Socket may already be closed
                pass

        # Clean up socket file
        if self.socket_path.exists():
            try:
                self.socket_path.unlink()
            except OSError:
                # Socket file may already be removed
                pass

        # Notify systemd we're stopping
        if SYSTEMD_AVAILABLE:
            systemd.daemon.notify("STOPPING=1")

        self.logger.info("Socket server stopped")


class RepairSocketClient:
    """Client for communicating with repair socket server"""

    def __init__(self, socket_path: str = "/run/hyper2kvm/repair.sock"):
        """
        Args:
            socket_path: Path to Unix domain socket
        """
        self.socket_path = Path(socket_path)
        self.logger = logging.getLogger(__name__)

    def send_request(self, request: RepairRequest, timeout: float = 30.0) -> RepairResponse:
        """Send request to server and wait for response

        Args:
            request: Request to send
            timeout: Timeout in seconds

        Returns:
            Response from server

        Raises:
            ConnectionError: If unable to connect
            TimeoutError: If request times out
        """
        if not self.socket_path.exists():
            raise ConnectionError(f"Socket not found: {self.socket_path}")

        client_socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        client_socket.settimeout(timeout)

        try:
            # Connect
            client_socket.connect(str(self.socket_path))

            # Send request
            request_data = json.dumps(request.to_dict()).encode("utf-8")
            length = struct.pack("!I", len(request_data))
            client_socket.sendall(length + request_data)

            # Receive response length
            length_data = self._recv_exact(client_socket, 4)
            if not length_data:
                raise ConnectionError("Connection closed by server")

            msg_length = struct.unpack("!I", length_data)[0]

            # Receive response
            response_data = self._recv_exact(client_socket, msg_length)
            if not response_data:
                raise ConnectionError("Connection closed by server")

            # Parse response
            response_dict = json.loads(response_data.decode("utf-8"))
            return RepairResponse.from_dict(response_dict)

        finally:
            client_socket.close()

    def _recv_exact(self, sock: socket.socket, length: int) -> Optional[bytes]:
        """Receive exact number of bytes from socket"""
        data = b""
        while len(data) < length:
            chunk = sock.recv(length - len(data))
            if not chunk:
                return None
            data += chunk
        return data

    def repair_vm(
        self,
        vm_image_path: str,
        output_dir: Optional[str] = None,
        options: Optional[dict] = None,
        request_id: Optional[str] = None,
    ) -> RepairResponse:
        """Request VM repair operation

        Args:
            vm_image_path: Path to VM disk image
            output_dir: Output directory for repaired image
            options: Additional repair options
            request_id: Optional request ID for tracking

        Returns:
            RepairResponse
        """
        request = RepairRequest(
            request_type=RequestType.REPAIR_VM.value,
            vm_image_path=vm_image_path,
            output_dir=output_dir,
            options=options or {},
            request_id=request_id,
        )
        return self.send_request(request)

    def get_status(self, request_id: str) -> RepairResponse:
        """Get status of a repair request

        Args:
            request_id: Request ID to query

        Returns:
            RepairResponse with status
        """
        request = RepairRequest(request_type=RequestType.STATUS.value, request_id=request_id)
        return self.send_request(request)

    def list_vms(self) -> RepairResponse:
        """List active repair requests

        Returns:
            RepairResponse with list of active requests
        """
        request = RepairRequest(request_type=RequestType.LIST_VMS.value)
        return self.send_request(request)

    def health_check(self) -> RepairResponse:
        """Check server health

        Returns:
            RepairResponse with health status
        """
        request = RepairRequest(request_type=RequestType.HEALTH_CHECK.value)
        return self.send_request(request)


def start_socket_server_daemon(
    socket_path: str = "/run/hyper2kvm/repair.sock", handler: Optional[Callable] = None
):
    """Start socket server as a daemon service

    This function is designed to be called from a systemd service.

    Args:
        socket_path: Path to Unix domain socket
        handler: Optional custom request handler
    """
    import signal
    import sys

    logger = logging.getLogger(__name__)

    # Setup logging
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")

    server = RepairSocketServer(socket_path, handler)

    # Setup signal handlers for graceful shutdown
    def signal_handler(signum, frame):
        logger.info(f"Received signal {signum}, shutting down...")
        server.stop()
        sys.exit(0)

    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    # Start server
    try:
        logger.info("Starting repair socket server daemon")
        server.start()
    except Exception as e:
        logger.exception(f"Server failed: {e}")
        sys.exit(1)
