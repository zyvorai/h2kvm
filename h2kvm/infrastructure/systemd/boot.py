# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""
Comprehensive Systemd Boot Path Integration
============================================

Advanced integration with systemd boot-time tools for VM preparation:
- systemd-repart: Automatic partition management
- systemd-growfs: Filesystem growth at boot
- systemd-makefs: On-demand filesystem creation
- systemd-mount: Systemd mount units
- systemd-firstboot: First boot configuration
- systemd-tmpfiles: Temporary file management
- systemd-remount-fs: Root filesystem remount
- systemd-bootchart: Boot performance analysis
- Boot environment recovery tools
"""

import importlib.util
import logging
import subprocess
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Optional

try:
    SYSTEMD_AVAILABLE = (
        importlib.util.find_spec("systemd.daemon") is not None
        and importlib.util.find_spec("systemd.journal") is not None
    )
except ImportError:
    SYSTEMD_AVAILABLE = False


class PartitionType(Enum):
    """GPT partition type GUIDs"""

    ESP = "c12a7328-f81f-11d2-ba4b-00a0c93ec93b"  # EFI System Partition
    XBOOTLDR = "bc13c2ff-59e6-4262-a352-b275fd6f7172"  # Extended Boot Loader
    ROOT_X86_64 = "4f68bce3-e8cd-4db1-96e7-fbcaf984b709"  # Root x86-64
    ROOT_ARM64 = "b921b045-1df0-41c3-af44-4c6f280d3fae"  # Root ARM64
    HOME = "933ac7e1-2eb4-4f13-b844-0e14e2aef915"  # Home partition
    VAR = "4d21b016-b534-45c2-a9fb-5c16e091fd2d"  # /var partition
    TMP = "7ec6f557-3bc5-4aca-b293-16ef5df639d1"  # /tmp partition
    SWAP = "0657fd6d-a4ab-43c4-84e5-0933c84b4f4f"  # Swap partition
    DATA = "0fc63daf-8483-4772-8e79-3d69d8477de4"  # Linux filesystem data
    LVM = "e6d6d379-f507-44c2-a23c-238f2a3df928"  # LVM PV
    RAID = "a19d880f-05fc-4d3b-a006-743f0f84911e"  # Linux RAID


class FilesystemType(Enum):
    """Supported filesystem types"""

    EXT4 = "ext4"
    XFS = "xfs"
    BTRFS = "btrfs"
    VFAT = "vfat"
    SWAP = "swap"
    TMPFS = "tmpfs"


class BootType(Enum):
    """Boot firmware type"""

    BIOS = "bios"
    UEFI = "uefi"
    UNKNOWN = "unknown"


class SystemdUnitType(Enum):
    """Systemd unit types"""

    SERVICE = "service"
    MOUNT = "mount"
    TIMER = "timer"
    PATH = "path"
    SLICE = "slice"
    TARGET = "target"


@dataclass
class PartitionDefinition:
    """Definition for systemd-repart partition"""

    type: PartitionType
    size_min: str  # e.g., "512M", "10G"
    size_max: str = ""  # Empty means grow to fill
    filesystem: Optional[FilesystemType] = None
    label: str = ""
    priority: int = 1000
    weight: int = 100
    grow: bool = True
    read_only: bool = False
    encrypt: Optional[str] = None  # Encryption method
    copy_blocks: Optional[str] = None  # Source to copy from
    make_directories: list[str] = field(default_factory=list)


@dataclass
class MountConfiguration:
    """Configuration for systemd mount unit"""

    what: str  # Device or source
    where: str  # Mount point
    type: FilesystemType
    options: list[str] = field(default_factory=lambda: ["defaults"])
    wanted_by: str = "local-fs.target"
    requires: list[str] = field(default_factory=list)
    after: list[str] = field(default_factory=list)
    before: list[str] = field(default_factory=list)
    timeout_sec: int = 90


@dataclass
class BootEnvironment:
    """Boot environment configuration"""

    boot_type: BootType
    root_device: str
    root_fstype: FilesystemType
    kernel_cmdline: list[str] = field(default_factory=list)
    initrd_modules: list[str] = field(default_factory=list)
    machine_id: Optional[str] = None
    hostname: Optional[str] = None


class SystemdRepartManager:
    """Manage systemd-repart for automatic partition management"""

    REPART_DIR = Path("/etc/repart.d")

    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.REPART_DIR.mkdir(parents=True, exist_ok=True)

    def create_partition_config(
        self, definition: PartitionDefinition, filename: Optional[str] = None
    ) -> Path:
        """Create partition definition file

        Args:
            definition: Partition definition
            filename: Output filename (auto-generated if None)

        Returns:
            Path to created config file
        """
        if not filename:
            label = definition.label or definition.type.name.lower()
            filename = f"10-{label}.conf"

        config_path = self.REPART_DIR / filename

        config = f"""[Partition]
