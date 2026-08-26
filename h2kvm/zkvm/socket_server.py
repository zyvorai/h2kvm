# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# h2kvm/tui/socket_server.py
# pylint: disable=too-many-lines  # single cohesive TUI socket protocol server; splitting would fragment request dispatch
"""
Asyncio Unix domain socket server bridging the Go TUI to the Python migration backend.

Protocol: newline-delimited JSON over a Unix domain socket.
Each message is a single JSON object terminated by '\n'.

Request format:
    {"type": "<request_type>", "id": "<optional_request_id>", ...params}

Response format:
    {"type": "response", "id": "<request_id>", "status": "ok"|"error", ...data}

Event format (server-initiated, broadcast to subscribers):
    {"type": "<event_type>", ...data}
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .migration_tracker import (
    MigrationRecord,
    MigrationStatus,
    MigrationTracker,
    create_migration_id,
)
from .zkvm_config import (
    TUIConfig,
    get_default_settings,
    load_tui_settings,
    save_tui_settings,
)

if TYPE_CHECKING:
    from .migration_controller import MigrationController

# Valid topics that clients can subscribe to
VALID_TOPICS = frozenset({"migrations", "logs", "metrics"})

# Valid request types and their handler method names
REQUEST_HANDLERS = {
    "subscribe": "_handle_subscribe",
    "list_migrations": "_handle_list_migrations",
    "list_vms": "_handle_list_vms",
    "list_local_disks": "_handle_list_local_disks",
    "start_migration": "_handle_start_migration",
    "pause_migration": "_handle_pause_migration",
    "resume_migration": "_handle_resume_migration",
    "cancel_migration": "_handle_cancel_migration",
    "get_stats": "_handle_get_stats",
    "get_config": "_handle_get_config",
    "set_config": "_handle_set_config",
    "get_ai_info": "_handle_get_ai_info",
}

# Default socket directory for root
_ROOT_SOCKET_DIR = "/run/h2kvm"
# Socket filename
_SOCKET_FILENAME = "zkvm.sock"


def get_default_socket_path() -> str:
    """
    Return the appropriate Unix domain socket path.

    For root (uid 0): /run/h2kvm/zkvm.sock
    For regular users: $XDG_RUNTIME_DIR/h2kvm/zkvm.sock

    If XDG_RUNTIME_DIR is not set for a non-root user, falls back to
    /tmp/h2kvm-<uid>/zkvm.sock.

    Returns:
        Absolute path to the socket file.
    """
    if os.getuid() == 0:
        return os.path.join(_ROOT_SOCKET_DIR, _SOCKET_FILENAME)

    runtime_dir = os.environ.get("XDG_RUNTIME_DIR")
    if runtime_dir:
        return os.path.join(runtime_dir, "h2kvm", _SOCKET_FILENAME)

    # Fallback for users without XDG_RUNTIME_DIR
    return os.path.join(f"/tmp/h2kvm-{os.getuid()}", _SOCKET_FILENAME)


class _ClientConnection:  # pylint: disable=too-few-public-methods  # plain __slots__ bookkeeping record, no behaviour
    """Internal bookkeeping for a single connected client."""

    __slots__ = ("client_id", "connected_at", "peer_name", "subscriptions", "writer")

    def __init__(self, client_id: str, writer: asyncio.StreamWriter) -> None:
        self.client_id = client_id
        self.writer = writer
        self.subscriptions: set[str] = set()
        self.connected_at = time.monotonic()
        self.peer_name: str | None = None


class TUISocketServer:  # pylint: disable=too-many-instance-attributes  # holds full server runtime state
    """
    Asyncio Unix domain socket server for the h2kvm TUI bridge.

    Accepts JSON requests from the Go TUI client, dispatches them to the
    MigrationTracker and MigrationController, and streams events (migration
    updates, logs, metrics) to all connected and subscribed clients.

    Multiple concurrent client connections are supported.
    """

    def __init__(
        self,
        tracker: MigrationTracker,
        controller: MigrationController,
        config: TUIConfig | None = None,
        socket_path: str | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        """
        Initialise the socket server.

        Args:
            tracker: MigrationTracker instance for querying/updating migrations.
            controller: MigrationController instance for pause/resume/cancel.
            config: Optional TUIConfig for settings management.  If ``None``,
                a default instance is created.
            socket_path: Override the socket path.  When ``None``,
                :func:`get_default_socket_path` is used.
            logger: Optional logger.  Falls back to module-level logger.
        """
        self.tracker = tracker
        self.controller = controller
        self.config = config or TUIConfig()
        self.socket_path = socket_path or get_default_socket_path()
        self.logger = logger or logging.getLogger(__name__)

        self._server: asyncio.AbstractServer | None = None
        self._clients: dict[str, _ClientConnection] = {}
        self._lock = asyncio.Lock()
        self._running = False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """
        Start listening on the Unix domain socket.

        Creates parent directories and removes a stale socket file if one
        already exists.  The server runs until :meth:`stop` is called.
        """
        socket_dir = os.path.dirname(self.socket_path)
        await asyncio.to_thread(Path(socket_dir).mkdir, mode=0o700, parents=True, exist_ok=True)

        # Remove stale socket file if present
        try:
            if await asyncio.to_thread(Path(self.socket_path).exists):
                os.unlink(self.socket_path)
        except OSError as exc:
            self.logger.exception(
                "Cannot remove stale socket at %s: %s. "
                "Delete the file manually or choose a different socket_path.",
                self.socket_path,
                exc,
            )
            raise

        self._server = await asyncio.start_unix_server(self.handle_client, path=self.socket_path)

        # Restrict socket permissions so only the owning user can connect.
        try:
            os.chmod(self.socket_path, 0o600)
        except OSError:
            self.logger.warning(
                "Could not restrict socket permissions on %s. "
                "Verify file ownership to ensure only authorised users can connect.",
                self.socket_path,
            )

        self._running = True
        self.logger.info("TUI socket server listening on %s", self.socket_path)

    async def stop(self) -> None:
        """
        Stop the server and disconnect all clients gracefully.
        """
        self._running = False

        # Close every connected client
        async with self._lock:
            for client in list(self._clients.values()):
                await self._close_client(client, reason="server shutdown")
            self._clients.clear()

        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None

        # Clean up socket file
        try:
            if await asyncio.to_thread(Path(self.socket_path).exists):
                os.unlink(self.socket_path)
        except OSError:
            pass

        self.logger.info("TUI socket server stopped")

    # ------------------------------------------------------------------
    # Client handling
    # ------------------------------------------------------------------

    async def handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        """
        Handle a single client connection.

        Reads newline-delimited JSON messages, dispatches each one through
        :meth:`handle_request`, and writes the JSON response back.
        The connection is kept open until the client disconnects or an
        unrecoverable I/O error occurs.

        Args:
            reader: Asyncio stream reader for the connection.
            writer: Asyncio stream writer for the connection.
        """
        client_id = uuid.uuid4().hex[:12]
        client = _ClientConnection(client_id, writer)

        # Try to capture peer info (useful for debugging)
        try:
            peername = writer.get_extra_info("peername")
            client.peer_name = str(peername) if peername else None
        except Exception:  # pylint: disable=broad-exception-caught  # peer-info capture is diagnostic only, must not break the connection
            pass

        async with self._lock:
            self._clients[client_id] = client

        self.logger.info(
            "Client %s connected (total clients: %d)",
            client_id,
            len(self._clients),
        )

        try:
            while self._running:
                line = await reader.readline()
                if not line:
                    # EOF -- client disconnected
                    break

                await self._process_line(client, line)

        except asyncio.CancelledError:
            self.logger.debug("Client %s handler cancelled", client_id)
        except ConnectionResetError:
            self.logger.debug("Client %s connection reset", client_id)
        except Exception:  # pylint: disable=broad-exception-caught  # one client's failure must not crash the server or other clients
            self.logger.exception("Unexpected error handling client %s", client_id)
        finally:
            async with self._lock:
                self._clients.pop(client_id, None)
            await self._close_client(client, reason="disconnected")
            self.logger.info(
                "Client %s disconnected (total clients: %d)",
                client_id,
                len(self._clients),
            )

    async def _process_line(self, client: _ClientConnection, line: bytes) -> None:
        """Parse one line of input and send back the response."""
        text = line.strip()
        if not text:
            return

        try:
            request = json.loads(text)
        except json.JSONDecodeError as exc:
            response = self._error_response(
                request_id=None,
                message=f"Invalid JSON: {exc}",
            )
            await self._send(client, response)
            return

        if not isinstance(request, dict):
            response = self._error_response(
                request_id=None,
                message="Request must be a JSON object",
            )
            await self._send(client, response)
            return

        # Attach the client_id so handlers can use it (e.g. subscribe)
        request["_client_id"] = client.client_id

        response = await self.handle_request(request)
        await self._send(client, response)

    # ------------------------------------------------------------------
    # Request dispatch
    # ------------------------------------------------------------------

    async def handle_request(self, request: dict) -> dict:
        """
        Dispatch a parsed request to the appropriate handler.

        Args:
            request: Parsed JSON request dictionary.  Must contain a ``type``
                key indicating the request type.

        Returns:
            A response dictionary ready for JSON serialisation.
        """
        request_id = request.get("id")
        request_type = request.get("type")

        if not request_type:
            return self._error_response(request_id, "Missing 'type' field in request")

        handler_name = REQUEST_HANDLERS.get(request_type)
        if handler_name is None:
            return self._error_response(
                request_id,
                f"Unknown request type: {request_type}. "
                f"Supported types: {', '.join(sorted(REQUEST_HANDLERS))}",
            )

        handler = getattr(self, handler_name)
        try:
            result = await handler(request)
            return self._ok_response(request_id, result)
        except Exception as exc:  # pylint: disable=broad-exception-caught  # any handler failure must become an error response, not crash the server
            self.logger.exception("Error handling request type '%s'", request_type)
            return self._error_response(request_id, str(exc))

    # ------------------------------------------------------------------
    # Broadcasting
    # ------------------------------------------------------------------

    async def broadcast(self, event: dict) -> None:
        """
        Send an event to all connected clients that are subscribed to the
        event's topic.

        The topic is derived from the event ``type``:
        - ``migration_update``, ``migration_complete`` -> topic ``migrations``
        - ``log`` -> topic ``logs``
        - ``metrics`` -> topic ``metrics``
        - ``error`` -> sent to *all* connected clients regardless of subscription.

        Args:
            event: Event dictionary.  Must contain a ``type`` key.
        """
        event_type = event.get("type", "")
        topic = self._topic_for_event(event_type)

        async with self._lock:
            targets = list(self._clients.values())

        dead_clients: list[str] = []
        for client in targets:
            # Errors are always delivered; other events require subscription
            if event_type != "error" and topic and topic not in client.subscriptions:
                continue
            try:
                await self._send(client, event)
            except Exception:  # pylint: disable=broad-exception-caught  # one dead client must not stop broadcast to the rest
                dead_clients.append(client.client_id)

        # Prune dead clients outside the send loop
        if dead_clients:
            async with self._lock:
                for cid in dead_clients:
                    removed = self._clients.pop(cid, None)
                    if removed:
                        await self._close_client(removed, reason="write failure")

    # ------------------------------------------------------------------
    # Request handlers
    # ------------------------------------------------------------------

    async def _handle_subscribe(self, request: dict) -> dict:
        """
        Subscribe the calling client to one or more topics.

        Request params:
            topics (list[str]): Topics to subscribe to.
                Valid values: ``migrations``, ``logs``, ``metrics``.

        Returns:
            Dictionary with the list of active subscriptions for the client.
        """
        topics = request.get("topics", [])
        if not isinstance(topics, list):
            raise TypeError("'topics' must be a list of strings")

        invalid = set(topics) - VALID_TOPICS
        if invalid:
            raise ValueError(
                f"Invalid topics: {', '.join(sorted(invalid))}. "
                f"Valid topics: {', '.join(sorted(VALID_TOPICS))}"
            )

        client_id = request.get("_client_id")
        async with self._lock:
            client = self._clients.get(client_id)
            if client is None:
                raise RuntimeError(
                    "TUI client session not found. The connection may have been dropped. "
                    "Please restart the TUI to re-establish the session."
                )
            client.subscriptions.update(topics)
            active = sorted(client.subscriptions)

        self.logger.debug("Client %s subscribed to: %s", client_id, ", ".join(active))
        return {"subscriptions": active}

    async def _handle_list_migrations(self, request: dict) -> dict:
        """
        List migration records.

        Optional request params:
            status (str): Filter by status (pending, running, paused, etc.).
            limit (int): Maximum number of records to return.

        Returns:
            Dictionary with a ``migrations`` list.
        """
        self.tracker.load()

        status_filter = request.get("status")
        limit = request.get("limit")

        records = list(self.tracker.migrations.values())

        if status_filter:
            try:
                target_status = MigrationStatus(status_filter)
                records = [r for r in records if r.status == target_status]
            except ValueError as err:
                raise ValueError(
                    f"Invalid status filter: {status_filter}. "
                    f"Valid values: {', '.join(s.value for s in MigrationStatus)}"
                ) from err

        # Sort by start_time descending (most recent first)
        records.sort(key=lambda r: r.start_time, reverse=True)

        if limit is not None:
            limit = int(limit)
            records = records[:limit]

        return {
            "migrations": [r.to_dict() for r in records],
            "total": len(self.tracker.migrations),
        }

    async def _handle_list_vms(self, request: dict) -> dict:
        """
        List VMs available for migration.

        Optional request params:
            source (str): Source type -- ``vsphere``, ``local``, ``hyperv``.
                Defaults to ``local``.
            path (str): For ``local`` source, directory to scan.
            search (str): Filter VMs by name substring (case-insensitive).

        Returns:
            Dictionary with a ``vms`` list.
        """
        source = request.get("source", "local")
        search = request.get("search", "").lower()

        if source == "local":
            scan_path = request.get("path", "/tmp/h2kvm-output")
            vms = self._scan_local_vms(scan_path)
        elif source == "vsphere":
            # vSphere listing requires an active connection which is managed
            # elsewhere.  Return a placeholder indicating the feature requires
            # configuration.
            vms = []
            self.logger.info("vSphere VM listing requested; integration pending")
        elif source == "hyperv":
            vms = []
            self.logger.info("Hyper-V VM listing requested; integration pending")
        else:
            raise ValueError(f"Unknown source type: {source}. Supported sources: local, vsphere, hyperv")

        if search:
            vms = [vm for vm in vms if search in vm.get("name", "").lower()]

        return {"vms": vms, "source": source}

    async def _handle_list_local_disks(self, request: dict) -> dict:
        """
        List local disk image files (VMDK, QCOW2, VDI, VHD, VHDX, OVA, RAW).

        Optional request params:
            path (str): Directory to scan.  Defaults to the configured
                default output directory.
            recursive (bool): Scan recursively.  Defaults to ``True``.

        Returns:
            Dictionary with a ``disks`` list.
        """
        settings = load_tui_settings(logger=self.logger)
        default_dir = settings.get("general", {}).get("default_output_dir", "/tmp/h2kvm-output")
        scan_path = request.get("path", default_dir)
        recursive = request.get("recursive", True)

        disks = self._scan_disk_files(scan_path, recursive=recursive)
        return {"disks": disks, "path": scan_path}

    async def _handle_start_migration(self, request: dict) -> dict:
        """
        Start a new migration.

        Required request params:
            vm_name (str): Name of the VM to migrate.
            source_type (str): Source type (vsphere, local, hyperv, ova).
            source_path (str): Path or identifier of the source.

        Optional request params:
            output_path (str): Destination path for converted images.
            format (str): Target format (qcow2, raw).  Defaults to config.
            metadata (dict): Arbitrary metadata to attach to the record.

        Returns:
            Dictionary with the new ``migration_id`` and record.
        """
        vm_name = request.get("vm_name")
        source_type = request.get("source_type")
        source_path = request.get("source_path")

        if not vm_name:
            raise ValueError(
                "'vm_name' is required to start a migration. Provide the name of the VM to migrate."
            )
        if not source_type:
            raise ValueError("'source_type' is required (e.g., 'vmdk', 'ova', 'ovf', 'vhd', 'raw').")
        if not source_path:
            raise ValueError(
                "'source_path' is required. Provide the path to the source disk image or OVA file."
            )

        settings = load_tui_settings(logger=self.logger)
        default_output = settings.get("general", {}).get("default_output_dir", "/tmp/h2kvm-output")
        output_path = request.get("output_path", default_output)
        metadata = request.get("metadata", {})

        migration_id = create_migration_id(vm_name)
        record = MigrationRecord(
            id=migration_id,
            vm_name=vm_name,
            source_type=source_type,
            status=MigrationStatus.PENDING,
            start_time=datetime.now().isoformat(),
            source_path=source_path,
            output_path=output_path,
            metadata=metadata,
        )

        self.tracker.add_migration(record)

        self.logger.info(
            "Migration %s created for VM '%s' (source=%s)",
            migration_id,
            vm_name,
            source_type,
        )

        # Broadcast the new migration event
        await self.broadcast(
            {
                "type": "migration_update",
                "migration_id": migration_id,
                "status": MigrationStatus.PENDING.value,
                "vm_name": vm_name,
                "progress": 0.0,
                "message": "Migration created",
            }
        )

        return {"migration_id": migration_id, "record": record.to_dict()}

    async def _handle_pause_migration(self, request: dict) -> dict:
        """
        Pause a running migration.

        Required request params:
            migration_id (str): ID of the migration to pause.

        Returns:
            Dictionary indicating success.
        """
        migration_id = request.get("migration_id")
        if not migration_id:
            raise ValueError("'migration_id' is required. Provide the ID of the migration to operate on.")

        record = self.tracker.get_migration(migration_id)
        if record is None:
            raise ValueError(f"Migration '{migration_id}' not found. It may have completed or been removed.")

        if record.status != MigrationStatus.RUNNING:
            raise ValueError(
                f"Cannot pause migration in state '{record.status.value}'. "
                "Only running migrations can be paused."
            )

        success = self.controller.pause_migration(migration_id)
        if not success:
            raise RuntimeError(
                f"Could not pause migration '{migration_id}'. "
                "The migration process may have already completed or been cancelled. "
                "Check the Migrations tab for current status."
            )

        await self.broadcast(
            {
                "type": "migration_update",
                "migration_id": migration_id,
                "status": MigrationStatus.PAUSED.value,
                "vm_name": record.vm_name,
                "progress": record.progress,
                "message": "Migration paused",
            }
        )

        return {"migration_id": migration_id, "paused": True}

    async def _handle_resume_migration(self, request: dict) -> dict:
        """
        Resume a paused migration.

        Required request params:
            migration_id (str): ID of the migration to resume.

        Returns:
            Dictionary indicating success.
        """
        migration_id = request.get("migration_id")
        if not migration_id:
            raise ValueError("'migration_id' is required. Provide the ID of the migration to operate on.")

        record = self.tracker.get_migration(migration_id)
        if record is None:
            raise ValueError(f"Migration '{migration_id}' not found. It may have completed or been removed.")

        if record.status != MigrationStatus.PAUSED:
            raise ValueError(
                f"Cannot resume migration in state '{record.status.value}'. "
                "Only paused migrations can be resumed."
            )

        success = self.controller.resume_migration(migration_id)
        if not success:
            raise RuntimeError(
                f"Could not resume migration '{migration_id}'. "
                "The migration process may have already completed or been cancelled. "
                "You may need to start a new migration."
            )

        await self.broadcast(
            {
                "type": "migration_update",
                "migration_id": migration_id,
                "status": MigrationStatus.RUNNING.value,
                "vm_name": record.vm_name,
                "progress": record.progress,
                "message": "Migration resumed",
            }
        )

        return {"migration_id": migration_id, "resumed": True}

    async def _handle_cancel_migration(self, request: dict) -> dict:
        """
        Cancel a migration.

        Required request params:
            migration_id (str): ID of the migration to cancel.

        Optional request params:
            force (bool): If ``True``, send SIGKILL instead of SIGTERM.
                Defaults to ``False``.

        Returns:
            Dictionary indicating success.
        """
        migration_id = request.get("migration_id")
        if not migration_id:
            raise ValueError("'migration_id' is required. Provide the ID of the migration to operate on.")

        record = self.tracker.get_migration(migration_id)
        if record is None:
            raise ValueError(f"Migration '{migration_id}' not found. It may have completed or been removed.")

        if not record.is_active():
            raise ValueError(
                f"Cannot cancel migration in state '{record.status.value}'. "
                "Only active migrations (pending/running/paused) can be cancelled."
            )

        force = bool(request.get("force", False))
        success = self.controller.cancel_migration(migration_id, force=force)

        if success:
            # Broadcast -- the tracker has been updated by the controller
            await self.broadcast(
                {
                    "type": "migration_update",
                    "migration_id": migration_id,
                    "status": MigrationStatus.CANCELLED.value,
                    "vm_name": record.vm_name,
                    "progress": record.progress,
                    "message": "Migration cancelled" + (" (forced)" if force else ""),
                }
            )

        return {"migration_id": migration_id, "cancelled": success, "forced": force}

    async def _handle_get_stats(self, request: dict) -> dict:  # pylint: disable=unused-argument  # fixed handler signature dispatched via REQUEST_HANDLERS
        """
        Get migration statistics.

        Returns:
            Dictionary with aggregated statistics from the tracker plus
            the number of currently connected clients.
        """
        self.tracker.load()
        stats = self.tracker.get_statistics()
        stats["connected_clients"] = len(self._clients)
        stats["active_processes"] = len(self.controller.get_active_processes())
        return stats

    async def _handle_get_config(self, request: dict) -> dict:
        """
        Get TUI configuration.

        Optional request params:
            key (str): Specific setting key (dot notation).  When omitted,
                all settings are returned.

        Returns:
            Dictionary with the settings.
        """
        settings = load_tui_settings(logger=self.logger)

        key = request.get("key")
        if key:
            value = self.config.get(key)
            # Fall back to merged settings if the config object has not
            # been loaded yet.
            if value is None:
                keys = key.split(".")
                current: Any = settings
                for k in keys:
                    if isinstance(current, dict) and k in current:
                        current = current[k]
                    else:
                        current = None
                        break
                value = current
            return {"key": key, "value": value}

        return {"settings": settings}

    async def _handle_set_config(self, request: dict) -> dict:
        """
        Update TUI configuration settings.

        Request params (at least one required):
            key (str) + value (any): Set a single key (dot notation supported).
            settings (dict): Merge a dictionary of settings.

        Returns:
            Dictionary confirming the update.
        """
        key = request.get("key")
        value = request.get("value")
        settings_update = request.get("settings")

        if key is not None and value is not None:
            self.config.load()
            # Ensure we have defaults merged in
            defaults = get_default_settings()
            merged = TUIConfig(logger=self.logger)
            merged.settings = defaults
            merged.update(self.config.get_all())
            merged.set(key, value)
            success = save_tui_settings(merged.get_all(), logger=self.logger)
            if not success:
                raise RuntimeError(
                    "Failed to save configuration. Check that ~/.config/h2kvm/ exists and is writable."
                )
            return {"updated_key": key, "value": value}

        if settings_update and isinstance(settings_update, dict):
            self.config.load()
            defaults = get_default_settings()
            merged = TUIConfig(logger=self.logger)
            merged.settings = defaults
            merged.update(self.config.get_all())
            merged.update(settings_update)
            success = save_tui_settings(merged.get_all(), logger=self.logger)
            if not success:
                raise RuntimeError(
                    "Failed to save configuration. Check that ~/.config/h2kvm/ exists and is writable."
                )
            return {"updated_keys": list(settings_update.keys())}

        raise ValueError("Provide either 'key'+'value' or a 'settings' dict to update")

    async def _handle_get_ai_info(self, request: dict) -> dict:  # pylint: disable=unused-argument  # fixed handler signature dispatched via REQUEST_HANDLERS
        """
        Get AI module status and information.

        Returns:
            Dictionary describing available AI capabilities and their status.
        """
        ai_info: dict[str, Any] = {
            "available": False,
            "modules": {},
            "message": "AI modules not loaded",
        }

        # Probe for optional AI integration modules
        # pylint: disable=import-outside-toplevel  # optional dependency, probed lazily
        try:
            from h2kvm.ai import get_ai_status  # type: ignore[import-untyped]

            ai_info = get_ai_status()
            ai_info["available"] = True
        except ImportError:
            ai_info["message"] = "AI module not installed.  Install with: pip install 'h2kvm[ai]'"
        except Exception as exc:  # pylint: disable=broad-exception-caught  # AI status probe is best-effort, must not break the request
            ai_info["message"] = f"AI module error: {exc}"

        return ai_info

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _ok_response(request_id: str | None, data: dict) -> dict:
        """Build a success response envelope."""
        response: dict[str, Any] = {
            "type": "response",
            "status": "ok",
        }
        if request_id is not None:
            response["id"] = request_id
        response.update(data)
        return response

    @staticmethod
    def _error_response(request_id: str | None, message: str) -> dict:
        """Build an error response envelope."""
        response: dict[str, Any] = {
            "type": "response",
            "status": "error",
            "error": message,
        }
        if request_id is not None:
            response["id"] = request_id
        return response

    @staticmethod
    def _topic_for_event(event_type: str) -> str | None:
        """Map an event type to a subscription topic."""
        if event_type in ("migration_update", "migration_complete"):
            return "migrations"
        if event_type == "log":
            return "logs"
        if event_type == "metrics":
            return "metrics"
        # "error" events bypass topic filtering
        return None

    async def _send(self, client: _ClientConnection, message: dict) -> None:
        """
        Send a JSON message to a single client.

        Serialises ``message`` as compact JSON followed by a newline.

        Args:
            client: Target client connection.
            message: Dictionary to serialise and send.

        Raises:
            ConnectionError: If the write fails.
        """
        try:
            payload = json.dumps(message, default=str).encode("utf-8") + b"\n"
            client.writer.write(payload)
            await client.writer.drain()
        except (ConnectionResetError, BrokenPipeError, OSError) as exc:
            self.logger.debug("Write failed for client %s: %s", client.client_id, exc)
            raise

    async def _close_client(self, client: _ClientConnection, reason: str = "") -> None:
        """Close a client writer gracefully."""
        try:
            if not client.writer.is_closing():
                client.writer.close()
                await client.writer.wait_closed()
        except Exception:  # pylint: disable=broad-exception-caught  # best-effort cleanup, client is already going away
            self.logger.debug("Error closing client %s (%s)", client.client_id, reason)

    # ------------------------------------------------------------------
    # Filesystem scanning helpers
    # ------------------------------------------------------------------

    _DISK_EXTENSIONS = frozenset({".vmdk", ".qcow2", ".vdi", ".vhd", ".vhdx", ".ova", ".raw", ".img"})

    def _scan_local_vms(self, directory: str) -> list[dict[str, Any]]:
        """
        Scan a directory for VM-related disk images and return a summary
        list suitable for the ``list_vms`` response.

        Each unique stem (filename without extension) is treated as one VM.
        """
        dir_path = Path(directory)
        if not dir_path.is_dir():
            return []

        vms_by_name: dict[str, dict[str, Any]] = {}
        try:
            for entry in dir_path.iterdir():
                if entry.suffix.lower() in self._DISK_EXTENSIONS:
                    name = entry.stem
                    if name not in vms_by_name:
                        try:
                            size_mb = entry.stat().st_size / (1024 * 1024)
                        except OSError:
                            size_mb = 0.0
                        vms_by_name[name] = {
                            "name": name,
                            "path": str(entry),
                            "format": entry.suffix.lstrip(".").lower(),
                            "size_mb": round(size_mb, 2),
                        }
        except PermissionError:
            self.logger.warning(
                "Permission denied scanning %s. Run as root or grant read access to the directory.",
                directory,
            )
        except OSError as exc:
            self.logger.warning("Error scanning %s: %s", directory, exc)

        return list(vms_by_name.values())

    def _scan_disk_files(self, directory: str, *, recursive: bool = True) -> list[dict[str, Any]]:
        """
        Scan for individual disk image files and return detailed info.
        """
        dir_path = Path(directory)
        if not dir_path.is_dir():
            return []

        disks: list[dict[str, Any]] = []
        try:
            pattern_iter = dir_path.rglob("*") if recursive else dir_path.iterdir()
            for entry in pattern_iter:
                if not entry.is_file():
                    continue
                if entry.suffix.lower() not in self._DISK_EXTENSIONS:
                    continue
                try:
                    stat = entry.stat()
                    size_mb = stat.st_size / (1024 * 1024)
                    modified = datetime.fromtimestamp(stat.st_mtime).isoformat()
                except OSError:
                    size_mb = 0.0
                    modified = ""

                disks.append(
                    {
                        "name": entry.name,
                        "path": str(entry),
                        "format": entry.suffix.lstrip(".").lower(),
                        "size_mb": round(size_mb, 2),
                        "modified": modified,
                    }
                )
        except PermissionError:
            self.logger.warning(
                "Permission denied scanning %s. Run as root or grant read access to the directory.",
                directory,
            )
        except OSError as exc:
            self.logger.warning("Error scanning %s: %s", directory, exc)

        # Sort by modification time descending
        disks.sort(key=lambda d: d.get("modified", ""), reverse=True)
        return disks
