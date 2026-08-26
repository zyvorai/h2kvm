# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# h2kvm/fixers/user_config_injector.py
"""
User account and SSH key injection for Linux VMs.

Allows creating users, deploying SSH keys, configuring sudo access, and
setting passwords for post-migration access without cloud-init.

Use cases:
- Create administrative users
- Deploy SSH keys for passwordless access
- Configure sudo/wheel access
- Set user passwords (hashed)
- Disable/lock default users
- Configure user home directories
"""

from __future__ import annotations

import contextlib
import secrets
import subprocess
import time
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from h2kvm.core.guestfs_typing import guestfs


def _resolve_fstab_device(g: guestfs.GuestFS, spec: str) -> str | None:
    """Resolve a fstab device spec (UUID=... or /dev/...) to an actual device path."""
    try:
        if spec.startswith("UUID="):
            uuid_val = spec.split("=", 1)[1]
            # Search nbd partitions for matching UUID
            for dev in sorted(g.list_devices() + g.list_partitions()):
                with contextlib.suppress(Exception):
                    if g.vfs_uuid(dev) == uuid_val:
                        return dev
            return None
        if spec.startswith("/dev/"):
            return spec
    except Exception:  # pylint: disable=broad-exception-caught  # guestfs device lookup is best-effort; skip this fstab entry on any failure
        return None
    return None


def _mount_fstab_secondary(  # pylint: disable=too-many-branches  # fault-tolerant fstab scan: each guest-specific skip/fallback is a distinct case
    g: guestfs.GuestFS, logger: Any
) -> list[str]:
    """
    Mount secondary fstab entries (/home, /var, /opt, etc.) so that user
    creation, SSH key deployment, and home dir creation work correctly on
    guests with separate partitions.

    Returns list of mountpoints that were mounted (for later unmount).
    """

    def _log(level: str, msg: str) -> None:
        if logger:
            with contextlib.suppress(Exception):
                getattr(logger, level)(msg)

    mounted: list[str] = []
    # Mountpoints worth mounting for user injection
    interesting = ("/home", "/var", "/opt", "/srv")

    try:
        if not g.is_file("/etc/fstab"):
            return mounted
        fstab = g.read_file("/etc/fstab")
        if isinstance(fstab, bytes):
            fstab = fstab.decode("utf-8", errors="replace")
    except Exception:  # pylint: disable=broad-exception-caught  # best-effort fstab read; skip secondary mounts if the guest fstab is unreadable
        return mounted

    for line in fstab.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) < 3:
            continue
        spec, mountpoint, fstype = parts[0], parts[1], parts[2]
        if mountpoint not in interesting:
            continue
        if fstype in ("swap", "none", "tmpfs", "devtmpfs", "sysfs", "proc"):
            continue

        # Find the device for this UUID/LABEL/path
        device = _resolve_fstab_device(g, spec)
        if not device:
            continue

        # Check if already mounted
        try:
            mount_root = getattr(g, "_mount_root", None)
            if not mount_root:
                # For VMCraft, check if the dir already has content
                if g.is_dir(mountpoint) and len(g.ls(mountpoint)) > 0:
                    continue  # Already has content, probably mounted
        except Exception:  # pylint: disable=broad-exception-caught  # best-effort already-mounted check; fall through to mount attempt on failure
            pass

        try:
            g.mount(device, mountpoint)
            mounted.append(mountpoint)
            _log("info", f"👤 Mounted {device} at {mountpoint} for user injection")
        except Exception as e:  # pylint: disable=broad-exception-caught  # per-mountpoint best-effort mount; must not abort user injection over one guest's quirk
            _log("debug", f"👤 Could not mount {device} at {mountpoint}: {e}")

    return mounted


def _umount_fstab_secondary(g: guestfs.GuestFS, logger: Any, mountpoints: list[str]) -> None:
    """Unmount secondary fstab partitions (in reverse order)."""

    def _log(level: str, msg: str) -> None:
        if logger:
            with contextlib.suppress(Exception):
                getattr(logger, level)(msg)

    for mp in reversed(mountpoints):
        try:
            g.umount(mp)
            _log("debug", f"👤 Unmounted {mp}")
        except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort cleanup unmount; must not abort over one mountpoint's quirk
            _log("debug", f"👤 Could not unmount {mp}: {e}")