Type={definition.type.value}
Label={definition.label or definition.type.name}
SizeMinBytes={definition.size_min}
"""

        if definition.size_max:
            config += f"SizeMaxBytes={definition.size_max}\n"

        if definition.filesystem:
            config += f"Format={definition.filesystem.value}\n"

        if definition.copy_blocks:
            config += f"CopyBlocks={definition.copy_blocks}\n"

        if definition.read_only:
            config += "ReadOnly=yes\n"

        if definition.encrypt:
            config += f"Encrypt={definition.encrypt}\n"

        config += f"Priority={definition.priority}\n"
        config += f"Weight={definition.weight}\n"

        if definition.make_directories:
            for directory in definition.make_directories:
                config += f"MakeDirectories={directory}\n"

        config_path.write_text(config)
        self.logger.info(f"Created repart config: {config_path}")

        return config_path

    def create_standard_layout(
        self, boot_type: BootType = BootType.UEFI, disk_size_gb: int = 50
    ) -> list[Path]:
        """Create standard partition layout

        Args:
            boot_type: BIOS or UEFI
            disk_size_gb: Total disk size for sizing

        Returns:
            List of created config files
        """
        configs = []

        # ESP/Boot partition
        if boot_type == BootType.UEFI:
            esp = PartitionDefinition(
                type=PartitionType.ESP,
                size_min="512M",
                size_max="1G",
                filesystem=FilesystemType.VFAT,
                label="ESP",
            )
            configs.append(self.create_partition_config(esp, "00-esp.conf"))

        # Root partition
        root = PartitionDefinition(
            type=PartitionType.ROOT_X86_64,
            size_min="10G",
            size_max=f"{disk_size_gb - 2}G",  # Leave space for swap
            filesystem=FilesystemType.EXT4,
            label="root",
            grow=True,
        )
        configs.append(self.create_partition_config(root, "10-root.conf"))

        # Swap partition
        swap_size = min(8, disk_size_gb // 10)  # 10% up to 8GB
        swap = PartitionDefinition(
            type=PartitionType.SWAP,
            size_min=f"{swap_size}G",
            size_max=f"{swap_size}G",
            filesystem=FilesystemType.SWAP,
            label="swap",
            grow=False,
        )
        configs.append(self.create_partition_config(swap, "20-swap.conf"))

        return configs

    def apply_repart(self, device: str, dry_run: bool = True) -> bool:
        """Apply repart configuration to device

        Args:
            device: Block device path (e.g., /dev/vda)
            dry_run: If True, only show what would be done

        Returns:
            True if successful
        """
        try:
            cmd = ["systemd-repart"]
            if dry_run:
                cmd.append("--dry-run=yes")
            else:
                cmd.append("--dry-run=no")

            cmd.append(device)

            result = subprocess.run(cmd, capture_output=True, text=True, check=False)

            if result.returncode == 0:
                self.logger.info(f"Repart {'simulation' if dry_run else 'application'} successful")
                self.logger.debug(result.stdout)
                return True
            self.logger.error(f"Repart failed: {result.stderr}")
            return False

        except Exception as e:
            self.logger.exception(f"Failed to apply repart: {e}")
            return False


class SystemdGrowfsManager:
    """Manage automatic filesystem growth at boot"""

    def __init__(self):
        self.logger = logging.getLogger(__name__)

    def configure_growfs(self, mount_configs: list[MountConfiguration]) -> list[Path]:
        """Configure filesystems for automatic growth

        Args:
            mount_configs: List of mount configurations to enable growfs for

        Returns:
            List of created unit drop-in files
        """
        created_files = []

        for config in mount_configs:
            if config.type in [FilesystemType.EXT4, FilesystemType.XFS, FilesystemType.BTRFS]:
                mount_unit = self._get_mount_unit_name(config.where)
                dropin_dir = Path(f"/etc/systemd/system/{mount_unit}.d")
                dropin_dir.mkdir(parents=True, exist_ok=True)

                dropin_file = dropin_dir / "growfs.conf"
                dropin_content = """[Mount]
