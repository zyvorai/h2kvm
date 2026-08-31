# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# h2kvm/cli/args/groups.py
"""
Argument group definitions for h2kvm CLI.

Organizes CLI arguments into logical groups (source, target, Azure, VMware, etc.)
for better help text organization and validation.
"""

# pylint: disable=too-many-lines
# One function per CLI argument group keeps each group's flags cohesive and
# easy to find; splitting across files would hurt discoverability more than
# the line count hurts readability.

from __future__ import annotations

import argparse
import os

from h2kvm import __version__
from h2kvm.core.constants import DEFAULT_CONTAINER_ISOLATION, SIZE_1_MIB
from h2kvm.core.utils import effective_cpu_count
from h2kvm.fixers.filesystem.fstab import FstabMode


def _add_global_config_logging(p: argparse.ArgumentParser) -> None:
    # Global config/logging (two-phase parse relies on these)
    p.add_argument(
        "--config",
        action="append",
        default=[],
        help="YAML/JSON config file (repeatable; later overrides earlier).",
    )
    p.add_argument(
        "--manifest",
        dest="manifest",
        default=None,
        help="Manifest JSON file for declarative pipeline workflow. "
        "When specified, uses manifest-driven LOAD→INSPECT→FIX→CONVERT→VALIDATE pipeline "
        "and generates report.json with per-stage results, warnings, and artifact paths.",
    )
    p.add_argument("--dump-config", action="store_true", help="Print merged normalized config and exit.")
    p.add_argument("--dump-args", action="store_true", help="Print final parsed args and exit.")
    p.add_argument("--version", action="version", version=__version__)
    p.add_argument("-v", "--verbose", action="count", default=0, help="Verbosity: -v, -vv")
    p.add_argument("--log-file", dest="log_file", default=None, help="Write logs to file.")
    p.add_argument(
        "--debug",
        dest="debug",
        action="store_true",
        help="Enable extra debug logging (also via env H2KVM_DEBUG=1 / VMDK2KVM_DEBUG=1).",
    )
    p.add_argument(
        "--log-format",
        dest="log_format",
        default="text",
        choices=["text", "json"],
        help="Log output format: text (human-readable, default) or json (structured NDJSON).",
    )


def _add_project_control(p: argparse.ArgumentParser) -> None:
    # Project control: YAML-driven operation (no subcommands)
    p.add_argument(
        "--cmd",
        dest="cmd",
        default=None,
        help="Operation (normally from YAML `cmd:`). Examples: local (alias: migrate), "
        "fetch-and-fix, ova, ovf, vhd, ami, raw, live-fix, libvirt-xml, vsphere, azure, "
        "daemon, generate-systemd",
    )
    p.add_argument(
        "--vs-action",
        dest="vs_action",
        default=None,
        help="vSphere action (normally from YAML `vs_action:`). Examples: list_vm_names, "
        "export_vm, download_only_vm, download_datastore_file, ovftool_export, "
        "ovftool_deploy, ...",
    )


def _add_global_operation_flags(p: argparse.ArgumentParser) -> None:
    # Global operation flags
    p.add_argument("--output-dir", dest="output_dir", default="./out", help="Output directory root.")
    p.add_argument(
        "--dry-run", dest="dry_run", action="store_true", help="Do not modify guest/convert output."
    )
    p.add_argument(
        "--no-backup", dest="no_backup", action="store_true", help="Skip backups inside guest (dangerous)."
    )
    p.add_argument(
        "--print-fstab", dest="print_fstab", action="store_true", help="Print /etc/fstab before+after."
    )
    p.add_argument(
        "--workdir",
        default=None,
        help="Working directory for intermediate files (default: <output-dir>/work).",
    )
    p.add_argument(
        "--conversion-dir",
        dest="conversion_dir",
        default=None,
        help="Directory for VMDK conversion temporary files (default: ~/.cache/h2kvm/conversions).",
    )
    p.add_argument(
        "--cleanup-cache",
        dest="cleanup_cache",
        action="store_true",
        default=True,
        help="Remove cached intermediate conversion files after successful migration (default: enabled).",
    )
    p.add_argument(
        "--no-cleanup-cache",
        dest="cleanup_cache",
        action="store_false",
        help="Keep cached intermediate conversion files after migration.",
    )
    p.add_argument(
        "--allowed-dir",
        dest="allowed_dirs",
        action="append",
        default=[],
        help="Additional directory allowed for VM image access (security). "
        "Can be specified multiple times. Example: --allowed-dir /home/user/vms "
        "Default allowed: /var/lib/libvirt/images, ~/vmware, ~/VirtualBox VMs",
    )


def _add_flatten_convert(p: argparse.ArgumentParser) -> None:
    # Flatten/convert
    p.add_argument(
        "--flatten", action="store_true", help="Flatten snapshot chain into a single working image first."
    )
    p.add_argument(
        "--flatten-format",
        dest="flatten_format",
        default="qcow2",
        choices=["qcow2", "raw"],
        help="Flatten output format.",
    )
    p.add_argument(
        "--to-output",
        dest="to_output",
        default=None,
        help="Convert final working image to this path (relative to output-dir if not absolute).",
    )
    p.add_argument(
        "--out-format",
        dest="out_format",
        default="qcow2",
        choices=["qcow2", "raw", "vdi"],
        help="Output format.",
    )
    p.add_argument("--compress", action="store_true", help="Compression (qcow2 only).")
    p.add_argument(
        "--compress-level",
        dest="compress_level",
        type=int,
        choices=range(1, 10),
        default=None,
        help="Compression level 1-9.",
    )
    p.add_argument("--checksum", action="store_true", help="Compute SHA256 checksum of output.")


