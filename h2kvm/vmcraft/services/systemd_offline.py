# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""Offline systemd inspection helpers for VMCraft."""
# pylint: disable=too-many-lines
# Cohesive collection of offline systemd inspection helpers; splitting would
# fragment closely-related guest-inspection logic more than it would help.

from __future__ import annotations

import configparser
import json
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
    import logging

CommandQuietFn = Callable[[list[str]], str]
CommandRunFn = Callable[[list[str]], str]
SystemdListUnitsFn = Callable[..., list[dict[str, Any]]]
SystemdStatusFn = Callable[[str], dict[str, Any]]
SystemdDetectVirtFn = Callable[[], dict[str, str]]
SystemdMachineIdFn = Callable[[], str]
SystemdBootEntriesFn = Callable[[], list[dict[str, Any]]]


def _size_mb(path: Path) -> float:
    """Return file size in mebibytes."""
    return path.stat().st_size / (1024 * 1024)


def _size_kb(path: Path) -> float:
    """Return file size in kibibytes."""
    return path.stat().st_size / 1024


def _relpath(path: Path, mount_root: Path) -> str:
    """Return path relative to mount root with leading slash."""
    return "/" + str(path.relative_to(mount_root))


def _read_ini_section(conf_file: Path, section_name: str) -> configparser.SectionProxy | None:
    """Return parsed INI section if file and section exist."""
    if not conf_file.exists():
        return None
    parser = configparser.ConfigParser()
    parser.read(conf_file)
    if section_name in parser:
        return parser[section_name]
    return None


def _merge_ini_config(
    defaults: dict[str, Any],
    conf_file: Path,
    section_name: str,
    *,
    split_keys: set[str] | None = None,
) -> dict[str, Any]:
    """Return defaults merged with optional INI section overrides."""
    merged: dict[str, Any] = dict(defaults)
    section = _read_ini_section(conf_file, section_name)
    if section is None:
        return merged

    split_keys = split_keys or set()
    for key in defaults:
        if key not in section:
            continue
        value = section[key]
        merged[key] = value.split() if key in split_keys else value
    return merged


def _parse_key_value_lines(content: str) -> dict[str, str]:
    """Parse key/value lines split by first whitespace, lower-casing keys."""
    data: dict[str, str] = {}
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if " " in line:
            key, value = line.split(None, 1)
            data[key.lower()] = value
    return data


def _append_file_records(items: list[dict[str, str]], directory: Path, pattern: str) -> None:
    """Append simple file/path records for files matching pattern."""
    for matched_file in directory.glob(pattern):
        items.append({"file": matched_file.name, "path": str(matched_file)})


def _first_existing_path(candidates: list[Path]) -> Path | None:
    """Return the first path that exists, or None."""
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def _append_image_entries(
    items: list[dict[str, Any]],
    directory: Path,
    pattern: str,
    *,
    entry_type: str | None = None,
    include_location: bool = False,
) -> None:
    """Append standardized image records for files matching pattern."""
    for image_file in directory.glob(pattern):
        entry: dict[str, Any] = {
            "name": image_file.stem,
            "path": str(image_file),
            "size_mb": _size_mb(image_file),
        }
        if entry_type is not None:
            entry["type"] = entry_type
        if include_location:
            entry["location"] = directory.name
        items.append(entry)


def systemd_machine_id(logger: logging.Logger, mount_root: Path) -> str:
    """Read machine-id from standard locations in offline root."""
    try:
        machine_id_path = mount_root / "etc/machine-id"
        if machine_id_path.exists():
            return machine_id_path.read_text().strip()

        dbus_id_path = mount_root / "var/lib/dbus/machine-id"
        if dbus_id_path.exists():
            return dbus_id_path.read_text().strip()

        return ""
    except Exception as e:  # pylint: disable=broad-exception-caught
        # reason: best-effort offline probe -- must not abort other checks;
        # caller treats the returned default as "unavailable".
        logger.debug("systemd_machine_id failed: %s", e)
        return ""


