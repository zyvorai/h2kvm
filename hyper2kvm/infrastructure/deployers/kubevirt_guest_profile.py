# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""KubeVirt VM metadata: guest OS family and distro variant hints for v9s / UIs."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

LINUX_SSH_PORT = 22
WINDOWS_RDP_PORT = 3389


@dataclass(frozen=True, slots=True)
class GuestProfile:
    """Resolved guest OS metadata for VirtualMachine labels and domain spec."""

    family: str  # "linux" | "windows"
    os_variant: str | None = None  # e.g. rhel8.10, ubuntu22.04, win2k22
    distro_id: str | None = None  # e.g. rhel, ubuntu, rocky
    version_id: str | None = None  # e.g. 8.10, 22.04
    pretty_name: str | None = None
    extra_labels: dict[str, str] = field(default_factory=dict)
    extra_annotations: dict[str, str] = field(default_factory=dict)


def is_windows_guest(args: Any) -> bool:
    guest = (getattr(args, "guest_os", None) or "").strip().lower()
    if guest == "windows":
        return True
    return bool(getattr(args, "windows", False))


def is_linux_guest(args: Any) -> bool:
    if is_windows_guest(args):
        return False
    guest = (getattr(args, "guest_os", None) or "").strip().lower()
    if guest in ("linux", "lin"):
        return True
    if guest == "windows":
        return False
    variant = _explicit_os_variant(args)
    if variant and not _looks_windows_variant(variant):
        return True
    if _linux_hints_from_args(args):
        return True
    # Default migrated Linux guests when not marked Windows.
    return not is_windows_guest(args)


def parse_os_release(text: str) -> dict[str, str]:
    """Parse KEY=value lines from /etc/os-release."""
    out: dict[str, str] = {}
    for line in (text or "").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        out[key.strip()] = val.strip().strip('"').strip("'")
    return out


def kubevirt_os_variant(
    *,
    distro_id: str,
    version_id: str = "",
    id_like: str = "",
) -> str | None:
    """
    Map os-release ID + VERSION_ID to a KubeVirt / virt-install style os-variant.

    Aligns with common v9s template variants (rhel8.x, ubuntu22.04, rocky9, …).
    """
    did = (distro_id or "").lower().strip()
    ver = (version_id or "").strip()
    like = (id_like or "").lower()
    major = ver.split(".")[0] if ver else ""

    def _minor_suffix() -> str:
        if "." in ver:
            parts = ver.split(".")
            return parts[1] if len(parts) > 1 else "0"
        return "0"

    if did in ("rhel", "redhat") or (did == "centos" and "rhel" in like):
        if major in ("6", "7", "8", "9", "10"):
            return f"rhel{major}.{_minor_suffix()}"
        return "rhel8.0" if not major else f"rhel{major}.0"

    if did == "rocky":
        if major:
            return f"rocky{major}.{_minor_suffix()}"
        return "rocky9.0"

    if did in ("almalinux", "alma"):
        if major:
            return f"almalinux{major}.{_minor_suffix()}"
        return "almalinux9.0"

    if did == "centos":
        if major == "7":
            return "centos7.0"
        if major in ("8", "9", "10"):
            return f"centos{major}.0"
        return "centos8.0"

    if did == "fedora":
        if major:
            return f"fedora{major}"
        return "fedora43"

    if did == "ubuntu":
        if ver:
            return f"ubuntu{ver}"
        return "ubuntu24.04"

    if did == "debian":
        if ver:
            return f"debian{ver.split('.')[0]}"
        return "debian12"

    if did in ("opensuse-leap", "opensuse"):
        if ver:
            return f"opensuse-leap{ver}"
        return "opensuse-leap15.6"

    if did == "sles":
        if major:
            return f"sles{major}"
        return "sles15"

    if did in ("photon", "vmware"):
        return "linux"  # generic; Photon has no standard virt-install name

    if did:
        if ver:
            return f"{did}{ver.replace('.', '')}"
        return did
    return None


def kubevirt_os_variant_from_name(name: str) -> str | None:
    """Best-effort variant from VM / image filename (rhel88 → rhel8.8, etc.)."""
    n = (name or "").lower()
    m = re.search(r"rhel[\-_]?(\d)(\d+)", n)
    if m:
        return f"rhel{m.group(1)}.{m.group(2)}"
    m = re.search(r"rocky[\-_]?(\d+)", n)
    if m:
        return f"rocky{m.group(1)}.0"
    m = re.search(r"ubuntu[\-_]?(\d{2})\.?(\d{2})?", n)
    if m:
        minor = m.group(2) or "04"
        return f"ubuntu{m.group(1)}.{minor}"
    m = re.search(r"u(\d{2})(\d{2})", n)  # u2204
    if m:
        return f"ubuntu{m.group(1)}.{m.group(2)}"
    if re.search(r"centos[\-_]?(\d+)", n):
        major = re.search(r"centos[\-_]?(\d+)", n).group(1)  # type: ignore[union-attr]
        return f"centos{major}.0"
    if "fedora" in n:
        m = re.search(r"fedora[\-_]?(\d+)", n)
        if m:
            return f"fedora{m.group(1)}"
    return None


