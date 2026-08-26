# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# h2kvm/fixers/firstboot_injector.py
"""
First-boot systemd service and script injection for Linux VMs.

Creates a oneshot systemd service that runs custom scripts on first boot
and disables itself automatically. Similar to cloud-init but simpler and
more lightweight for specific use cases.

Use cases:
- Network configuration without cloud-init
- Hostname/identity setup
- License activation
- Post-migration cleanup
- Custom initialization scripts
"""

from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    try:
        import guestfs
    except ImportError:
        from typing import Protocol

        # pylint: disable=invalid-name,missing-class-docstring,too-few-public-methods,duplicate-code
        # Typing-only stand-in named to match the real 'guestfs' module so
        # 'guestfs.GuestFS' annotations resolve when the module is absent. This tiny
        # boilerplate stub is intentionally repeated verbatim across fixer modules
        # (see grub.py) rather than shared, to keep each module's typing self-contained.
        class guestfs:  # type: ignore
            class GuestFS(Protocol): ...


def _guest_has_systemd(g: guestfs.GuestFS) -> bool:
    """Check if guest has systemd"""
    systemd_paths = [
        "/usr/lib/systemd/systemd",
        "/lib/systemd/systemd",
        "/bin/systemd",
        "/usr/bin/systemctl",
    ]
    for path in systemd_paths:
        try:
            if g.exists(path):
                return True
        except Exception:  # pylint: disable=broad-exception-caught
            # best-effort detection across guestfs backends; a probing failure means "not found"
            pass
    return False


def _write_file_executable(self, g: guestfs.GuestFS, path: str, content: str) -> None:
    """Write file and make it executable"""
    # Write file
    g.write(path, content.encode("utf-8"))

    # Make executable (0755)
    try:
        g.chmod(0o755, path)
    except Exception as e:  # pylint: disable=broad-exception-caught
        # Fallback: not all guestfs backends support chmod
        logger = getattr(self, "logger", None)
        if logger:
            logger.warning(f"Could not chmod {path}: {e}")


def _enable_systemd_service(self, g: guestfs.GuestFS, service_name: str) -> bool:
    """
    Enable systemd service by creating symlink in multi-user.target.wants.
    Returns True on success, False on failure.
    """
    logger = getattr(self, "logger", None)

    # systemd service file location
    service_file = f"/etc/systemd/system/{service_name}"

    # Create symlink in multi-user.target.wants
    wants_dir = "/etc/systemd/system/multi-user.target.wants"
    symlink_path = f"{wants_dir}/{service_name}"

    try:
        # Ensure wants directory exists
        if not g.is_dir(wants_dir):
            g.mkdir_p(wants_dir)

        # Create symlink
        if g.exists(symlink_path):
            g.rm(symlink_path)

        g.ln_sf(service_file, symlink_path)

        if logger:
            logger.info(f"Enabled systemd service: {service_name}")
        return True

    except Exception as e:  # pylint: disable=broad-exception-caught
        # best-effort service enablement; caller treats a False return as a soft failure
        if logger:
            logger.exception(f"Failed to enable systemd service {service_name}: {e}")
        return False