def inject_user_config(self, g: guestfs.GuestFS) -> dict[str, Any]:
    """
    Inject user accounts and SSH key configuration.

    Expected payload (self.user_config_inject):
      {
        "users": [
          {
            "name": "admin",
            "uid": 1000,  # Optional, auto-assigned if not specified
            "gid": 1000,  # Optional, defaults to uid
            "groups": ["wheel", "docker"],  # Optional, additional groups
            "comment": "Admin User",  # Optional, GECOS field
            "shell": "/bin/bash",  # Optional, default /bin/bash
            "home": "/home/admin",  # Optional, default /home/username
            "create_home": true,  # Optional, default true
            "ssh_keys": [  # Optional
              "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQC... user@host"
            ],
            "password": "plaintextpassword",  # Optional, will be hashed
            "password_hash": "$6$...",  # Optional, pre-hashed password
            "sudo": "NOPASSWD:ALL",  # Optional, sudo configuration
            "lock": false  # Optional, lock account (default false)
          }
        ],
        "disable_users": ["ubuntu", "centos"],  # Optional, lock these users
        "delete_users": ["test"],  # Optional, delete these users
      }
    """
    logger = getattr(self, "logger", None)

    def _log(level: str, msg: str) -> None:
        if logger:
            with contextlib.suppress(Exception):
                getattr(logger, level)(msg)

    _log("debug", "👤 user-config: inject_user_config(): enter")

    # Get configuration
    config = getattr(self, "user_config_inject", None)
    if config is None:
        _log("debug", "👤 user-config: no user_config_inject set; skipping")
        return {"injected": False, "reason": "no_config"}

    if not isinstance(config, dict):
        _log("warning", f"👤 user-config: user_config_inject is not a dict: {type(config).__name__}")
        return {"injected": False, "reason": "invalid_config"}

    dry = bool(getattr(self, "dry_run", False))
    _log("debug", f"👤 user-config: dry_run={dry}")

    results: dict[str, Any] = {
        "injected": True,
        "dry_run": dry,
        "users_created": [],
        "users_disabled": [],
        "users_deleted": [],
        "ssh_keys_deployed": 0,
        "sudo_configured": [],
    }

    users = config.get("users", [])
    disable_users = config.get("disable_users", [])
    delete_users = config.get("delete_users", [])

    if not users and not disable_users and not delete_users:
        _log("warning", "👤 user-config: no users, disable_users, or delete_users provided")
        return {"injected": False, "reason": "no_config"}

    # Mount secondary fstab partitions (/home, /var, etc.) so useradd -m works
    mounted_extra = _mount_fstab_secondary(g, logger)

    # Process user creation, then disable/delete requests
    _process_user_creation(g, logger, users, dry, results)
    _process_user_disable(g, logger, disable_users, dry, results)
    _process_user_delete(g, logger, delete_users, dry, results)

    # Unmount secondary partitions
    _umount_fstab_secondary(g, logger, mounted_extra)

    _log(
        "info",
        f"👤 user-config: injection complete; "
        f"created={len(results['users_created'])}, "
        f"disabled={len(results['users_disabled'])}, "
        f"deleted={len(results['users_deleted'])}",
    )
    return results


def _process_user_creation(
    g: guestfs.GuestFS, logger: Any, users: list[dict[str, Any]], dry: bool, results: dict[str, Any]
) -> None:
    """Create each configured user account, recording results (or dry-run intent)."""

    def _log(level: str, msg: str) -> None:
        if logger:
            with contextlib.suppress(Exception):
                getattr(logger, level)(msg)

    for user_config in users:
        username = user_config.get("name")
        if not username:
            _log("warning", "👤 user-config: user has no name, skipping")
            continue

        if dry:
            _log("info", f"DRY-RUN: would create user: {username}")
            results["users_created"].append(username)
            if user_config.get("ssh_keys"):
                results["ssh_keys_deployed"] += len(user_config["ssh_keys"])
            if user_config.get("sudo"):
                results["sudo_configured"].append(username)
        else:
            try:
                _create_user(g, logger, user_config)
                results["users_created"].append(username)
                _log("info", f"Created user: {username}")

                # Deploy SSH keys
                ssh_keys = user_config.get("ssh_keys", [])
                if ssh_keys:
                    _deploy_ssh_keys(g, logger, username, ssh_keys, user_config.get("home"))
                    results["ssh_keys_deployed"] += len(ssh_keys)

                # Configure sudo
                sudo_spec = user_config.get("sudo")
                if sudo_spec:
                    _configure_sudo(g, logger, username, sudo_spec)
                    results["sudo_configured"].append(username)

            except Exception as e:
                _log(
                    "error",
                    f"Failed to create user '{username}' in the guest filesystem: {e}. "
                    "The user account will not be available after migration. "
                    "Create the user manually after first boot with: useradd -m {username}".format(
                        username=username
                    ),
                )
                raise