def systemd_detect_virt(logger: logging.Logger, command_quiet: CommandQuietFn) -> dict[str, str]:
    """Detect virtualization/container type using systemd-detect-virt."""
    try:
        vm_result = command_quiet(["systemd-detect-virt", "--vm"])
        vm_type = vm_result.strip() if vm_result else "none"

        container_result = command_quiet(["systemd-detect-virt", "--container"])
        container_type = container_result.strip() if container_result else "none"

        if vm_type != "none":
            overall_type = "vm"
        elif container_type != "none":
            overall_type = "container"
        else:
            overall_type = "none"

        return {"type": overall_type, "vm": vm_type, "container": container_type}
    except Exception as e:  # pylint: disable=broad-exception-caught
        # reason: best-effort offline probe -- must not abort other checks;
        # caller treats the returned default as "unavailable".
        logger.debug("systemd_detect_virt failed: %s", e)
        return {"type": "none", "vm": "none", "container": "none"}


def journalctl_list_boots_detailed(
    logger: logging.Logger, command_quiet: CommandQuietFn
) -> list[dict[str, Any]]:
    """Parse `journalctl --list-boots --output=json` output."""
    try:
        result = command_quiet(["journalctl", "--list-boots", "--output=json"])
        boots: list[dict[str, Any]] = []
        for line in result.splitlines():
            if not line.strip():
                continue
            boot_data = json.loads(line)
            boots.append(
                {
                    "boot_id": boot_data.get("boot_id", ""),
                    "first_entry": boot_data.get("first_entry", ""),
                    "last_entry": boot_data.get("last_entry", ""),
                }
            )
        return boots
    except Exception as e:  # pylint: disable=broad-exception-caught
        # reason: best-effort offline probe -- must not abort other checks;
        # caller treats the returned default as "unavailable".
        logger.debug("journalctl_list_boots_detailed failed: %s", e)
        return []


def journalctl_export_to_file(
    logger: logging.Logger,
    command_quiet: CommandQuietFn,
    output_path: str,
    since: str | None = None,
    until: str | None = None,
) -> bool:
    """Export journal output to a file using `journalctl --output=export`."""
    try:
        cmd = ["journalctl", "--output=export"]
        if since:
            cmd.extend(["--since", since])
        if until:
            cmd.extend(["--until", until])

        result = command_quiet(cmd)
        Path(output_path).write_bytes(result.encode("utf-8"))
        return True
    except Exception as e:  # pylint: disable=broad-exception-caught
        # reason: best-effort offline probe -- must not abort other checks;
        # caller treats the returned default as "unavailable".
        logger.debug("journalctl_export_to_file failed: %s", e)
        return False


def systemd_networkd_config(logger: logging.Logger, mount_root: Path) -> dict[str, Any]:
    """List offline systemd-networkd config files."""
    config: dict[str, Any] = {"networks": [], "netdevs": [], "links": []}
    try:
        network_dir = mount_root / "etc/systemd/network"
        if network_dir.exists():
            _append_file_records(config["networks"], network_dir, "*.network")
            _append_file_records(config["netdevs"], network_dir, "*.netdev")
            _append_file_records(config["links"], network_dir, "*.link")
        return config
    except Exception as e:  # pylint: disable=broad-exception-caught
        # reason: best-effort offline probe -- must not abort other checks;
        # caller treats the returned default as "unavailable".
        logger.debug("systemd_networkd_config failed: %s", e)
        return config


def systemd_resolved_config(logger: logging.Logger, mount_root: Path) -> dict[str, Any]:
    """Parse offline `resolved.conf` into structured DNS settings."""
    default = {"dns_servers": [], "fallback_dns": [], "domains": [], "dnssec": "allow-downgrade"}
    try:
        resolved_conf = mount_root / "etc/systemd/resolved.conf"
        key_map = {
            "dns_servers": "DNS",
            "fallback_dns": "FallbackDNS",
            "domains": "Domains",
            "dnssec": "DNSSEC",
        }
        section = _read_ini_section(resolved_conf, "Resolve")
        if section is None:
            return dict(default)

        config = dict(default)
        for cfg_key, ini_key in key_map.items():
            if ini_key not in section:
                continue
            value = section[ini_key]
            config[cfg_key] = value.split() if cfg_key != "dnssec" else value
        return config
    except Exception as e:  # pylint: disable=broad-exception-caught
        # reason: best-effort offline probe -- must not abort other checks;
        # caller treats the returned default as "unavailable".
        logger.debug("systemd_resolved_config failed: %s", e)
        return default