def _add_fixing_behavior(p: argparse.ArgumentParser) -> None:
    # Fixing behavior
    p.add_argument(
        "--backend",
        dest="backend",
        default="guestkit",
        choices=["guestkit", "guestfs", "auto"],
        help=(
            "Offline guest fix backend: guestkit (default, GuestKit PyO3 Guestfs), "
            "guestfs (libguestfs), auto (guestkit then guestfs)."
        ),
    )
    p.add_argument(
        "--container-isolation",
        dest="container_isolation",
        action="store_true",
        default=DEFAULT_CONTAINER_ISOLATION,
        help="Run LVM activation inside a container (podman or docker, auto-detected). "
        "Default: enabled. Provides stronger isolation by restricting LVM operations "
        "to the container's namespace.",
    )
    p.add_argument(
        "--no-container-isolation",
        dest="container_isolation",
        action="store_false",
        help="Disable container isolation for LVM activation (run directly on host).",
    )
    p.add_argument(
        "--fstab-mode",
        dest="fstab_mode",
        default=FstabMode.STABILIZE_ALL.value,
        choices=[m.value for m in FstabMode],
        help="fstab rewrite mode: stabilize-all (recommended), bypath-only, noop",
    )
    p.add_argument(
        "--no-grub",
        dest="no_grub",
        action="store_true",
        help="Skip GRUB root= update and device.map cleanup.",
    )
    p.add_argument(
        "--regen-initramfs",
        dest="regen_initramfs",
        action="store_true",
        help="Regenerate initramfs + grub config (best-effort).",
    )
    p.add_argument(
        "--no-regen-initramfs",
        dest="regen_initramfs",
        action="store_false",
        help="Disable initramfs/grub regen.",
    )
    p.set_defaults(regen_initramfs=True)
    p.add_argument(
        "--initramfs-add-drivers",
        dest="initramfs_add_drivers",
        default=None,
        help="Additional kernel modules to include in initramfs (space-separated string or list). "
        "Example: 'nvme e1000e' or ['nvme', 'e1000e']. "
        "Default includes common virtio drivers. Use this to add hardware-specific drivers.",
    )

    p.add_argument(
        "--serial-console",
        dest="serial_console",
        action="store_true",
        help="Inject serial console (console=ttyS0,115200) into kernel cmdline for virsh console access.",
    )
    p.add_argument(
        "--no-serial-console",
        dest="serial_console",
        action="store_false",
        help="Disable serial console injection.",
    )
    p.set_defaults(serial_console=True)

    p.add_argument(
        "--root-password",
        dest="root_password",
        default=None,
        help="Set root password in converted guest (convenience shortcut for user_config_inject).",
    )
    p.add_argument(
        "--ssh-authorized-key",
        dest="ssh_authorized_key",
        default=None,
        help="Deploy SSH authorized key for root in converted guest (convenience shortcut for user_config_inject).",
    )

    p.add_argument(
        "--remove-vmware-tools",
        dest="remove_vmware_tools",
        action="store_true",
        help="Remove VMware tools from guest (Linux only).",
    )
    p.add_argument(
        "--enable-rdp",
        dest="enable_rdp",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Enable Windows Remote Desktop via firstboot (default: on when --guest-os windows or --windows).",
    )
    p.add_argument(
        "--cloud-init-config",
        dest="cloud_init_config",
        default=None,
        help="Cloud-init config (YAML/JSON) to inject.",
    )
    p.add_argument(
        "--firstboot-scripts",
        dest="firstboot_scripts",
        default=None,
        help="Firstboot scripts configuration (YAML/JSON). Creates systemd oneshot "
        "service that runs scripts on first boot and disables itself.",
    )
    p.add_argument(
        "--network-config-inject",
        dest="network_config_inject",
        default=None,
        help="Network configuration injection (YAML/JSON). Injects systemd-networkd "
        "(.network, .netdev) and/or NetworkManager (.nmconnection) files for "
        "static network configuration.",
    )
    p.add_argument(
        "--user-config-inject",
        dest="user_config_inject",
        default=None,
        help="User account configuration (YAML/JSON). Creates users, deploys SSH "
        "keys, configures sudo access, and manages user accounts.",
    )
    p.add_argument(
        "--service-config-inject",
        dest="service_config_inject",
        default=None,
        help="Systemd service configuration (YAML/JSON). Enables, disables, or masks systemd services.",
    )
    p.add_argument(
        "--hostname-config-inject",
        dest="hostname_config_inject",
        default=None,
        help="Hostname and hosts file configuration (YAML/JSON). Sets hostname, domain, and manages /etc/hosts file.",
    )
    p.add_argument(
        "--enable-recovery",
        dest="enable_recovery",
        action="store_true",
        help="Enable checkpoint recovery for long operations.",
    )

    # ✅ Process-based parallelism (no threads): used by Orchestrator.process_disks_parallel
    p.add_argument(
        "--parallel-processing",
        dest="parallel_processing",
        action="store_true",
        help="Process multiple disks in parallel (multi-process).",
    )
    p.add_argument(
        "--workers",
        dest="workers",
        type=int,
        default=min(effective_cpu_count(), 8),
        help=(
            "Max worker PROCESSES when --parallel-processing is set. "
            f"Default: {min(effective_cpu_count(), 8)} (auto-scaled to CPU count, capped at 8). "
            "Also overridable via env H2KVM_WORKERS / VMDK2KVM_WORKERS."
        ),
    )

    p.add_argument("--resize", default=None, help="Resize root filesystem (enlarge only, e.g., +10G or 50G)")
    p.add_argument(
        "--report", default=None, help="Write Markdown report (relative to output-dir if not absolute)."
    )
    p.add_argument(
        "--virtio-drivers-dir",
        dest="virtio_drivers_dir",
        default=None,
        help="Path to virtio-win.iso or extracted driver directory for Windows injection. "
        "If not specified, auto-discovered at /var/lib/h2kvm/virtio-win.iso "
        "(install with: ./scripts/install-deps.sh --virtio-win).",
    )


def _add_windows_virtio_definitions(p: argparse.ArgumentParser) -> None:
    # Windows VirtIO driver *definitions* config (PnP payload discovery)
    p.add_argument(
        "--virtio-config",
        dest="virtio_config_path",
        default=None,
        help=(
            "Windows VirtIO: path to driver-definition config (.yaml/.yml/.json). "
            "Controls driver patterns, PCI IDs, services, bucket mapping, etc. "
            "If unset, baked defaults are used."
        ),
    )
    p.add_argument(
        "--virtio-config-json",
        dest="virtio_config_json",
        default=None,
        help=(
            "Windows VirtIO: inline JSON object for driver-definition overrides (advanced). "
            'Example: --virtio-config-json \'{"drivers":{"storage":[...]}}\''
        ),
    )

    # Multi-stage VirtIO boot deployment
    p.add_argument(
        "--virtio-deploy-boot",
        dest="virtio_deploy_boot",
        action="store_true",
        help=(
            "Enable multi-stage VirtIO boot deployment. "
            "Boots the VM with SATA + VirtIO devices, waits for guest agent "
            "(driver installation), shuts down, verifies drivers offline, "
            "then creates a final VM with VirtIO disk bus."
        ),
    )
    p.add_argument(
        "--virtio-deploy-timeout",
        dest="virtio_deploy_timeout",
        type=int,
        default=180,
        help="Timeout in seconds to wait for QEMU guest agent during staged boot (default: 180).",
    )
    p.add_argument(
        "--no-virtio-deploy-start-final",
        dest="virtio_deploy_start_final",
        action="store_false",
        help="Do not auto-start the final VM after staged VirtIO deployment.",
    )


# Note: h2kvm uses only internal converters and fixers


def _add_windows_network_override(p: argparse.ArgumentParser) -> None:
    # Windows network retention override (first-boot apply)
    p.add_argument(
        "--win-net-override",
        dest="win_net_override",
        default=None,
        help=(
            "Windows: path to JSON network override file on the host. "
            "If set, it is staged into guest as C:\\h2kvm\\net\\network_override.json and applied at first boot."
        ),
    )
    p.add_argument(
        "--win-net-json",
        dest="win_net_json",
        default=None,
        help=(
            "Windows: inline JSON string for network override (advanced). "
            "Useful for systemd/YAML embedding. Example: "
            '--win-net-json \'{"schema":1,"mode":"dhcp","dhcp":{"dns_servers":["10.0.0.53"]}}\''
        ),
    )


def _add_luks_knobs(p: argparse.ArgumentParser) -> None:
    # LUKS knobs
    p.add_argument(
        "--luks-passphrase",
        dest="luks_passphrase",
        default=os.environ.get("H2KVM_LUKS_PASSPHRASE") or os.environ.get("VMDK2KVM_LUKS_PASSPHRASE"),
        help="Passphrase for LUKS-encrypted disks (or set H2KVM_LUKS_PASSPHRASE "
        "/ VMDK2KVM_LUKS_PASSPHRASE env var).",
    )
    p.add_argument(
        "--luks-passphrase-env",
        dest="luks_passphrase_env",
        default=None,
        help="Env var containing LUKS passphrase (overrides --luks-passphrase if set at runtime).",
    )
    p.add_argument(
        "--luks-keyfile",
        dest="luks_keyfile",
        default=None,
        help="Path to LUKS keyfile (binary/text). Overrides passphrase if provided.",
    )
    p.add_argument(
        "--luks-mapper-prefix",
        dest="luks_mapper_prefix",
        default="h2kvm-crypt",
        help="Mapper name prefix for opened LUKS devices (default: h2kvm-crypt).",
    )
    p.add_argument(
        "--luks-enable",
        dest="luks_enable",
        action="store_true",
        help="Explicitly enable LUKS unlocking (otherwise inferred from passphrase/keyfile).",
    )
    p.add_argument(
        "--luks-clevis",
        dest="luks_clevis",
        action="store_true",
        help="Enable Clevis/NBDE auto-unlock for LUKS volumes bound to Tang servers or TPM2.",
    )
    p.add_argument(
        "--luks-clevis-tang-url",
        dest="luks_clevis_tang_url",
        default=None,
        help="Tang server URL for Clevis/NBDE (informational, binding is in LUKS header).",
    )