# Automatically grow filesystem to partition size at boot
Options=x-systemd.growfs
"""
                dropin_file.write_text(dropin_content)
                created_files.append(dropin_file)

                self.logger.info(f"Configured growfs for {config.where}")

        return created_files

    @staticmethod
    def _get_mount_unit_name(mount_point: str) -> str:
        """Convert mount point to systemd unit name"""
        # Remove leading slash and replace remaining slashes with dashes
        unit_name = mount_point.lstrip("/").replace("/", "-")
        if not unit_name:
            unit_name = "-"  # Root mount
        return f"{unit_name}.mount"


class SystemdMakefsManager:
    """Manage on-demand filesystem creation"""

    def __init__(self):
        self.logger = logging.getLogger(__name__)

    def configure_makefs(self, configs: list[MountConfiguration]) -> list[Path]:
        """Configure filesystems for on-demand creation

        Args:
            configs: Mount configurations

        Returns:
            List of created unit drop-in files
        """
        created_files = []

        for config in configs:
            mount_unit = SystemdGrowfsManager._get_mount_unit_name(config.where)
            dropin_dir = Path(f"/etc/systemd/system/{mount_unit}.d")
            dropin_dir.mkdir(parents=True, exist_ok=True)

            dropin_file = dropin_dir / "makefs.conf"
            dropin_content = f"""[Mount]
# Automatically create filesystem if it doesn't exist
Options=x-systemd.makefs
Type={config.type.value}
"""
            dropin_file.write_text(dropin_content)
            created_files.append(dropin_file)

            self.logger.info(f"Configured makefs for {config.where}")

        return created_files


class SystemdMountManager:
    """Manage systemd mount units"""

    SYSTEM_DIR = Path("/etc/systemd/system")

    def __init__(self):
        self.logger = logging.getLogger(__name__)

    def create_mount_unit(self, config: MountConfiguration) -> Path:
        """Create systemd mount unit

        Args:
            config: Mount configuration

        Returns:
            Path to created unit file
        """
        unit_name = SystemdGrowfsManager._get_mount_unit_name(config.where)
        unit_path = self.SYSTEM_DIR / unit_name

        options = ",".join(config.options)

        unit_content = f"""[Unit]
Description=Mount {config.where}
Documentation=man:systemd.mount(5)
"""

        if config.requires:
            unit_content += f"Requires={' '.join(config.requires)}\n"

        if config.after:
            unit_content += f"After={' '.join(config.after)}\n"

        if config.before:
            unit_content += f"Before={' '.join(config.before)}\n"

        unit_content += f"""
[Mount]
What={config.what}
Where={config.where}
Type={config.type.value}
Options={options}
TimeoutSec={config.timeout_sec}