# Orchestrates the whole firstboot pipeline (config validation, systemd detection, script
# writing, runner/service generation) end to end; each step is a distinct early-out case,
# so the branch/return/local count reflects the real number of independent failure modes.
# pylint: disable-next=too-many-locals,too-many-return-statements,too-many-branches,too-many-statements
def inject_firstboot(self, g: guestfs.GuestFS) -> dict[str, Any]:
    """
    Inject firstboot systemd service and scripts.

    Expected payload (self.firstboot_config):
      {
        "service_name": "h2kvm-firstboot",  # optional, default
        "scripts": [
          {
            "name": "setup-network",
            "content": "#!/bin/bash\\n...",
            "order": 10  # optional, execution order
          },
          {
            "name": "set-hostname",
            "content": "#!/bin/bash\\nhostname kvm-server",
            "order": 20
          }
        ],
        # OR provide inline script:
        "script": "#!/bin/bash\\necho 'First boot!'",

        # Optional systemd service customization
        "service": {
          "Description": "h2kvm first boot configuration",
          "After": "network.target",
          "Before": "",  # optional
          "RequiresMountsFor": [],  # optional
          "Environment": ["VAR=value"],  # optional
        },

        # Optional: don't disable service after run (for debugging)
        "keep_enabled": false
      }
    """
    logger = getattr(self, "logger", None)

    def _log(level: str, msg: str) -> None:
        if logger:
            with contextlib.suppress(Exception):
                getattr(logger, level)(msg)

    _log("debug", "🚀 firstboot: inject_firstboot(): enter")

    # Get configuration
    config = getattr(self, "firstboot_config", None)
    if not config:
        _log("debug", "🚀 firstboot: no firstboot_config set; skipping")
        return {"injected": False, "reason": "no_config"}

    if not isinstance(config, dict):
        _log("warning", f"🚀 firstboot: firstboot_config is not a dict: {type(config).__name__}")
        return {"injected": False, "reason": "invalid_config"}

    # Check for systemd
    if not _guest_has_systemd(g):
        _log(
            "warning",
            "🚀 firstboot: systemd not detected in guest filesystem. "
            "Firstboot scripts require systemd to run as a oneshot service. "
            "For non-systemd guests (SysV init, OpenRC), add scripts to /etc/rc.local manually.",
        )
        return {"injected": False, "reason": "no_systemd"}

    dry = bool(getattr(self, "dry_run", False))
    _log("debug", f"🚀 firstboot: dry_run={dry}")

    results: dict[str, Any] = {
        "injected": True,
        "dry_run": dry,
        "files_created": [],
        "service_enabled": False,
    }

    # Service name
    service_name = config.get("service_name", "h2kvm-firstboot.service")
    if not service_name.endswith(".service"):
        service_name += ".service"

    results["service_name"] = service_name

    # Directories
    scripts_dir = "/usr/local/lib/h2kvm-firstboot"
    service_file = f"/etc/systemd/system/{service_name}"

    # Create scripts directory
    if not dry:
        try:
            g.mkdir_p(scripts_dir)
            _log("debug", f"📁 Created directory: {scripts_dir}")
        except Exception as e:  # pylint: disable=broad-exception-caught
            # guestfs mkdir_p can fail in many backend-specific ways; report and abort injection
            _log(
                "error",
                f"Failed to create firstboot scripts directory {scripts_dir}: {e}. "
                "Check that the guest filesystem is writable and has available space.",
            )
            return {"injected": False, "reason": "mkdir_failed", "error": str(e)}

    # Handle scripts
    scripts = config.get("scripts", [])
    inline_script = config.get("script")

    if inline_script:
        # Convert inline script to script list
        scripts = [{"name": "main", "content": inline_script, "order": 50}]
    elif not scripts:
        _log("warning", "🚀 firstboot: no scripts or script provided")
        return {"injected": False, "reason": "no_scripts"}

    # Sort scripts by order
    scripts = sorted(scripts, key=lambda s: s.get("order", 50))

    # Write individual scripts
    script_paths = []
    for idx, script in enumerate(scripts):
        script_name = script.get("name", f"script-{idx}")
        script_content = script.get("content", "")

        if not script_content:
            _log("warning", f"🚀 firstboot: script '{script_name}' has no content, skipping")
            continue

        # Ensure script starts with shebang
        if not script_content.strip().startswith("#!"):
            script_content = "#!/bin/bash\n" + script_content

        script_path = f"{scripts_dir}/{script_name}.sh"
        script_paths.append(script_path)

        if dry:
            _log("info", f"DRY-RUN: would write script: {script_path}")
            results["files_created"].append(
                {"path": script_path, "bytes": len(script_content.encode("utf-8")), "kind": "script"}
            )
        else:
            try:
                _write_file_executable(self, g, script_path, script_content)
                _log("info", f"Wrote firstboot script: {script_path}")
                results["files_created"].append(
                    {"path": script_path, "bytes": len(script_content.encode("utf-8")), "kind": "script"}
                )
            except Exception as e:
                _log("error", f"Failed to write script {script_path}: {e}")
                raise

    if not script_paths:
        _log("warning", "🚀 firstboot: no valid scripts to execute")
        return {"injected": False, "reason": "no_valid_scripts"}

    # Create main runner script
    runner_script = _generate_runner_script(
        script_paths, service_name, keep_enabled=config.get("keep_enabled", False)
    )
    runner_path = f"{scripts_dir}/run-firstboot.sh"

    if dry:
        _log("info", f"DRY-RUN: would write runner: {runner_path}")
        results["files_created"].append(
            {"path": runner_path, "bytes": len(runner_script.encode("utf-8")), "kind": "runner"}
        )
    else:
        try:
            _write_file_executable(self, g, runner_path, runner_script)
            _log("info", f"Wrote firstboot runner: {runner_path}")
            results["files_created"].append(
                {"path": runner_path, "bytes": len(runner_script.encode("utf-8")), "kind": "runner"}
            )
        except Exception as e:
            _log("error", f"Failed to write runner script: {e}")
            raise

    # Generate systemd service unit
    service_config = config.get("service", {})
    service_content = _generate_systemd_service(runner_path, service_config)

    if dry:
        _log("info", f"DRY-RUN: would write service: {service_file}")
        results["files_created"].append(
            {"path": service_file, "bytes": len(service_content.encode("utf-8")), "kind": "service"}
        )
    else:
        try:
            g.write(service_file, service_content.encode("utf-8"))
            _log("info", f"Wrote systemd service: {service_file}")
            results["files_created"].append(
                {"path": service_file, "bytes": len(service_content.encode("utf-8")), "kind": "service"}
            )

            # Enable the service
            if _enable_systemd_service(self, g, service_name):
                results["service_enabled"] = True
            else:
                _log("warning", f"Failed to enable service {service_name}")

        except Exception as e:
            _log("error", f"Failed to write systemd service: {e}")
            raise

    _log("info", f"🚀 firstboot: injection complete; files={len(results['files_created'])}")
    return results