def _process_user_disable(
    g: guestfs.GuestFS, logger: Any, disable_users: list[str], dry: bool, results: dict[str, Any]
) -> None:
    """Lock each requested user account, recording results (or dry-run intent)."""

    def _log(level: str, msg: str) -> None:
        if logger:
            with contextlib.suppress(Exception):
                getattr(logger, level)(msg)

    for username in disable_users:
        if dry:
            _log("info", f"DRY-RUN: would disable user: {username}")
            results["users_disabled"].append(username)
        else:
            try:
                _disable_user(g, logger, username)
                results["users_disabled"].append(username)
                _log("info", f"Disabled user: {username}")
            except Exception as e:  # pylint: disable=broad-exception-caught  # per-user best-effort disable; must not abort remaining users
                _log(
                    "warning",
                    f"Failed to disable user '{username}' in the guest: {e}. "
                    "The account remains active. After boot, disable it with: usermod -L {username}".format(
                        username=username
                    ),
                )


def _process_user_delete(
    g: guestfs.GuestFS, logger: Any, delete_users: list[str], dry: bool, results: dict[str, Any]
) -> None:
    """Delete each requested user account, recording results (or dry-run intent)."""

    def _log(level: str, msg: str) -> None:
        if logger:
            with contextlib.suppress(Exception):
                getattr(logger, level)(msg)

    for username in delete_users:
        if dry:
            _log("info", f"DRY-RUN: would delete user: {username}")
            results["users_deleted"].append(username)
        else:
            try:
                _delete_user(g, logger, username)
                results["users_deleted"].append(username)
                _log("info", f"Deleted user: {username}")
            except Exception as e:  # pylint: disable=broad-exception-caught  # per-user best-effort delete; must not abort remaining users
                _log(
                    "warning",
                    f"Failed to delete user '{username}' from the guest: {e}. "
                    "The account remains in /etc/passwd. After boot, delete it with: userdel -r {username}".format(
                        username=username
                    ),
                )


def _filter_valid_groups(g: guestfs.GuestFS, logger: Any, groups: list[str]) -> list[str]:
    """Filter requested group names down to those that exist in the guest's /etc/group."""

    def _log(level: str, msg: str) -> None:
        if logger:
            with contextlib.suppress(Exception):
                getattr(logger, level)(msg)

    if not groups:
        return []
    try:
        group_content = g.read_file("/etc/group").decode("utf-8")
        existing_groups = {line.split(":")[0] for line in group_content.splitlines() if ":" in line}
        valid_groups = []
        for grp in groups:
            if grp in existing_groups:
                valid_groups.append(grp)
            else:
                _log("debug", f"Skipping group '{grp}' (not found in guest /etc/group)")
        return valid_groups
    except Exception:  # pylint: disable=broad-exception-caught  # best-effort group validation; fall back to the unfiltered group list
        return list(groups)


def _build_useradd_cmd(  # pylint: disable=too-many-arguments,too-many-positional-arguments  # mirrors the many independent useradd(8) options
    username: str,
    uid: int | None,
    gid: int | None,
    valid_groups: list[str],
    comment: str,
    shell: str,
    home: str,
    create_home: bool,
) -> list[str]:
    """Build a useradd command line from the resolved user fields."""
    cmd = ["useradd"]
    if uid:
        cmd.extend(["-u", str(uid)])
    if gid:
        cmd.extend(["-g", str(gid)])
    if valid_groups:
        cmd.extend(["-G", ",".join(valid_groups)])
    if comment:
        cmd.extend(["-c", comment])
    if shell:
        cmd.extend(["-s", shell])
    if home:
        cmd.extend(["-d", home])
    if create_home:
        cmd.append("-m")
    else:
        cmd.append("-M")
    cmd.append(username)
    return cmd