[Install]
WantedBy={config.wanted_by}
"""

        unit_path.write_text(unit_content)
        self.logger.info(f"Created mount unit: {unit_path}")

        return unit_path

    def enable_mount(self, mount_point: str) -> bool:
        """Enable mount unit

        Args:
            mount_point: Mount point path

        Returns:
            True if successful
        """
        try:
            unit_name = SystemdGrowfsManager._get_mount_unit_name(mount_point)
            subprocess.run(["systemctl", "enable", unit_name], check=True)
            self.logger.info(f"Enabled mount unit: {unit_name}")
            return True
        except subprocess.CalledProcessError as e:
            self.logger.exception(f"Failed to enable mount unit: {e}")
            return False


class SystemdFirstBootManager:
    """Manage first boot configuration with systemd-firstboot"""

    def __init__(self):
        self.logger = logging.getLogger(__name__)

    def configure_firstboot(
        self,
        root_path: str = "/",
        hostname: Optional[str] = None,
        timezone: Optional[str] = None,
        locale: Optional[str] = None,
        keymap: Optional[str] = None,
        root_password: Optional[str] = None,
        root_shell: Optional[str] = None,
    ) -> bool:
        """Configure system for first boot

        Args:
            root_path: Root filesystem path
            hostname: System hostname
            timezone: System timezone
            locale: System locale
            keymap: Console keymap
            root_password: Root password (hashed)
            root_shell: Root shell path

        Returns:
            True if successful
        """
        try:
            cmd = ["systemd-firstboot", f"--root={root_path}"]

            if hostname:
                cmd.extend(["--hostname", hostname])

            if timezone:
                cmd.extend(["--timezone", timezone])

            if locale:
                cmd.extend(["--locale", locale])

            if keymap:
                cmd.extend(["--keymap", keymap])

            if root_password:
                cmd.extend(["--root-password-hashed", root_password])

            if root_shell:
                cmd.extend(["--root-shell", root_shell])

            result = subprocess.run(cmd, capture_output=True, text=True, check=False)

            if result.returncode == 0:
                self.logger.info("First boot configuration successful")
                return True
            self.logger.error(f"First boot configuration failed: {result.stderr}")
            return False

        except Exception as e:
            self.logger.exception(f"Failed to configure first boot: {e}")
            return False

    def setup_machine_id(self, root_path: str = "/") -> Optional[str]:
        """Setup machine ID

        Args:
            root_path: Root filesystem path

        Returns:
            Machine ID if successful
        """
        try:
            cmd = ["systemd-machine-id-setup", f"--root={root_path}"]
            result = subprocess.run(cmd, capture_output=True, text=True, check=False)

            if result.returncode == 0:
                machine_id_file = Path(root_path) / "etc/machine-id"
                if machine_id_file.exists():
                    machine_id = machine_id_file.read_text().strip()
                    self.logger.info(f"Machine ID setup: {machine_id}")
                    return machine_id

            self.logger.error(f"Failed to setup machine ID: {result.stderr}")
            return None

        except Exception as e:
            self.logger.exception(f"Failed to setup machine ID: {e}")
            return None


class SystemdTmpfilesManager:
    """Manage temporary files with systemd-tmpfiles"""

    TMPFILES_DIR = Path("/etc/tmpfiles.d")

    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.TMPFILES_DIR.mkdir(parents=True, exist_ok=True)

    def create_tmpfiles_config(
        self, name: str, entries: list[tuple[str, str, str, str, str, str, str]]
    ) -> Path:
        """Create tmpfiles.d configuration

        Args:
            name: Config file name
            entries: List of (type, path, mode, user, group, age, argument) tuples

        Returns:
            Path to created config file
        """
        config_path = self.TMPFILES_DIR / f"{name}.conf"

        lines = []
        for entry in entries:
            type_char, path, mode, user, group, age, argument = entry
            line = f"{type_char} {path} {mode} {user} {group} {age} {argument}"
            lines.append(line)

        config_path.write_text("\n".join(lines) + "\n")
        self.logger.info(f"Created tmpfiles config: {config_path}")

        return config_path

    def create_vm_tmpfiles(self) -> Path:
        """Create tmpfiles configuration for VM environment

        Returns:
            Path to created config file
        """
        entries = [
            # Type, Path, Mode, User, Group, Age, Argument
            ("d", "/var/lib/h2kvm", "0755", "root", "root", "-", "-"),
            ("d", "/var/log/h2kvm", "0755", "root", "root", "-", "-"),
            ("d", "/run/h2kvm", "0755", "root", "root", "-", "-"),
            ("d", "/tmp/h2kvm", "1777", "root", "root", "10d", "-"),
            ("L+", "/var/lib/h2kvm/current", "-", "-", "-", "-", "/var/lib/libvirt/images"),
        ]

        return self.create_tmpfiles_config("h2kvm", entries)

    def apply_tmpfiles(self, root_path: str = "/") -> bool:
        """Apply tmpfiles configuration

        Args:
            root_path: Root filesystem path

        Returns:
            True if successful
        """
        try:
            cmd = ["systemd-tmpfiles", "--create", "--remove", f"--root={root_path}"]
            result = subprocess.run(cmd, capture_output=True, text=True, check=False)

            if result.returncode == 0:
                self.logger.info("Tmpfiles applied successfully")
                return True
            self.logger.error(f"Failed to apply tmpfiles: {result.stderr}")
            return False

        except Exception as e:
            self.logger.exception(f"Failed to apply tmpfiles: {e}")
            return False


class SystemdRemountFSManager:
    """Manage root filesystem remount"""

    def __init__(self):
        self.logger = logging.getLogger(__name__)

    def configure_remount_fs(self, root_device: str, fstype: FilesystemType, options: list[str]) -> bool:
        """Configure root filesystem remount

        Args:
            root_device: Root device path
            fstype: Filesystem type
            options: Mount options

        Returns:
            True if successful
        """
        try:
            # Update fstab for root
            fstab_path = Path("/etc/fstab")
            if not fstab_path.exists():
                self.logger.warning("fstab not found")
                return False

            fstab_content = fstab_path.read_text()
            lines = fstab_content.split("\n")

            new_lines = []
            root_found = False

            for line in lines:
                if line.strip() and not line.strip().startswith("#"):
                    fields = line.split()
                    if len(fields) >= 2 and fields[1] == "/":
                        # Update root entry
                        opts = ",".join(options)
                        new_line = f"{root_device} / {fstype.value} {opts} 0 1"
                        new_lines.append(new_line)
                        root_found = True
                        continue

                new_lines.append(line)

            if not root_found:
                # Add root entry
                opts = ",".join(options)
                new_lines.append(f"{root_device} / {fstype.value} {opts} 0 1")

            fstab_path.write_text("\n".join(new_lines))
            self.logger.info("Updated fstab for root remount")

            return True

        except Exception as e:
            self.logger.exception(f"Failed to configure remount-fs: {e}")
            return False


class BootPerformanceAnalyzer:
    """Analyze boot performance using systemd-analyze"""

    def __init__(self):
        self.logger = logging.getLogger(__name__)

    def get_boot_time(self) -> Optional[dict[str, float]]:
        """Get boot time breakdown

        Returns:
            Dictionary with boot time components
        """
        try:
            result = subprocess.run(["systemd-analyze", "time"], capture_output=True, text=True, check=False)

            if result.returncode != 0:
                return None

            # Parse output
            times = {}
            output = result.stdout

            if "firmware" in output:
                times["firmware"] = self._parse_time(output, "firmware")
            if "loader" in output:
                times["loader"] = self._parse_time(output, "loader")
            if "kernel" in output:
                times["kernel"] = self._parse_time(output, "kernel")
            if "userspace" in output:
                times["userspace"] = self._parse_time(output, "userspace")

            return times

        except Exception as e:
            self.logger.exception(f"Failed to get boot time: {e}")
            return None

    def get_critical_chain(self) -> Optional[str]:
        """Get critical boot path

        Returns:
            Critical chain output
        """
        try:
            result = subprocess.run(
                ["systemd-analyze", "critical-chain"], capture_output=True, text=True, check=False
            )

            if result.returncode == 0:
                return result.stdout
            return None

        except Exception as e:
            self.logger.exception(f"Failed to get critical chain: {e}")
            return None

    def get_blame(self) -> Optional[list[tuple[float, str]]]:
        """Get services by initialization time

        Returns:
            List of (time, service) tuples sorted by time
        """
        try:
            result = subprocess.run(
                ["systemd-analyze", "blame"], capture_output=True, text=True, check=False
            )

            if result.returncode != 0:
                return None

            blame = []
            for line in result.stdout.split("\n"):
                line = line.strip()
                if not line:
                    continue

                parts = line.split(None, 1)
                if len(parts) == 2:
                    time_str, service = parts
                    time_ms = self._time_to_ms(time_str)
                    if time_ms is not None:
                        blame.append((time_ms, service))

            return sorted(blame, reverse=True)

        except Exception as e:
            self.logger.exception(f"Failed to get blame: {e}")
            return None

    @staticmethod
    def _parse_time(text: str, component: str) -> float:
        """Parse time from systemd-analyze output"""
        import re

        pattern = f"{component}\\s*=\\s*([\\d.]+)(ms|s|min)"
        match = re.search(pattern, text)
        if match:
            value = float(match.group(1))
            unit = match.group(2)
            if unit == "s":
                value *= 1000
            elif unit == "min":
                value *= 60000
            return value
        return 0.0

    @staticmethod
    def _time_to_ms(time_str: str) -> Optional[float]:
        """Convert time string to milliseconds"""
        time_str = time_str.strip()
        if time_str.endswith("ms"):
            return float(time_str[:-2])
        if time_str.endswith("s"):
            return float(time_str[:-1]) * 1000
        if time_str.endswith("min"):
            return float(time_str[:-3]) * 60000
        return None


class BootEnvironmentRecovery:
    """Boot environment recovery tools"""

    def __init__(self):
        self.logger = logging.getLogger(__name__)

    def generate_rescue_target(self, root_path: str = "/") -> Path:
        """Generate rescue.target drop-in for VM recovery

        Args:
            root_path: Root filesystem path

        Returns:
            Path to created drop-in file
        """
        dropin_dir = Path(root_path) / "etc/systemd/system/rescue.target.d"
        dropin_dir.mkdir(parents=True, exist_ok=True)

        dropin_file = dropin_dir / "vm-recovery.conf"
        dropin_content = """[Unit]