def systemd_coredump_list(logger: logging.Logger, mount_root: Path) -> list[dict[str, Any]]:
    """List systemd core dump files from offline root."""
    try:
        coredump_dir = mount_root / "var/lib/systemd/coredump"
        if not coredump_dir.exists():
            return []

        coredumps: list[dict[str, Any]] = []
        for dump_file in coredump_dir.glob("core.*"):
            # core.<command>.<uid>.<gid>.<pid>.<timestamp>...
            parts = dump_file.name.split(".")
            if len(parts) >= 6:
                coredumps.append(
                    {
                        "command": parts[1],
                        "uid": parts[2],
                        "gid": parts[3],
                        "pid": parts[4],
                        "timestamp": parts[5],
                        "file": str(dump_file),
                        "size_mb": _size_mb(dump_file),
                    }
                )

        return coredumps
    except Exception as e:  # pylint: disable=broad-exception-caught
        # reason: best-effort offline probe -- must not abort other checks;
        # caller treats the returned default as "unavailable".
        logger.debug("systemd_coredump_list failed: %s", e)
        return []


def systemd_coredump_config(logger: logging.Logger, mount_root: Path) -> dict[str, str]:
    """Read coredump.conf from offline root with defaults."""
    config = {
        "Storage": "external",
        "Compress": "yes",
        "ProcessSizeMax": "2G",
        "ExternalSizeMax": "2G",
    }
    try:
        conf_file = mount_root / "etc/systemd/coredump.conf"
        return _merge_ini_config(config, conf_file, "Coredump")
    except Exception as e:  # pylint: disable=broad-exception-caught
        # reason: best-effort offline probe -- must not abort other checks;
        # caller treats the returned default as "unavailable".
        logger.debug("systemd_coredump_config failed: %s", e)
        return config


def systemd_pstore_list(logger: logging.Logger, mount_root: Path) -> list[dict[str, Any]]:
    """List pstore crash records from offline root."""
    try:
        pstore_dir = mount_root / "sys/fs/pstore"
        if not pstore_dir.exists():
            return []

        entries: list[dict[str, Any]] = []
        for pstore_file in pstore_dir.iterdir():
            if not pstore_file.is_file():
                continue

            pstore_type = "unknown"
            if "dmesg" in pstore_file.name:
                pstore_type = "dmesg"
            elif "console" in pstore_file.name:
                pstore_type = "console"
            elif "panic" in pstore_file.name:
                pstore_type = "panic"

            entries.append(
                {
                    "file": pstore_file.name,
                    "type": pstore_type,
                    "size_kb": _size_kb(pstore_file),
                    "path": str(pstore_file),
                }
            )
        return entries
    except Exception as e:  # pylint: disable=broad-exception-caught
        # reason: best-effort offline probe -- must not abort other checks;
        # caller treats the returned default as "unavailable".
        logger.debug("systemd_pstore_list failed: %s", e)
        return []


def systemd_sysusers_config(logger: logging.Logger, mount_root: Path) -> list[dict[str, Any]]:
    """Parse systemd-sysusers entries from offline root."""
    try:
        sysusers_dir = mount_root / "usr/lib/sysusers.d"
        if not sysusers_dir.exists():
            return []

        entries: list[dict[str, Any]] = []
        # pylint: disable=duplicate-code
        # reason: this "read + split whitespace-separated fields" parsing
        # loop mirrors a similar per-user parsing loop in
        # core/inspectors/linux_extractor.py (/var/spool/cron scan) --
        # structurally similar by coincidence, not shared logic; keeping
        # independent avoids coupling unrelated per-user config parsing.
        for conf_file in sysusers_dir.glob("*.conf"):
            content = conf_file.read_text()
            for line in content.splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue

                # type name id gecos home shell
                parts = line.split(None, 5)
                if len(parts) >= 2:
                    entries.append(
                        {
                            "type": parts[0],
                            "name": parts[1],
                            "id": parts[2] if len(parts) > 2 else "-",
                            "gecos": parts[3] if len(parts) > 3 else "",
                            "home": parts[4] if len(parts) > 4 else "/",
                            "shell": parts[5] if len(parts) > 5 else "/usr/sbin/nologin",
                            "source_file": conf_file.name,
                        }
                    )
        return entries
    except Exception as e:  # pylint: disable=broad-exception-caught
        # reason: best-effort offline probe -- must not abort other checks;
        # caller treats the returned default as "unavailable".
        logger.debug("systemd_sysusers_config failed: %s", e)
        return []