def _create_user(  # pylint: disable=too-many-locals  # unpacks many independent optional user_config fields
    g: guestfs.GuestFS, logger: Any, user_config: dict[str, Any]
) -> None:
    """Create a user account with specified configuration"""

    def _log(level: str, msg: str) -> None:
        if logger:
            with contextlib.suppress(Exception):
                getattr(logger, level)(msg)

    username = user_config["name"]
    uid = user_config.get("uid")
    gid = user_config.get("gid", uid)
    groups = user_config.get("groups", [])
    comment = user_config.get("comment", "")
    shell = user_config.get("shell", "/bin/bash")
    home = user_config.get("home", f"/home/{username}")
    create_home = user_config.get("create_home", True)
    password = user_config.get("password")
    password_hash = user_config.get("password_hash")
    lock = user_config.get("lock", False)

    valid_groups = _filter_valid_groups(g, logger, groups)
    cmd = _build_useradd_cmd(username, uid, gid, valid_groups, comment, shell, home, create_home)

    # Execute useradd
    try:
        g.command(cmd)
    except Exception as e:  # pylint: disable=broad-exception-caught  # deliberate fallback: any useradd failure triggers manual account creation below
        _log("debug", f"useradd command failed: {e}, trying alternative approach")
        # Fallback: manually edit /etc/passwd, /etc/shadow, /etc/group
        _create_user_manual(g, logger, user_config)
        return

    # Set password if provided
    if password_hash:
        _set_password_hash(g, logger, username, password_hash)
    elif password:
        # Hash the password
        password_hash = _hash_password(password)
        _set_password_hash(g, logger, username, password_hash)

    # Lock account if requested
    if lock:
        try:
            g.command(["usermod", "-L", username])
        except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort lock; account creation already succeeded, must not raise here
            _log("warning", f"Failed to lock user {username}: {e}")


def _manual_write_passwd_entry(  # pylint: disable=too-many-arguments,too-many-positional-arguments  # mirrors the /etc/passwd field layout
    g: guestfs.GuestFS, logger: Any, username: str, uid: int, gid: int, comment: str, home: str, shell: str
) -> None:
    """Append a manually-constructed /etc/passwd entry for the new user."""

    def _log(level: str, msg: str) -> None:
        if logger:
            with contextlib.suppress(Exception):
                getattr(logger, level)(msg)

    try:
        passwd_content = g.read_file("/etc/passwd").decode("utf-8")
        passwd_entry = f"{username}:x:{uid}:{gid}:{comment}:{home}:{shell}\n"
        g.write("/etc/passwd", (passwd_content + passwd_entry).encode("utf-8"))
    except Exception as e:
        _log(
            "error",
            f"Failed to update /etc/passwd for user '{username}': {e}. "
            "Check that the guest filesystem is writable and /etc/passwd exists.",
        )
        raise


def _manual_write_shadow_entry(g: guestfs.GuestFS, logger: Any, username: str, password_hash: str) -> None:
    """Append a manually-constructed /etc/shadow entry for the new user."""

    def _log(level: str, msg: str) -> None:
        if logger:
            with contextlib.suppress(Exception):
                getattr(logger, level)(msg)

    try:
        shadow_content = g.read_file("/etc/shadow").decode("utf-8")
        # Append shadow entry (days since epoch for last password change)
        days_since_epoch = int(time.time() / 86400)
        shadow_entry = f"{username}:{password_hash}:{days_since_epoch}:0:99999:7:::\n"
        g.write("/etc/shadow", (shadow_content + shadow_entry).encode("utf-8"))
    except Exception as e:
        shadow_err_msg = f"Failed to update /etc/shadow for user '{username}': {e}. "
        shadow_err_msg += f"The user password will not be set. After boot, set it with: passwd {username}"
        _log("error", shadow_err_msg)
        raise