def _add_tests(p: argparse.ArgumentParser) -> None:
    # Tests
    p.add_argument(
        "--libvirt-test",
        dest="libvirt_test",
        action="store_true",
        help="Libvirt smoke test after conversion.",
    )
    p.add_argument(
        "--qemu-test", dest="qemu_test", action="store_true", help="QEMU smoke test after conversion."
    )
    p.add_argument("--vm-name", dest="vm_name", default="converted-vm", help="VM name for libvirt test.")
    p.add_argument("--memory", type=int, default=2048, help="Memory MiB for tests.")
    p.add_argument("--vcpus", type=int, default=2, help="vCPUs for tests.")
    p.add_argument(
        "--uefi", action="store_true", help="Force UEFI firmware (legacy; prefer --firmware-mode uefi)."
    )
    p.add_argument(
        "--firmware-mode",
        dest="firmware_mode",
        choices=["auto", "bios", "uefi"],
        default="auto",
        help=(
            "Guest firmware for libvirt/KubeVirt deploy: auto (detect from disk/offline analysis), "
            "bios, or uefi."
        ),
    )
    p.add_argument(
        "--firmware-fallback",
        dest="firmware_fallback",
        action=argparse.BooleanOptionalAction,
        default=True,
        help=(
            "After KubeVirt deploy, probe serial console and retry with alternate firmware "
            "(BIOS↔UEFI) if boot fails."
        ),
    )
    p.add_argument(
        "--hyperv-generation",
        dest="hyperv_generation",
        type=int,
        default=None,
        help="Hyper-V VM generation hint (1=BIOS, 2=UEFI) for firmware auto-detection.",
    )
    p.add_argument(
        "--win-secure-boot",
        dest="win_secure_boot",
        action=argparse.BooleanOptionalAction,
        default=None,
        help=(
            "Windows/UEFI: enable Secure Boot in emitted libvirt or KubeVirt domain "
            "(KubeVirt also enables SMM). Omit for auto (Win11+ UEFI, OVF, guest heuristics); "
            "use --no-win-secure-boot to force off (e.g. KubeVirt without SMM)."
        ),
    )
    p.add_argument("--timeout", type=int, default=60, help="Timeout seconds for libvirt state check.")
    p.add_argument(
        "--keep-domain", dest="keep_domain", action="store_true", help="Keep libvirt domain after test."
    )
    p.add_argument("--headless", action="store_true", help="Headless libvirt domain (no graphics).")
    p.add_argument(
        "--health-check",
        dest="health_check",
        action="store_true",
        help="Run post-boot health check after libvirt smoke test (IP detection, guest agent ping).",
    )
    p.add_argument(
        "--health-check-timeout",
        dest="health_check_timeout",
        type=int,
        default=120,
        help="Timeout seconds for post-boot health check (default: 120).",
    )
    p.add_argument(
        "--libvirt-network-config",
        dest="libvirt_network_config",
        type=str,
        default=None,
        help="Libvirt network config as JSON string "
        '(e.g. \'{"name":"migration-net","subnet":"192.168.200.0/24"}\').'
        " YAML config files may provide this as a dict directly.",
    )


def _add_domain_emission(p: argparse.ArgumentParser) -> None:
    # Libvirt domain XML emission (after pipeline)
    p.add_argument(
        "--emit-domain-xml",
        dest="emit_domain_xml",
        action="store_true",
        help="Emit libvirt domain XML for the produced image (written to <output-dir>/libvirt/<vm-name>.xml).",
    )
    p.add_argument(
        "--virsh-define",
        dest="virsh_define",
        action="store_true",
        help="Define the emitted domain using `virsh define` (Linux emitter only, if supported).",
    )
    p.add_argument(
        "--mac-address",
        dest="mac_address",
        default=None,
        help="Preserve MAC address in domain XML (e.g. '52:54:00:ab:cd:ef'). "
        "If not set, libvirt assigns a random MAC.",
    )
    p.add_argument(
        "--force-replace",
        dest="force_replace",
        action="store_true",
        help="Force-replace existing libvirt domain (destroy+undefine) instead of auto-renaming.",
    )

    # Guest kind selection (helps Windows vs Linux)
    p.add_argument(
        "--guest-os",
        dest="guest_os",
        default=None,
        choices=["linux", "windows"],
        help="Guest OS hint for domain XML emission (linux/windows). If unset, heuristics may be used.",
    )
    p.add_argument(
        "--windows",
        dest="windows",
        action="store_true",
        help="Alias hint: treat guest as Windows (domain XML emission).",
    )

    # Common domain knobs (Linux+Windows)
    p.add_argument("--machine", dest="machine", default="q35", help="Libvirt machine type (default: q35).")
    p.add_argument(
        "--graphics",
        dest="graphics",
        default=None,
        help="Graphics type when not headless (default: auto-detect spice/vnc).",
    )
    p.add_argument(
        "--graphics-listen",
        dest="graphics_listen",
        default="127.0.0.1",
        help="Graphics listen address (default: 127.0.0.1). Use 0.0.0.0 for remote consoles (be careful).",
    )
    p.add_argument(
        "--video",
        dest="video",
        default=None,
        help="Video model (Linux default virtio, Windows default qxl if unset by emitter).",
    )
    p.add_argument(
        "--disk-cache", dest="disk_cache", default="none", help="Disk cache mode (default: none)."
    )
    p.add_argument("--net-model", dest="net_model", default="virtio", help="NIC model (default: virtio).")
    p.add_argument(
        "--libvirt-network",
        dest="libvirt_network",
        default="default",
        help="Libvirt network name (default: default).",
    )
    p.add_argument(
        "--usb-tablet",
        dest="usb_tablet",
        action="store_true",
        help="Enable USB tablet input (mainly for graphical consoles).",
    )
    p.add_argument(
        "--no-usb-tablet", dest="usb_tablet", action="store_false", help="Disable USB tablet input."
    )
    p.set_defaults(usb_tablet=True)

    # Firmware paths (used by both; Linux emitter supports templates)
    p.add_argument(
        "--ovmf-code",
        dest="ovmf_code",
        default=None,
        help="Path to OVMF_CODE.fd (auto-detected if not set).",
    )
    p.add_argument(
        "--nvram-vars",
        dest="nvram_vars",
        default=None,
        help="Path to NVRAM vars file (will be copied/created by emitter if supported).",
    )
    p.add_argument(
        "--ovmf-vars-template",
        dest="ovmf_vars_template",
        default=None,
        help="Template vars file for per-VM NVRAM (Linux emitter).",
    )

    # High-performance tuning knobs (Linux domain)
    p.add_argument(
        "--hugepages",
        dest="hugepages",
        action="store_true",
        help="Enable hugepages and locked memory (<memoryBacking><hugepages/><locked/></memoryBacking>).",
    )
    p.add_argument(
        "--iothreads",
        dest="iothreads",
        type=int,
        default=None,
        help="Number of IOThreads (adds <iothreads>N</iothreads> and iothread attr on disk driver).",
    )
    p.add_argument(
        "--disable-memballoon",
        dest="disable_memballoon",
        action="store_true",
        help="Disable memory ballooning (<memballoon model='none'/>).",
    )
    p.add_argument(
        "--cpu-topology",
        dest="cpu_topology",
        default=None,
        help="CPU topology as 'sockets:cores:threads' (e.g. '1:4:1').",
    )
    p.add_argument(
        "--tsc-timer",
        dest="tsc_timer",
        action="store_true",
        help="Add TSC timer with native mode (<timer name='tsc' present='yes' mode='native'/>).",
    )
    p.add_argument(
        "--disk-io",
        dest="disk_io",
        default=None,
        help="Disk I/O mode (e.g. 'native', 'threads').",
    )
    p.add_argument(
        "--disk-discard",
        dest="disk_discard",
        default=None,
        help="Disk discard mode (e.g. 'unmap', 'ignore').",
    )
    p.add_argument(
        "--high-perf",
        dest="high_perf",
        action="store_true",
        help="Convenience flag: enable hugepages, iothreads=1, disable memballoon, TSC timer, "
        "disk io=native, disk discard=unmap. Individual flags override.",
    )

    # Linux-only emission knobs
    p.add_argument(
        "--disk-bus", dest="disk_bus", default="virtio", help="Linux domain: disk bus (default: virtio)."
    )
    p.add_argument(
        "--disk-dev", dest="disk_dev", default="vda", help="Linux domain: disk target dev (default: vda)."
    )
    p.add_argument("--clock", dest="clock", default="utc", help="Linux domain clock (default: utc).")
    p.add_argument(
        "--cloudinit-iso",
        dest="cloudinit_iso",
        default=None,
        help="Attach cloud-init seed ISO (Linux domain emission).",
    )
    p.add_argument(
        "--cloudinit-seed-iso",
        dest="cloudinit_seed_iso",
        default=None,
        help="Alias for --cloudinit-iso (Linux domain emission).",
    )

    # Windows-only emission knobs
    p.add_argument(
        "--win-stage",
        dest="win_stage",
        default="bootstrap",
        choices=["bootstrap", "final"],
        help="Windows domain emission stage: bootstrap (SATA disk, default — safe "
        "first boot) or final (VirtIO disk, after drivers installed).",
    )
    p.add_argument(
        "--win-driver-iso",
        dest="win_driver_iso",
        default=None,
        help="Windows domain: attach virtio-win.iso as CDROM (bootstrap helper).",
    )
    p.add_argument(
        "--virtio-win-iso", dest="virtio_win_iso", default=None, help="Alias for --win-driver-iso"
    )
    p.add_argument("--driver-iso", dest="driver_iso", default=None, help="Alias for --win-driver-iso")
    p.add_argument(
        "--custom-pnp-drivers",
        dest="custom_pnp_drivers",
        action="append",
        default=[],
        help="Custom PnP driver directory or ISO to stage in Windows guest (repeatable). "
        "Drivers are copied to C:\\h2kvm-drivers and installed via pnputil on first boot.",
    )
    p.add_argument(
        "--win-localtime-clock",
        dest="win_localtime_clock",
        action="store_true",
        help="Windows domain: set clock offset to localtime (default on).",
    )
    p.add_argument(
        "--no-win-localtime-clock",
        dest="win_localtime_clock",
        action="store_false",
        help="Windows domain: set clock offset to utc.",
    )
    p.set_defaults(win_localtime_clock=True)
    p.add_argument(
        "--win-hyperv",
        dest="win_hyperv",
        action="store_true",
        help="Windows domain: enable Hyper-V enlightenments (default on).",
    )
    p.add_argument(
        "--no-win-hyperv",
        dest="win_hyperv",
        action="store_false",
        help="Windows domain: disable Hyper-V enlightenments.",
    )
    p.set_defaults(win_hyperv=True)