def systemd_logind_config(logger: logging.Logger, mount_root: Path) -> dict[str, Any]:
    """Read logind.conf from offline root with defaults."""
    config: dict[str, Any] = {
        "KillUserProcesses": "no",
        "KillExcludeUsers": [],
        "HandlePowerKey": "poweroff",
        "HandleSuspendKey": "suspend",
        "HandleLidSwitch": "suspend",
        "IdleAction": "ignore",
        "IdleActionSec": "30min",
    }
    try:
        conf_file = mount_root / "etc/systemd/logind.conf"
        return _merge_ini_config(config, conf_file, "Login", split_keys={"KillExcludeUsers"})
    except Exception as e:  # pylint: disable=broad-exception-caught
        # reason: best-effort offline probe -- must not abort other checks;
        # caller treats the returned default as "unavailable".
        logger.debug("systemd_logind_config failed: %s", e)
        return config


def systemd_boot_entries(logger: logging.Logger, mount_root: Path) -> list[dict[str, Any]]:
    """Parse systemd-boot entry files from offline root."""
    try:
        entries_dir = _first_existing_path(
            [mount_root / "boot/loader/entries", mount_root / "boot/efi/loader/entries"]
        )
        if entries_dir is None:
            return []

        entries: list[dict[str, Any]] = []
        for entry_file in entries_dir.glob("*.conf"):
            entry: dict[str, Any] = {"file": entry_file.name}
            entry.update(_parse_key_value_lines(entry_file.read_text()))
            entries.append(entry)
        return entries
    except Exception as e:  # pylint: disable=broad-exception-caught
        # reason: best-effort offline probe -- must not abort other checks;
        # caller treats the returned default as "unavailable".
        logger.debug("systemd_boot_entries failed: %s", e)
        return []


def systemd_boot_loader_config(logger: logging.Logger, mount_root: Path) -> dict[str, str]:
    """Parse loader.conf from offline root."""
    try:
        conf_file = _first_existing_path(
            [mount_root / "boot/loader/loader.conf", mount_root / "boot/efi/loader/loader.conf"]
        )
        if conf_file is None:
            return {}

        return _parse_key_value_lines(conf_file.read_text())
    except Exception as e:  # pylint: disable=broad-exception-caught
        # reason: best-effort offline probe -- must not abort other checks;
        # caller treats the returned default as "unavailable".
        logger.debug("systemd_boot_loader_config failed: %s", e)
        return {}


def systemd_sysext_list(logger: logging.Logger, mount_root: Path) -> list[dict[str, Any]]:
    """List system extension raw images from offline root."""
    try:
        sysext_dirs = [mount_root / "var/lib/extensions", mount_root / "usr/lib/extensions"]
        extensions: list[dict[str, Any]] = []
        for ext_dir in sysext_dirs:
            if not ext_dir.exists():
                continue
            _append_image_entries(
                extensions,
                ext_dir,
                "*.raw",
                include_location=True,
            )
        return extensions
    except Exception as e:  # pylint: disable=broad-exception-caught
        # reason: best-effort offline probe -- must not abort other checks;
        # caller treats the returned default as "unavailable".
        logger.debug("systemd_sysext_list failed: %s", e)
        return []


def systemd_oomd_config(logger: logging.Logger, mount_root: Path) -> dict[str, Any]:
    """Read oomd.conf from offline root with defaults."""
    config: dict[str, Any] = {
        "SwapUsedLimit": "90%",
        "DefaultMemoryPressureLimit": "60%",
        "DefaultMemoryPressureDurationSec": "30s",
    }
    try:
        oomd_conf = mount_root / "etc/systemd/oomd.conf"
        return _merge_ini_config(config, oomd_conf, "OOM")
    except Exception as e:  # pylint: disable=broad-exception-caught
        # reason: best-effort offline probe -- must not abort other checks;
        # caller treats the returned default as "unavailable".
        logger.debug("systemd_oomd_config failed: %s", e)
        return config


def systemd_timesyncd_config(logger: logging.Logger, mount_root: Path) -> dict[str, Any]:
    """Read timesyncd.conf from offline root with defaults."""
    config: dict[str, Any] = {
        "NTP": [],
        "FallbackNTP": ["time.cloudflare.com", "time.google.com"],
        "RootDistanceMaxSec": "5",
        "PollIntervalMinSec": "32",
        "PollIntervalMaxSec": "2048",
    }
    try:
        timesyncd_conf = mount_root / "etc/systemd/timesyncd.conf"
        return _merge_ini_config(
            config,
            timesyncd_conf,
            "Time",
            split_keys={"NTP", "FallbackNTP"},
        )
    except Exception as e:  # pylint: disable=broad-exception-caught
        # reason: best-effort offline probe -- must not abort other checks;
        # caller treats the returned default as "unavailable".
        logger.debug("systemd_timesyncd_config failed: %s", e)
        return config