def _manual_ensure_user_group(g: guestfs.GuestFS, logger: Any, username: str, gid: int) -> None:
    """Create a private group entry for the user in /etc/group if one doesn't exist."""

    def _log(level: str, msg: str) -> None:
        if logger:
            with contextlib.suppress(Exception):
                getattr(logger, level)(msg)

    try:
        group_content = g.read_file("/etc/group").decode("utf-8")
        # Check if group exists
        if not any(line.startswith(f"{username}:") for line in group_content.splitlines()):
            group_entry = f"{username}:x:{gid}:\n"
            g.write("/etc/group", (group_content + group_entry).encode("utf-8"))
    except Exception as e:
        _log("error", f"Failed to update /etc/group: {e}")
        raise


def _manual_create_home_dir(g: guestfs.GuestFS, logger: Any, home: str, uid: int, gid: int) -> None:
    """Create the user's home directory, populate it from /etc/skel, and set ownership."""

    def _log(level: str, msg: str) -> None:
        if logger:
            with contextlib.suppress(Exception):
                getattr(logger, level)(msg)

    try:
        if not g.is_dir(home):
            g.mkdir_p(home)
            _log("info", f"Created home directory: {home}")
        # Copy skeleton files from /etc/skel if available
        with contextlib.suppress(Exception):
            if g.is_dir("/etc/skel"):
                for skel_file in g.ls("/etc/skel"):
                    skel_src = f"/etc/skel/{skel_file}"
                    skel_dst = f"{home}/{skel_file}"
                    if g.is_file(skel_src) and not g.exists(skel_dst):
                        with contextlib.suppress(Exception):
                            skel_content = g.read_file(skel_src)
                            g.write(skel_dst, skel_content)
        # Set ownership and permissions via chroot command
        with contextlib.suppress(Exception):
            g.command(["chown", "-R", f"{uid}:{gid}", home])
        with contextlib.suppress(Exception):
            g.command(["chmod", "700", home])
    except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort home dir setup; account itself is already created
        _log("warning", f"Failed to create home directory {home}: {e}")


def _create_user_manual(g: guestfs.GuestFS, logger: Any, user_config: dict[str, Any]) -> None:
    """Manually create user by editing /etc/passwd, /etc/shadow, /etc/group"""
    username = user_config["name"]
    uid = user_config.get("uid", 1000)
    gid = user_config.get("gid", uid)
    comment = user_config.get("comment", "")
    shell = user_config.get("shell", "/bin/bash")
    home = user_config.get("home", f"/home/{username}")
    password_hash = user_config.get("password_hash")

    # Hash plain password if provided
    if not password_hash and user_config.get("password"):
        password_hash = _hash_password(user_config["password"])

    # Default to locked if no password provided
    if not password_hash:
        password_hash = "!"

    _manual_write_passwd_entry(g, logger, username, uid, gid, comment, home, shell)
    _manual_write_shadow_entry(g, logger, username, password_hash)
    _manual_ensure_user_group(g, logger, username, gid)

    if user_config.get("create_home", True):
        _manual_create_home_dir(g, logger, home, uid, gid)


