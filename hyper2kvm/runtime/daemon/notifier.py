# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# hyper2kvm/daemon/notifier.py
"""
Notification system for daemon mode.
Sends alerts via webhook, email, or other channels.
"""

from __future__ import annotations

import smtplib
from datetime import datetime
from email.message import EmailMessage
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import logging
    from pathlib import Path

try:
    import requests

    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False


class DaemonNotifier:
    """
    Sends notifications for daemon events.

    Supports:
    - Webhook (Slack, Discord, generic HTTP POST)
    - Email (SMTP)
    """

    def __init__(self, logger: logging.Logger, config: dict[str, Any]):
        self.logger = logger
        self.config = config
        self.enabled = config.get("enabled", False)

        if not self.enabled:
            return

        # Notification settings
        self.on_success = config.get("on_success", False)
        self.on_failure = config.get("on_failure", True)
        self.on_stalled = config.get("on_stalled", True)

        # Webhook settings
        self.webhook_url = config.get("webhook_url")
        self.webhook_type = config.get("webhook_type", "generic")  # 'slack', 'discord', 'generic'

        # Email settings
        self.email_enabled = config.get("email_enabled", False)
        self.email_smtp_host = config.get("email_smtp_host")
        self.email_smtp_port = config.get("email_smtp_port", 587)
        self.email_from = config.get("email_from")
        self.email_to = config.get("email_to")
        self.email_username = config.get("email_username")
        self.email_password = config.get("email_password")

        if self.enabled:
            self.logger.info("🔔 Notifications enabled")
            if self.webhook_url:
                self.logger.info(f"  Webhook: {self.webhook_type}")
            if self.email_enabled:
                self.logger.info(f"  Email: {self.email_from} → {self.email_to}")

    def notify_success(self, filename: str, duration_seconds: float, output_path: Path) -> None:
        """Notify successful conversion."""
        if not self.enabled or not self.on_success:
            return

        message = {
            "event": "conversion_success",
            "filename": filename,
            "duration_seconds": duration_seconds,
            "output_path": str(output_path),
            "timestamp": datetime.now().isoformat(),
        }

        self._send_notification(
            title="✅ Conversion Successful",
            message=f"Successfully converted {filename} in {duration_seconds:.1f}s",
            details=message,
            level="success",
        )

    def notify_failure(self, filename: str, error: str, retry_count: int = 0) -> None:
        """Notify failed conversion."""
        if not self.enabled or not self.on_failure:
            return

        message = {
            "event": "conversion_failure",
            "filename": filename,
            "error": error,
            "retry_count": retry_count,
            "timestamp": datetime.now().isoformat(),
        }

        self._send_notification(
            title="❌ Conversion Failed",
            message=f"Failed to convert {filename}: {error}",
            details=message,
            level="error",
        )

    def notify_stalled(self, queue_depth: int, last_activity: datetime) -> None:
        """Notify when daemon is stalled (no activity)."""
        if not self.enabled or not self.on_stalled:
            return

        idle_minutes = (datetime.now() - last_activity).total_seconds() / 60

        message = {
            "event": "daemon_stalled",
            "queue_depth": queue_depth,
            "idle_minutes": idle_minutes,
            "last_activity": last_activity.isoformat(),
            "timestamp": datetime.now().isoformat(),
        }

        self._send_notification(
            title="⚠️ Daemon Stalled",
            message=f"Daemon idle for {idle_minutes:.0f} minutes with {queue_depth} items in queue",
            details=message,
            level="warning",
        )

    def _send_notification(self, title: str, message: str, details: dict, level: str) -> None:
        """Send notification via configured channels."""
        # Send webhook
        if self.webhook_url:
            self._send_webhook(title, message, details, level)

        # Send email
        if self.email_enabled:
            self._send_email(title, message, details, level)

    def _send_webhook(self, title: str, message: str, details: dict, level: str) -> None:
        """Send webhook notification."""
        if not REQUESTS_AVAILABLE:
            self.logger.warning("requests library not available, skipping webhook")
            return

        try:
            if self.webhook_type == "slack":
                payload = self._format_slack(title, message, details, level)
            elif self.webhook_type == "discord":
                payload = self._format_discord(title, message, details, level)
            else:
                payload = self._format_generic(title, message, details, level)

            response = requests.post(
                self.webhook_url, json=payload, timeout=10, headers={"Content-Type": "application/json"}
            )
            response.raise_for_status()
            self.logger.debug(f"Webhook sent: {title}")

        except Exception as e:
            self.logger.exception(f"Failed to send webhook: {e}")

    def _format_slack(self, title: str, message: str, details: dict, level: str) -> dict:
        """Format notification for Slack."""
        color_map = {
            "success": "#36a64f",
            "warning": "#ff9900",
            "error": "#ff0000",
        }

        return {
            "attachments": [
                {
                    "color": color_map.get(level, "#808080"),
                    "title": title,
                    "text": message,
                    "fields": [
                        {"title": k, "value": str(v), "short": True}
                        for k, v in details.items()
                        if k not in ("event", "timestamp")
                    ],
                    "footer": "hyper2kvm daemon",
                    "ts": int(datetime.now().timestamp()),
                }
            ]
        }

    def _format_discord(self, title: str, message: str, details: dict, level: str) -> dict:
        """Format notification for Discord."""
        color_map = {
            "success": 3066993,  # Green
            "warning": 16776960,  # Yellow
            "error": 15158332,  # Red
        }

        fields = [
            {"name": k, "value": str(v), "inline": True}
            for k, v in details.items()
            if k not in ("event", "timestamp")
        ]

        return {
            "embeds": [
                {
                    "title": title,
                    "description": message,
                    "color": color_map.get(level, 8421504),
                    "fields": fields,
                    "footer": {"text": "hyper2kvm daemon"},
                    "timestamp": datetime.now().isoformat(),
                }
            ]
        }

    def _format_generic(self, title: str, message: str, details: dict, level: str) -> dict:
        """Format generic webhook payload."""
        return {
            "title": title,
            "message": message,
            "level": level,
            "details": details,
            "source": "hyper2kvm-daemon",
            "timestamp": datetime.now().isoformat(),
        }

    def _send_email(self, title: str, message: str, details: dict, level: str) -> None:
        """Send email notification."""
        if not all([self.email_smtp_host, self.email_from, self.email_to]):
            self.logger.warning("Email not configured properly, skipping")
            return

        try:
            msg = EmailMessage()
            msg["Subject"] = f"[hyper2kvm] {title}"
            msg["From"] = self.email_from
            msg["To"] = self.email_to

            # Format email body
            body = f"{message}\n\n"
            body += "Details:\n"
            body += "=" * 60 + "\n"
            for k, v in details.items():
                body += f"{k}: {v}\n"
            body += "=" * 60 + "\n"

            msg.set_content(body)

            # Send email
            with smtplib.SMTP(self.email_smtp_host, self.email_smtp_port) as server:
                server.starttls()
                if self.email_username and self.email_password:
                    server.login(self.email_username, self.email_password)
                server.send_message(msg)

            self.logger.debug(f"Email sent: {title}")

        except Exception as e:
            self.logger.exception(f"Failed to send email: {e}")