def resolve_guest_profile(args: Any, *, vm_name: str = "") -> GuestProfile:
    """Resolve Windows or Linux guest profile from CLI args and optional fixer report."""
    if is_windows_guest(args):
        variant = _explicit_os_variant(args) or "win2k22"
        return GuestProfile(
            family="windows",
            os_variant=variant if _looks_windows_variant(variant) else "win2k22",
            extra_labels={"v9s.io/rdp": "enabled"},
        )

    parsed = _os_release_from_args(args)
    distro = (
        getattr(args, "linux_distro", None) or getattr(args, "detected_distro", None) or ""
    ).strip().lower() or parsed.get("ID", "").lower()
    version = (
        getattr(args, "linux_version", None) or getattr(args, "detected_version", None) or ""
    ).strip() or parsed.get("VERSION_ID", "")
    pretty = (
        getattr(args, "linux_os_pretty_name", None)
        or getattr(args, "detected_os_pretty_name", None)
        or parsed.get("PRETTY_NAME")
    )

    variant = _explicit_os_variant(args)
    if variant and not _looks_windows_variant(variant):
        os_variant = variant
    else:
        os_variant = kubevirt_os_variant(
            distro_id=distro,
            version_id=version,
            id_like=parsed.get("ID_LIKE", ""),
        )
    if not os_variant and vm_name:
        os_variant = kubevirt_os_variant_from_name(vm_name)

    labels: dict[str, str] = {}
    annotations: dict[str, str] = {}
    if os_variant:
        labels["os.template.kubevirt.io/variant"] = os_variant
    if distro:
        labels["hyper2kvm.io/os-distro"] = distro
    if version:
        labels["hyper2kvm.io/os-version"] = version
    if pretty:
        annotations["hyper2kvm.io/os-pretty-name"] = str(pretty)[:256]

    return GuestProfile(
        family="linux",
        os_variant=os_variant,
        distro_id=distro or None,
        version_id=version or None,
        pretty_name=str(pretty) if pretty else None,
        extra_labels=labels,
        extra_annotations=annotations,
    )


def apply_guest_metadata(
    labels: dict[str, str],
    annotations: dict[str, str],
    profile: GuestProfile,
) -> None:
    """Merge standard hyper2kvm / v9s guest-os labels."""
    labels["hyper2kvm.io/guest-os"] = profile.family
    labels["v9s.io/guest-os"] = profile.family
    annotations["hyper2kvm.io/guest-os"] = profile.family
    if profile.os_variant:
        annotations["hyper2kvm.io/os-variant"] = profile.os_variant
    labels.update(profile.extra_labels)
    annotations.update(profile.extra_annotations)


def _explicit_os_variant(args: Any) -> str | None:
    for attr in ("k8s_os_variant", "os_variant", "linux_os_variant"):
        raw = getattr(args, attr, None)
        if raw and str(raw).strip():
            return str(raw).strip()
    return None


def _looks_windows_variant(variant: str) -> bool:
    v = variant.lower()
    return v.startswith("win") or "windows" in v


def _linux_hints_from_args(args: Any) -> bool:
    if getattr(args, "linux_distro", None) or getattr(args, "detected_distro", None):
        return True
    if _os_release_from_args(args):
        return True
    report = getattr(args, "last_fixer_report", None)
    if isinstance(report, dict):
        guest = (report.get("analysis") or {}).get("guest") or {}
        if guest.get("os_release"):
            return True
    return False


def _os_release_from_args(args: Any) -> dict[str, str]:
    text = getattr(args, "linux_os_release", None) or ""
    if text:
        return parse_os_release(str(text))
    report = getattr(args, "last_fixer_report", None)
    if isinstance(report, dict):
        guest = (report.get("analysis") or {}).get("guest") or {}
        osr = guest.get("os_release") or ""
        if osr:
            return parse_os_release(str(osr))
    return {}