def systemd_portable_list(logger: logging.Logger, mount_root: Path) -> list[dict[str, Any]]:
    """List portable service image files from offline root."""
    try:
        portable_dirs = [mount_root / "var/lib/portables", mount_root / "etc/portables"]
        portables: list[dict[str, Any]] = []
        for portable_dir in portable_dirs:
            if not portable_dir.exists():
                continue

            _append_image_entries(portables, portable_dir, "*.raw", entry_type="raw")
            _append_image_entries(portables, portable_dir, "*.portable", entry_type="portable")
        return portables
    except Exception as e:  # pylint: disable=broad-exception-caught
        # reason: best-effort offline probe -- must not abort other checks;
        # caller treats the returned default as "unavailable".
        logger.debug("systemd_portable_list failed: %s", e)
        return []


def systemd_analyze_plot_offline(
    logger: logging.Logger,
    mount_root: Path,
    run_command: CommandRunFn,
    output_path: str | None = None,
) -> str:
    """Generate offline systemd-analyze plot SVG."""
    try:
        journal_dir = mount_root / "var/log/journal"
        if not journal_dir.exists():
            logger.debug("No journal directory found")
            return ""

        cmd = ["systemd-analyze", "plot", "--directory", str(mount_root)]
        svg_content = run_command(cmd)

        if output_path:
            Path(output_path).write_text(svg_content, encoding="utf-8")
        return svg_content
    except Exception as e:  # pylint: disable=broad-exception-caught
        # reason: best-effort offline probe -- must not abort other checks;
        # caller treats the returned default as "unavailable".
        logger.debug("systemd_analyze_plot_offline failed: %s", e)
        return ""


def systemd_analyze_security_offline(
    logger: logging.Logger,
    mount_root: Path,
    run_command: CommandRunFn,
    unit: str | None = None,
) -> list[dict[str, Any]]:
    """Run offline security analysis and parse table output."""
    try:
        cmd = ["systemd-analyze", "security", "--offline", str(mount_root), "--no-pager"]
        if unit:
            cmd.append(unit)

        output = run_command(cmd).strip()
        security_results: list[dict[str, Any]] = []
        lines = output.split("\n")

        data_start = 0
        for i, line in enumerate(lines):
            if "─" in line:
                data_start = i + 1
                break

        for line in lines[data_start:]:
            if not line.strip():
                continue
            parts = line.split()
            if len(parts) >= 3:
                security_results.append(
                    {
                        "unit": parts[0],
                        "exposure": parts[1],
                        "predicate": parts[2],
                    }
                )

        return security_results
    except Exception as e:  # pylint: disable=broad-exception-caught
        # reason: best-effort offline probe -- must not abort other checks;
        # caller treats the returned default as "unavailable".
        logger.debug("systemd_analyze_security_offline failed: %s", e)
        return []


def systemd_analyze_time_offline(
    logger: logging.Logger,
    mount_root: Path,
    run_command: CommandRunFn,
) -> dict[str, float]:
    """Run offline boot timing analysis and parse timings in seconds."""
    try:
        cmd = ["systemd-analyze", "time", "--directory", str(mount_root)]
        output = run_command(cmd).strip()

        timing = {"kernel_time": 0.0, "userspace_time": 0.0, "total_time": 0.0}

        kernel_match = re.search(r"([\d.]+)s\s*\(kernel\)", output)
        if kernel_match:
            timing["kernel_time"] = float(kernel_match.group(1))

        userspace_match = re.search(r"([\d.]+)s\s*\(userspace\)", output)
        if userspace_match:
            timing["userspace_time"] = float(userspace_match.group(1))

        total_match = re.search(r"=\s*([\d.]+)s", output)
        if total_match:
            timing["total_time"] = float(total_match.group(1))

        return timing
    except Exception as e:  # pylint: disable=broad-exception-caught
        # reason: best-effort offline probe -- must not abort other checks;
        # caller treats the returned default as "unavailable".
        logger.debug("systemd_analyze_time_offline failed: %s", e)
        return {"kernel_time": 0.0, "userspace_time": 0.0, "total_time": 0.0}


