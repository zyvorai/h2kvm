# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# h2kvm/core/guest_identity.py
"""Guest OS identity detection and representation."""

from __future__ import annotations

import contextlib
import re
import subprocess
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any

from .guestfs_factory import create_guestfs
from .utils import U

if TYPE_CHECKING:
    from pathlib import Path

    from h2kvm.core.guestfs_typing import guestfs


# Canonical Windows detection from your repo (fixers/windows/virtio/core.py)
try:
    from h2kvm.fixers.windows.virtio.core import is_windows as _wv_is_windows  # type: ignore

    _WIN_VIRTIO_DETECT_OK = True
except ImportError:  # pragma: no cover
    _wv_is_windows = None  # type: ignore
    _WIN_VIRTIO_DETECT_OK = False


class GuestType(Enum):
    """Guest operating system types."""

    LINUX = "linux"
    WINDOWS = "windows"
    BSD = "bsd"
    MACOS = "macos"
    UNKNOWN = "unknown"

    @classmethod
    def from_string(cls, value: str) -> GuestType:
        """Parse a lowercase/whitespace-insensitive string into a GuestType, or UNKNOWN."""
        value = (value or "").lower().strip()
        for member in cls:
            if member.value == value:
                return member
        return cls.UNKNOWN


@dataclass
class GuestIdentity:  # pylint: disable=too-many-instance-attributes
    """Container for guest identity information."""

    # too-many-instance-attributes: this is a flat data container spanning
    # Linux and Windows identity fields plus detection metadata; splitting it
    # would only push the same fields into sub-dataclasses without reducing
    # complexity.

    type: GuestType = GuestType.UNKNOWN

    # Linux-ish (also useful for general OS)
    hostname: str | None = None
    machine_id: str | None = None
    os_name: str | None = None
    os_pretty_name: str | None = None
    os_version: str | None = None
    architecture: str | None = None
    kernel_version: str | None = None
    cpe_name: str | None = None
    support_end: str | None = None

    # Windows-ish (NOTE: major/minor are not very meaningful for modern Windows, kept for compatibility)
    windows_major: str | None = None
    windows_minor: str | None = None
    windows_distro: str | None = None

    # Better Windows identifiers (populate later via registry if desired)
    windows_build: str | None = None
    windows_display_version: str | None = None
    windows_edition: str | None = None

    # Detection meta
    confidence: float = 0.0
    detection_method: str = "unknown"

    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class _WvShim:
    """
    windows_virtio.is_windows expects:
      - self.logger (optional)
      - self.inspect_root (required for strongest detection path)
    """

    logger: object
    inspect_root: str | None = None