def propagate_linux_metadata_from_report(args: Any, report: dict[str, Any] | None) -> None:
    """
    Copy Linux identity from offline fixer report onto ``args`` for KubeVirt deploy.

    Called by the orchestrator after disk fixes when the guest is not Windows.
    """
    if not report or is_windows_guest(args):
        return
    analysis = report.get("analysis") or {}
    if analysis.get("windows"):
        return

    guest = analysis.get("guest") or {}
    osr_text = guest.get("os_release") or ""
    if not osr_text:
        return

    parsed = parse_os_release(str(osr_text))
    if not parsed.get("ID") and not parsed.get("PRETTY_NAME"):
        return

    explicit = (getattr(args, "guest_os", None) or "").strip().lower()
    if explicit == "windows":
        return

    args.last_fixer_report = report  # type: ignore[attr-defined]
    args.linux_os_release = osr_text  # type: ignore[attr-defined]
    if parsed.get("ID"):
        args.linux_distro = parsed["ID"]  # type: ignore[attr-defined]
    if parsed.get("VERSION_ID"):
        args.linux_version = parsed["VERSION_ID"]  # type: ignore[attr-defined]
    if parsed.get("PRETTY_NAME"):
        args.linux_os_pretty_name = parsed["PRETTY_NAME"]  # type: ignore[attr-defined]

    variant = kubevirt_os_variant(
        distro_id=parsed.get("ID", ""),
        version_id=parsed.get("VERSION_ID", ""),
        id_like=parsed.get("ID_LIKE", ""),
    )
    if variant and not getattr(args, "k8s_os_variant", None):
        args.k8s_os_variant = variant  # type: ignore[attr-defined]

    if explicit not in ("linux", "lin"):
        args.guest_os = "linux"  # type: ignore[attr-defined]


def build_kubevirt_vm_manifest(
    *,
    vm_name: str,
    namespace: str,
    run_strategy: str,
    volume: dict[str, Any],
    root_disk_bus: str,
    memory: str,
    cpu_cores: str,
    args: Any,
) -> dict[str, Any]:
    """Build a KubeVirt VirtualMachine CR with guest OS hints for v9s and other UIs."""
    profile = resolve_guest_profile(args, vm_name=vm_name)
    windows = profile.family == "windows"

    labels: dict[str, str] = {
        "app": vm_name,
        "hyper2kvm.io/migrated": "true",
    }
    annotations: dict[str, str] = {}
    apply_guest_metadata(labels, annotations, profile)

    iface: dict[str, Any] = {"name": "default", "masquerade": {}}
    if windows:
        iface["ports"] = [
            {"name": "rdp", "port": WINDOWS_RDP_PORT, "protocol": "TCP"},
        ]
    else:
        iface["ports"] = [
            {"name": "ssh", "port": LINUX_SSH_PORT, "protocol": "TCP"},
        ]

    try:
        cores = max(1, int(str(cpu_cores).strip()))
    except (TypeError, ValueError):
        cores = 2

    domain: dict[str, Any] = {
        "cpu": {"cores": cores},
        "devices": {
            "disks": [{"name": "rootdisk", "disk": {"bus": root_disk_bus}}],
            "interfaces": [iface],
            "autoattachGraphicsDevice": True,
        },
        "machine": {"type": "q35"},
        "resources": {
            "requests": {"memory": memory},
        },
    }

    if windows:
        domain["features"] = {
            "acpi": {},
            "apic": {},
            "hyperv": {
                "relaxed": {},
                "vapic": {},
                "spinlocks": {"spinlocks": 8191},
            },
        }
        domain["clock"] = {
            "utc": {},
            "timer": {
                "hpet": {"present": False},
                "pit": {"tickPolicy": "delay"},
                "rtc": {"tickPolicy": "catchup"},
                "hyperv": {},
            },
        }
        # Do not set domain.devices.video — requires KubeVirt VideoConfig feature gate.
        # autoattachGraphicsDevice uses cluster-default VGA/virtio for console/RDP.
    else:
        domain["features"] = {"acpi": {}, "apic": {}}
        domain["clock"] = {
            "utc": {},
            "timer": {
                "hpet": {"present": False},
                "pit": {"tickPolicy": "delay"},
                "rtc": {"tickPolicy": "catchup"},
            },
        }
        domain["devices"]["rng"] = {}

    if getattr(args, "uefi", False):
        # KubeVirt defaults EFI secureBoot to true when omitted; that requires features.smm.
        secure = bool(getattr(args, "win_secure_boot", False))
        domain["firmware"] = {
            "bootloader": {"efi": {"secureBoot": secure}},
        }
        if secure:
            feats = domain.setdefault("features", {})
            smm = feats.setdefault("smm", {})
            smm["enabled"] = True

    metadata: dict[str, Any] = {
        "name": vm_name,
        "namespace": namespace,
        "labels": labels,
    }
    if annotations:
        metadata["annotations"] = annotations

    return {
        "apiVersion": "kubevirt.io/v1",
        "kind": "VirtualMachine",
        "metadata": metadata,
        "spec": {
            "runStrategy": run_strategy,
            "template": {
                "metadata": {"labels": {"kubevirt.io/vm": vm_name}},
                "spec": {
                    "domain": domain,
                    "networks": [{"name": "default", "pod": {}}],
                    "volumes": [volume],
                },
            },
        },
    }