def systemd_security_compliance_check(  # pylint: disable=too-many-branches,too-many-statements
    logger: logging.Logger, mount_root: Path
) -> dict[str, Any]:
    # reason: runs several independent offline compliance checks (unnecessary
    # services, journal/coredump config, SUID audit), each with its own pass/fail
    # branching and finding/recommendation bookkeeping.
    """Run offline systemd security compliance checks."""
    compliance: dict[str, Any] = {
        "score": 0,
        "total_checks": 0,
        "passed": 0,
        "failed": 0,
        "findings": [],
        "recommendations": [],
    }

    unnecessary_services = ["debug-shell.service", "systemd-halt.service"]

    for service in unnecessary_services:
        compliance["total_checks"] += 1
        try:
            service_path = mount_root / f"etc/systemd/system/{service}"
            if service_path.exists():
                compliance["failed"] += 1
                compliance["findings"].append(
                    {
                        "check": f"Unnecessary service: {service}",
                        "status": "FAIL",
                        "severity": "medium",
                    }
                )
                compliance["recommendations"].append(f"Disable {service} to reduce attack surface")
            else:
                compliance["passed"] += 1
        except Exception:  # pylint: disable=broad-exception-caught
            # reason: per-service best-effort check -- one failure must not abort
            # the rest of the compliance scan.
            pass

    compliance["total_checks"] += 1
    try:
        journal_conf = mount_root / "etc/systemd/journald.conf"
        if journal_conf.exists():
            content = journal_conf.read_text()
            if "Compress=yes" in content:
                compliance["passed"] += 1
            else:
                compliance["failed"] += 1
                compliance["findings"].append(
                    {"check": "Journal compression", "status": "FAIL", "severity": "low"}
                )
                compliance["recommendations"].append("Enable journal compression to save disk space")
    except Exception:  # pylint: disable=broad-exception-caught
        # reason: best-effort check -- one failure must not abort the rest of
        # the compliance scan.
        pass

    compliance["total_checks"] += 1
    try:
        coredump_conf = mount_root / "etc/systemd/coredump.conf"
        if coredump_conf.exists():
            content = coredump_conf.read_text()
            if "Storage=none" in content:
                compliance["passed"] += 1
            else:
                compliance["failed"] += 1
                compliance["findings"].append(
                    {"check": "Core dump restriction", "status": "FAIL", "severity": "medium"}
                )
                compliance["recommendations"].append("Set Storage=none in coredump.conf")
    except Exception:  # pylint: disable=broad-exception-caught
        # reason: best-effort check -- one failure must not abort the rest of
        # the compliance scan.
        pass

    compliance["total_checks"] += 1
    try:
        known_safe_suid = {
            "/usr/bin/sudo",
            "/usr/bin/su",
            "/usr/bin/passwd",
            "/usr/bin/mount",
            "/usr/bin/umount",
            "/usr/bin/ping",
        }
        suid_binaries: list[str] = []
        for root_dir in [mount_root / "usr/bin", mount_root / "usr/sbin"]:
            if not root_dir.exists():
                continue
            for binary in root_dir.iterdir():
                if binary.is_file() and (binary.stat().st_mode & 0o4000):
                    rel_path = _relpath(binary, mount_root)
                    if rel_path not in known_safe_suid:
                        suid_binaries.append(rel_path)

        if suid_binaries:
            compliance["failed"] += 1
            compliance["findings"].append(
                {
                    "check": "SUID binaries audit",
                    "status": "WARN",
                    "severity": "high",
                    "details": f"Found {len(suid_binaries)} unexpected SUID binaries",
                    "binaries": suid_binaries,
                }
            )
            compliance["recommendations"].append("Review and remove unnecessary SUID binaries")
        else:
            compliance["passed"] += 1
    except Exception as e:  # pylint: disable=broad-exception-caught
        # reason: best-effort offline probe -- must not abort other checks;
        # caller treats the returned default as "unavailable".
        logger.debug("SUID check failed: %s", e)

    if compliance["total_checks"] > 0:
        compliance["score"] = int((compliance["passed"] / compliance["total_checks"]) * 100)
    return compliance


