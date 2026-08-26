# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""vsock agent for host-guest communication without network."""

import socket
import struct


class VsockClient:
    """
    vsock client for host-side communication.

    Allows host to communicate with VM guest over vsock
    without requiring network connectivity.

    Example:
        >>> client = VsockClient(cid=3, port=9000)
        >>> response = client.send(b"health-check")
        >>> print(response)
    """

    def __init__(self, cid: int, port: int):
        """
        Initialize vsock client.

        Args:
            cid: VM context ID (from vmspawn --vsock)
            port: Port number to connect to
        """
        self.cid = cid
        self.port = port

    def send(self, message: bytes, timeout: int = 30) -> bytes:
        """
        Send message to VM via vsock.

        Args:
            message: Message bytes
            timeout: Socket timeout in seconds

        Returns:
            Response bytes
        """
        try:
            # AF_VSOCK is Linux-only stdlib; this module targets Linux hosts
            sock = socket.socket(socket.AF_VSOCK, socket.SOCK_STREAM)  # pylint: disable=no-member
            sock.settimeout(timeout)

            sock.connect((self.cid, self.port))

            # Send message length + message
            msg_len = struct.pack("!I", len(message))
            sock.sendall(msg_len + message)

            # Receive response length
            resp_len_bytes = sock.recv(4)
            if not resp_len_bytes:
                return b""

            resp_len = struct.unpack("!I", resp_len_bytes)[0]

            # Receive response
            response = b""
            while len(response) < resp_len:
                chunk = sock.recv(min(resp_len - len(response), 4096))
                if not chunk:
                    break
                response += chunk

            sock.close()

            return response

        except Exception as e:
            raise RuntimeError(
                f"Failed to communicate with VM via vsock (CID={self.cid}, port={self.port}). "
                f"Ensure the VM is running and vsock is enabled. Detail: {e}"
            ) from e

    def health_check(self) -> bool:
        """
        Simple health check via vsock.

        Returns:
            True if VM responds
        """
        try:
            response = self.send(b"PING", timeout=5)
            return response == b"PONG"
        except Exception:  # pylint: disable=broad-exception-caught  # health check must degrade to False, never raise
            return False


class VsockServer:  # pylint: disable=too-few-public-methods  # single-purpose guest-side listener, handle() is its only operation
    """
    vsock server for guest-side communication.

    Run this inside the VM to handle host requests.

    Example (inside VM):
        >>> server = VsockServer(port=9000)
        >>> server.handle(lambda msg: b"PONG" if msg == b"PING" else b"OK")
    """

    def __init__(self, port: int):
        """
        Initialize vsock server.

        Args:
            port: Port to listen on
        """
        self.port = port

    def handle(self, handler_func, max_connections: int = 100):
        """
        Handle incoming vsock connections.

        Args:
            handler_func: Function that takes message bytes and returns response bytes
            max_connections: Maximum number of connections to handle
        """
        # AF_VSOCK / VMADDR_CID_ANY are Linux-only stdlib; this module targets Linux hosts
        sock = socket.socket(socket.AF_VSOCK, socket.SOCK_STREAM)  # pylint: disable=no-member
        sock.bind((socket.VMADDR_CID_ANY, self.port))  # pylint: disable=no-member
        sock.listen(max_connections)

        print(f"vsock server listening on port {self.port}")

        while True:
            conn, _addr = sock.accept()

            try:
                # Receive message length
                msg_len_bytes = conn.recv(4)
                if not msg_len_bytes:
                    continue

                msg_len = struct.unpack("!I", msg_len_bytes)[0]

                # Receive message
                message = b""
                while len(message) < msg_len:
                    chunk = conn.recv(min(msg_len - len(message), 4096))
                    if not chunk:
                        break
                    message += chunk

                # Process message
                response = handler_func(message)

                # Send response length + response
                resp_len = struct.pack("!I", len(response))
                conn.sendall(resp_len + response)

            except Exception as e:  # pylint: disable=broad-exception-caught  # one bad connection must not crash the accept loop
                print(f"Error handling connection: {e}")

            finally:
                conn.close()