def _hash_password(password: str) -> str:
    """Generate SHA-512 password hash (same as mkpasswd -m sha-512)"""
    # Generate salt
    salt = secrets.token_hex(8)
    # Use crypt-compatible SHA-512
    try:
        # crypt is deprecated/removed in Python 3.13+ and may not be installed here;
        # kept as an optional lazy import with an openssl fallback below.
        import crypt  # pylint: disable=import-outside-toplevel,deprecated-module,import-error

        return crypt.crypt(password, f"$6${salt}$")
    except Exception:  # pylint: disable=broad-exception-caught  # crypt may be missing (3.13+) or fail; fall back to openssl below
        # Fallback if crypt module is not available (Python 3.13+)
        # Shell out to openssl which produces a valid crypt(3) $6$ hash
        # pylint: disable=duplicate-code
        # reason: this subprocess.run(...capture_output=True, timeout=10)
        # shape mirrors similar subprocess wrappers in
        # h2kvm/fixers/offline_fixer.py (blkid UUID lookup) --
        # structurally similar by coincidence, not shared logic; keeping
        # independent avoids coupling unrelated subprocess-invocation code
        # paths.
        try:
            result = subprocess.run(
                ["openssl", "passwd", "-6", "-salt", salt, "-stdin"],
                input=password,
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip()
        except Exception:  # pylint: disable=broad-exception-caught  # best-effort openssl fallback; fall through to locked hash below
            pass
        # Last resort: return a locked hash (user must set password manually)
        return "!"


def _set_password_hash(g: guestfs.GuestFS, logger: Any, username: str, password_hash: str) -> None:
    """Set password hash in /etc/shadow"""

    def _log(level: str, msg: str) -> None:
        if logger:
            with contextlib.suppress(Exception):
                getattr(logger, level)(msg)

    try:
        temp_content = f"{username}:{password_hash}\n"
        g.write("/tmp/.chpasswd_temp", temp_content.encode("utf-8"))
        try:
            g.chmod(0o600, "/tmp/.chpasswd_temp")
            g.command(["sh", "-c", "chpasswd -e < /tmp/.chpasswd_temp"])
        finally:
            with contextlib.suppress(Exception):
                g.rm("/tmp/.chpasswd_temp")
    except Exception as e:  # pylint: disable=broad-exception-caught  # chpasswd may fail for many guest-specific reasons; fall back to direct shadow edit below
        _log("debug", f"chpasswd failed, updating /etc/shadow directly: {e}")
        try:
            shadow_content = g.read_file("/etc/shadow").decode("utf-8")
            lines = shadow_content.splitlines()
            new_lines = []
            for line in lines:
                if line.startswith(f"{username}:"):
                    parts = line.split(":")
                    parts[1] = password_hash
                    new_lines.append(":".join(parts))
                else:
                    new_lines.append(line)
            g.write("/etc/shadow", ("\n".join(new_lines) + "\n").encode("utf-8"))
            with contextlib.suppress(Exception):
                g.chmod(0o640, "/etc/shadow")
        except Exception as e2:
            _log("error", f"Failed to set password hash: {e2}")
            raise


def _deploy_ssh_keys(
    g: guestfs.GuestFS, logger: Any, username: str, ssh_keys: list[str], home: str | None = None
) -> None:
    """Deploy SSH public keys to user's authorized_keys"""

    def _log(level: str, msg: str) -> None:
        if logger:
            with contextlib.suppress(Exception):
                getattr(logger, level)(msg)

    if not home:
        home = f"/home/{username}"

    ssh_dir = f"{home}/.ssh"
    authorized_keys = f"{ssh_dir}/authorized_keys"

    # Create .ssh directory
    try:
        if not g.is_dir(ssh_dir):
            g.mkdir_p(ssh_dir)
    except Exception as e:
        _log(
            "error",
            f"Failed to create SSH directory {ssh_dir} for user '{username}': {e}. "
            "SSH key-based login will not work. After boot, manually create the directory: "
            f"mkdir -p {ssh_dir} && chmod 700 {ssh_dir} && chown {username}:{username} {ssh_dir}",
        )
        raise

    # Write authorized_keys
    keys_content = "\n".join(ssh_keys) + "\n"
    try:
        g.write(authorized_keys, keys_content.encode("utf-8"))
        # Set permissions
        try:
            g.command(["chmod", "700", ssh_dir])
            g.command(["chmod", "600", authorized_keys])
            # Try to set ownership
            with contextlib.suppress(Exception):
                g.command(["chown", "-R", f"{username}:{username}", ssh_dir])
        except Exception as e:  # pylint: disable=broad-exception-caught  # keys are already written; permission tweaks are best-effort
            _log("warning", f"Failed to set permissions on SSH files: {e}")
    except Exception as e:
        _log(
            "error",
            f"Failed to write SSH authorized_keys for user '{username}' at {authorized_keys}: {e}. "
            "SSH key-based login will not work. After boot, manually add keys to "
            f"{authorized_keys} with permissions 600.",
        )
        raise


def _configure_sudo(g: guestfs.GuestFS, logger: Any, username: str, sudo_spec: str) -> None:
    """Configure sudo access for user"""

    def _log(level: str, msg: str) -> None:
        if logger:
            with contextlib.suppress(Exception):
                getattr(logger, level)(msg)

    sudoers_dir = "/etc/sudoers.d"
    sudoers_file = f"{sudoers_dir}/{username}"

    # Ensure sudoers.d directory exists
    try:
        if not g.is_dir(sudoers_dir):
            g.mkdir_p(sudoers_dir)
    except Exception as e:  # pylint: disable=broad-exception-caught  # best-effort sudoers.d setup; must not abort the rest of user injection
        _log(
            "warning",
            f"Could not create /etc/sudoers.d directory for user '{username}': {e}. "
            "Sudo access will not be configured. After boot, run: "
            f"echo '{username} {sudo_spec}' > /etc/sudoers.d/{username} && chmod 0440 /etc/sudoers.d/{username}",
        )
        return

    # Create sudoers file
    # If sudo_spec doesn't contain ALL=(, prepend it
    if "ALL=(" not in sudo_spec:
        sudo_spec = f"ALL=(ALL) {sudo_spec}"
    sudoers_content = f"{username} {sudo_spec}\n"
    try:
        g.write(sudoers_file, sudoers_content.encode("utf-8"))
        # Set proper permissions (0440)
        with contextlib.suppress(Exception):
            g.command(["chmod", "0440", sudoers_file])
    except Exception as e:
        _log("error", f"Failed to create sudoers file: {e}")
        raise


def _disable_user(g: guestfs.GuestFS, logger: Any, username: str) -> None:
    """Lock/disable a user account"""

    def _log(level: str, msg: str) -> None:
        if logger:
            with contextlib.suppress(Exception):
                getattr(logger, level)(msg)

    try:
        g.command(["usermod", "-L", username])
    except Exception as e:  # pylint: disable=broad-exception-caught  # usermod may fail for many guest-specific reasons; fall back to direct shadow edit below
        _log("debug", f"usermod failed, locking via /etc/shadow: {e}")
        # Fallback: prefix password hash with !
        try:
            shadow_content = g.read_file("/etc/shadow").decode("utf-8")
            lines = shadow_content.splitlines()
            new_lines = []
            for line in lines:
                if line.startswith(f"{username}:"):
                    parts = line.split(":")
                    if not parts[1].startswith("!"):
                        parts[1] = "!" + parts[1]
                    new_lines.append(":".join(parts))
                else:
                    new_lines.append(line)
            g.write("/etc/shadow", ("\n".join(new_lines) + "\n").encode("utf-8"))
            with contextlib.suppress(Exception):
                g.chmod(0o640, "/etc/shadow")
        except Exception as e2:
            _log("error", f"Failed to disable user: {e2}")
            raise


def _delete_user(g: guestfs.GuestFS, logger: Any, username: str) -> None:
    """Delete a user account"""

    def _log(level: str, msg: str) -> None:
        if logger:
            with contextlib.suppress(Exception):
                getattr(logger, level)(msg)

    try:
        g.command(["userdel", "-r", username])
    except Exception as e:  # pylint: disable=broad-exception-caught  # userdel may fail for many guest-specific reasons; fall back to manual removal below
        _log("debug", f"userdel failed, removing manually: {e}")
        # Fallback: manually remove from passwd/shadow/group
        try:
            # Remove from /etc/passwd
            passwd_content = g.read_file("/etc/passwd").decode("utf-8")
            passwd_lines = [l for l in passwd_content.splitlines() if not l.startswith(f"{username}:")]
            g.write("/etc/passwd", ("\n".join(passwd_lines) + "\n").encode("utf-8"))

            # Remove from /etc/shadow
            shadow_content = g.read_file("/etc/shadow").decode("utf-8")
            shadow_lines = [l for l in shadow_content.splitlines() if not l.startswith(f"{username}:")]
            g.write("/etc/shadow", ("\n".join(shadow_lines) + "\n").encode("utf-8"))
            with contextlib.suppress(Exception):
                g.chmod(0o640, "/etc/shadow")

            # Remove from /etc/group
            group_content = g.read_file("/etc/group").decode("utf-8")
            group_lines = [l for l in group_content.splitlines() if not l.startswith(f"{username}:")]
            g.write("/etc/group", ("\n".join(group_lines) + "\n").encode("utf-8"))

            # Try to remove home directory
            home = f"/home/{username}"
            try:
                if g.is_dir(home):
                    g.command(["rm", "-rf", home])
            except Exception:  # pylint: disable=broad-exception-caught  # home dir removal is best-effort during account cleanup
                pass
        except Exception as e2:
            _log("error", f"Failed to delete user: {e2}")
            raise