def _add_daemon_flags(p: argparse.ArgumentParser) -> None:
    # Daemon flags
    p.add_argument("--daemon", action="store_true", help="Run in daemon mode (for systemd service).")
    p.add_argument(
        "--watch-dir",
        dest="watch_dir",
        default=None,
        help="Directory to watch for new VMDK files in daemon mode.",
    )
    p.add_argument(
        "--workflow-mode",
        dest="workflow_mode",
        action="store_true",
        help="Enable 3-directory workflow (to_be_processed → processing → processed).",
    )
    p.add_argument(
        "--workflow-dir",
        dest="workflow_dir",
        default=None,
        help="Base directory for workflow mode (creates subdirs: to_be_processed/, processing/, processed/, failed/).",
    )
    p.add_argument(
        "--max-concurrent-jobs",
        dest="max_concurrent_jobs",
        type=int,
        default=min(effective_cpu_count(), 8),
        help=(
            "Maximum concurrent conversion jobs in daemon mode "
            f"(default: {min(effective_cpu_count(), 8)}, auto-scaled to CPU count, capped at 8)."
        ),
    )
    p.add_argument(
        "--manifest-workflow-mode",
        dest="manifest_workflow_mode",
        action="store_true",
        help="Enable manifest workflow mode (to_be_processed → processing → processed).",
    )
    p.add_argument(
        "--manifest-workflow-dir",
        dest="manifest_workflow_dir",
        default=None,
        help="Base directory for manifest workflow (creates subdirs: "
        "to_be_processed/, processing/, processed/, failed/).",
    )
    p.add_argument(
        "--kubeconfig",
        dest="kubeconfig",
        default=None,
        help="Path to kubeconfig file for KubeVirt deploy in daemon mode (sets KUBECONFIG env).",
    )


def _add_ovf_ova_knobs(p: argparse.ArgumentParser) -> None:
    # OVF/OVA knobs
    p.add_argument(
        "--log-virt-filesystems",
        dest="log_virt_filesystems",
        action="store_true",
        help="For OVA/OVF inputs, log `virt-filesystems --all --long -h` for each disk.",
    )
    p.add_argument(
        "--ova-convert-to-qcow2",
        dest="ova_convert_to_qcow2",
        action="store_true",
        help="For OVA/OVF inputs, convert extracted VMDK(s) to qcow2 before continuing pipeline.",
    )
    p.add_argument(
        "--ova-qcow2-dir",
        dest="ova_qcow2_dir",
        default=None,
        help="Output directory for qcow2 images created from OVA/OVF disks (default: <output-dir>/qcow2).",
    )
    p.add_argument(
        "--ova-convert-compress",
        dest="ova_convert_compress",
        action="store_true",
        help="When converting OVA/OVF disks to qcow2, enable compression.",
    )
    p.add_argument(
        "--ova-convert-compress-level",
        dest="ova_convert_compress_level",
        type=int,
        choices=range(1, 10),
        default=None,
        help="Compression level 1-9 for qcow2 conversion of OVA/OVF disks.",
    )


def _add_ami_extraction_knobs(p: argparse.ArgumentParser) -> None:
    # AMI/cloud tarball extraction knobs
    p.add_argument(
        "--extract-nested-tar",
        dest="extract_nested_tar",
        action="store_true",
        help="For AMI/cloud tarballs: extract one level of nested tarballs (tar-in-tar).",
    )
    p.add_argument(
        "--no-extract-nested-tar",
        dest="extract_nested_tar",
        action="store_false",
        help="Disable nested tar extraction for AMI/cloud tarballs.",
    )
    p.set_defaults(extract_nested_tar=True)
    p.add_argument(
        "--convert-payload-to-qcow2",
        dest="convert_payload_to_qcow2",
        action="store_true",
        help="For AMI/cloud tarballs: convert extracted payload disk(s) to qcow2 before continuing pipeline.",
    )
    p.add_argument(
        "--payload-qcow2-dir",
        dest="payload_qcow2_dir",
        default=None,
        help="Output directory for qcow2 created from AMI/cloud payload disks (default: <output-dir>/qcow2).",
    )


def _add_libvirt_xml_knobs(p: argparse.ArgumentParser) -> None:
    # Libvirt domain XML parsing knobs
    p.add_argument(
        "--libvirt-xml",
        "--xml-path",
        dest="libvirt_xml",
        default=None,
        help="Path to libvirt domain XML file for manifest generation (use with cmd: libvirt-xml in config).",
    )
    p.add_argument(
        "--compute-checksums",
        dest="compute_checksums",
        action="store_true",
        default=True,
        help="Compute SHA256 checksums for disks when parsing libvirt XML (default: enabled).",
    )
    p.add_argument(
        "--no-compute-checksums",
        dest="compute_checksums",
        action="store_false",
        help="Skip checksum computation when parsing libvirt XML.",
    )
    p.add_argument(
        "--manifest-filename",
        dest="manifest_filename",
        default="manifest.json",
        help="Output manifest filename for libvirt-xml mode (default: manifest.json).",
    )


def _add_input_paths(p: argparse.ArgumentParser) -> None:
    # Former subcommand args, promoted to globals (YAML-driven; CLI overrides)
    p.add_argument("--vmdk", default=None, help="Local VMDK path (descriptor OR monolithic/binary VMDK)")
    p.add_argument("--ova", default=None, help="Path to .ova")
    p.add_argument("--ovf", default=None, help="Path to .ovf (disks in same dir)")
    p.add_argument(
        "--vhd",
        default=None,
        help="Path to .vhd/.vhdx file, tarball (.tar/.tar.gz), OR directory "
        "containing multiple .vhd/.vhdx disks (multi-disk Hyper-V).",
    )
    p.add_argument(
        "--ami",
        default=None,
        help="Path to tar/tar.gz/tgz/tar.xz containing a disk payload (raw/img/qcow2/vmdk/vhd/...).",
    )
    p.add_argument(
        "--raw", default=None, help="Path to raw disk image (.raw/.img) OR tarball containing a raw disk."
    )


def _add_ssh_fetch_knobs(p: argparse.ArgumentParser) -> None:
    # fetch-and-fix + live-fix common SSH knobs:
    p.add_argument("--host", default=None, help="Remote host for fetch-and-fix/live-fix")
    p.add_argument("--user", default="root", help="Remote user (fetch-and-fix/live-fix)")
    p.add_argument("--port", type=int, default=22, help="SSH port (fetch-and-fix/live-fix)")
    p.add_argument("--identity", default=None, help="SSH identity key path (fetch-and-fix/live-fix)")
    p.add_argument("--ssh-opt", action="append", default=None, help="Extra ssh/scp options (repeatable).")
    p.add_argument("--remote", default=None, help="Remote path to VMDK descriptor (fetch-and-fix)")
    p.add_argument(
        "--fetch-dir",
        dest="fetch_dir",
        default=None,
        help="Where to store fetched files (default: <output-dir>/downloaded)",
    )
    p.add_argument(
        "--fetch-all",
        dest="fetch_all",
        action="store_true",
        help="Fetch full snapshot descriptor chain recursively.",
    )
    p.add_argument("--sudo", action="store_true", help="Run remote commands through sudo -n (live-fix)")
    p.add_argument(
        "--ssh-password",
        dest="ssh_password",
        default=None,
        help="SSH password (uses sshpass). For non-interactive/automation use.",
    )