def systemd_detect_anomalies(  # pylint: disable=too-many-branches
    logger: logging.Logger, mount_root: Path
) -> dict[str, list[dict[str, Any]]]:
    # reason: scans four independent anomaly categories (hidden/writable units,
    # suspicious timers/sockets), each with its own file-type and content checks.
    """Detect suspicious offline systemd config anomalies."""
    anomalies: dict[str, list[dict[str, Any]]] = {
        "hidden_units": [],
        "writable_units": [],
        "suspicious_timers": [],
        "suspicious_sockets": [],
    }
    try:
        systemd_dir = mount_root / "etc/systemd/system"
        if not systemd_dir.exists():
            return anomalies

        for hidden_file in systemd_dir.glob(".*"):
            if hidden_file.is_file():
                anomalies["hidden_units"].append(
                    {"file": str(hidden_file.relative_to(mount_root)), "size": hidden_file.stat().st_size}
                )

        for unit_file in systemd_dir.rglob("*"):
            if unit_file.is_file() and (unit_file.stat().st_mode & 0o002):
                anomalies["writable_units"].append(
                    {"file": str(unit_file.relative_to(mount_root)), "mode": oct(unit_file.stat().st_mode)}
                )

        for timer_file in systemd_dir.rglob("*.timer"):
            if not timer_file.is_file():
                continue
            content = timer_file.read_text()
            if "OnCalendar=*:0/1" in content or "OnCalendar=minutely" in content:
                anomalies["suspicious_timers"].append(
                    {
                        "file": timer_file.name,
                        "reason": "Very frequent activation",
                        "path": str(timer_file.relative_to(mount_root)),
                    }
                )

        for socket_file in systemd_dir.rglob("*.socket"):
            if not socket_file.is_file():
                continue
            content = socket_file.read_text()
            for match in re.finditer(r"ListenStream=([^\n]+)", content):
                listen_addr = match.group(1)
                if listen_addr.startswith(("127.0.0.1", "/", "localhost")):
                    continue
                anomalies["suspicious_sockets"].append(
                    {
                        "file": socket_file.name,
                        "address": listen_addr,
                        "reason": "Listening on non-localhost",
                        "path": str(socket_file.relative_to(mount_root)),
                    }
                )
        return anomalies
    except Exception as e:  # pylint: disable=broad-exception-caught
        # reason: best-effort offline probe -- must not abort other checks;
        # caller treats the returned default as "unavailable".
        logger.debug("systemd_detect_anomalies failed: %s", e)
        return anomalies


def systemd_migration_readiness_check(  # pylint: disable=too-many-branches
    logger: logging.Logger, mount_root: Path
) -> dict[str, Any]:
    # reason: assesses three independent readiness dimensions (host-specific units,
    # hardcoded MAC addresses, non-portable fstab entries), each with its own
    # detection and blocker/warning bookkeeping.
    """Assess migration readiness from offline systemd/network/fstab config."""
    assessment: dict[str, Any] = {
        "ready": True,
        "blockers": [],
        "warnings": [],
        "recommendations": [],
        "checks_performed": 0,
        "checks_passed": 0,
    }

    systemd_dir = mount_root / "etc/systemd/system"
    try:
        assessment["checks_performed"] += 1
        host_specific_found = False
        if systemd_dir.exists():
            for unit_file in systemd_dir.rglob("*.service"):
                if not unit_file.is_file():
                    continue
                content = unit_file.read_text()
                if "ConditionHost=" in content:
                    assessment["warnings"].append(
                        {
                            "check": "Host-specific unit",
                            "file": unit_file.name,
                            "issue": "Contains ConditionHost dependency",
                            "impact": "May not start on new host",
                        }
                    )
                    assessment["recommendations"].append(
                        f"Review {unit_file.name} for host-specific conditions"
                    )
                    host_specific_found = True
        if not host_specific_found:
            assessment["checks_passed"] += 1

        assessment["checks_performed"] += 1
        mac_hardcoded = False
        network_dir = mount_root / "etc/systemd/network"
        if network_dir.exists():
            for net_file in network_dir.glob("*.network"):
                content = net_file.read_text()
                if "MACAddress=" in content or "PermanentMACAddress=" in content:
                    assessment["blockers"].append(
                        {
                            "check": "Hardcoded MAC address",
                            "file": net_file.name,
                            "issue": "Network config has hardcoded MAC",
                            "impact": "Network will fail on new host",
                            "severity": "high",
                        }
                    )
                    assessment["recommendations"].append(f"Remove MAC address from {net_file.name}")
                    assessment["ready"] = False
                    mac_hardcoded = True
        if not mac_hardcoded:
            assessment["checks_passed"] += 1

        assessment["checks_performed"] += 1
        fstab_file = mount_root / "etc/fstab"
        if fstab_file.exists():
            content = fstab_file.read_text()
            non_portable_mounts = re.findall(r"/dev/[sh]d[a-z]\d+", content)
            if non_portable_mounts:
                assessment["warnings"].append(
                    {
                        "check": "Non-portable filesystem mounts",
                        "issue": f"fstab uses device names: {', '.join(set(non_portable_mounts))}",
                        "impact": "Mounts may fail if device names change",
                        "severity": "medium",
                    }
                )
                assessment["recommendations"].append("Convert fstab to use UUID or PARTUUID")
            else:
                assessment["checks_passed"] += 1

        return assessment
    except Exception as e:  # pylint: disable=broad-exception-caught
        # reason: best-effort offline probe -- must not abort other checks;
        # caller treats the returned default as "unavailable".
        logger.debug("systemd_migration_readiness_check failed: %s", e)
        assessment["ready"] = False
        assessment["blockers"].append(
            {"check": "Migration readiness scan", "issue": f"Error during scan: {e}", "severity": "unknown"}
        )
        return assessment