def _generate_runner_script(script_paths: list[str], service_name: str, keep_enabled: bool = False) -> str:
    """Generate the main runner script that executes all firstboot scripts"""
    scripts_list = "\n".join(f'  "{path}"' for path in script_paths)

    disable_cmd = "" if keep_enabled else f"  systemctl disable {service_name}"

    return f"""#!/bin/bash
# h2kvm firstboot runner script
# Auto-generated - DO NOT EDIT

set -e

LOG_FILE="/var/log/h2kvm-firstboot.log"

log() {{
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE"
}}

log "========================================="
log "h2kvm firstboot starting"
log "========================================="

# Array of scripts to execute in order
SCRIPTS=(
{scripts_list}
)

SUCCESS_COUNT=0
FAIL_COUNT=0

# Execute each script
for script in "${{SCRIPTS[@]}}"; do
  if [ -f "$script" ] && [ -x "$script" ]; then
    log "Executing: $script"
    if "$script" >> "$LOG_FILE" 2>&1; then
      log "SUCCESS: $script"
      ((SUCCESS_COUNT++))
    else
      log "FAILED: $script (exit code: $?)"
      ((FAIL_COUNT++))
    fi
  else
    log "SKIPPED: $script (not found or not executable)"
    ((FAIL_COUNT++))
  fi
done

log "========================================="
log "h2kvm firstboot completed"
log "Success: $SUCCESS_COUNT, Failed: $FAIL_COUNT"
log "========================================="

# Disable the service so it doesn't run again
{disable_cmd}

exit 0
"""


def _generate_systemd_service(runner_path: str, service_config: dict[str, Any]) -> str:
    """Generate systemd service unit file content"""
    description = service_config.get("Description", "h2kvm first boot configuration")
    after = service_config.get("After", "network.target")
    before = service_config.get("Before", "")
    requires_mounts_for = service_config.get("RequiresMountsFor", [])
    environment = service_config.get("Environment", [])

    # Build [Unit] section
    unit_section = f"""[Unit]
Description={description}
After={after}"""

    if before:
        unit_section += f"\nBefore={before}"

    if requires_mounts_for:
        mounts = " ".join(requires_mounts_for)
        unit_section += f"\nRequiresMountsFor={mounts}"

    # Build [Service] section
    service_section = f"""[Service]
Type=oneshot
ExecStart={runner_path}
RemainAfterExit=no
StandardOutput=journal
StandardError=journal"""

    if environment:
        for env in environment:
            service_section += f'\nEnvironment="{env}"'

    # Build [Install] section
    install_section = """[Install]
WantedBy=multi-user.target"""

    return f"{unit_section}\n\n{service_section}\n\n{install_section}\n"