def _add_systemd_gen(p: argparse.ArgumentParser) -> None:
    # generate-systemd:
    p.add_argument(
        "--systemd-output",
        dest="systemd_output",
        default=None,
        help="Write systemd unit to file instead of stdout",
    )


def _add_vsphere_core_knobs(p: argparse.ArgumentParser) -> None:
    # vSphere / vCenter knobs (promoted to globals)
    p.add_argument("--vcenter", default=None, help="vCenter/ESXi hostname or IP")
    p.add_argument("--vc-user", dest="vc_user", default=None, help="vCenter username")
    p.add_argument(
        "--vc-password", dest="vc_password", default=None, help="vCenter password (or use --vc-password-env)"
    )
    p.add_argument(
        "--vc-password-env", dest="vc_password_env", default=None, help="Env var containing vCenter password"
    )
    p.add_argument(
        "--vc-port", dest="vc_port", type=int, default=443, help="vCenter HTTPS port (default: 443)"
    )
    p.add_argument("--vc-insecure", dest="vc_insecure", action="store_true", help="Disable TLS verification")
    p.add_argument(
        "--dc-name",
        dest="dc_name",
        default="ha-datacenter",
        help="Datacenter name for /folder URL (default: ha-datacenter)",
    )

    # Export policy knobs (govc path)
    p.add_argument(
        "--export-mode",
        dest="export_mode",
        default=None,
        choices=["ovf_export", "ova_export", "auto", "ovftool_export"],
        help="vSphere export mode preference (export_vm action): ovf_export, ova_export, auto, or ovftool_export.",
    )

    # vSphere control-plane selection: govc vs pyvmomi
    p.add_argument(
        "--vs-control-plane",
        dest="vs_control_plane",
        default="govc",
        choices=["auto", "govc", "pyvmomi"],
        help="vSphere control-plane backend: auto (prefer govc), govc, or pyvmomi.",
    )

    # download-only transport (HTTP/HTTPS only)
    p.add_argument(
        "--vs-download-transport",
        dest="vs_download_transport",
        default="https",
        choices=["https", "http", "auto"],
        help="download-only transport preference (default: https). auto behaves like https.",
    )


def _add_govc_knobs(p: argparse.ArgumentParser) -> None:
    # govc context knobs (CLI overrides; YAML can carry same keys)
    p.add_argument(
        "--govc-url",
        dest="govc_url",
        default=None,
        help="govc URL (e.g. https://vcenter/sdk or https://esxi/sdk).",
    )
    p.add_argument(
        "--govc-user", dest="govc_user", default=None, help="govc username (defaults to vc_user if unset)."
    )
    p.add_argument(
        "--govc-password",
        dest="govc_password",
        default=None,
        help="govc password (defaults to vc_password if unset).",
    )
    p.add_argument(
        "--govc-password-env",
        dest="govc_password_env",
        default=None,
        help="Env var containing govc password.",
    )
    p.add_argument(
        "--govc-insecure", dest="govc_insecure", action="store_true", help="govc: disable TLS verification."
    )
    p.add_argument(
        "--govc-datacenter", dest="govc_datacenter", default=None, help="govc datacenter (GOVC_DATACENTER)."
    )
    p.add_argument("--govc-cluster", dest="govc_cluster", default=None, help="govc cluster (optional).")
    p.add_argument(
        "--govc-folder", dest="govc_folder", default=None, help="govc inventory folder root (optional)."
    )
    p.add_argument("--govc-ds", dest="govc_ds", default=None, help="govc datastore default (optional).")
    p.add_argument(
        "--govc-resource-pool",
        dest="govc_resource_pool",
        default=None,
        help="govc resource pool (optional).",
    )
    p.add_argument(
        "--govc-stdout-json",
        dest="govc_stdout_json",
        action="store_true",
        help="Prefer govc JSON output where supported.",
    )

    # govc export workflow knobs
    p.add_argument(
        "--govc-export-power-off",
        dest="govc_export_power_off",
        action="store_true",
        help="govc export: power off VM before export (force).",
    )
    p.add_argument(
        "--govc-export-shutdown",
        dest="govc_export_shutdown",
        action="store_true",
        help="govc export: guest shutdown before export (best-effort).",
    )
    p.add_argument(
        "--govc-export-shutdown-timeout-s",
        dest="govc_export_shutdown_timeout_s",
        type=float,
        default=300.0,
        help="govc export: shutdown timeout seconds.",
    )
    p.add_argument(
        "--govc-export-shutdown-poll-s",
        dest="govc_export_shutdown_poll_s",
        type=float,
        default=5.0,
        help="govc export: shutdown poll interval seconds.",
    )
    p.add_argument(
        "--govc-export-remove-cdroms",
        dest="govc_export_remove_cdroms",
        action="store_true",
        help="govc export: remove CDROM devices before export (recommended).",
    )
    p.add_argument(
        "--no-govc-export-remove-cdroms",
        dest="govc_export_remove_cdroms",
        action="store_false",
        help="govc export: do NOT remove CDROM devices.",
    )
    p.set_defaults(govc_export_remove_cdroms=True)
    p.add_argument(
        "--govc-export-show-vm-info",
        dest="govc_export_show_vm_info",
        action="store_true",
        help="govc export: print vm.info summary before export.",
    )
    p.add_argument(
        "--no-govc-export-show-vm-info",
        dest="govc_export_show_vm_info",
        action="store_false",
        help="govc export: do NOT print vm.info summary.",
    )
    p.set_defaults(govc_export_show_vm_info=True)
    p.add_argument(
        "--govc-max-detail",
        dest="govc_max_detail",
        type=int,
        default=500,
        help="govc list_vm_names: max VMs to fetch detailed vm.info JSON for.",
    )


def _add_ovftool_knobs(p: argparse.ArgumentParser) -> None:
    # OVF Tool (ovftool) knobs
    p.add_argument(
        "--ovftool-path",
        dest="ovftool_path",
        default=None,
        help="Path to OVF Tool binary or install dir (optional; auto-detect if unset).",
    )
    p.add_argument(
        "--ovftool-no-ssl-verify",
        dest="ovftool_no_ssl_verify",
        action="store_true",
        help="OVF Tool: disable TLS verification (adds --noSSLVerify).",
    )
    p.add_argument(
        "--no-ovftool-no-ssl-verify",
        dest="ovftool_no_ssl_verify",
        action="store_false",
        help="OVF Tool: keep TLS verification (do not add --noSSLVerify).",
    )
    p.set_defaults(ovftool_no_ssl_verify=True)

    p.add_argument(
        "--ovftool-thumbprint",
        dest="ovftool_thumbprint",
        default=None,
        help="OVF Tool: expected TLS thumbprint (e.g. AA:BB:...); used instead of disabling verification.",
    )
    p.add_argument(
        "--ovftool-accept-all-eulas",
        dest="ovftool_accept_all_eulas",
        action="store_true",
        help="OVF Tool: accept all EULAs (adds --acceptAllEulas).",
    )
    p.add_argument(
        "--no-ovftool-accept-all-eulas",
        dest="ovftool_accept_all_eulas",
        action="store_false",
        help="OVF Tool: do NOT accept EULAs automatically.",
    )
    p.set_defaults(ovftool_accept_all_eulas=True)

    p.add_argument(
        "--ovftool-quiet",
        dest="ovftool_quiet",
        action="store_true",
        help="OVF Tool: quiet output (adds --quiet).",
    )
    p.add_argument(
        "--ovftool-verbose",
        dest="ovftool_verbose",
        action="store_true",
        help="OVF Tool: verbose output (adds --verbose).",
    )
    p.add_argument(
        "--ovftool-overwrite",
        dest="ovftool_overwrite",
        action="store_true",
        help="OVF Tool: overwrite outputs / target objects (adds --overwrite).",
    )
    p.add_argument(
        "--ovftool-disk-mode",
        dest="ovftool_disk_mode",
        default=None,
        help="OVF Tool: disk mode for deploy/export where supported (e.g. thin|thick|eagerZeroedThick).",
    )
    p.add_argument(
        "--ovftool-retries",
        dest="ovftool_retries",
        type=int,
        default=3,
        help="OVF Tool wrapper: retry count for transient failures (default 3).",
    )
    p.add_argument(
        "--ovftool-retry-backoff-s",
        dest="ovftool_retry_backoff_s",
        type=float,
        default=2.0,
        help="OVF Tool wrapper: base backoff seconds between retries (default 2.0).",
    )
    p.add_argument(
        "--ovftool-extra-arg",
        dest="ovftool_extra_args",
        action="append",
        default=[],
        help="OVF Tool: extra raw arg passed through as-is (repeatable). "
        "Example: --ovftool-extra-arg=--X:logLevel=verbose",
    )

    # OVF Tool deploy-only targeting knobs
    p.add_argument(
        "--ovftool-target-folder",
        dest="ovftool_target_folder",
        default=None,
        help="OVF Tool deploy: target inventory folder under /vm (relative path). Example: 'Prod/Linux'.",
    )
    p.add_argument(
        "--ovftool-target-resource-pool",
        dest="ovftool_target_resource_pool",
        default=None,
        help="OVF Tool deploy: target resource pool path under /host (advanced; "
        "exact format depends on vCenter inventory).",
    )
    p.add_argument(
        "--ovftool-network-map",
        dest="ovftool_network_map",
        default=None,
        help="OVF Tool deploy: network mapping 'src:dst, src2:dst2'. Example: 'VM Network:KVM-Bridge'.",
    )
    p.add_argument(
        "--ovftool-power-on",
        dest="ovftool_power_on",
        action="store_true",
        help="OVF Tool deploy: power on after deploy.",
    )
    p.add_argument(
        "--ovftool-vm-name",
        dest="ovftool_vm_name",
        default=None,
        help="OVF Tool deploy: override VM name (--name in ovftool).",
    )
    p.add_argument(
        "--ovftool-datastore",
        dest="ovftool_datastore",
        default=None,
        help="OVF Tool deploy: target datastore name.",
    )