def systemd_analyze_failures(
    logger: logging.Logger,
    systemctl_list_units: SystemdListUnitsFn,
    systemctl_status: SystemdStatusFn,
) -> dict[str, Any]:
    """Analyze failed units and summarize failure patterns."""
    analysis: dict[str, Any] = {"failed_units": [], "failure_patterns": {}, "recommendations": []}
    try:
        failed = systemctl_list_units(state="failed")
        for unit_dict in failed:
            unit = unit_dict.get("unit", "")
            status = systemctl_status(unit)
            analysis["failed_units"].append({"unit": unit, "status": status})

            status_str = str(status).lower()
            if "dependency" in status_str:
                analysis["failure_patterns"]["dependency"] = (
                    analysis["failure_patterns"].get("dependency", 0) + 1
                )
            if "timeout" in status_str:
                analysis["failure_patterns"]["timeout"] = analysis["failure_patterns"].get("timeout", 0) + 1

        if analysis["failure_patterns"].get("dependency", 0) > 0:
            analysis["recommendations"].append("Check service dependencies with systemctl list-dependencies")
        if analysis["failure_patterns"].get("timeout", 0) > 0:
            analysis["recommendations"].append("Consider increasing TimeoutStartSec in unit files")
        return analysis
    except Exception as e:  # pylint: disable=broad-exception-caught
        # reason: best-effort offline probe -- must not abort other checks;
        # caller treats the returned default as "unavailable".
        logger.debug("systemd_analyze_failures failed: %s", e)
        return analysis


def systemd_post_migration_validation(  # pylint: disable=redefined-outer-name
    logger: logging.Logger,
    systemd_detect_virt: SystemdDetectVirtFn,
    systemd_machine_id: SystemdMachineIdFn,
    systemd_boot_entries: SystemdBootEntriesFn,
) -> dict[str, Any]:
    # reason: these callback parameters are deliberately named after the module-level
    # functions of the same purpose -- callers (see vmcraft/api/systemd_ops.py) bind
    # them by keyword to the host's own systemd_detect_virt/systemd_machine_id/
    # systemd_boot_entries methods, so renaming would break that call site.
    """Validate post-migration systemd state using callback-provided checks."""
    validation: dict[str, Any] = {
        "valid": True,
        "checks": [],
        "issues": [],
        "recommendations": [],
    }
    try:
        virt = systemd_detect_virt()
        validation["checks"].append(
            {
                "name": "Virtualization detection",
                "status": "pass" if virt.get("vm") != "none" else "fail",
                "details": f"Detected: {virt.get('vm', 'unknown')}",
            }
        )
        if virt.get("vm") == "none":
            validation["valid"] = False
            validation["issues"].append("Virtualization not detected after migration")

        machine_id = systemd_machine_id()
        validation["checks"].append(
            {
                "name": "Machine ID",
                "status": "pass" if machine_id else "fail",
                "details": machine_id[:16] + "..." if machine_id else "Missing",
            }
        )
        if not machine_id:
            validation["valid"] = False
            validation["issues"].append("Machine ID missing")
            validation["recommendations"].append("Run: systemd-machine-id-setup")

        boot_entries = systemd_boot_entries()
        validation["checks"].append(
            {
                "name": "Boot entries",
                "status": "pass" if boot_entries else "warn",
                "details": f"Found {len(boot_entries)} boot entries",
            }
        )
        return validation
    except Exception as e:  # pylint: disable=broad-exception-caught
        # reason: best-effort offline probe -- must not abort other checks;
        # caller treats the returned default as "unavailable".
        logger.debug("systemd_post_migration_validation failed: %s", e)
        validation["valid"] = False
        validation["issues"].append(f"Validation error: {e}")
        return validation