class GuestDetector:
    """
    Enhanced guest detection with multiple fallback strategies.

    IMPORTANT:
      - We use guestfs.GuestFS(python_return_dict=True) in detect()
      - That means some APIs (notably inspect_get_mountpoints) return dicts.
        We normalize that shape to avoid shape bugs.
    """

    OS_INDICATORS: dict[GuestType, list[str]] = {
        GuestType.LINUX: [
            "/etc/os-release",
            "/usr/lib/os-release",
            "/etc/lsb-release",
            "/etc/redhat-release",
            "/etc/debian_version",
            "/etc/arch-release",
            "/etc/SuSE-release",
            "/etc/alpine-release",
            "/proc",
            "/sys",
        ],
        GuestType.WINDOWS: [
            "/Windows/System32",
            "/WINDOWS/System32",
            "/winnt/system32",
            "/Windows/explorer.exe",
            "/WINDOWS/explorer.exe",
            "/Program Files",
            "/Program Files (x86)",
        ],
        GuestType.BSD: [
            "/etc/freebsd-update.conf",
            "/etc/openbsd-version",
            "/etc/netbsd-version",
            "/etc/bsd-release",
        ],
        GuestType.MACOS: [
            "/System/Library/CoreServices",
            "/Applications",
            "/Library/Preferences",
            "/usr/bin/sw_vers",
        ],
        GuestType.UNKNOWN: [],
    }

    WINDOWS_REGISTRY_HIVES: list[str] = [
        "/Windows/System32/config/SOFTWARE",
        "/Windows/System32/config/SYSTEM",
        "/WINDOWS/System32/config/SOFTWARE",
        "/WINDOWS/System32/config/SYSTEM",
        "/winnt/system32/config/SOFTWARE",
        "/winnt/system32/config/SYSTEM",
    ]

    # Small parsing helpers

    @staticmethod
    def read_first_line(g: guestfs.GuestFS, path: str) -> str | None:
        """Return the stripped first line of a guest file, or None if unreadable."""
        try:
            if not g.is_file(path):
                return None
            content = (g.read_file(path) or b"").decode("utf-8", errors="ignore")
            lines = content.splitlines()
            return lines[0].strip() if lines else None
        except Exception:  # pylint: disable=broad-exception-caught
            # guestfs raises library-specific/opaque errors on I/O failures;
            # this is a best-effort read that must never abort detection.
            return None

    @staticmethod
    def parse_os_release(text: str) -> dict[str, str]:
        """Parse KEY=VALUE (os-release/lsb-release style) text into a dict."""
        out: dict[str, str] = {}
        for line in (text or "").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            v = v.strip().strip('"').strip("'")
            out[k.strip()] = v
        return out

    @staticmethod
    def parse_issue_file(content: str) -> str | None:
        """Strip /etc/issue backslash escapes and return the cleaned text, or None if empty."""
        if not content:
            return None
        # /etc/issue commonly includes backslash escapes like \S \n \l etc.
        # We remove only "single-letter" escapes to reduce accidental clobbering.
        content = re.sub(r"\\[A-Za-z]", "", content)
        content = content.replace("\\n", " ").replace("\\r", " ")
        content = content.strip()
        return content or None

    # Mounting (shape-safe)

    @staticmethod
    def _normalize_mountpoints(mps: Any) -> list[tuple[str, str]]:
        """
        guestfs inspect_get_mountpoints(root) can be:
          - dict when python_return_dict=True: { mountpoint: device }
          - list/tuple when python_return_dict=False: [(device, mountpoint), ...]
        We normalize to: [(device, mountpoint), ...]
        """
        out: list[tuple[str, str]] = []
        if mps is None:
            return out

        # python_return_dict=True => dict { mp: dev }
        if isinstance(mps, dict):
            for mp, dev in mps.items():
                if isinstance(dev, str) and isinstance(mp, str):
                    out.append((dev, mp))
            return out

        # list/tuple => iterable of 2-tuples
        if isinstance(mps, (list, tuple)):
            for item in mps:
                try:
                    dev, mp = item  # type: ignore[misc]
                    if isinstance(dev, str) and isinstance(mp, str):
                        out.append((dev, mp))
                except (TypeError, ValueError):
                    continue
            return out

        return out

    @staticmethod
    def _path_depth(mp: str) -> int:
        mp = (mp or "").strip()
        if mp == "/":
            return 0
        return len([p for p in mp.split("/") if p])

    @staticmethod
    def _mounted_anything(g: guestfs.GuestFS) -> bool:
        try:
            mps = g.mountpoints()
            return bool(mps)
        except Exception:  # pylint: disable=broad-exception-caught
            # guestfs raises library-specific/opaque errors; treat any
            # failure as "nothing mounted" rather than propagating.
            return False

    @staticmethod
    def _resolve_fstab_device(dev: str) -> str:
        """
        Resolve UUID=, LABEL=, PARTUUID= references to actual device paths.

        On NBD-attached images, /dev/disk/by-uuid/ symlinks may not exist,
        so we use blkid to resolve them.
        """
        if not any(dev.startswith(pfx) for pfx in ("UUID=", "LABEL=", "PARTUUID=")):
            return dev

        tag, value = dev.split("=", 1)
        try:
            result = subprocess.run(
                ["blkid", "-t", f"{tag}={value}", "-o", "device"],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            resolved = result.stdout.strip().splitlines()
            if resolved:
                return resolved[0]
        except (OSError, subprocess.SubprocessError):
            pass
        return dev

    @classmethod
    def mount_inspected_root(cls, g: guestfs.GuestFS, root: str) -> None:
        """
        Mount all mountpoints for an inspected root, in safe order.
        Never throws (best-effort).
        """
        try:
            raw = g.inspect_get_mountpoints(root)
        except Exception:  # pylint: disable=broad-exception-caught
            # guestfs raises library-specific/opaque errors; this is
            # best-effort mounting that must never abort detection.
            return

        mps = cls._normalize_mountpoints(raw)

        # Ensure "/" mounts first, then shallower paths before deeper paths,
        # then length as a tie-breaker.
        def _mp_sort_key(item: tuple[str, str]) -> tuple[int, int, int]:
            _dev, mp = item
            return (0 if mp == "/" else 1, cls._path_depth(mp), len(mp))

        for dev, mp in sorted(mps, key=_mp_sort_key):
            try:
                resolved = cls._resolve_fstab_device(dev)
                g.mount(resolved, mp)
            except Exception:  # pylint: disable=broad-exception-caught
                # guestfs raises library-specific/opaque errors; skip this
                # mountpoint and keep mounting the rest best-effort.
                continue

    # Detection strategies

    @classmethod
    def detect_by_indicators(cls, g: guestfs.GuestFS) -> dict[GuestType, float]:
        """
        Path-based indicator detection.

        IMPORTANT:
          - This expects the inspected root to already be mounted.
          - If nothing is mounted, we return all-zero scores.
        """
        if not cls._mounted_anything(g):
            return dict.fromkeys(GuestType, 0.0)

        scores: dict[GuestType, float] = dict.fromkeys(GuestType, 0.0)

        for os_type, indicators in cls.OS_INDICATORS.items():
            if os_type == GuestType.UNKNOWN:
                continue
            for indicator in indicators:
                try:
                    if g.is_dir(indicator):
                        scores[os_type] += 1.0
                    elif g.is_file(indicator):
                        scores[os_type] += 0.8
                except Exception:  # pylint: disable=broad-exception-caught
                    # guestfs raises library-specific/opaque errors; skip
                    # this indicator and keep scoring best-effort.
                    continue

        # Extra hint for Windows: registry hives
        for hive in cls.WINDOWS_REGISTRY_HIVES:
            try:
                if g.is_file(hive):
                    scores[GuestType.WINDOWS] += 1.5
                    break
            except Exception:  # pylint: disable=broad-exception-caught
                # guestfs raises library-specific/opaque errors; skip this
                # hive and keep checking the rest best-effort.
                continue

        return scores

    @classmethod
    def detect_by_inspection(cls, g: guestfs.GuestFS, root: str) -> GuestType | None:
        """Map guestfs's own inspect_get_type() result to a GuestType, or None if unknown."""
        try:
            os_type = g.inspect_get_type(root)
            if not os_type:
                return None
            os_type_str = (U.to_text(os_type) or "").lower().strip()
            if os_type_str == "windows":
                return GuestType.WINDOWS
            if os_type_str == "linux":
                return GuestType.LINUX
            if "bsd" in os_type_str:
                return GuestType.BSD
            if "darwin" in os_type_str or "mac" in os_type_str:
                return GuestType.MACOS
        except Exception:  # pylint: disable=broad-exception-caught
            # guestfs raises library-specific/opaque errors; treat any
            # failure as "type undetermined" rather than propagating.
            pass
        return None

    @classmethod
    def detect_by_canonical(
        cls, g: guestfs.GuestFS, root: str, logger
    ) -> tuple[GuestType | None, str | None]:
        """
        Canonical helper answers ONLY: "is this Windows?"
        If it says "no", we return None (do NOT assume Linux).

        Returns: (GuestType|None, error_str|None)
        """
        if not _WIN_VIRTIO_DETECT_OK or _wv_is_windows is None:
            return (None, None)

        shim = _WvShim(logger=logger, inspect_root=root)
        try:
            ok = bool(_wv_is_windows(shim, g))  # type: ignore[misc]
            return (GuestType.WINDOWS if ok else None, None)
        except Exception as e:  # pylint: disable=broad-exception-caught
            # The external windows_virtio detection module's exception
            # surface isn't guaranteed; capture any failure as diagnostic
            # error text instead of aborting detection.
            return (None, f"{type(e).__name__}: {e}")

    # Identity collection

    @staticmethod
    def _versionish_key(s: str) -> list[tuple[int, Any]]:
        """
        Comparable version-ish key.

        We return a list of tagged tuples so Python never needs to compare int vs str:
          - ints => (0, int_value)
          - strings => (1, string_value)

        Example: "6.12.10-200.fc41" becomes:
          [(0, 6), (1,'.'), (0, 12), (1,'.'), (0, 10), (1,'-'), (0, 200), (1,'.'), (1,'fc'), (0, 41)]
        """
        s = (s or "").strip()
        out: list[tuple[int, Any]] = []
        for tok in re.split(r"(\d+)", s):
            if tok == "":
                continue
            if tok.isdigit():
                try:
                    out.append((0, int(tok)))
                except ValueError:
                    out.append((1, tok))
            else:
                out.append((1, tok))
        return out

    @classmethod
    def best_effort_kernel(cls, g: guestfs.GuestFS) -> str | None:
        """Guess the newest installed kernel version from /lib/modules or /boot."""
        try:
            if g.is_dir("/lib/modules"):
                vers = [U.to_text(x) or "" for x in g.ls("/lib/modules")]
                vers = [v for v in vers if v.strip()]
                vers.sort(key=cls._versionish_key)
                return vers[-1] if vers else None
        except Exception:  # pylint: disable=broad-exception-caught
            # guestfs raises library-specific/opaque errors; fall through to
            # the /boot fallback below.
            pass
        try:
            if g.is_dir("/boot"):
                entries = [U.to_text(x) or "" for x in g.ls("/boot")]
                vml = [x for x in entries if x.startswith("vmlinuz-")]
                if not vml:
                    return None
                vml.sort(key=cls._versionish_key)
                last = vml[-1]
                return last[len("vmlinuz-") :] if last.startswith("vmlinuz-") else last
        except Exception:  # pylint: disable=broad-exception-caught
            # guestfs raises library-specific/opaque errors; kernel version
            # is best-effort only.
            pass
        return None

    @classmethod
    def collect_linux_identity(  # pylint: disable=too-many-branches
        cls, g: guestfs.GuestFS, root: str
    ) -> GuestIdentity:
        """
        Collect Linux identity.

        EXPECTATION:
          - The caller has already mounted the inspected root.

        too-many-branches: each branch is a distinct best-effort identity
        source (os-release, lsb-release, distro-specific files, debian
        version, hostname, machine-id, kernel, issue fallback); splitting
        further would obscure the fallback order.
        """
        ident = GuestIdentity(type=GuestType.LINUX)

        # arch
        with contextlib.suppress(Exception):
            ident.architecture = U.to_text(g.inspect_get_arch(root))

        # os-release
        osr_raw = ""
        for p in ("/etc/os-release", "/usr/lib/os-release"):
            try:
                if g.is_file(p):
                    osr_raw = (g.read_file(p) or b"").decode("utf-8", errors="ignore")
                    break
            except Exception:  # pylint: disable=broad-exception-caught
                # guestfs raises library-specific/opaque errors; try the
                # next candidate path best-effort.
                continue
        osr = cls.parse_os_release(osr_raw)
        ident.os_pretty_name = osr.get("PRETTY_NAME")
        ident.os_name = osr.get("NAME")
        ident.os_version = osr.get("VERSION")
        ident.cpe_name = osr.get("CPE_NAME")
        # Not standardized across distros; safe best-effort only
        ident.support_end = osr.get("SUPPORT_END") or osr.get("SUPPORT_END_DATE")

        # lsb-release fallback (Ubuntu/Debian when os-release is missing or empty)
        if not ident.os_pretty_name:
            try:
                if g.is_file("/etc/lsb-release"):
                    lsb_raw = (g.read_file("/etc/lsb-release") or b"").decode("utf-8", errors="ignore")
                    lsb = cls.parse_os_release(lsb_raw)  # same KEY=VALUE format
                    ident.os_pretty_name = ident.os_pretty_name or lsb.get("DISTRIB_DESCRIPTION")
                    ident.os_name = ident.os_name or lsb.get("DISTRIB_ID")
                    ident.os_version = ident.os_version or lsb.get("DISTRIB_RELEASE")
            except Exception:  # pylint: disable=broad-exception-caught
                # guestfs raises library-specific/opaque errors; lsb-release
                # is a best-effort fallback only.
                pass

        # distro-specific fallbacks
        if not ident.os_pretty_name:
            for distro_file in (
                "/etc/redhat-release",
                "/etc/centos-release",
                "/etc/fedora-release",
                "/etc/SuSE-release",
            ):
                line = cls.read_first_line(g, distro_file)
                if line:
                    ident.os_pretty_name = line
                    break

        if not ident.os_name and not ident.os_pretty_name:
            # Debian stores just the version number
            deb_ver = cls.read_first_line(g, "/etc/debian_version")
            if deb_ver:
                ident.os_name = "Debian"
                ident.os_version = deb_ver

        # hostname
        ident.hostname = cls.read_first_line(g, "/etc/hostname")

        # machine-id
        ident.machine_id = cls.read_first_line(g, "/etc/machine-id") or cls.read_first_line(
            g, "/var/lib/dbus/machine-id"
        )

        # kernel
        ident.kernel_version = cls.best_effort_kernel(g)

        # issue fallback
        try:
            if g.is_file("/etc/issue") and not ident.os_pretty_name:
                issue = (g.read_file("/etc/issue") or b"").decode("utf-8", errors="ignore")
                txt = cls.parse_issue_file(issue)
                if txt:
                    ident.os_pretty_name = txt
        except Exception:  # pylint: disable=broad-exception-caught
            # guestfs raises library-specific/opaque errors; /etc/issue is a
            # best-effort fallback only.
            pass

        return ident

    @classmethod
    def collect_windows_identity(cls, g: guestfs.GuestFS, root: str) -> GuestIdentity:
        """
        Collect Windows identity.

        EXPECTATION:
          - The caller has already mounted the inspected root.
        """
        ident = GuestIdentity(type=GuestType.WINDOWS)

        with contextlib.suppress(Exception):
            ident.os_name = U.to_text(g.inspect_get_product_name(root))
        with contextlib.suppress(Exception):
            ident.architecture = U.to_text(g.inspect_get_arch(root))
        with contextlib.suppress(Exception):
            ident.windows_distro = U.to_text(g.inspect_get_distro(root))
        with contextlib.suppress(Exception):
            ident.windows_major = str(g.inspect_get_major_version(root))
        with contextlib.suppress(Exception):
            ident.windows_minor = str(g.inspect_get_minor_version(root))

        # evidence (dirs/hives)
        windows_dirs: list[str] = []
        for d in ("/Windows", "/WINDOWS", "/winnt"):
            try:
                if g.is_dir(d):
                    windows_dirs.append(d)
            except Exception:  # pylint: disable=broad-exception-caught
                # guestfs raises library-specific/opaque errors; skip this
                # candidate directory and keep checking the rest best-effort.
                continue
        if windows_dirs:
            ident.metadata["windows_dirs"] = windows_dirs

        reg_hives: list[str] = []
        for h in cls.WINDOWS_REGISTRY_HIVES:
            try:
                if g.is_file(h):
                    reg_hives.append(h)
            except Exception:  # pylint: disable=broad-exception-caught
                # guestfs raises library-specific/opaque errors; skip this
                # hive and keep checking the rest best-effort.
                continue
        if reg_hives:
            ident.metadata["registry_hives"] = reg_hives

        return ident

    # Root selection + main detect()

    @classmethod
    def best_root(cls, g: guestfs.GuestFS) -> str | None:
        """Return the preferred inspected OS root, favoring a Windows root if present."""
        try:
            roots = g.inspect_os()
        except Exception:  # pylint: disable=broad-exception-caught
            # guestfs raises library-specific/opaque errors; no roots means
            # no detectable OS.
            return None
        if not roots:
            return None
        # Prefer a Windows root if present
        for r in roots:
            try:
                t = (U.to_text(g.inspect_get_type(r)) or "").strip().lower()
                if t == "windows":
                    return r
            except Exception:  # pylint: disable=broad-exception-caught
                # guestfs raises library-specific/opaque errors; skip this
                # root and keep checking the rest best-effort.
                continue
        return roots[0]

    @classmethod
    # pylint: disable=too-many-locals,too-many-branches,too-many-statements
    def detect(cls, img_path: Path, logger, readonly: bool = True) -> GuestIdentity | None:
        """
        Open guestfs read-only and detect guest OS + identity.

        Returns GuestIdentity or None if no OS roots.

        too-many-locals/branches/statements: this orchestrates the full
        multi-strategy detection pipeline (canonical, inspection, indicator
        scoring, identity collection, confidence nudging) end-to-end inside
        one guarded try/finally so guestfs launch/cleanup stays paired;
        splitting it would scatter that pairing across functions.
        """
        g = None
        try:
            g = create_guestfs(python_return_dict=True, backend="guestkit")
            g.add_drive_opts(str(img_path), readonly=bool(readonly))
            g.launch()

            # pylint: disable=duplicate-code
            # reason: this inspect_os() try/except-to-empty-list fallback
            # mirrors the equivalent guard in
            # h2kvm/fixers/offline_fixer.py (detect_and_mount_root) --
            # structurally similar by coincidence, not shared logic;
            # keeping independent avoids coupling unrelated guest-detection
            # and fixer code paths.
            try:
                roots = g.inspect_os()
            except Exception:  # pylint: disable=broad-exception-caught
                # guestfs raises library-specific/opaque errors; treat as
                # "no roots found".
                roots = []

            if not roots:
                with contextlib.suppress(Exception):
                    logger.debug("GuestDetector: no inspectable OS roots found in image=%s", img_path)
                return None

            root = cls.best_root(g) or roots[0]

            # ---- CRITICAL FIX ----
            # Mount early so indicator detection (and other path-based checks) operate on real FS paths.
            cls.mount_inspected_root(g, root)

            # Fallback: if fstab-based mounting failed (common on Ubuntu where fstab uses
            # UUID= entries that can't be resolved for NBD-attached devices), mount root directly.
            if not cls._mounted_anything(g):
                with contextlib.suppress(Exception):
                    g.mount(root, "/")
                    logger.debug("GuestDetector: fallback direct mount of %s at /", root)

            # Canonical Windows-only detection (capture error for debugging)
            t_can, can_err = cls.detect_by_canonical(g, root, logger)

            identity: GuestIdentity | None = None

            # Strategy A: canonical Windows-only detection
            if t_can == GuestType.WINDOWS:
                identity = GuestIdentity(
                    type=GuestType.WINDOWS,
                    confidence=0.90,
                    detection_method="canonical_windows_virtio",
                )

            # Strategy B: guestfs inspection
            if identity is None:
                t_ins = cls.detect_by_inspection(g, root)
                if t_ins:
                    identity = GuestIdentity(
                        type=t_ins, confidence=0.78, detection_method="guestfs_inspection"
                    )

            # Strategy C: indicator scoring (fallback only; now works because we mounted)
            scores = cls.detect_by_indicators(g)
            candidates = [GuestType.LINUX, GuestType.WINDOWS, GuestType.BSD, GuestType.MACOS]
            best_type = max(candidates, key=lambda t: scores.get(t, 0.0))
            best_score = float(scores.get(best_type, 0.0))

            if identity is None:
                if best_score <= 0.0:
                    identity = GuestIdentity(
                        type=GuestType.UNKNOWN, confidence=0.10, detection_method="indicator_files"
                    )
                else:
                    indicator_conf = min(best_score / 5.0, 0.60)
                    identity = GuestIdentity(
                        type=best_type, confidence=indicator_conf, detection_method="indicator_files"
                    )
            # Nudge confidence a bit if indicators agree (never override)
            elif best_score > 0.0 and best_type == identity.type:
                identity.confidence = min(identity.confidence + 0.05, 1.0)

            # Debug metadata (very useful when detection seems "weird")
            with contextlib.suppress(Exception):
                identity.metadata["indicator_scores"] = {k.value: float(v) for k, v in scores.items()}
            if can_err:
                identity.metadata["canonical_error"] = can_err

            # Collect detailed identity
            if identity.type == GuestType.LINUX:
                detailed = cls.collect_linux_identity(g, root)
            elif identity.type == GuestType.WINDOWS:
                detailed = cls.collect_windows_identity(g, root)
            else:
                detailed = GuestIdentity(type=identity.type)

            # merge (do not overwrite meta like detection_method/confidence)
            for f in detailed.__dataclass_fields__:  # pylint: disable=no-member
                # __dataclass_fields__ is injected by @dataclass on
                # GuestIdentity; pylint can't see it statically.
                if f in ("confidence", "detection_method"):
                    continue
                v = getattr(detailed, f)

                # Merge rules:
                # - keep None as "missing"
                # - skip empty strings (common for file parsing)
                if v is None:
                    continue
                if isinstance(v, str) and v.strip() == "":
                    continue

                setattr(identity, f, v)

            # nudge confidence if we found good identity anchors
            if identity.hostname or identity.os_name or identity.os_pretty_name:
                identity.confidence = min(identity.confidence + 0.10, 1.0)

            # Best-effort cleanup
            with contextlib.suppress(Exception):
                g.umount_all()

            return identity

        except Exception as e:  # pylint: disable=broad-exception-caught
            # Top-level guard: create_guestfs/launch/inspect and the whole
            # detection pipeline can raise a wide variety of library-specific
            # errors; a single guest's failure must never abort the run.
            # Check if this is a locked image error (don't log full stack trace for expected errors)
            error_str = str(e).lower()
            if "image" in error_str and "locked" in error_str and "another process" in error_str:
                logger.warning(
                    "Guest detection skipped: %s is locked by another process (possibly a running VM)",
                    img_path.name,
                )
            else:
                with contextlib.suppress(Exception):
                    logger.exception("Guest detection failed: %s", e)
            return None
        finally:
            if g is not None:
                with contextlib.suppress(Exception):
                    g.shutdown()
                with contextlib.suppress(Exception):
                    g.close()


def _fmt_table(title: str, rows: list[tuple[str, str]]) -> str:
    """Format rows as an aligned key-value table with box border."""
    label_w = max(len(label) for label, _ in rows)
    lines = [f"  {label:<{label_w}} : {value}" for label, value in rows]
    inner_w = max(len(line) for line in lines) + 1
    border = "─" * (inner_w + 1)
    header = f"│  {title:<{inner_w - 1}}│"
    body = "\n".join(f"│{line:<{inner_w}}│" for line in lines)
    return f"┌{border}┐\n{header}\n├{border}┤\n{body}\n└{border}┘"


def emit_guest_identity_log(logger, identity: GuestIdentity) -> None:
    """Emit a hostnamectl-style identity summary with box formatting."""
    if identity.type == GuestType.LINUX:
        rows = [
            ("Static hostname", identity.hostname or "n/a"),
            ("Machine ID", identity.machine_id or "n/a"),
            ("Operating System", identity.os_name or "Linux"),
            ("OS Pretty Name", identity.os_pretty_name or "n/a"),
            ("OS Version", identity.os_version or "n/a"),
            ("CPE OS Name", identity.cpe_name or "n/a"),
            ("OS Support End", identity.support_end or "n/a"),
            ("Architecture", identity.architecture or "unknown"),
            ("Kernel", identity.kernel_version or "n/a"),
            ("Detection", f"{identity.detection_method} ({identity.confidence * 100:.0f}%)"),
        ]
        logger.info("\n%s", _fmt_table("Guest Identity (Linux)", rows))
        return

    if identity.type == GuestType.WINDOWS:
        reg_hives = identity.metadata.get("registry_hives", [])
        win_dirs = identity.metadata.get("windows_dirs", [])
        rows = [
            ("Operating System", identity.os_name or "Windows"),
            ("Architecture", identity.architecture or "unknown"),
            ("Windows Distro", identity.windows_distro or "n/a"),
            ("Version", f"{identity.windows_major or '?'}.{identity.windows_minor or '?'}"),
            ("Build Number", identity.windows_build or "n/a"),
            ("Display Version", identity.windows_display_version or "n/a"),
            ("Edition", identity.windows_edition or "n/a"),
            ("Registry Hives", str(len(reg_hives)) if isinstance(reg_hives, list) else "n/a"),
            ("Windows Dirs", str(len(win_dirs)) if isinstance(win_dirs, list) else "n/a"),
            ("Detection", f"{identity.detection_method} ({identity.confidence * 100:.0f}%)"),
        ]
        logger.info("\n%s", _fmt_table("Guest Identity (Windows)", rows))
        return

    rows = [
        ("Detected Type", identity.type.value),
        ("Detection", f"{identity.detection_method} ({identity.confidence * 100:.0f}%)"),
    ]
    logger.info("\n%s", _fmt_table("Guest Identity (Unknown)", rows))
