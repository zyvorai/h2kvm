# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""
System configuration tools integration for VMCraft.

Provides timedatectl, hostnamectl, and localectl integration.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    import logging


class SystemConfigManager:
    """
    Manage system configuration via systemd tools.

    Every query method below is best-effort: it runs one systemd CLI tool
    (timedatectl/hostnamectl/localectl) and returns an empty/default result
    on any failure rather than raising, so callers can probe several tools
    without one missing/failing tool aborting the whole inspection.
    """

    def __init__(self, command_runner: Callable[[list[str]], str], logger: logging.Logger):
        """
        Initialize SystemConfigManager.

        Args:
            command_runner: Function to execute commands in guest
            logger: Logger instance
        """
        self.command = command_runner
        self.logger = logger

    # ==================== timedatectl ====================

    def timedatectl_status(self) -> dict[str, str]:
        """
        Get time and date settings.

        Returns:
            Dict with time/date configuration
            Keys: local_time, universal_time, rtc_time, timezone,
                  ntp_enabled, ntp_synchronized, rtc_in_local_tz

        Example:
            status = manager.timedatectl_status()
            print(f"Timezone: {status['timezone']}")
            print(f"NTP synchronized: {status['ntp_synchronized']}")
        """
        try:
            result = self.command(["timedatectl", "status"])

            status = {}
            for line in result.splitlines():
                line = line.strip()
                if ":" in line:
                    key, value = line.split(":", 1)
                    key = key.strip().lower().replace(" ", "_").replace("-", "_")
                    value = value.strip()
                    status[key] = value

            return status

        except Exception as e:  # pylint: disable=broad-exception-caught
            self.logger.debug(f"timedatectl status failed: {e}")
            return {}

    def timedatectl_list_timezones(self) -> list[str]:
        """
        List available timezones.

        Returns:
            List of timezone names

        Example:
            tzones = manager.timedatectl_list_timezones()
            if "America/New_York" in tzones:
                print("New York timezone available")
        """
        try:
            result = self.command(["timedatectl", "list-timezones"])

            timezones = []
            for line in result.splitlines():
                line = line.strip()
                if line:
                    timezones.append(line)

            return timezones

        except Exception as e:  # pylint: disable=broad-exception-caught
            self.logger.debug(f"timedatectl list-timezones failed: {e}")
            return []

    def timedatectl_show(self) -> dict[str, str]:
        """
        Show time/date properties in machine-readable format.

        Returns:
            Dict with all timedatectl properties

        Example:
            props = manager.timedatectl_show()
            print(f"Timezone: {props.get('Timezone')}")
            print(f"NTP: {props.get('NTP')}")
        """
        # pylint: disable=duplicate-code
        # reason: mirrors the equivalent "key=value" output-parsing loop in
        # vmcraft/systemd/systemctl.py (show_unit_properties) --
        # structurally similar by coincidence, not shared logic; keeping
        # independent avoids coupling unrelated systemd-output parsing.
        try:
            result = self.command(["timedatectl", "show"])

            properties = {}
            for line in result.splitlines():
                line = line.strip()
                if "=" in line:
                    key, value = line.split("=", 1)
                    properties[key] = value

            return properties

        except Exception as e:  # pylint: disable=broad-exception-caught
            self.logger.debug(f"timedatectl show failed: {e}")
            return {}

    # ==================== hostnamectl ====================

    def hostnamectl_status(self) -> dict[str, str]:
        """
        Get hostname and system information.

        Returns:
            Dict with hostname configuration
            Keys: static_hostname, pretty_hostname, icon_name, chassis,
                  machine_id, boot_id, operating_system, kernel, architecture

        Example:
            status = manager.hostnamectl_status()
            print(f"Hostname: {status['static_hostname']}")
            print(f"OS: {status['operating_system']}")
            print(f"Kernel: {status['kernel']}")
        """
        try:
            result = self.command(["hostnamectl", "status"])

            status = {}
            for line in result.splitlines():
                line = line.strip()
                if ":" in line:
                    key, value = line.split(":", 1)
                    key = key.strip().lower().replace(" ", "_").replace("-", "_")
                    value = value.strip()
                    status[key] = value

            return status

        except Exception as e:  # pylint: disable=broad-exception-caught
            self.logger.debug(f"hostnamectl status failed: {e}")
            return {}

    def hostnamectl_hostname(self) -> str:
        """
        Get current hostname.

        Returns:
            Hostname string

        Example:
            hostname = manager.hostnamectl_hostname()
            print(f"Current hostname: {hostname}")
        """
        try:
            result = self.command(["hostnamectl", "hostname"])
            return result.strip()
        except Exception:  # pylint: disable=broad-exception-caught
            return ""

    # ==================== localectl ====================

    def localectl_status(self) -> dict[str, str]:
        """
        Get locale and keyboard configuration.

        Returns:
            Dict with locale settings
            Keys: system_locale, vc_keymap, x11_layout, x11_model, x11_variant, x11_options

        Example:
            status = manager.localectl_status()
            print(f"Locale: {status.get('system_locale')}")
            print(f"Keymap: {status.get('vc_keymap')}")
        """
        try:
            result = self.command(["localectl", "status"])

            status = {}
            for line in result.splitlines():
                line = line.strip()
                if ":" in line:
                    key, value = line.split(":", 1)
                    key = key.strip().lower().replace(" ", "_").replace("-", "_")
                    value = value.strip()
                    status[key] = value

            return status

        except Exception as e:  # pylint: disable=broad-exception-caught
            self.logger.debug(f"localectl status failed: {e}")
            return {}

    def localectl_list_locales(self) -> list[str]:
        """
        List available locales.

        Returns:
            List of locale names

        Example:
            locales = manager.localectl_list_locales()
            if "en_US.UTF-8" in locales:
                print("US English locale available")
        """
        try:
            result = self.command(["localectl", "list-locales"])

            locales = []
            for line in result.splitlines():
                line = line.strip()
                if line:
                    locales.append(line)

            return locales

        except Exception as e:  # pylint: disable=broad-exception-caught
            self.logger.debug(f"localectl list-locales failed: {e}")
            return []

    def localectl_list_keymaps(self) -> list[str]:
        """
        List available keyboard mappings.

        Returns:
            List of keymap names

        Example:
            keymaps = manager.localectl_list_keymaps()
            if "us" in keymaps:
                print("US keymap available")
        """
        try:
            result = self.command(["localectl", "list-keymaps"])

            keymaps = []
            for line in result.splitlines():
                line = line.strip()
                if line:
                    keymaps.append(line)

            return keymaps

        except Exception as e:  # pylint: disable=broad-exception-caught
            self.logger.debug(f"localectl list-keymaps failed: {e}")
            return []

    def localectl_list_x11_keymap_models(self) -> list[str]:
        """
        List available X11 keymap models.

        Returns:
            List of X11 keymap model names
        """
        try:
            result = self.command(["localectl", "list-x11-keymap-models"])

            models = []
            for line in result.splitlines():
                line = line.strip()
                if line:
                    models.append(line)

            return models

        except Exception as e:  # pylint: disable=broad-exception-caught
            self.logger.debug(f"localectl list-x11-keymap-models failed: {e}")
            return []

    def localectl_list_x11_keymap_layouts(self) -> list[str]:
        """
        List available X11 keymap layouts.

        Returns:
            List of X11 keymap layout names
        """
        try:
            result = self.command(["localectl", "list-x11-keymap-layouts"])

            layouts = []
            for line in result.splitlines():
                line = line.strip()
                if line:
                    layouts.append(line)

            return layouts

        except Exception as e:  # pylint: disable=broad-exception-caught
            self.logger.debug(f"localectl list-x11-keymap-layouts failed: {e}")
            return []

    # ==================== loginctl ====================

    def loginctl_list_sessions(self) -> list[dict[str, str]]:
        """
        List current login sessions.

        Returns:
            List of dicts with session information
            Keys: session, uid, user, seat, tty

        Example:
            sessions = manager.loginctl_list_sessions()
            for session in sessions:
                print(f"User {session['user']} on {session['tty']}")
        """
        # pylint: disable=duplicate-code
        # reason: mirrors the equivalent "for line in result.splitlines():
        # parts = line.split(None, N)" output-parsing loop in
        # vmcraft/systemd/systemctl.py (list_units) -- structurally
        # similar by coincidence, not shared logic; keeping independent
        # avoids coupling unrelated systemd-output parsing.
        try:
            result = self.command(["loginctl", "list-sessions", "--no-pager", "--no-legend"])

            sessions = []
            for line in result.splitlines():
                line = line.strip()
                if not line:
                    continue

                parts = line.split(None, 4)
                if len(parts) >= 4:
                    sessions.append(
                        {
                            "session": parts[0],
                            "uid": parts[1],
                            "user": parts[2],
                            "seat": parts[3],
                            "tty": parts[4] if len(parts) > 4 else "",
                        }
                    )

            return sessions

        except Exception as e:  # pylint: disable=broad-exception-caught
            self.logger.debug(f"loginctl list-sessions failed: {e}")
            return []

    def loginctl_list_users(self) -> list[dict[str, str]]:
        """
        List logged-in users.

        Returns:
            List of dicts with user information
            Keys: uid, user

        Example:
            users = manager.loginctl_list_users()
            print(f"{len(users)} users logged in")
        """
        # pylint: disable=duplicate-code
        # reason: mirrors similar "for line in result.splitlines(): parts =
        # line.split(None, N)" output-parsing loops in
        # vmcraft/systemd/systemctl.py (unit_files/list-unit-files) --
        # structurally similar by coincidence, not shared logic; keeping
        # independent avoids coupling unrelated systemd-output parsing.
        try:
            result = self.command(["loginctl", "list-users", "--no-pager", "--no-legend"])

            users = []
            for line in result.splitlines():
                line = line.strip()
                if not line:
                    continue

                parts = line.split(None, 1)
                if len(parts) >= 2:
                    users.append(
                        {
                            "uid": parts[0],
                            "user": parts[1],
                        }
                    )

            return users

        except Exception as e:  # pylint: disable=broad-exception-caught
            self.logger.debug(f"loginctl list-users failed: {e}")
            return []

    def loginctl_show_session(self, session: str) -> dict[str, str]:
        """
        Show properties of a login session.

        Args:
            session: Session ID

        Returns:
            Dict with session properties

        Example:
            props = manager.loginctl_show_session("1")
            print(f"User: {props.get('Name')}")
            print(f"State: {props.get('State')}")
        """
        try:
            result = self.command(["loginctl", "show-session", session])

            properties = {}
            for line in result.splitlines():
                line = line.strip()
                if "=" in line:
                    key, value = line.split("=", 1)
                    properties[key] = value

            return properties

        except Exception as e:  # pylint: disable=broad-exception-caught
            self.logger.debug(f"loginctl show-session failed for {session}: {e}")
            return {}