def _add_vsphere_export_and_download_knobs(p: argparse.ArgumentParser) -> None:
    # vSphere export knobs, download-only knobs, VDDK knobs...
    p.add_argument(
        "--vs-export",
        dest="vs_export",
        action="store_true",
        help="EXPERIMENTAL: export VM(s) directly from vSphere (VDDK/SSH) and then run normal pipeline.",
    )
    p.add_argument(
        "--vs-vm", dest="vs_vm", default=None, help="VM name to export (alternative to --vm-name)."
    )
    p.add_argument("--vs-vms", dest="vs_vms", nargs="*", default=None, help="Multiple VM names to export.")
    p.add_argument(
        "--vs-datacenter",
        dest="vs_datacenter",
        default="ha-datacenter",
        help="Datacenter name (default: ha-datacenter)",
    )

    # IMPORTANT: no default here (avoids silently selecting VDDK)
    p.add_argument(
        "--vs-transport",
        dest="vs_transport",
        default=None,
        choices=["vddk", "ssh"],
        help="EXPERIMENTAL export transport method (set explicitly).",
    )

    p.add_argument(
        "--vs-vddk-libdir",
        dest="vs_vddk_libdir",
        default=None,
        help="Path to VDDK libdir (if using vddk transport)",
    )
    p.add_argument(
        "--vs-vddk-thumbprint",
        dest="vs_vddk_thumbprint",
        default=None,
        help="vCenter TLS thumbprint for VDDK verification",
    )
    p.add_argument(
        "--vs-snapshot-moref",
        dest="vs_snapshot_moref",
        default=None,
        help="Snapshot MoRef (e.g. snapshot-123) to export from",
    )
    p.add_argument(
        "--vs-create-snapshot",
        dest="vs_create_snapshot",
        action="store_true",
        help="Create a quiesced snapshot before export and use it",
    )

    p.add_argument(
        "--vs-download-only",
        dest="vs_download_only",
        action="store_true",
        help="vSphere export: download/export ONLY (skip inspection/fixes/tests in later pipeline).",
    )
    p.add_argument(
        "--vs-no-download-only",
        dest="vs_download_only",
        action="store_false",
        help="Disable download-only mode (run normal pipeline after export).",
    )
    p.set_defaults(vs_download_only=False)

    p.add_argument(
        "--vs-export-concurrency",
        dest="vs_export_concurrency",
        type=int,
        default=1,
        help="Max concurrent vSphere exports (default: 1).",
    )
    p.add_argument(
        "--vs-no-verify",
        dest="vs_no_verify",
        action="store_true",
        help="Disable TLS verification for vSphere connection (use with caution).",
    )

    p.add_argument(
        "--include-glob",
        dest="vs_include_glob",
        action="append",
        default=[],
        help="download-only VM folder: include file glob (repeatable). Default is ['*'] if none supplied.",
    )
    p.add_argument(
        "--exclude-glob",
        dest="vs_exclude_glob",
        action="append",
        default=[],
        help="download-only VM folder: exclude file glob (repeatable).",
    )
    p.add_argument(
        "--concurrency",
        dest="vs_concurrency",
        type=int,
        default=4,
        help="download-only VM folder: concurrent downloads (default: 4).",
    )
    p.add_argument(
        "--max-files",
        dest="vs_max_files",
        type=int,
        default=5000,
        help="download-only VM folder: refuse to download more than this many files (default: 5000).",
    )

    p.add_argument(
        "--use-async-http",
        dest="vs_use_async_http",
        action="store_true",
        help="download-only VM folder: prefer aiohttp/aiofiles when available.",
    )
    p.add_argument(
        "--no-use-async-http",
        dest="vs_use_async_http",
        action="store_false",
        help="download-only VM folder: disable aiohttp/aiofiles (force requests).",
    )
    p.set_defaults(vs_use_async_http=True)

    p.add_argument(
        "--fail-on-missing",
        dest="vs_fail_on_missing",
        action="store_true",
        help="download-only VM folder: treat any failed/missing download as fatal.",
    )

    # NOTE: These remain for any separate raw-VDDK download actions you may have.
    p.add_argument(
        "--vddk-libdir",
        dest="vs_vddk_libdir2",
        default=None,
        help="EXPERIMENTAL: VDDK raw download: directory containing libvixDiskLib.so (or a parent that contains it).",
    )
    p.add_argument(
        "--vddk-thumbprint",
        dest="vs_vddk_thumbprint2",
        default=None,
        help="EXPERIMENTAL: VDDK raw download: ESXi/vCenter thumbprint (SHA1 AA:BB:..).",
    )
    p.add_argument(
        "--no-verify",
        dest="vs_no_verify2",
        action="store_true",
        help="EXPERIMENTAL: VDDK raw download: disable TLS verification (insecure).",
    )
    p.add_argument(
        "--vddk-transports",
        dest="vs_vddk_transports2",
        default=None,
        help="EXPERIMENTAL: VDDK raw download: transport modes string (e.g. 'nbdssl:nbd').",
    )

    # vSphere action-scoped params (now global)
    p.add_argument(
        "--json", dest="json", action="store_true", help="Output in JSON format (where supported)."
    )
    p.add_argument(
        "--vm_name", dest="vm_name_vsphere", default=None, help="vSphere VM name for actions that require it"
    )
    p.add_argument("--name", dest="name_vsphere", default=None, help="VM name for get_vm_by_name")
    p.add_argument(
        "--label_or_index", dest="label_or_index", default=None, help="Disk label or index for select_disk"
    )
    p.add_argument(
        "--datastore", dest="datastore", default=None, help="Datastore name (download_datastore_file)"
    )
    p.add_argument(
        "--ds_path", dest="ds_path", default=None, help="Datastore path (download_datastore_file)"
    )
    p.add_argument("--local_path", dest="local_path", default=None, help="Local output path (download_*)")
    p.add_argument(
        "--chunk_size",
        dest="chunk_size",
        type=int,
        default=SIZE_1_MIB,
        help="Download chunk size bytes (default 1MiB)",
    )

    p.add_argument(
        "--snapshot_name",
        dest="snapshot_name",
        default=None,
        help="Snapshot name (create_snapshot/query_changed_disk_areas/cbt_sync)",
    )
    p.add_argument(
        "--quiesce",
        dest="quiesce",
        action="store_true",
        default=True,
        help="Quiesce filesystem (create_snapshot)",
    )
    p.add_argument(
        "--no_quiesce", dest="quiesce", action="store_false", help="Disable quiesce (create_snapshot)"
    )
    p.add_argument(
        "--snapshot_memory",
        dest="snapshot_memory",
        action="store_true",
        default=False,
        help="Include memory in snapshot (create_snapshot)",
    )
    p.add_argument(
        "--description",
        dest="snapshot_description",
        default="Created by h2kvm",
        help="Snapshot description (create_snapshot)",
    )

    p.add_argument("--enable_cbt", dest="enable_cbt", action="store_true", help="Enable CBT (cbt_sync)")
    p.add_argument(
        "--device_key",
        dest="device_key",
        type=int,
        default=None,
        help="Device key (query_changed_disk_areas)",
    )
    p.add_argument(
        "--disk",
        dest="disk",
        default=None,
        help="Disk index/label (query_changed_disk_areas/download_vm_disk/cbt_sync/vddk_download_disk)",
    )
    p.add_argument(
        "--start_offset",
        dest="start_offset",
        type=int,
        default=0,
        help="Start offset (query_changed_disk_areas)",
    )
    p.add_argument(
        "--change_id", dest="change_id", default="*", help="Change ID (query_changed_disk_areas/cbt_sync)"
    )

    p.add_argument(
        "--vs_output_dir",
        dest="vs_output_dir",
        default=None,
        help="Local output dir override for download_only_vm (defaults to --output-dir)",
    )

    # OVF Tool deploy action arg (input local OVA/OVF)
    p.add_argument(
        "--source-path",
        dest="source_path",
        default=None,
        help="ovftool_deploy: local source path to .ova or .ovf (required for vs_action=ovftool_deploy).",
    )


