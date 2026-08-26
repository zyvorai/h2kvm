# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""XFS command helpers for VMCraft."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any, Callable

from ._runner import RunCommandFn, run_captured

if TYPE_CHECKING:
    import logging


def _parse_xfs_label(output: str) -> str | None:
    """Extract XFS label from xfs_admin output."""
    match = re.search(r'label\s*=\s*"([^"]*)"', output)
    return match.group(1) if match else None


def _parse_xfs_uuid(output: str) -> str | None:
    """Extract XFS UUID from xfs_admin output."""
    match = re.search(r"UUID\s*=\s*([a-f0-9-]+)", output)
    return match.group(1) if match else None


def _probe_xfs_admin_field(
    logger: logging.Logger,
    run_sudo: RunCommandFn,
    device: str,
    flag: str,
    parser: Callable[[str], str | None],
) -> str | None:
    """Probe one xfs_admin field and parse value from stdout."""
    result = run_captured(
        logger,
        run_sudo,
        ["xfs_admin", flag, device],
        debug_failure=True,
    )
    return parser(result.stdout)


def xfs_info(  # pylint: disable=too-many-branches,too-many-statements
    logger: logging.Logger, run_sudo: RunCommandFn, device: str
) -> dict[str, Any]:
    # reason: parsing xfs_info's multi-section text output (meta-data, data, naming,
    # log, sector size) needs one branch+regex per field; inherent to the format.
    """Get XFS metadata from `xfs_info` and xfs_admin probes."""
    try:
        result = run_captured(
            logger,
            run_sudo,
            ["xfs_info", device],
            debug_failure=True,
        )

        info: dict[str, Any] = {}
        for raw_line in result.stdout.splitlines():
            line = raw_line.strip()
            if line.startswith("meta-data="):
                m = re.search(r"isize=(\d+)", line)
                if m:
                    info["inodesize"] = int(m.group(1))
                m = re.search(r"agcount=(\d+)", line)
                if m:
                    info["agcount"] = int(m.group(1))
                m = re.search(r"agsize=(\d+)", line)
                if m:
                    info["agsize"] = int(m.group(1))
            elif line.startswith("data"):
                m = re.search(r"bsize=(\d+)", line)
                if m:
                    info["blocksize"] = int(m.group(1))
                m = re.search(r"blocks=(\d+)", line)
                if m:
                    info["blocks"] = int(m.group(1))
                m = re.search(r"imaxpct=(\d+)", line)
                if m:
                    info["imaxpct"] = int(m.group(1))
            elif line.startswith("naming"):
                m = re.search(r"version\s+(\d+)", line)
                if m:
                    info["naming_version"] = int(m.group(1))
                m = re.search(r"ftype=(\d+)", line)
                if m:
                    info["ftype"] = int(m.group(1))
            elif line.startswith("log"):
                if "internal" in line:
                    info["log_internal"] = True
                elif "external" in line:
                    info["log_internal"] = False
                m = re.search(r"blocks=(\d+)", line)
                if m:
                    info["log_blocks"] = int(m.group(1))
            elif "sectsz=" in line:
                m = re.search(r"sectsz=(\d+)", line)
                if m:
                    info["sectsize"] = int(m.group(1))

        try:
            label = _probe_xfs_admin_field(
                logger,
                run_sudo,
                device,
                "-l",
                _parse_xfs_label,
            )
            if label is not None:
                info["label"] = label
        except Exception:  # pylint: disable=broad-exception-caught
            # reason: best-effort probe -- label is simply omitted if unavailable.
            pass

        try:
            uuid_value = _probe_xfs_admin_field(
                logger,
                run_sudo,
                device,
                "-u",
                _parse_xfs_uuid,
            )
            if uuid_value is not None:
                info["uuid"] = uuid_value
        except Exception:  # pylint: disable=broad-exception-caught
            # reason: best-effort probe -- uuid is simply omitted if unavailable.
            pass

        return info
    except Exception as e:  # pylint: disable=broad-exception-caught
        # reason: best-effort metadata probe -- caller treats {} as "unavailable".
        logger.debug("xfs_info failed for %s: %s", device, e)
        return {}