Description=VM Recovery Mode
Documentation=man:systemd.special(7)

# Additional recovery services
Wants=systemd-fsck-root.service
Wants=systemd-fsck@.service
After=systemd-fsck-root.service
After=systemd-fsck@.service
"""

        dropin_file.write_text(dropin_content)
        self.logger.info(f"Created rescue target drop-in: {dropin_file}")

        return dropin_file

    def create_emergency_shell_override(self, root_path: str = "/") -> Path:
        """Create emergency shell override for VM access

        Args:
            root_path: Root filesystem path

        Returns:
            Path to created drop-in file
        """
        dropin_dir = Path(root_path) / "etc/systemd/system/emergency.service.d"
        dropin_dir.mkdir(parents=True, exist_ok=True)

        dropin_file = dropin_dir / "vm-access.conf"
        dropin_content = """[Service]
# Allow passwordless emergency access for VM recovery
Environment=SYSTEMD_SULOGIN_FORCE=1
StandardInput=tty-force
StandardOutput=inherit
StandardError=inherit
"""

        dropin_file.write_text(dropin_content)
        self.logger.info(f"Created emergency shell override: {dropin_file}")

        return dropin_file

    def verify_boot_environment(self, root_path: str) -> dict[str, Any]:
        """Verify boot environment is ready

        Args:
            root_path: Root filesystem path

        Returns:
            Verification results dictionary
        """
        results = {
            "fstab_exists": False,
            "initramfs_exists": False,
            "grub_config_exists": False,
            "machine_id_exists": False,
            "systemd_exists": False,
            "issues": [],
        }

        root = Path(root_path)

        # Check fstab
        fstab = root / "etc/fstab"
        results["fstab_exists"] = fstab.exists()
        if not results["fstab_exists"]:
            results["issues"].append("Missing /etc/fstab")

        # Check initramfs
        boot = root / "boot"
        initramfs_files = list(boot.glob("initramfs-*.img")) + list(boot.glob("initrd.img-*"))
        results["initramfs_exists"] = len(initramfs_files) > 0
        if not results["initramfs_exists"]:
            results["issues"].append("No initramfs found in /boot")

        # Check GRUB
        grub_cfg = root / "boot/grub2/grub.cfg"
        if not grub_cfg.exists():
            grub_cfg = root / "boot/grub/grub.cfg"
        results["grub_config_exists"] = grub_cfg.exists()
        if not results["grub_config_exists"]:
            results["issues"].append("GRUB configuration not found")

        # Check machine-id
        machine_id = root / "etc/machine-id"
        results["machine_id_exists"] = machine_id.exists() and machine_id.stat().st_size > 0
        if not results["machine_id_exists"]:
            results["issues"].append("Machine ID not set")

        # Check systemd
        systemd = root / "usr/lib/systemd/systemd"
        if not systemd.exists():
            systemd = root / "lib/systemd/systemd"
        results["systemd_exists"] = systemd.exists()
        if not results["systemd_exists"]:
            results["issues"].append("systemd binary not found")

        results["ready"] = len(results["issues"]) == 0

        return results


class SystemdBootIntegration:
    """Main integration class combining all systemd boot-time tools"""

    def __init__(self, root_path: str = "/", vm_name: Optional[str] = None):
        """Initialize boot integration

        Args:
            root_path: Root filesystem path for VM
            vm_name: VM name for logging
        """
        self.root_path = root_path
        self.vm_name = vm_name or "unknown"
        self.logger = logging.getLogger(__name__)

        # Initialize all managers
        self.repart = SystemdRepartManager()
        self.growfs = SystemdGrowfsManager()
        self.makefs = SystemdMakefsManager()
        self.mount = SystemdMountManager()
        self.firstboot = SystemdFirstBootManager()
        self.tmpfiles = SystemdTmpfilesManager()
        self.remount = SystemdRemountFSManager()
        self.analyzer = BootPerformanceAnalyzer()
        self.recovery = BootEnvironmentRecovery()

    def prepare_vm_boot_environment(
        self, boot_env: BootEnvironment, setup_machine_id: bool = True, configure_recovery: bool = True
    ) -> dict[str, Any]:
        """Prepare complete VM boot environment

        Args:
            boot_env: Boot environment configuration
            setup_machine_id: Whether to setup machine ID
            configure_recovery: Whether to configure recovery mode

        Returns:
            Results dictionary
        """
        results = {
            "success": False,
            "machine_id": None,
            "tmpfiles_created": False,
            "recovery_configured": False,
            "verification": {},
        }

        try:
            # Setup machine ID
            if setup_machine_id:
                machine_id = self.firstboot.setup_machine_id(self.root_path)
                results["machine_id"] = machine_id

            # Configure hostname if provided
            if boot_env.hostname:
                self.firstboot.configure_firstboot(root_path=self.root_path, hostname=boot_env.hostname)

            # Create tmpfiles
            tmpfiles_path = self.tmpfiles.create_vm_tmpfiles()
            results["tmpfiles_created"] = tmpfiles_path.exists()

            # Configure recovery
            if configure_recovery:
                self.recovery.generate_rescue_target(self.root_path)
                self.recovery.create_emergency_shell_override(self.root_path)
                results["recovery_configured"] = True

            # Verify boot environment
            verification = self.recovery.verify_boot_environment(self.root_path)
            results["verification"] = verification
            results["success"] = verification["ready"]

            if results["success"]:
                self.logger.info(f"VM boot environment prepared successfully for {self.vm_name}")
            else:
                self.logger.warning(f"Boot environment has issues: {verification['issues']}")

        except Exception as e:
            self.logger.exception(f"Failed to prepare boot environment: {e}")
            results["error"] = str(e)

        return results

    def configure_auto_grow_filesystems(self, mount_points: list[str]) -> bool:
        """Configure filesystems for automatic growth

        Args:
            mount_points: List of mount points to enable auto-grow

        Returns:
            True if successful
        """
        try:
            configs = []
            for mount_point in mount_points:
                config = MountConfiguration(
                    what="auto",  # Will be determined from fstab
                    where=mount_point,
                    type=FilesystemType.EXT4,  # Default, will be overridden
                )
                configs.append(config)

            created = self.growfs.configure_growfs(configs)
            self.logger.info(f"Configured auto-grow for {len(created)} filesystems")

            return len(created) > 0

        except Exception as e:
            self.logger.exception(f"Failed to configure auto-grow: {e}")
            return False

    def analyze_boot_performance(self) -> Optional[dict[str, Any]]:
        """Analyze VM boot performance

        Returns:
            Boot performance analysis
        """
        try:
            analysis = {
                "boot_time": self.analyzer.get_boot_time(),
                "critical_chain": self.analyzer.get_critical_chain(),
                "slow_services": [],
            }

            blame = self.analyzer.get_blame()
            if blame:
                # Get top 10 slowest services
                analysis["slow_services"] = [{"time_ms": time, "service": svc} for time, svc in blame[:10]]

            return analysis

        except Exception as e:
            self.logger.exception(f"Failed to analyze boot performance: {e}")
            return None

    def apply_all_features(
        self,
        boot_env: BootEnvironment,
        auto_grow_mounts: Optional[list[str]] = None,
        analyze_performance: bool = False,
    ) -> dict[str, Any]:
        """Apply all systemd boot integration features

        Args:
            boot_env: Boot environment configuration
            auto_grow_mounts: Mount points for auto-grow
            analyze_performance: Whether to analyze boot performance

        Returns:
            Complete results dictionary
        """
        results = {}

        # Prepare boot environment
        results["boot_env"] = self.prepare_vm_boot_environment(boot_env)

        # Configure auto-grow
        if auto_grow_mounts:
            results["auto_grow"] = self.configure_auto_grow_filesystems(auto_grow_mounts)

        # Analyze performance if requested
        if analyze_performance:
            results["performance"] = self.analyze_boot_performance()

        return results


def integrate_with_vm_repair(
    vm_name: str, root_path: str, root_device: str, hostname: Optional[str] = None
) -> bool:
    """Integrate systemd boot features with VM repair workflow

    Args:
        vm_name: VM name
        root_path: Mounted root filesystem path
        root_device: Root device path
        hostname: VM hostname

    Returns:
        True if successful
    """
    logger = logging.getLogger(__name__)

    try:
        # Create boot environment
        boot_env = BootEnvironment(
            boot_type=BootType.UEFI,  # Detect from system
            root_device=root_device,
            root_fstype=FilesystemType.EXT4,  # Detect from mount
            hostname=hostname,
        )

        # Initialize integration
        integration = SystemdBootIntegration(root_path, vm_name)

        # Apply all features
        results = integration.apply_all_features(
            boot_env=boot_env,
            auto_grow_mounts=["/"],  # Enable auto-grow for root
            analyze_performance=False,  # Skip analysis during preparation
        )

        if results.get("boot_env", {}).get("success"):
            logger.info(f"Systemd boot integration successful for {vm_name}")
            return True
        logger.warning(f"Systemd boot integration completed with issues for {vm_name}")
        return False

    except Exception as e:
        logger.exception(f"Failed systemd boot integration: {e}")
        return False