def _add_batch_knobs(p: argparse.ArgumentParser) -> None:
    # Batch conversion knobs
    p.add_argument(
        "--batch-manifest",
        dest="batch_manifest",
        default=None,
        help="Path to batch manifest (JSON/YAML) for multi-VM conversion. "
        "When specified, processes multiple VMs in batch with parallel execution support.",
    )
    p.add_argument(
        "--batch-parallel",
        dest="batch_parallel",
        type=int,
        default=None,
        help="Override parallel limit for batch processing (default: from batch manifest or 4).",
    )
    p.add_argument(
        "--batch-continue-on-error",
        dest="batch_continue_on_error",
        action="store_true",
        default=None,
        help="Override continue-on-error behavior for batch (default: from batch manifest or True).",
    )
    p.add_argument(
        "--no-batch-continue-on-error",
        dest="batch_continue_on_error",
        action="store_false",
        help="Stop batch on first VM failure (overrides batch manifest).",
    )


def _add_azure_knobs(p: argparse.ArgumentParser) -> None:
    # Azure VM migration knobs
    p.add_argument(
        "--azure-subscription",
        dest="azure_subscription",
        default=None,
        help="Azure subscription ID (optional; uses current az account if unset)",
    )
    p.add_argument("--azure-tenant", dest="azure_tenant", default=None, help="Azure tenant ID (optional)")

    # VM selection
    p.add_argument(
        "--azure-resource-group",
        dest="azure_resource_group",
        default=None,
        help="Azure resource group (required unless --azure-allow-all-rgs)",
    )
    p.add_argument(
        "--azure-vm-names",
        dest="azure_vm_names",
        nargs="*",
        default=None,
        help="VM name patterns (glob supported, e.g., 'web-*', 'db-prod-01')",
    )
    p.add_argument(
        "--azure-tags",
        dest="azure_tags",
        default=None,
        help="Filter VMs by tags (format: key1=val1, key2=val2)",
    )
    p.add_argument(
        "--azure-power-state",
        dest="azure_power_state",
        default=None,
        help="Filter by power state (running, stopped, deallocated)",
    )
    p.add_argument(
        "--azure-list-only",
        dest="azure_list_only",
        action="store_true",
        help="List VMs only, don't download",
    )
    p.add_argument(
        "--azure-allow-all-rgs",
        dest="azure_allow_all_rgs",
        action="store_true",
        help="Allow searching all resource groups (dangerous)",
    )

    # Shutdown control
    p.add_argument(
        "--azure-shutdown-mode",
        dest="azure_shutdown_mode",
        default="none",
        choices=["none", "stop", "deallocate"],
        help="Shutdown mode: none (default), stop, or deallocate",
    )
    p.add_argument(
        "--azure-shutdown-force",
        dest="azure_shutdown_force",
        action="store_true",
        help="Force shutdown even when using snapshots",
    )
    p.add_argument(
        "--azure-shutdown-wait",
        dest="azure_shutdown_wait",
        action="store_true",
        default=True,
        help="Wait for shutdown to complete",
    )
    p.add_argument(
        "--no-azure-shutdown-wait",
        dest="azure_shutdown_wait",
        action="store_false",
        help="Don't wait for shutdown (async)",
    )

    # Export control
    p.add_argument(
        "--azure-use-snapshots",
        dest="azure_use_snapshots",
        action="store_true",
        default=True,
        help="Use snapshots for zero-downtime migration (default)",
    )
    p.add_argument(
        "--no-azure-use-snapshots",
        dest="azure_use_snapshots",
        action="store_false",
        help="Export directly from disk (requires shutdown)",
    )
    p.add_argument(
        "--azure-stage-disk",
        dest="azure_stage_disk",
        action="store_true",
        help="Create temp disk from snapshot before export (slower but safer)",
    )
    p.add_argument(
        "--azure-disks",
        dest="azure_disks",
        default="all",
        choices=["all", "os", "data"],
        help="Which disks to export: all (default), os, or data",
    )
    p.add_argument(
        "--azure-consistency",
        dest="azure_consistency",
        default="crash_consistent",
        choices=["crash_consistent", "best_effort_quiesce"],
        help="Snapshot consistency: crash_consistent (default) or best_effort_quiesce",
    )
    p.add_argument(
        "--azure-tag-resources",
        dest="azure_tag_resources",
        action="store_true",
        default=True,
        help="Tag created Azure resources (default)",
    )
    p.add_argument(
        "--no-azure-tag-resources",
        dest="azure_tag_resources",
        action="store_false",
        help="Don't tag Azure resources",
    )
    p.add_argument(
        "--azure-keep-snapshots",
        dest="azure_keep_snapshots",
        action="store_true",
        help="Keep snapshots after export (default: delete)",
    )
    p.add_argument(
        "--azure-keep-temp-disks",
        dest="azure_keep_temp_disks",
        action="store_true",
        help="Keep temporary disks after export (default: delete)",
    )
    p.add_argument(
        "--azure-run-tag",
        dest="azure_run_tag",
        default=None,
        help="Custom run tag (default: auto-generated timestamp)",
    )
    p.add_argument(
        "--azure-sas-duration",
        dest="azure_sas_duration",
        type=int,
        default=3600,
        help="SAS token duration in seconds (default: 3600 = 1 hour)",
    )

    # Download control
    p.add_argument(
        "--azure-parallel",
        dest="azure_parallel",
        type=int,
        default=4,
        help="Parallel disk downloads (default: 4)",
    )
    p.add_argument(
        "--azure-chunk-mb",
        dest="azure_chunk_mb",
        type=int,
        default=4,
        help="Download chunk size in MB (default: 4)",
    )
    p.add_argument(
        "--azure-resume",
        dest="azure_resume",
        action="store_true",
        default=True,
        help="Resume interrupted downloads (default)",
    )
    p.add_argument(
        "--no-azure-resume", dest="azure_resume", action="store_false", help="Don't resume downloads"
    )
    p.add_argument(
        "--azure-verify-size",
        dest="azure_verify_size",
        action="store_true",
        default=True,
        help="Verify download size (default)",
    )
    p.add_argument(
        "--no-azure-verify-size",
        dest="azure_verify_size",
        action="store_false",
        help="Don't verify download size",
    )
    p.add_argument(
        "--azure-strict-verify",
        dest="azure_strict_verify",
        action="store_true",
        help="Fail on size mismatch (default: warn only)",
    )
    p.add_argument(
        "--azure-temp-suffix",
        dest="azure_temp_suffix",
        default=".part",
        help="Temp file suffix (default: .part)",
    )
    p.add_argument(
        "--azure-connect-timeout",
        dest="azure_connect_timeout",
        type=int,
        default=30,
        help="Connection timeout in seconds (default: 30)",
    )
    p.add_argument(
        "--azure-read-timeout",
        dest="azure_read_timeout",
        type=int,
        default=300,
        help="Read timeout in seconds (default: 300)",
    )
    p.add_argument(
        "--azure-retries",
        dest="azure_retries",
        type=int,
        default=3,
        help="Download retry attempts (default: 3)",
    )
    p.add_argument(
        "--azure-backoff-base",
        dest="azure_backoff_base",
        type=float,
        default=1.0,
        help="Retry backoff base in seconds (default: 1.0)",
    )
    p.add_argument(
        "--azure-backoff-cap",
        dest="azure_backoff_cap",
        type=float,
        default=60.0,
        help="Retry backoff cap in seconds (default: 60.0)",
    )