def xfs_admin(
    logger: logging.Logger,
    run_sudo: RunCommandFn,
    device: str,
    *,
    label: str | None = None,
    uuid: str | None = None,
) -> dict[str, str]:
    """Get or set XFS label/UUID via xfs_admin."""
    info: dict[str, str] = {}

    if label is not None:
        if len(label) > 12:
            raise RuntimeError(
                f"XFS label '{label}' is too long ({len(label)} chars). "
                f"XFS labels must be 12 characters or less."
            )
        try:
            run_captured(logger, run_sudo, ["xfs_admin", "-L", label, device])
            info["label"] = label
        except Exception as e:
            raise RuntimeError(
                f"Failed to set XFS label '{label}' on {device}. "
                f"Ensure the filesystem is unmounted and xfs_admin is installed. "
                f"Detail: {e}"
            ) from e

    if uuid is not None:
        try:
            target = "generate" if uuid.lower() == "generate" else uuid
            run_captured(logger, run_sudo, ["xfs_admin", "-U", target, device])
            info["uuid"] = uuid
        except Exception as e:
            raise RuntimeError(
                f"Failed to set XFS UUID on {device}. "
                f"Ensure the filesystem is unmounted and xfs_admin is installed. "
                f"Detail: {e}"
            ) from e

    try:
        label_value = _probe_xfs_admin_field(
            logger,
            run_sudo,
            device,
            "-l",
            _parse_xfs_label,
        )
        info["label"] = label_value if label_value is not None else ""
    except Exception:  # pylint: disable=broad-exception-caught
        # reason: best-effort probe -- report empty label rather than fail the call.
        info["label"] = ""

    try:
        uuid_value = _probe_xfs_admin_field(
            logger,
            run_sudo,
            device,
            "-u",
            _parse_xfs_uuid,
        )
        info["uuid"] = uuid_value if uuid_value is not None else ""
    except Exception:  # pylint: disable=broad-exception-caught
        # reason: best-effort probe -- report empty uuid rather than fail the call.
        info["uuid"] = ""

    return info


def xfs_growfs(
    logger: logging.Logger,
    run_sudo: RunCommandFn,
    mountpoint: str,
    *,
    data_blocks: int | None = None,
    xfs_info_fn: Callable[[str], dict[str, Any]],
) -> dict[str, Any]:
    """Grow an XFS filesystem and report old/new block counts."""
    try:
        info_before = xfs_info_fn(mountpoint)
        old_blocks = info_before.get("blocks", 0)

        cmd = ["xfs_growfs"]
        if data_blocks is not None:
            cmd.extend(["-D", str(data_blocks)])
        cmd.append(mountpoint)

        result = run_captured(logger, run_sudo, cmd)
        new_blocks = old_blocks
        m = re.search(r"data blocks changed from \d+ to (\d+)", result.stdout)
        if m:
            new_blocks = int(m.group(1))

        return {"success": True, "old_blocks": old_blocks, "new_blocks": new_blocks}
    except Exception as e:
        raise RuntimeError(
            f"Failed to grow XFS filesystem at {mountpoint}. "
            f"Ensure the filesystem is mounted and the underlying device has available space. "
            f"Detail: {e}"
        ) from e


def xfs_repair(
    logger: logging.Logger,
    run_sudo: RunCommandFn,
    device: str,
    *,
    check_only: bool = False,
) -> dict[str, Any]:
    """Check or repair XFS filesystem."""
    try:
        cmd = ["xfs_repair"]
        if check_only:
            cmd.append("-n")
        cmd.append(device)

        result = run_captured(logger, run_sudo, cmd, check=False, debug_failure=True)

        output = result.stdout
        clean = "no modifications needed" in output.lower() or result.returncode == 0
        errors_found = "errors found" in output.lower() or "corruption" in output.lower()
        errors_repaired = (not check_only) and errors_found and result.returncode == 0

        return {
            "clean": clean,
            "errors_found": errors_found,
            "errors_repaired": errors_repaired,
            "output": output,
            "returncode": result.returncode,
        }
    except Exception as e:
        if "mounted" in str(e).lower():
            raise RuntimeError(
                f"Cannot repair XFS filesystem on {device} while it is mounted. "
                f"Unmount the filesystem first, then retry."
            ) from e
        raise RuntimeError(
            f"XFS repair failed on {device}. The filesystem may be severely corrupted. Detail: {e}"
        ) from e


def xfs_db(logger: logging.Logger, run_sudo: RunCommandFn, device: str, commands: list[str]) -> str:
    """Run xfs_db in read-only mode and return stdout."""
    try:
        cmd_string = "\n".join(commands) + "\nquit\n"
        result = run_captured(
            logger,
            run_sudo,
            ["xfs_db", "-r", "-c", cmd_string, device],
            debug_failure=True,
        )
        return result.stdout
    except Exception as e:  # pylint: disable=broad-exception-caught
        # reason: best-effort probe -- caller treats "" as "unavailable".
        logger.debug("xfs_db failed: %s", e)
        return ""