def _add_kubernetes_deployment(p: argparse.ArgumentParser) -> None:
    """Kubernetes/k3s deployment options."""
    # Enable deployment
    p.add_argument(
        "--deploy-k8s",
        dest="deploy_k8s",
        action="store_true",
        help="Deploy migrated VM to Kubernetes/k3s cluster with KubeVirt. "
        "Automatically creates namespace, PVC, uploads image, and creates VirtualMachine resource.",
    )

    # Target cluster configuration
    p.add_argument(
        "--k8s-namespace",
        dest="k8s_namespace",
        default="default",
        help="Kubernetes namespace for VM deployment (default: default). Created if doesn't exist.",
    )
    p.add_argument(
        "--k8s-vm-name",
        dest="k8s_vm_name",
        default=None,
        help="VirtualMachine resource name (default: derived from image filename).",
    )
    p.add_argument(
        "--k8s-pvc-name",
        dest="k8s_pvc_name",
        default=None,
        help="PersistentVolumeClaim name for VM disk (default: <vm-name>-disk).",
    )

    # Storage configuration
    p.add_argument(
        "--k8s-storage-class",
        dest="k8s_storage_class",
        default="local-path",
        help="StorageClass for PVC (default: local-path for k3s).",
    )
    p.add_argument(
        "--k8s-pvc-size",
        dest="k8s_pvc_size",
        default="10Gi",
        help="PVC size (default: 10Gi). Should be larger than QCOW2 image.",
    )

    # VM resource configuration
    p.add_argument(
        "--k8s-cpu",
        dest="k8s_cpu",
        default="2",
        help="CPU cores for VM (default: 2).",
    )
    p.add_argument(
        "--k8s-memory",
        dest="k8s_memory",
        default="2Gi",
        help="Memory for VM (default: 2Gi).",
    )
    p.add_argument(
        "--k8s-disk-bus",
        dest="k8s_disk_bus",
        choices=("auto", "virtio", "sata", "scsi"),
        default="auto",
        help=(
            "KubeVirt root disk bus (default: auto). "
            "auto picks SATA when --guest-os windows or --windows is set (same default as libvirt "
            "Windows domains); otherwise virtio. Use explicit virtio/sata/scsi to override."
        ),
    )

    # VM lifecycle
    p.add_argument(
        "--k8s-stop-before-deploy",
        dest="k8s_stop_before_deploy",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="If a KubeVirt VM with the same name already exists: stop any VMI, refresh the "
        "PVC disk, delete the old VirtualMachine object, then recreate the VM (default: true). "
        "Use --no-k8s-stop-before-deploy only when no VM exists or the VM is already halted and "
        "you will remove the VM object yourself before redeploying.",
    )
    p.add_argument(
        "--k8s-stop-wait-timeout",
        dest="k8s_stop_wait_timeout",
        type=int,
        default=600,
        metavar="SEC",
        help="Max seconds to wait for the VMI to terminate after stop (default: 600).",
    )
    p.add_argument(
        "--k8s-auto-start",
        dest="k8s_auto_start",
        action="store_true",
        help="Automatically start VM after creation (default: false).",
    )
    p.add_argument(
        "--k8s-wait-ready",
        dest="k8s_wait_ready",
        action="store_true",
        default=True,
        help="Wait for VM to be ready after start (default: true).",
    )
    p.add_argument(
        "--no-k8s-wait-ready",
        dest="k8s_wait_ready",
        action="store_false",
        help="Don't wait for VM ready status.",
    )
    p.add_argument(
        "--k8s-novnc",
        dest="k8s_novnc",
        action="store_true",
        default=False,
        help="Deploy noVNC web console for browser-based VNC access to the VM.",
    )
    p.add_argument(
        "--k8s-novnc-port",
        dest="k8s_novnc_port",
        type=int,
        default=0,
        help="NodePort for noVNC web console (default: 0 = auto-allocate from free pool).",
    )


def _add_openstack_deployment(p: argparse.ArgumentParser) -> None:
    """OpenStack Glance upload and optional Nova boot."""
    g = p.add_argument_group("OpenStack deployment")
    g.add_argument(
        "--deploy-openstack",
        dest="deploy_openstack",
        action="store_true",
        help="After conversion, upload the QCOW2 image to Glance (requires openstacksdk).",
    )
    g.add_argument(
        "--glance-name",
        dest="glance_name",
        default=None,
        help="Glance image name (default: --vm-name or QCOW2 filename stem).",
    )
    g.add_argument(
        "--openstack-description",
        dest="openstack_description",
        default=None,
        help="Glance image description.",
    )
    g.add_argument(
        "--openstack-visibility",
        dest="openstack_visibility",
        choices=("private", "shared", "public"),
        default="private",
        help="Glance image visibility (default: private).",
    )
    g.add_argument(
        "--os-cloud",
        dest="os_cloud",
        default=None,
        help="Cloud name from clouds.yaml (openstacksdk).",
    )
    g.add_argument("--os-auth-url", dest="os_auth_url", default=None, help="Keystone auth URL.")
    g.add_argument("--os-username", dest="os_username", default=None)
    g.add_argument("--os-password", dest="os_password", default=None)
    g.add_argument("--os-project-name", dest="os_project_name", default=None)
    g.add_argument("--os-user-domain-name", dest="os_user_domain_name", default=None)
    g.add_argument("--os-project-domain-name", dest="os_project_domain_name", default=None)
    g.add_argument(
        "--openstack-boot-instance",
        dest="openstack_boot_instance",
        action="store_true",
        help="Boot a Nova instance after Glance upload.",
    )
    g.add_argument(
        "--openstack-server-name",
        dest="openstack_server_name",
        default=None,
        help="Nova instance name (default: <glance-name>-instance).",
    )
    g.add_argument(
        "--openstack-flavor", dest="openstack_flavor", default=None, help="Nova flavor name or ID."
    )
    g.add_argument(
        "--openstack-network", dest="openstack_network", default=None, help="Neutron network UUID."
    )
    g.add_argument(
        "--openstack-key-name", dest="openstack_key_name", default=None, help="Nova keypair name."
    )
    g.add_argument(
        "--openstack-security-group",
        dest="openstack_security_group",
        default=None,
        help="Security group name for the instance.",
    )
    g.add_argument(
        "--openstack-availability-zone",
        dest="openstack_availability_zone",
        default=None,
        help="Nova availability zone.",
    )
    g.add_argument(
        "--openstack-wait",
        dest="openstack_wait",
        action="store_true",
        help="Wait for Nova instance to reach ACTIVE (with --openstack-boot-instance).",
    )
    g.add_argument(
        "--openstack-continue-on-error",
        dest="openstack_continue_on_error",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Continue migration if OpenStack deploy fails (default: true).",
    )


def _add_zkvm_flags(p: argparse.ArgumentParser) -> None:
    """zkvm (Terminal User Interface) flags."""
    g = p.add_argument_group("zkvm (Terminal User Interface)")
    g.add_argument(
        "--zkvm",
        dest="zkvm",
        action="store_true",
        default=False,
        help="Launch the Go-based TUI (zkvm). Starts the socket server and the TUI binary.",
    )
    g.add_argument(
        "--zkvm-server",
        dest="zkvm_server",
        action="store_true",
        default=False,
        help="Start zkvm socket server only (for external TUI clients).",
    )
    g.add_argument(
        "--zkvm-socket",
        dest="zkvm_socket",
        default=None,
        help="Custom Unix socket path for zkvm communication "
        "(default: /run/h2kvm/zkvm.sock for root, "
        "$XDG_RUNTIME_DIR/h2kvm/zkvm.sock for users).",
    )


def _add_ai_flags(p: argparse.ArgumentParser) -> None:
    """AI migration intelligence flags."""
    g = p.add_argument_group("AI Migration Intelligence")
    g.add_argument(
        "--no-ai",
        dest="no_ai",
        action="store_true",
        default=False,
        help="Disable AI migration intelligence (prediction, diagnosis, health checks).",
    )
    g.add_argument(
        "--ai-info",
        dest="ai_info",
        action="store_true",
        default=False,
        help="Show AI module status, knowledge-base statistics, and exit.",
    )
