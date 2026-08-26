# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# hyper2kvm/deployers/kubernetes.py
"""
Kubernetes/k3s deployment module for hyper2kvm.

Automatically deploys migrated VMs to Kubernetes clusters with KubeVirt.
"""

from __future__ import annotations

import contextlib
import os
import re
import secrets
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

from hyper2kvm.converters.qemu.converter import Convert, run_qemu_img_convert
from hyper2kvm.core.exceptions import DiskConversionError, InfrastructureError
from hyper2kvm.core.firmware_resolver import serial_indicates_boot_failure
from hyper2kvm.infrastructure.deployers.kubevirt_guest_profile import (
    LINUX_SSH_PORT,
    WINDOWS_RDP_PORT,
    build_kubevirt_vm_manifest,
    is_windows_guest,
)

try:
    from kubernetes import client, config
    from kubernetes.client.rest import ApiException

    HAS_KUBERNETES = True
except ImportError:
    HAS_KUBERNETES = False


def _exception_chain_text(exc: BaseException) -> str:
    """Flatten exception __cause__/__context__ for substring checks."""
    parts: list[str] = []
    seen: set[int] = set()
    cur: BaseException | None = exc
    while cur is not None and id(cur) not in seen:
        seen.add(id(cur))
        parts.append(f"{type(cur).__name__} {cur}")
        cur = cur.__cause__ or cur.__context__
    return " ".join(parts).lower()


def _is_k8s_tls_verify_failure(exc: BaseException) -> bool:
    """True when urllib3/ssl rejected the Kubernetes API server certificate."""
    blob = _exception_chain_text(exc)
    return (
        "sslcertverificationerror" in blob
        or "certificate_verify_failed" in blob
        or "certificate verify failed" in blob
        or "self-signed certificate" in blob
        or "self signed certificate" in blob
    )


def _is_k8s_unreachable(exc: BaseException) -> bool:
    """True for TCP/DNS/timeouts when TLS verification is not the root cause."""
    if _is_k8s_tls_verify_failure(exc):
        return False
    blob = _exception_chain_text(exc)
    return (
        "connection refused" in blob
        or "connection reset" in blob
        or "max retries exceeded" in blob
        or "name or service not known" in blob
        or "nodename nor servname" in blob
        or "timed out" in blob
        or "network is unreachable" in blob
        or "no route to host" in blob
    )


def _extract_api_server_url(exc: BaseException) -> str | None:
    """Best-effort parse of https://host:port from urllib3/kubernetes tracebacks."""
    blob = _exception_chain_text(exc)
    m = re.search(r"https?://[^\s)\"']+", blob)
    return m.group(0).rstrip(".,)") if m else None


def _stderr_suggests_cdi_qcow2_incompatible(stderr: str) -> bool:
    """True when CDI/qemu-img rejects qcow2 compression (e.g. zstd vs older importer)."""
    s = (stderr or "").lower()
    if "unknown compression type" in s:
        return True
    if "unsupported compression" in s:
        return True
    return "compression type" in s and "qemu-img" in s and "qcow2" in s


def _stderr_suggests_cdi_pvc_not_ready(stderr: str) -> bool:
    """True when virtctl ran before CDI created the upload PVC (race after DataVolume create)."""
    s = (stderr or "").lower()
    if "persistentvolumeclaims" in s and "not found" in s:
        return True
    if "persistentvolumeclaim" in s and "not found" in s:
        return True
    return "datavolumes" in s and "not found" in s


def _stderr_suggests_cdi_upload_transient(stderr: str) -> bool:
    """True when virtctl/CDI upload failed for a retryable reason (not qcow2 codec).

    virtctl defaults to --wait-secs=300; slow local-path provisioning or a long
    pre-upload qemu re-encode often hits ``rate: Wait(n=1) would exceed context deadline``.
    """
    s = (stderr or "").lower()
    if "rate limiter" in s and "deadline" in s:
        return True
    if "exceed context deadline" in s:
        return True
    if "context deadline exceeded" in s:
        return True
    return "timed out" in s and ("upload" in s or "waiting for pvc" in s)


# CDI upload annotations (see kubevirt containerized-data-importer).
_CDI_POD_READY_ANNOTATION = "cdi.kubevirt.io/storage.pod.ready"
_CDI_POD_PHASE_ANNOTATION = "cdi.kubevirt.io/storage.pod.phase"
_CDI_FORCE_BIND_ANNOTATION = "cdi.kubevirt.io/storage.bind.immediate.requested"
_CDI_DV_PHASE_UPLOAD_READY = "UploadReady"

# Wait for UploadReady in Python first (actionable logs); virtctl then uploads.
_CDI_UPLOAD_READY_TIMEOUT_S = 900
# virtctl --wait-secs: upload-server readiness after pre-wait + HTTP transfer window.
_VIRTCTL_UPLOAD_WAIT_SECS = 3600
_VIRTCTL_UPLOAD_RETRIES = 10


def _qcow2_json_compression_type(info: dict[str, Any]) -> str | None:
    """Return lowercased qcow2 ``compression-type`` from ``qemu-img info --output=json`` if present."""
    fs = info.get("format-specific")
    if not isinstance(fs, dict):
        return None
    data = fs.get("data")
    if not isinstance(data, dict):
        return None
    raw = data.get("compression-type") or data.get("compression_type")
    if raw is None:
        return None
    return str(raw).strip().lower() or None


def _qcow2_json_uses_zstd(info: dict[str, Any]) -> bool:
    """True when image json reports zstd qcow2 clusters (incompatible with many CDI importers)."""
    if (info.get("format") or "").lower() != "qcow2":
        return False
    return _qcow2_json_compression_type(info) == "zstd"


def standard_kubeconfig_candidates() -> tuple[Path, ...]:
    """Well-known kubeconfig paths; prefer /etc (k3s, RKE2, kubeadm) before ~/.kube/config."""
    return (
        Path("/etc/rancher/k3s/k3s.yaml"),
        Path("/etc/rancher/rke2/rke2.yaml"),
        Path("/etc/kubernetes/admin.conf"),
        Path("/var/snap/microk8s/current/credentials/client.config"),
        Path.home() / ".kube" / "config",
    )


def kubeconfig_flavor_hint(path: Path) -> str:
    """Short label for logs (k3s vs kubeadm vs user copy)."""
    s = str(path)
    if "/rancher/k3s/" in s or s.endswith("/k3s.yaml"):
        return "k3s"
    if "/rancher/rke2/" in s or "rke2.yaml" in s:
        return "rke2"
    if "admin.conf" in s:
        return "kubeadm"
    if "microk8s" in s:
        return "microk8s"
    return "user"


def pick_preferred_kubeconfig(paths: list[str]) -> str | None:
    """Resolve KUBECONFIG env (possibly multiple paths): prefer existing files under /etc/."""
    existing: list[str] = []
    for p in paths:
        if not p or not p.strip():
            continue
        expanded = str(Path(p.strip()).expanduser())
        if Path(expanded).is_file():
            existing.append(expanded)
    if not existing:
        return None
    if len(existing) == 1:
        return existing[0]
    etc = [p for p in existing if p.startswith("/etc/")]
    if etc:
        priority = (
            "/etc/rancher/k3s/k3s.yaml",
            "/etc/rancher/rke2/rke2.yaml",
            "/etc/kubernetes/admin.conf",
            "/var/snap/microk8s/current/credentials/client.config",
        )
        for want in priority:
            if want in etc:
                return want
        return etc[0]
    return existing[0]


def sanitize_k8s_dns_subdomain(name: str, *, max_len: int = 253) -> str:
    """
    Normalize a string for Kubernetes metadata.name and OCI image path segments:
    lowercase RFC 1123 DNS subdomain (PVC, VM, Pod names; containerd requires lowercase repos).
    """
    s = name.strip().lower()
    s = re.sub(r"[^a-z0-9.-]+", "-", s)
    s = re.sub(r"-+", "-", s).strip("-")
    s = re.sub(r"\.+", ".", s)
    if not s:
        s = "vm"
    # Start/end with alphanumeric (required by API validation)
    s = re.sub(r"^[^a-z0-9]+", "", s)
    s = re.sub(r"[^a-z0-9]+$", "", s)
    if not s:
        s = "vm"
    if len(s) > max_len:
        s = s[:max_len].rstrip("-")
        s = re.sub(r"[^a-z0-9]+$", "", s)
    if not s:
        s = "vm"
    return s


# podman/buildah COPY into scratch images streams via tar; very large qcow2 layers hit
# Go tar limits ("archive/tar: write too long"). Skip containerDisk above this size.
CONTAINER_DISK_QCOW2_MAX_BYTES = int(
    os.environ.get("HYPER2KVM_CONTAINER_DISK_MAX_BYTES", str(4 * 1024 * 1024 * 1024))
)


class KubernetesDeployer:
    """Deploy migrated VMs to Kubernetes with KubeVirt."""

    def __init__(self, logger, args):
        """
        Initialize Kubernetes deployer.

        Args:
            logger: Logger instance
            args: Parsed arguments with k8s deployment options
        """
        self.logger = logger
        self.args = args

        if not HAS_KUBERNETES:
            raise InfrastructureError(
                code=69, msg="Cannot deploy to Kubernetes: kubernetes Python package not installed"
            ).with_context(
                solutions=[
                    "Install kubernetes client: pip install kubernetes",
                    "Or use alternative deployment method (libvirt, manual)",
                ]
            )

        # K8s deployment options
        self.namespace = getattr(args, "k8s_namespace", "default")
        self.vm_name = getattr(args, "k8s_vm_name", None)
        self.pvc_name = getattr(args, "k8s_pvc_name", None)
        self.storage_class = getattr(args, "k8s_storage_class", "local-path")
        self.pvc_size = getattr(args, "k8s_pvc_size", "10Gi")
        self.cpu_cores = getattr(args, "k8s_cpu", "2")
        self.memory = getattr(args, "k8s_memory", "2Gi")
        self.auto_start = getattr(args, "k8s_auto_start", False)
        self.wait_ready = getattr(args, "k8s_wait_ready", True)
        self.novnc = getattr(args, "k8s_novnc", False)
        self.novnc_port = int(getattr(args, "k8s_novnc_port", 0) or 0)  # 0 = auto-allocate
        self.stop_before_deploy = getattr(args, "k8s_stop_before_deploy", True)
        self.stop_wait_timeout = max(30, int(getattr(args, "k8s_stop_wait_timeout", 600) or 600))
        self.root_disk_bus = self._resolve_root_disk_bus(args)

        # Same kubeconfig path kubectl + Python will use (for preflight messages)
        self._loaded_incluster = False
        self._kubeconfig_resolved_path: str | None = None

        # Initialize k8s client — auto-detect kubeconfig from multiple sources
        try:
            config.load_incluster_config()
            self._loaded_incluster = True
            self.logger.info("Loaded in-cluster Kubernetes config")
        except config.ConfigException:
            kubeconfig_path = self._find_kubeconfig()
            try:
                if kubeconfig_path:
                    config.load_kube_config(config_file=kubeconfig_path)
                    self._kubeconfig_resolved_path = kubeconfig_path
                    self.logger.info("Loaded Kubernetes config from %s", kubeconfig_path)
                else:
                    config.load_kube_config()
                    # Match explicit path used by kubectl preflight: prefer /etc cluster configs
                    kc = os.environ.get("KUBECONFIG", "").strip()
                    if kc:
                        picked = pick_preferred_kubeconfig(kc.split(os.pathsep))
                        if picked:
                            self._kubeconfig_resolved_path = picked
                    if not self._kubeconfig_resolved_path:
                        for p in standard_kubeconfig_candidates():
                            if p.is_file():
                                self._kubeconfig_resolved_path = str(p)
                                break
                    self.logger.info("Loaded Kubernetes config from default kubeconfig")
            except config.ConfigException as e:
                raise InfrastructureError(
                    code=69, msg=f"Failed to load Kubernetes configuration: {e}"
                ).with_context(
                    solutions=[
                        "Set KUBECONFIG environment variable or pass --kubeconfig <path>",
                        "For K3s: kubeconfig is at /etc/rancher/k3s/k3s.yaml",
                        "For MicroK8s: try microk8s config > ~/.kube/config",
                        "Check that ~/.kube/config exists and is readable",
                    ]
                ) from e

        self.core_api = client.CoreV1Api()
        self.custom_api = client.CustomObjectsApi()

    @staticmethod
    def _resolve_root_disk_bus(args: Any) -> str:
        """KubeVirt root disk bus: Windows defaults to SATA (no in-guest virtio driver required)."""
        raw = (getattr(args, "k8s_disk_bus", None) or "auto").strip().lower()
        if raw != "auto":
            return raw
        guest = (getattr(args, "guest_os", None) or "").strip().lower()
        if guest == "windows" or bool(getattr(args, "windows", False)):
            return "sata"
        return "virtio"

    def _find_kubeconfig(self) -> str | None:
        """Auto-detect kubeconfig from user args, env, or well-known paths.

        Search order:
        1. --kubeconfig CLI arg
        2. KUBECONFIG (single path, or multiple paths — prefer files under /etc/)
        3. Host installs under /etc (k3s, RKE2, kubeadm, MicroK8s) before ~/.kube/config
        """
        # 1. User-supplied via CLI
        user_path = getattr(self.args, "kubeconfig", None)
        if user_path and Path(user_path).is_file():
            return str(user_path)

        # 2. KUBECONFIG — may be OS-pathsep-separated list
        env_raw = os.environ.get("KUBECONFIG", "").strip()
        if env_raw:
            parts = [p.strip() for p in env_raw.split(os.pathsep) if p.strip()]
            picked = pick_preferred_kubeconfig(parts)
            if picked:
                self.logger.debug("Kubeconfig from KUBECONFIG env: %s", picked)
                return picked

        # 3. Prefer distro/cluster configs on disk (fixes broken ~/.kube pointing at wrong CA)
        for p in standard_kubeconfig_candidates():
            if p.is_file():
                self.logger.info(
                    "Auto-selected kubeconfig %s (%s)",
                    p,
                    kubeconfig_flavor_hint(p),
                )
                return str(p)

        return None

    def _kubectl_env_for_host(self) -> dict[str, str]:
        """Environment for kubectl/virtctl subprocesses.

        systemd services often omit HOME; kubectl then defaults to localhost:8080.
        Ensure KUBECONFIG matches the Python client.
        """
        env = os.environ.copy()
        kcfg = self._kubeconfig_resolved_path or self._find_kubeconfig()
        if kcfg and Path(kcfg).is_file():
            env["KUBECONFIG"] = kcfg
        if not (env.get("HOME") or "").strip():
            env["HOME"] = "/root"
        return env

    def _kubectl_argv_prefix(self) -> list[str]:
        """kubectl with explicit --kubeconfig (same file as kubernetes Python client)."""
        kubectl = shutil.which("kubectl")
        if not kubectl:
            kubectl = "kubectl"
        if self._loaded_incluster:
            return [kubectl]
        kcfg = self._kubeconfig_resolved_path or self._find_kubeconfig()
        if kcfg and Path(kcfg).is_file():
            return [kubectl, "--kubeconfig", kcfg]
        return [kubectl]

    def _msg_tls_verification_failed(self, exc: BaseException) -> str:
        """User-facing TLS message; includes API URL when present in the traceback."""
        url = _extract_api_server_url(exc)
        head = (
            f"Kubernetes API endpoint was found at {url}, but TLS verification failed. "
            if url
            else "Kubernetes API TLS verification failed. "
        )
        return (
            head + "This usually means h2kvmctl is not using the k3s kubeconfig CA data. "
            "Set KUBECONFIG=/etc/rancher/k3s/k3s.yaml or copy it to ~/.kube/config."
        )

    def _preflight_kubectl(self) -> None:
        """Reachability + TLS + KubeVirt CRD using the same kubeconfig file as config.load_kube_config."""
        if self._loaded_incluster:
            self.logger.info(
                "Preflight: in-cluster config — skipping kubectl --kubeconfig checks "
                "(reachability/TLS validated via Python client)"
            )
            return

        kcfg = self._kubeconfig_resolved_path
        if not kcfg or not Path(kcfg).is_file():
            raise InfrastructureError(
                code=69,
                msg=f"Preflight: kubeconfig file not found or not resolved (path={kcfg!r})",
            ).with_context(
                solutions=[
                    "Set KUBECONFIG or pass --kubeconfig to a readable file",
                    "For k3s: /etc/rancher/k3s/k3s.yaml",
                ],
            )

        kubectl = shutil.which("kubectl")
        if not kubectl:
            self.logger.warning(
                "kubectl not in PATH — skipping kubectl preflight; "
                "validating reachability and TLS with the Python client only"
            )
            return

        self.logger.info("Preflight — kubeconfig: %s", kcfg)

        def run_kubectl(args: list[str]) -> subprocess.CompletedProcess:
            return subprocess.run(
                [kubectl, "--kubeconfig", kcfg, *args],
                capture_output=True,
                text=True,
                timeout=90,
                check=False,
            )

        r = run_kubectl(["cluster-info"])
        if r.returncode != 0:
            err = (r.stderr or r.stdout or "").strip()
            raise InfrastructureError(
                code=69,
                msg=f"Preflight failed: Kubernetes cluster unreachable with kubeconfig {kcfg}: {err}",
            ).with_context(
                solutions=[
                    "Verify the API server is running and the server URL in kubeconfig is correct",
                    "Compare: kubectl --kubeconfig " + kcfg + " cluster-info",
                ],
                kubeconfig=kcfg,
            )

        r = run_kubectl(["get", "--raw", "/api/v1"])
        if r.returncode != 0:
            err = (r.stderr or r.stdout or "").strip()
            el = err.lower()
            if any(x in el for x in ("x509", "certificate", "tls", "verify", "authority")):
                raise InfrastructureError(
                    code=69,
                    msg=(
                        "Preflight failed: Kubernetes API/TLS validation failed with kubectl "
                        f"(kubeconfig {kcfg}). {err}"
                    ),
                ).with_context(
                    solutions=[
                        "Use a kubeconfig that embeds certificate-authority-data",
                        "For k3s: export KUBECONFIG=/etc/rancher/k3s/k3s.yaml",
                        "Ensure certificate-authority file paths in kubeconfig exist on this host",
                    ],
                    kubeconfig=kcfg,
                )
            raise InfrastructureError(
                code=69,
                msg=f"Preflight failed: kubectl get --raw /api/v1 failed with kubeconfig {kcfg}: {err}",
            ).with_context(
                solutions=["Check kube-apiserver and kubeconfig server URL"],
                kubeconfig=kcfg,
            )

        r = run_kubectl(["get", "crd", "virtualmachines.kubevirt.io"])
        if r.returncode != 0:
            err = (r.stderr or r.stdout or "").strip()
            raise InfrastructureError(
                code=69,
                msg=f"Preflight failed: KubeVirt CRD missing (kubeconfig {kcfg}): {err}",
            ).with_context(
                solutions=[
                    "Install KubeVirt: https://kubevirt.io/user-guide/cluster_admin/installation/",
                ],
                kubeconfig=kcfg,
            )

        self.logger.info("Preflight OK: Kubernetes reachable, TLS trusted (kubectl), KubeVirt CRD present")

    def deploy(self, qcow2_path: str) -> dict[str, Any]:
        """
        Deploy QCOW2 image to Kubernetes cluster.

        Args:
            qcow2_path: Path to the migrated QCOW2 image

        Returns:
            Dict with deployment details (namespace, vm_name, pvc_name, etc.)
        """
        self.logger.info("━" * 80)
        self.logger.info("🚀 Deploying to Kubernetes/k3s")
        self.logger.info("━" * 80)

        # Validate image exists
        if not Path(qcow2_path).exists():
            raise DiskConversionError(
                code=66, msg=f"Cannot deploy: QCOW2 image not found at {qcow2_path}"
            ).with_context(
                solutions=[
                    "Verify the migration completed successfully",
                    "Check the output directory contains the converted image",
                    "Ensure the file path is correct",
                ],
                qcow2_path=qcow2_path,
            )

        # Set defaults if not provided
        if not self.vm_name:
            self.vm_name = Path(qcow2_path).stem
        raw_vm = self.vm_name
        self.vm_name = sanitize_k8s_dns_subdomain(self.vm_name, max_len=63)
        if self.vm_name != raw_vm:
            self.logger.info("Normalized VM name for Kubernetes/DNS: %r → %s", raw_vm, self.vm_name)

        if not self.pvc_name:
            self.pvc_name = f"{self.vm_name}-disk"
        else:
            raw_pvc = self.pvc_name
            self.pvc_name = sanitize_k8s_dns_subdomain(self.pvc_name, max_len=253)
            if self.pvc_name != raw_pvc:
                self.logger.info("Normalized PVC name for Kubernetes: %r → %s", raw_pvc, self.pvc_name)

        self.logger.info(f"Namespace: {self.namespace}")
        self.logger.info(f"VM Name: {self.vm_name}")
        self.logger.info(f"PVC Name: {self.pvc_name}")
        self.logger.info(f"Storage Class: {self.storage_class}")
        self.logger.info("KubeVirt root disk bus: %s", self.root_disk_bus)

        # Step 1: Preflight (kubectl: same kubeconfig as Python client) + validate (Python client)
        self._preflight_kubectl()
        self._validate_cluster()

        # Step 2: Create namespace if needed
        self._ensure_namespace()

        # Step 2b: Halt existing KubeVirt VM so PVC/disk can be updated (offline migrate)
        self._stop_existing_kubevirt_vm_if_needed()

        # Step 3: Upload image to PVC (CDI if available, fallback to kubectl cp)
        self._upload_image_auto(qcow2_path)

        # Step 3b: Remove prior VM definition so we can recreate the same name (PVC unchanged)
        self._remove_existing_kubevirt_vm_before_recreate()

        # Step 4: Create VirtualMachine resource
        vm_created = self._create_vm()

        # Step 5: Optionally start and wait
        if self.auto_start:
            self._start_vm()
            if self.wait_ready:
                self._wait_for_vm()
            if getattr(self.args, "firmware_fallback", True):
                self._maybe_firmware_fallback_after_deploy()

        # Step 6: Deploy noVNC web console if requested
        novnc_url = None
        if self.novnc:
            novnc_url = self._deploy_novnc()

        if is_windows_guest(self.args):
            self._log_windows_rdp_access_hints(guest_ip=self._get_vmi_guest_ip())

        self.logger.info("━" * 80)
        self.logger.info("✅ Kubernetes deployment complete")
        if novnc_url:
            self.logger.info(f"🖥  noVNC console: {novnc_url}")
        self.logger.info("━" * 80)

        result = {
            "namespace": self.namespace,
            "vm_name": self.vm_name,
            "pvc_name": self.pvc_name,
            "vm_created": vm_created,
            "vm_started": self.auto_start,
        }
        if novnc_url:
            result["novnc_url"] = novnc_url
        return result

    def _validate_cluster(self):
        """Validate Kubernetes cluster is accessible."""
        self.logger.info("➡️ Validating Kubernetes cluster")

        try:
            self.core_api.get_api_resources()
            self.logger.info("✅ Cluster is accessible")
        except ApiException as e:
            if e.status in (401, 403):
                raise InfrastructureError(
                    code=77,
                    msg=f"Kubernetes authentication failed (HTTP {e.status}): credentials may be expired or lack permissions",
                ).with_context(
                    solutions=[
                        "Refresh credentials: kubectl config use-context <context>",
                        "For K3s: ensure /etc/rancher/k3s/k3s.yaml is readable",
                        "Check RBAC: kubectl auth can-i list pods --namespace default",
                        "Re-login if using OIDC/SSO authentication",
                    ],
                    namespace=self.namespace,
                    http_status=e.status,
                ) from e
            raise InfrastructureError(
                code=69, msg=f"Kubernetes API error (HTTP {e.status}): {e.reason}"
            ).with_context(
                solutions=[
                    "Verify kubectl can connect: kubectl cluster-info",
                    "Check KUBECONFIG is set correctly",
                    "Ensure the cluster is running and accessible",
                ],
                namespace=self.namespace,
                http_status=e.status,
            ) from e
        except Exception as e:
            if _is_k8s_tls_verify_failure(e):
                raise InfrastructureError(
                    code=69,
                    msg=self._msg_tls_verification_failed(e),
                ).with_context(
                    solutions=[
                        "Use a kubeconfig that embeds certificate-authority-data (fix broken certificate-authority paths).",
                        "For k3s: export KUBECONFIG=/etc/rancher/k3s/k3s.yaml or copy to ~/.kube/config with correct ownership.",
                        "Match environments: if h2kvmctl runs under systemd/sudo, set KUBECONFIG there too.",
                        "Check: kubectl cluster-info; grep -E 'certificate-authority|server:' \"$KUBECONFIG\"",
                        "Verify KubeVirt after TLS works: kubectl get crd virtualmachines.kubevirt.io",
                    ],
                    namespace=self.namespace,
                    kubeconfig=self._kubeconfig_resolved_path,
                ) from e
            if _is_k8s_unreachable(e):
                raise InfrastructureError(
                    code=69,
                    msg=(
                        "Cannot reach Kubernetes API. Check k3s/kube-apiserver is running and "
                        f"KUBECONFIG is correct for this host. ({e})"
                    ),
                ).with_context(
                    solutions=[
                        "kubectl cluster-info using the same kubeconfig as h2kvmctl",
                        "For k3s: systemctl status k3s",
                    ],
                    namespace=self.namespace,
                    kubeconfig=self._kubeconfig_resolved_path,
                ) from e
            raise InfrastructureError(code=69, msg=f"Cannot reach Kubernetes cluster: {e}").with_context(
                solutions=[
                    "Verify kubectl can connect: kubectl cluster-info",
                    "Check KUBECONFIG is set correctly",
                    "Ensure the cluster is running and network connectivity is working",
                ],
                namespace=self.namespace,
                kubeconfig=self._kubeconfig_resolved_path,
            ) from e

        # Check for KubeVirt — auto-install if missing
        try:
            self.custom_api.get_api_resources(group="kubevirt.io", version="v1")
            self.logger.info("✅ KubeVirt CRDs found")
        except ApiException:
            self.logger.info("KubeVirt not found — installing automatically...")
            self._install_kubevirt()

        # Check for CDI — auto-install if missing
        if not self._has_cdi():
            self.logger.info("CDI not found — installing automatically...")
            self._install_cdi()

    def _install_kubevirt(self):
        """Auto-install KubeVirt operator + CR if not present."""
        try:
            # Get stable version
            result = subprocess.run(
                [
                    "curl",
                    "-sL",
                    "https://storage.googleapis.com/kubevirt-prow/release/kubevirt/kubevirt/stable.txt",
                ],
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            version = result.stdout.strip()
            if not version.startswith("v"):
                self.logger.warning("⚠️  Could not determine KubeVirt version")
                return

            self.logger.info(f"Installing KubeVirt {version}...")
            base = f"https://github.com/kubevirt/kubevirt/releases/download/{version}"

            # Install operator
            subprocess.run(
                ["kubectl", "apply", "-f", f"{base}/kubevirt-operator.yaml"],
                capture_output=True,
                text=True,
                timeout=120,
                check=True,
            )
            # Install CR
            subprocess.run(
                ["kubectl", "apply", "-f", f"{base}/kubevirt-cr.yaml"],
                capture_output=True,
                text=True,
                timeout=30,
                check=True,
            )

            # Wait for KubeVirt to be available (up to 5 minutes)
            self.logger.info("Waiting for KubeVirt to be ready...")
            subprocess.run(
                [
                    "kubectl",
                    "-n",
                    "kubevirt",
                    "wait",
                    "kv",
                    "kubevirt",
                    "--for",
                    "condition=Available",
                    "--timeout=300s",
                ],
                capture_output=True,
                text=True,
                timeout=330,
                check=False,
            )
            self.logger.info(f"✅ KubeVirt {version} installed")

            # Install virtctl if not present
            # SECURITY: virtctl binary is downloaded without checksum verification.
            # Full verification would require fetching checksums from the GitHub
            # release page. As a best-effort measure, we compute and log the sha256
            # so operators can manually verify it.
            import shutil

            if not shutil.which("virtctl"):
                import hashlib
                import platform

                arch = "amd64" if platform.machine() in ("x86_64", "AMD64") else "arm64"
                self.logger.info("Installing virtctl...")
                subprocess.run(
                    [
                        "curl",
                        "-sL",
                        "-o",
                        "/usr/local/bin/virtctl",
                        f"{base}/virtctl-{version}-linux-{arch}",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=120,
                    check=True,
                )
                subprocess.run(["chmod", "+x", "/usr/local/bin/virtctl"], check=False)
                try:
                    with open("/usr/local/bin/virtctl", "rb") as _f:
                        sha256 = hashlib.sha256(_f.read()).hexdigest()
                    self.logger.warning(
                        f"⚠️  virtctl downloaded WITHOUT checksum verification. "
                        f"SHA256: {sha256} — verify against upstream release page."
                    )
                except Exception:
                    self.logger.warning("⚠️  virtctl downloaded WITHOUT checksum verification.")
                self.logger.info("✅ virtctl installed")

        except Exception as e:
            self.logger.warning(
                f"KubeVirt auto-install failed: {e}. "
                "KubeVirt is required to run VMs on Kubernetes. Install manually:\n"
                "  kubectl apply -f https://github.com/kubevirt/kubevirt/releases/latest/download/kubevirt-operator.yaml\n"
                "  kubectl apply -f https://github.com/kubevirt/kubevirt/releases/latest/download/kubevirt-cr.yaml\n"
                "  Docs: https://kubevirt.io/user-guide/cluster_admin/installation/"
            )

    def _install_cdi(self):
        """Auto-install CDI (Containerized Data Importer) if not present."""
        try:
            result = subprocess.run(
                [
                    "curl",
                    "-sL",
                    "https://api.github.com/repos/kubevirt/containerized-data-importer/releases/latest",
                ],
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            import json as _json

            version = _json.loads(result.stdout).get("tag_name", "")
            if not version:
                self.logger.warning("⚠️  Could not determine CDI version")
                return

            self.logger.info(f"Installing CDI {version}...")
            base = f"https://github.com/kubevirt/containerized-data-importer/releases/download/{version}"

            subprocess.run(
                ["kubectl", "apply", "-f", f"{base}/cdi-operator.yaml"],
                capture_output=True,
                text=True,
                timeout=120,
                check=True,
            )
            subprocess.run(
                ["kubectl", "apply", "-f", f"{base}/cdi-cr.yaml"],
                capture_output=True,
                text=True,
                timeout=30,
                check=True,
            )

            # Wait for CDI to deploy (up to 3 minutes)
            self.logger.info("Waiting for CDI to be ready...")
            for _ in range(18):
                if self._has_cdi():
                    self.logger.info(f"✅ CDI {version} installed")
                    return
                time.sleep(10)

            self.logger.warning("⚠️  CDI installed but not yet ready — continuing")

        except Exception as e:
            self.logger.warning(
                f"CDI (Containerized Data Importer) auto-install failed: {e}. "
                "CDI is needed for disk image upload to KubeVirt. Install manually:\n"
                "  kubectl apply -f https://github.com/kubevirt/containerized-data-importer/releases/latest/download/cdi-operator.yaml\n"
                "  kubectl apply -f https://github.com/kubevirt/containerized-data-importer/releases/latest/download/cdi-cr.yaml"
            )

    def _ensure_namespace(self):
        """Create namespace if it doesn't exist."""
        self.logger.info(f"➡️ Ensuring namespace: {self.namespace}")

        try:
            self.core_api.read_namespace(self.namespace)
            self.logger.info(f"✅ Namespace exists: {self.namespace}")
        except ApiException as e:
            if e.status == 404:
                # Create namespace
                ns = client.V1Namespace(metadata=client.V1ObjectMeta(name=self.namespace))
                self.core_api.create_namespace(ns)
                self.logger.info(f"✅ Created namespace: {self.namespace}")
            else:
                raise

    def _kubevirt_vmi_exists(self) -> bool:
        """Return True if a VirtualMachineInstance exists for ``self.vm_name``."""
        try:
            self.custom_api.get_namespaced_custom_object(
                group="kubevirt.io",
                version="v1",
                namespace=self.namespace,
                plural="virtualmachineinstances",
                name=self.vm_name,
            )
            return True
        except ApiException as e:
            if e.status == 404:
                return False
            raise

    def _patch_vm_run_strategy_halted(self) -> None:
        """Request runStrategy=Halted on the VirtualMachine (stops guest when VMI is running)."""
        self.custom_api.patch_namespaced_custom_object(
            group="kubevirt.io",
            version="v1",
            namespace=self.namespace,
            plural="virtualmachines",
            name=self.vm_name,
            body={"spec": {"runStrategy": "Halted"}},
        )

    def _virtctl_stop_vm(self) -> bool:
        """Run ``virtctl stop`` if available. Returns False if virtctl is missing or errors."""
        virtctl = shutil.which("virtctl")
        if not virtctl:
            return False
        cmd = [virtctl, "stop", self.vm_name, "-n", self.namespace]
        if not self._loaded_incluster:
            kcfg = self._kubeconfig_resolved_path or self._find_kubeconfig()
            if kcfg and Path(kcfg).is_file():
                cmd.extend(["--kubeconfig", kcfg])
        r = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
            env=self._kubectl_env_for_host(),
            check=False,
        )
        if r.returncode != 0:
            err = (r.stderr or r.stdout or "").strip()
            self.logger.warning("virtctl stop failed (rc=%s): %s", r.returncode, err[:500])
            return False
        return True

    def _wait_until_vmi_gone(self) -> None:
        """Poll until the VMI is deleted or timeout (disk is safe to replace)."""
        deadline = time.time() + float(self.stop_wait_timeout)
        interval = 3.0
        while time.time() < deadline:
            if not self._kubevirt_vmi_exists():
                self.logger.info("✅ VMI gone — safe to update PVC disk")
                return
            time.sleep(interval)
        raise InfrastructureError(
            code=69,
            msg=(
                f"Timed out after {self.stop_wait_timeout}s waiting for VMI {self.vm_name!r} "
                "to terminate. Stop the VM manually or increase --k8s-stop-wait-timeout."
            ),
        ).with_context(
            namespace=self.namespace,
            vm_name=self.vm_name,
            solutions=[
                f"virtctl stop {self.vm_name} -n {self.namespace}",
                f"kubectl get vmi -n {self.namespace} {self.vm_name} -o wide",
            ],
        )

    def _stop_existing_kubevirt_vm_if_needed(self) -> None:
        """If a VM with this name is running, stop it before uploading to its PVC."""
        if not self.stop_before_deploy:
            return
        try:
            self.custom_api.get_namespaced_custom_object(
                group="kubevirt.io",
                version="v1",
                namespace=self.namespace,
                plural="virtualmachines",
                name=self.vm_name,
            )
        except ApiException as e:
            if e.status == 404:
                return
            raise

        if not self._kubevirt_vmi_exists():
            self.logger.debug("No VMI for %r — skip pre-deploy stop", self.vm_name)
            return

        self.logger.info(
            "➡️ Stopping KubeVirt VM %r before disk upload (offline migrate / redeploy)",
            self.vm_name,
        )
        if not self._virtctl_stop_vm():
            self.logger.info("Applying runStrategy=Halted on VirtualMachine %r", self.vm_name)
            self._patch_vm_run_strategy_halted()

        self._wait_until_vmi_gone()

    def _wait_until_vm_crd_gone(self, timeout_s: float = 120.0) -> None:
        """Poll until the VirtualMachine object is deleted."""
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            try:
                self.custom_api.get_namespaced_custom_object(
                    group="kubevirt.io",
                    version="v1",
                    namespace=self.namespace,
                    plural="virtualmachines",
                    name=self.vm_name,
                )
            except ApiException as e:
                if e.status == 404:
                    return
                raise
            time.sleep(2.0)
        raise InfrastructureError(
            code=69,
            msg=f"Timed out waiting for VirtualMachine {self.vm_name!r} to be deleted",
        ).with_context(namespace=self.namespace, vm_name=self.vm_name)

    def _remove_existing_kubevirt_vm_before_recreate(self) -> None:
        """Delete existing VM so ``_create_vm`` can reuse the same name after a disk refresh."""
        if not self.stop_before_deploy:
            return
        try:
            self.custom_api.get_namespaced_custom_object(
                group="kubevirt.io",
                version="v1",
                namespace=self.namespace,
                plural="virtualmachines",
                name=self.vm_name,
            )
        except ApiException as e:
            if e.status == 404:
                return
            raise

        if self._kubevirt_vmi_exists():
            self.logger.info(
                "VMI still present before recreate — stopping again (namespace=%s)",
                self.namespace,
            )
            if not self._virtctl_stop_vm():
                self._patch_vm_run_strategy_halted()
            self._wait_until_vmi_gone()

        self.logger.info(
            "➡️ Deleting existing VirtualMachine %r (PVC %r is kept) for offline redeploy",
            self.vm_name,
            self.pvc_name,
        )
        try:
            self.custom_api.delete_namespaced_custom_object(
                group="kubevirt.io",
                version="v1",
                namespace=self.namespace,
                plural="virtualmachines",
                name=self.vm_name,
            )
        except ApiException as e:
            if e.status == 404:
                return
            raise
        self._wait_until_vm_crd_gone()

    def _create_pvc(self):
        """Create PersistentVolumeClaim for VM disk.

        On HTTP 409 (name already taken), pick a new ``{base}-{random}`` name and
        retry so a stale PVC from a prior failed run does not block this deploy.
        """
        self.logger.info("➡️ Creating PVC (collision-safe)")

        base = self.pvc_name
        last_exc: ApiException | None = None

        for attempt in range(16):
            if attempt > 0:
                self.pvc_name = sanitize_k8s_dns_subdomain(
                    f"{base}-{secrets.token_hex(4)}",
                    max_len=253,
                )
                self.logger.info(
                    "PVC name was taken — trying new name %r (attempt %d/16)",
                    self.pvc_name,
                    attempt + 1,
                )

            pvc = client.V1PersistentVolumeClaim(
                metadata=client.V1ObjectMeta(name=self.pvc_name),
                spec=client.V1PersistentVolumeClaimSpec(
                    access_modes=["ReadWriteOnce"],
                    volume_mode="Filesystem",
                    storage_class_name=self.storage_class,
                    resources=client.V1ResourceRequirements(requests={"storage": self.pvc_size}),
                ),
            )

            try:
                self.core_api.create_namespaced_persistent_volume_claim(namespace=self.namespace, body=pvc)
                self.logger.info("✅ Created PVC: %s", self.pvc_name)
                return
            except ApiException as e:
                last_exc = e
                if e.status == 409:
                    if self._pvc_exists(self.pvc_name):
                        self.logger.info(
                            "PVC %s appeared during create — reusing it",
                            self.pvc_name,
                        )
                        return
                    continue
                raise

        raise InfrastructureError(
            code=69,
            msg=f"Could not create a PVC after 16 name attempts (last name={self.pvc_name!r})",
        ).with_context(
            solutions=[
                "Delete stuck PVCs: kubectl get pvc -n " + self.namespace,
                "Or pick a unique k8s_pvc_name in config",
            ],
            namespace=self.namespace,
            last_error=str(last_exc) if last_exc else "",
        ) from last_exc

    def _pvc_exists(self, name: str) -> bool:
        """Return True if a PVC with ``name`` already exists in the deploy namespace."""
        try:
            self.core_api.read_namespaced_persistent_volume_claim(name=name, namespace=self.namespace)
            return True
        except ApiException as e:
            if e.status == 404:
                return False
            raise

    def _ensure_pvc_for_upload(self) -> None:
        """Create the target PVC or reuse one from a pre-created CDI DataVolume."""
        if self._pvc_exists(self.pvc_name):
            self.logger.info(
                "Reusing existing PVC %s for disk upload (CDI DataVolume or prior attempt)",
                self.pvc_name,
            )
            return
        if self._wait_for_cdi_upload_pvc(timeout_s=600):
            self.logger.info(
                "Reusing PVC %s provisioned by CDI DataVolume",
                self.pvc_name,
            )
            return
        self._create_pvc()

    def _wait_for_cdi_upload_pvc(self, *, timeout_s: int = 600) -> bool:
        """Poll until the upload PVC exists (CDI creates it after the DataVolume)."""
        deadline = time.time() + max(30, int(timeout_s))
        logged = False
        while time.time() < deadline:
            if self._pvc_exists(self.pvc_name):
                if not logged:
                    self.logger.info("✅ Upload PVC exists: %s", self.pvc_name)
                return True
            if not logged:
                self.logger.info(
                    "Waiting for CDI to create upload PVC %s (DataVolume controller)...",
                    self.pvc_name,
                )
                logged = True
            time.sleep(2)
        self.logger.warning(
            "Upload PVC %s not found after %ds — CDI may still be provisioning",
            self.pvc_name,
            timeout_s,
        )
        return False

    def _read_cdi_upload_status(self) -> dict[str, Any]:
        """Snapshot DataVolume phase and PVC upload annotations."""
        status: dict[str, Any] = {
            "dv_phase": None,
            "dv_message": None,
            "pvc_phase": None,
            "upload_pod_ready": False,
            "upload_pod_phase": None,
        }
        try:
            dv = self.custom_api.get_namespaced_custom_object(
                group="cdi.kubevirt.io",
                version="v1beta1",
                namespace=self.namespace,
                plural="datavolumes",
                name=self.pvc_name,
            )
            dv_status = dv.get("status") if isinstance(dv.get("status"), dict) else {}
            status["dv_phase"] = dv_status.get("phase")
            status["dv_message"] = dv_status.get("message") or dv_status.get("conditions")
        except ApiException as e:
            if e.status != 404:
                self.logger.debug("DataVolume status read failed: %s", e)
        except Exception as e:
            self.logger.debug("DataVolume status read failed: %s", e)

        try:
            pvc = self.core_api.read_namespaced_persistent_volume_claim(
                name=self.pvc_name, namespace=self.namespace
            )
            if pvc.status and pvc.status.phase:
                status["pvc_phase"] = pvc.status.phase
            ann = pvc.metadata.annotations if pvc.metadata and pvc.metadata.annotations else {}
            ready_raw = ann.get(_CDI_POD_READY_ANNOTATION, "")
            status["upload_pod_ready"] = str(ready_raw).lower() == "true"
            status["upload_pod_phase"] = ann.get(_CDI_POD_PHASE_ANNOTATION)
        except ApiException as e:
            if e.status != 404:
                self.logger.debug("PVC status read failed: %s", e)
        except Exception as e:
            self.logger.debug("PVC status read failed: %s", e)

        return status

    def _cdi_upload_target_ready(self, status: dict[str, Any]) -> bool:
        if status.get("dv_phase") == _CDI_DV_PHASE_UPLOAD_READY:
            return True
        return bool(status.get("upload_pod_ready"))

    def _format_cdi_upload_status(self, status: dict[str, Any]) -> str:
        return (
            f"dv_phase={status.get('dv_phase')!r} "
            f"pvc_phase={status.get('pvc_phase')!r} "
            f"upload_pod_ready={status.get('upload_pod_ready')!r} "
            f"upload_pod_phase={status.get('upload_pod_phase')!r}"
        )

    def _log_cdi_upload_diagnostics(self) -> None:
        """Emit DV/PVC state and recent events when CDI upload is stuck."""
        status = self._read_cdi_upload_status()
        self.logger.warning(
            "CDI upload diagnostics for %s/%s: %s",
            self.namespace,
            self.pvc_name,
            self._format_cdi_upload_status(status),
        )
        if status.get("dv_message"):
            self.logger.warning("DataVolume status detail: %s", status["dv_message"])

        for kind, name in (("DataVolume", self.pvc_name), ("PersistentVolumeClaim", self.pvc_name)):
            try:
                evs = self.core_api.list_namespaced_event(
                    namespace=self.namespace,
                    field_selector=f"involvedObject.name={name}",
                )
                for ev in (evs.items or [])[-8:]:
                    self.logger.warning(
                        "CDI event [%s/%s] %s: %s",
                        kind,
                        name,
                        ev.reason,
                        (ev.message or "")[:500],
                    )
            except Exception as e:
                self.logger.debug("Could not list events for %s: %s", name, e)

        self.logger.warning(
            "Check: kubectl -n %s describe dv,pvc %s; kubectl -n cdi get pods; "
            "kubectl -n %s get pods | grep upload",
            self.namespace,
            self.pvc_name,
            self.namespace,
        )

    def _wait_for_cdi_upload_ready(self, *, timeout_s: int = _CDI_UPLOAD_READY_TIMEOUT_S) -> bool:
        """Wait until CDI reports UploadReady or the upload server pod is ready."""
        deadline = time.time() + max(60, int(timeout_s))
        last_log = 0.0
        self.logger.info(
            "Waiting for CDI upload readiness on %s (up to %ds, phase=%s)...",
            self.pvc_name,
            timeout_s,
            _CDI_DV_PHASE_UPLOAD_READY,
        )
        while time.time() < deadline:
            status = self._read_cdi_upload_status()
            if self._cdi_upload_target_ready(status):
                self.logger.info(
                    "✅ CDI upload target ready: %s",
                    self._format_cdi_upload_status(status),
                )
                return True
            now = time.time()
            if now - last_log >= 30.0:
                self.logger.info(
                    "CDI upload not ready yet (%s)",
                    self._format_cdi_upload_status(status),
                )
                last_log = now
            time.sleep(3)

        self.logger.warning(
            "CDI upload target %s not ready after %ds",
            self.pvc_name,
            timeout_s,
        )
        self._log_cdi_upload_diagnostics()
        return False

    def _has_cdi(self) -> bool:
        """Check if CDI (Containerized Data Importer) is available."""
        try:
            result = self.custom_api.list_cluster_custom_object(
                group="cdi.kubevirt.io",
                version="v1beta1",
                plural="cdis",
            )
            items = result.get("items", [])
            if items:
                phase = items[0].get("status", {}).get("phase", "")
                return phase == "Deployed"
            return False
        except Exception as e:
            self.logger.debug(f"CDI deployment check failed: {e}")
            return False

    def _get_cdi_upload_url(self) -> str | None:
        """Get CDI upload proxy URL."""
        try:
            svc = self.core_api.read_namespaced_service("cdi-uploadproxy", "cdi")
            ip = svc.spec.cluster_ip
            return f"https://{ip}:443"
        except Exception as e:
            self.logger.debug(f"CDI upload proxy URL not available: {e}")
            return None

    def _rewrite_qcow2_for_cdi_importer(self, qcow2_path: str) -> Path | None:
        """Re-encode qcow2 to qcow2 1.1 + zlib for CDI's older ``qemu-img`` importer.

        CDI rejects zstd clusters (``unknown compression type: 1``). We do not use
        ``compression_type=none`` — many host qemu-img builds reject that value and
        waste minutes before the zlib pass.
        """
        src = Path(qcow2_path)
        dst = src.with_name(f"{src.stem}.cdi-compat{src.suffix}")

        _cdi_qcow2_zlib_opts = "compat=1.1,compression_type=zlib,lazy_refcounts=off"

        def try_convert(argv: list[str], label: str) -> bool:
            self.logger.info("CDI compat: qemu-img convert (%s) → %s", label, dst.name)
            last_logged = [-1.0]

            def _progress(frac: float) -> None:
                pct = frac * 100.0
                if pct < 99.5 and pct - last_logged[0] < 3.0:
                    return
                last_logged[0] = pct
                self.logger.info("CDI compat re-encode (%s): %.1f%%", label, pct)

            try:
                run_qemu_img_convert(
                    self.logger,
                    argv,
                    dst,
                    src=src,
                    task_label=f"CDI compat re-encode ({label})",
                    progress_callback=_progress,
                    log_every_s=8.0,
                )
            except KeyboardInterrupt:
                raise
            except subprocess.CalledProcessError as e:
                tail = (e.stderr or "").strip() if isinstance(e.stderr, str) else ""
                self.logger.warning(
                    "CDI compat convert (%s) failed rc=%s: %s",
                    label,
                    e.returncode,
                    tail[:1200] if tail else "(no output)",
                )
                with contextlib.suppress(OSError):
                    dst.unlink(missing_ok=True)
                return False
            if dst.is_file():
                self.logger.info("CDI compat: re-encode complete (%s)", label)
                return True
            with contextlib.suppress(OSError):
                dst.unlink(missing_ok=True)
            return False

        with contextlib.suppress(OSError):
            dst.unlink(missing_ok=True)

        if try_convert(
            [
                "qemu-img",
                "convert",
                "-p",
                "-f",
                "qcow2",
                "-O",
                "qcow2",
                "-c",
                "-o",
                _cdi_qcow2_zlib_opts,
                str(src),
                str(dst),
            ],
            "qcow2 1.1 + zlib (CDI-safe)",
        ):
            return dst

        return None

    def _ensure_cdi_dv_force_bind(self) -> None:
        """Patch an existing upload DataVolume so local-path binds before virtctl waits."""
        patch = {
            "metadata": {
                "annotations": {_CDI_FORCE_BIND_ANNOTATION: ""},
            },
        }
        try:
            self.custom_api.patch_namespaced_custom_object(
                group="cdi.kubevirt.io",
                version="v1beta1",
                namespace=self.namespace,
                plural="datavolumes",
                name=self.pvc_name,
                body=patch,
            )
            self.logger.info(
                "Patched DataVolume %s with %s (immediate bind for WFFC storage)",
                self.pvc_name,
                _CDI_FORCE_BIND_ANNOTATION,
            )
        except ApiException as e:
            self.logger.warning(
                "Could not patch DataVolume %s for immediate bind (status=%s)",
                self.pvc_name,
                e.status,
            )

    def _ensure_cdi_upload_datavolume(self, pvc_size: str) -> str:
        """Create an upload DataVolume with explicit PVC fields for local-path and similar SCs.

        StorageProfiles like local-path often cannot infer accessMode/volumeMode; CDI then
        rejects the DataVolume. Returns ``dv`` when a DataVolume was created or already
        exists (use ``virtctl image-upload dv … --no-create``), else ``pvc`` for virtctl
        to create the target with CLI flags.
        """
        dv_body: dict[str, Any] = {
            "apiVersion": "cdi.kubevirt.io/v1beta1",
            "kind": "DataVolume",
            "metadata": {
                "name": self.pvc_name,
                "namespace": self.namespace,
                # local-path (and other WFFC storage classes) stay Pending until a
                # consumer exists unless CDI is told to bind immediately (virtctl --force-bind).
                "annotations": {_CDI_FORCE_BIND_ANNOTATION: ""},
            },
            "spec": {
                "source": {"upload": {}},
                "pvc": {
                    "accessModes": ["ReadWriteOnce"],
                    "volumeMode": "Filesystem",
                    "resources": {"requests": {"storage": pvc_size}},
                    "storageClassName": self.storage_class,
                },
            },
        }
        try:
            self.custom_api.create_namespaced_custom_object(
                group="cdi.kubevirt.io",
                version="v1beta1",
                namespace=self.namespace,
                plural="datavolumes",
                body=dv_body,
            )
            self.logger.info(
                "Created upload DataVolume %s (accessMode=ReadWriteOnce, volumeMode=Filesystem, "
                "storageClass=%s, immediateBind=true)",
                self.pvc_name,
                self.storage_class,
            )
            return "dv"
        except ApiException as e:
            if e.status == 409:
                self.logger.info(
                    "Reusing existing upload target %s for CDI image-upload",
                    self.pvc_name,
                )
                self._ensure_cdi_dv_force_bind()
                return "dv"
            self.logger.warning(
                "Could not pre-create DataVolume %s (status=%s) — virtctl will create the PVC/DV",
                self.pvc_name,
                e.status,
            )
            return "pvc"

    def _upload_via_cdi(self, qcow2_path: str) -> bool:
        """Upload image via CDI virtctl image-upload (handles qcow2→raw conversion)."""
        upload_url = self._get_cdi_upload_url()
        if not upload_url:
            self.logger.warning("⚠️  CDI upload proxy not found")
            return False

        # Use user-specified PVC size, or derive from actual disk usage.
        # CDI needs PVC >= virtual size, but local-path provisioner is thin.
        # Use the user's --k8s-pvc-size if set, otherwise use virtual size.
        pvc_size = self.pvc_size
        sized = False
        info: dict[str, Any] | None = None
        try:
            info = Convert.qemu_img_info(self.logger, Path(qcow2_path))
            virtual_bytes = int(info.get("virtual-size", 0) or 0)
            actual_bytes = int(info.get("actual-size", 0) or 0)
            virtual_gib = virtual_bytes / (1024**3)
            actual_gib = actual_bytes / (1024**3)
            # PVC must be >= virtual size for CDI
            pvc_gib = max(int(virtual_gib * 1.05) + 1, 5)  # virtual + overhead
            pvc_size = f"{pvc_gib}Gi"
            sized = True
            self.logger.info(
                "Image: virtual=%.0fG actual=%.1fG → PVC=%s",
                virtual_gib,
                actual_gib,
                pvc_size,
            )
        except Exception as e:
            self.logger.warning("Could not determine exact image size for PVC sizing: %s", e)
            try:
                sb = Path(qcow2_path).stat().st_size
                file_gib = sb / (1024**3)
                # Conservative when JSON fails: qcow2 actual size < virtual; CDI expands to raw.
                pvc_gib = max(int(file_gib * 1.2) + 8, 35)
                pvc_gib = min(pvc_gib, 2048)
                pvc_size = f"{pvc_gib}Gi"
                sized = True
                self.logger.info(
                    "PVC size fallback from file size (~%.1f GiB on disk): %s",
                    file_gib,
                    pvc_size,
                )
            except OSError:
                pass

        if not sized:
            self.logger.info("Using configured PVC size (no size probe): %s", pvc_size)

        self.logger.info("➡️ Uploading via CDI (PVC size: %s)", pvc_size)

        kubeconfig = self._find_kubeconfig()

        upload_target = self._ensure_cdi_upload_datavolume(pvc_size)
        if upload_target == "dv":
            if not self._wait_for_cdi_upload_pvc(timeout_s=600):
                self._log_cdi_upload_diagnostics()
                return False
            if not self._wait_for_cdi_upload_ready():
                return False

        wait_secs = _VIRTCTL_UPLOAD_WAIT_SECS
        subprocess_timeout = wait_secs + 7200  # upload transfer + CDI import after pod ready

        def virtctl_cmd(image_path: str, *, wait_secs_override: int | None = None) -> list[str]:
            ws = wait_secs_override if wait_secs_override is not None else wait_secs
            cmd = [
                "virtctl",
                "image-upload",
                upload_target,
                self.pvc_name,
                f"--size={pvc_size}",
                f"--image-path={image_path}",
                f"--uploadproxy-url={upload_url}",
                "--insecure",
                "--force-bind",
                f"--wait-secs={ws}",
                f"--retry={_VIRTCTL_UPLOAD_RETRIES}",
                "--access-mode=ReadWriteOnce",
                "--volume-mode=filesystem",
                f"--namespace={self.namespace}",
            ]
            if self.storage_class:
                cmd.append(f"--storage-class={self.storage_class}")
            if upload_target == "dv":
                cmd.append("--no-create")
            if kubeconfig:
                cmd.append(f"--kubeconfig={kubeconfig}")
            return cmd

        def run_virtctl(
            image_path: str, *, wait_secs_override: int | None = None
        ) -> subprocess.CompletedProcess[str]:
            cmd = virtctl_cmd(image_path, wait_secs_override=wait_secs_override)
            self.logger.info("Running: %s", " ".join(cmd))
            return subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=subprocess_timeout,
                env=self._kubectl_env_for_host(),
                check=False,
            )

        compat_tmp: Path | None = None
        zstd_preencoded = False
        try:
            upload_src = qcow2_path
            if info is not None and _qcow2_json_uses_zstd(info):
                self.logger.info(
                    "QCOW2 uses zstd clusters — CDI importer cannot read zstd; "
                    "re-encoding to qcow2+zlib before upload"
                )
                compat = self._rewrite_qcow2_for_cdi_importer(qcow2_path)
                if compat is None:
                    return False
                compat_tmp = compat
                upload_src = str(compat)
                zstd_preencoded = True

            result = run_virtctl(upload_src)
            if result.returncode == 0:
                self.logger.info("✅ Image uploaded via CDI (qcow2→raw conversion handled)")
                return True

            err_blob = f"{result.stderr or ''}\n{result.stdout or ''}"
            self.logger.warning("⚠️  CDI upload failed: %s", (result.stderr or "").strip())

            if _stderr_suggests_cdi_pvc_not_ready(err_blob):
                self.logger.info(
                    "CDI upload PVC not ready yet — waiting for %s then retrying virtctl",
                    self.pvc_name,
                )
                if self._wait_for_cdi_upload_pvc(timeout_s=600):
                    result_pvc = run_virtctl(upload_src)
                    if result_pvc.returncode == 0:
                        self.logger.info("✅ Image uploaded via CDI after PVC became ready")
                        return True
                    err_blob = f"{result_pvc.stderr or ''}\n{result_pvc.stdout or ''}"
                    self.logger.warning(
                        "⚠️  CDI upload still failed after PVC ready: %s",
                        (result_pvc.stderr or "").strip(),
                    )

            if _stderr_suggests_cdi_upload_transient(err_blob):
                self._log_cdi_upload_diagnostics()
                self.logger.warning(
                    "virtctl timed out after --wait-secs=%d (upload pod never became ready "
                    "or transfer stalled). Fix CDI/DataVolume before retrying — not retrying "
                    "the same virtctl command.",
                    wait_secs,
                )
                return False

            if _stderr_suggests_cdi_pvc_not_ready(err_blob):
                self.logger.warning(
                    "CDI upload PVC %s never became ready — not using kubectl cp "
                    "(use virtctl image-upload after `kubectl get pvc` shows Bound)",
                    self.pvc_name,
                )
                return False

            if zstd_preencoded or not _stderr_suggests_cdi_qcow2_incompatible(err_blob):
                return False

            self.logger.info("CDI rejected qcow2 compression — re-encoding to qcow2 1.1 + zlib for importer")
            compat = self._rewrite_qcow2_for_cdi_importer(qcow2_path)
            if compat is None:
                return False
            compat_tmp = compat
            try:
                result2 = run_virtctl(str(compat))
                if result2.returncode == 0:
                    self.logger.info(
                        "✅ Image uploaded via CDI after qcow2 re-encode "
                        "(CDI importer lacked source compression codec)"
                    )
                    return True
                self.logger.warning(
                    "⚠️  CDI upload still failed after qcow2 re-encode: %s",
                    (result2.stderr or "").strip(),
                )
            finally:
                with contextlib.suppress(OSError):
                    compat.unlink(missing_ok=True)
                compat_tmp = None

            return False
        finally:
            if compat_tmp is not None:
                with contextlib.suppress(OSError):
                    compat_tmp.unlink(missing_ok=True)

    def _parse_pvc_size_gib(self) -> int:
        """Parse k8s_pvc_size like '32Gi' or '500Mi' → integer GiB (Mi rounded up)."""
        s = (self.pvc_size or "10Gi").strip().lower()
        m = re.match(r"^(\d+(?:\.\d+)?)\s*gi\s*$", s)
        if m:
            return max(1, int(float(m.group(1))))
        m = re.match(r"^(\d+(?:\.\d+)?)\s*mi\s*$", s)
        if m:
            mib = float(m.group(1))
            return max(1, int((mib + 1023) // 1024))
        return 10

    def _sync_pvc_size_from_disk(self, qcow2_path: str) -> None:
        """Raise PVC request when default is too small for this qcow2 (virtual size)."""
        want_gib = 0
        try:
            import json as _json

            r = subprocess.run(
                ["qemu-img", "info", "--output=json", qcow2_path],
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            raw = (r.stdout or "").strip()
            if r.returncode == 0 and raw:
                info = _json.loads(raw)
                vb = int(info.get("virtual-size", 0) or 0)
                want_gib = max(int(vb / (1024**3) * 1.05) + 1, 5)
        except Exception:
            pass
        if want_gib == 0:
            try:
                sb = Path(qcow2_path).stat().st_size
                file_gib = sb / (1024**3)
                want_gib = max(int(file_gib * 1.2) + 8, 35)
                want_gib = min(want_gib, 2048)
            except OSError:
                return
        cur_gib = self._parse_pvc_size_gib()
        if want_gib > cur_gib:
            self.pvc_size = f"{want_gib}Gi"
            self.logger.info("Adjusted PVC size to %s for disk import (was too small)", self.pvc_size)

    def _build_container_disk(self, qcow2_path: str) -> str | None:
        """Build a container image with the qcow2 and import into the cluster.

        containerDisk is the simplest KubeVirt disk type — wraps qcow2 in a
        container image, no PVC needed, works with any virtual size.

        Returns the image reference if successful, None otherwise.
        """
        import shutil
        import tempfile

        image_tag = f"localhost/hyper2kvm/{self.vm_name}:latest"

        # Check if we can build (need buildah, podman, or docker + ctr/k3s)
        builder = None
        for cmd in ("buildah", "podman", "docker"):
            if shutil.which(cmd):
                builder = cmd
                break

        importer = None
        for cmd in ("ctr", "nerdctl"):
            if shutil.which(cmd):
                importer = cmd
                break

        if not builder:
            self.logger.debug("No container builder found (buildah/podman/docker)")
            return None

        if not importer:
            self.logger.debug("No container importer found (ctr/nerdctl) — cannot load into K3s")
            return None

        try:
            qsz = Path(qcow2_path).stat().st_size
        except OSError as e:
            self.logger.warning("containerDisk: cannot stat %s: %s", qcow2_path, e)
            return None
        if qsz > CONTAINER_DISK_QCOW2_MAX_BYTES:
            self.logger.info(
                "Skipping containerDisk build (%s is %.1f GiB; max %.1f GiB for COPY/tar reliability). "
                "Using CDI or PVC upload instead.",
                Path(qcow2_path).name,
                qsz / (1024**3),
                CONTAINER_DISK_QCOW2_MAX_BYTES / (1024**3),
            )
            return None

        try:
            qcow2_dir = str(Path(qcow2_path).resolve().parent)
            b_env = self._kubectl_env_for_host()

            # Dockerfile uses absolute path as build context
            dockerfile_content = f"FROM scratch\nCOPY {Path(qcow2_path).name} /disk/\n"

            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".Dockerfile", dir=qcow2_dir, delete=False
            ) as df:
                df.write(dockerfile_content)
                dockerfile_path = df.name

            try:
                # Build using the qcow2's directory as build context
                self.logger.info(f"Building containerDisk image: {image_tag}")
                result = subprocess.run(
                    [builder, "build", "-t", image_tag, "-f", dockerfile_path, qcow2_dir],
                    capture_output=True,
                    text=True,
                    timeout=600,
                    env=b_env,
                    check=False,
                )
            finally:
                Path(dockerfile_path).unlink(missing_ok=True)

            if result.returncode != 0:
                self.logger.warning(f"Container build failed: {result.stderr.strip()}")
                return None

            self.logger.info(f"✅ Built containerDisk image: {image_tag}")

            # Import into containerd (K3s/k8s)
            # K3s uses its own containerd socket — detect and use it
            k3s_sock = Path("/run/k3s/containerd/containerd.sock")
            ctr_addr = ["--address", str(k3s_sock)] if k3s_sock.exists() else []

            with tempfile.TemporaryDirectory() as tmpdir:
                tar_path = Path(tmpdir) / "image.tar"
                self.logger.info("Saving image to tar for containerd import...")
                subprocess.run(
                    [builder, "save", "-o", str(tar_path), image_tag],
                    capture_output=True,
                    text=True,
                    timeout=600,
                    check=True,
                    env=b_env,
                )
                if importer == "ctr":
                    subprocess.run(
                        ["ctr", *ctr_addr, "-n", "k8s.io", "images", "import", str(tar_path)],
                        capture_output=True,
                        text=True,
                        timeout=600,
                        check=True,
                        env=b_env,
                    )
                else:
                    subprocess.run(
                        ["nerdctl", *ctr_addr, "-n", "k8s.io", "load", "-i", str(tar_path)],
                        capture_output=True,
                        text=True,
                        timeout=600,
                        check=True,
                        env=b_env,
                    )
                self.logger.info("✅ Imported image into containerd")

            return image_tag

        except Exception as e:
            self.logger.warning(f"containerDisk build failed: {e}")
            return None

    def _upload_image_auto(self, qcow2_path: str):
        """Upload image to cluster: small containerDisk (optional) → CDI → PVC + kubectl cp."""
        self.logger.info("➡️ Uploading image to cluster")

        # 1. Try containerDisk (simplest, no PVC needed, supports any virtual size)
        container_image = self._build_container_disk(qcow2_path)
        if container_image:
            self._container_disk_image = container_image
            return

        self._container_disk_image = None

        # 2. Try CDI upload (handles qcow2→raw conversion)
        if self._has_cdi():
            self.logger.info("CDI detected — using virtctl image-upload")
            if self._upload_via_cdi(qcow2_path):
                return
            self.logger.info("Falling back to kubectl cp method")

        # 3. Fallback: reuse CDI PVC if present, else create + kubectl cp
        self._sync_pvc_size_from_disk(qcow2_path)
        self._ensure_pvc_for_upload()
        self._upload_image(qcow2_path)

    def _upload_image(self, qcow2_path: str):
        """Upload disk image to PVC using a temporary pod (fallback when CDI unavailable).

        KubeVirt requires raw disk format on PVC. If the input is qcow2,
        converts to raw on the host first (sparse file), then copies to the pod.
        """
        # Convert qcow2 → raw if needed (KubeVirt requires raw on PVC)
        upload_path = qcow2_path
        raw_tmp = None
        try:
            info = Convert.qemu_img_info(self.logger, Path(qcow2_path))
            fmt = info.get("format", "")
            if fmt == "qcow2":
                raw_tmp = qcow2_path + ".raw"
                self.logger.info("Converting qcow2 → raw for KubeVirt PVC (sparse)...")
                run_qemu_img_convert(
                    self.logger,
                    [
                        "qemu-img",
                        "convert",
                        "-f",
                        "qcow2",
                        "-O",
                        "raw",
                        "-S",
                        "4k",
                        qcow2_path,
                        raw_tmp,
                    ],
                    Path(raw_tmp),
                    src=Path(qcow2_path),
                    task_label="qcow2 → raw (KubeVirt PVC)",
                    log_every_s=15.0,
                )
                Convert.qemu_img_info(self.logger, Path(raw_tmp))
                self.logger.info("✅ Converted to raw: %s", Path(raw_tmp).name)
                upload_path = raw_tmp
        except Exception as e:
            self.logger.warning("qcow2→raw conversion failed, uploading qcow2 directly: %s", e)
            if raw_tmp and Path(raw_tmp).exists():
                Path(raw_tmp).unlink(missing_ok=True)
                raw_tmp = None

        self.logger.info("➡️ Uploading image to PVC (kubectl cp)")

        # Create uploader pod (unique name per run so a stale pod from a failed run
        # does not leave us attached to the wrong workload on 409 AlreadyExists).
        uploader_name = ""
        for _attempt in range(8):
            stem = self.vm_name[:35].rstrip("-")
            uploader_name = sanitize_k8s_dns_subdomain(
                f"up-{stem}-{secrets.token_hex(4)}",
                max_len=63,
            )
            pod = client.V1Pod(
                metadata=client.V1ObjectMeta(name=uploader_name),
                spec=client.V1PodSpec(
                    restart_policy="Never",
                    containers=[
                        client.V1Container(
                            name="uploader",
                            image="alpine",
                            command=["sleep", "3600"],
                            volume_mounts=[client.V1VolumeMount(name="disk", mount_path="/disk")],
                        )
                    ],
                    volumes=[
                        client.V1Volume(
                            name="disk",
                            persistent_volume_claim=client.V1PersistentVolumeClaimVolumeSource(
                                claim_name=self.pvc_name
                            ),
                        )
                    ],
                ),
            )
            try:
                self.core_api.create_namespaced_pod(namespace=self.namespace, body=pod)
                self.logger.info("Created uploader pod: %s", uploader_name)
                break
            except ApiException as e:
                if e.status == 409:
                    self.logger.info(
                        "Uploader pod name collision on %r — retrying with a new name",
                        uploader_name,
                    )
                    continue
                raise
        else:
            raise InfrastructureError(
                code=69,
                msg="Could not create uploader pod after repeated name collisions",
            ).with_context(namespace=self.namespace)

        # Wait for pod to be ready
        self.logger.info("Waiting for uploader pod to be ready...")
        for _i in range(60):
            try:
                pod_status = self.core_api.read_namespaced_pod_status(
                    name=uploader_name, namespace=self.namespace
                )
                if pod_status.status.phase == "Running":
                    self.logger.info("✅ Uploader pod is ready")
                    break
            except ApiException as e:
                self.logger.debug(f"Uploader pod not ready yet (HTTP {e.status}), retrying...")
            time.sleep(2)
        else:
            raise InfrastructureError(
                code=69, msg=f"Uploader pod {uploader_name} did not become ready within 120 seconds"
            ).with_context(
                solutions=[
                    f"Check pod status: kubectl get pod -n {self.namespace} {uploader_name}",
                    f"Check pod logs: kubectl logs -n {self.namespace} {uploader_name}",
                    "Verify cluster has sufficient resources",
                    "Check if image pull secrets are configured",
                ],
                namespace=self.namespace,
                pod_name=uploader_name,
                timeout_seconds=120,
            )

        # Copy image to pod
        self.logger.info(f"Copying {Path(upload_path).name} to PVC (this may take a while)...")
        cmd = [
            *self._kubectl_argv_prefix(),
            "cp",
            upload_path,
            f"{self.namespace}/{uploader_name}:/disk/disk.img",
        ]

        # Large raw images often exceed the apiserver websocket window (~minutes).
        cp_timeout = max(14400, int(os.environ.get("HYPER2KVM_KUBECTL_CP_TIMEOUT", "14400")))
        self.logger.info(
            "kubectl cp timeout: %ds (set HYPER2KVM_KUBECTL_CP_TIMEOUT to override)",
            cp_timeout,
        )
        cp_result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=cp_timeout,
            env=self._kubectl_env_for_host(),
            check=False,
        )
        if cp_result.returncode != 0:
            raise InfrastructureError(
                code=69, msg=f"Failed to upload image {Path(upload_path).name} to Kubernetes PVC"
            ).with_context(
                solutions=[
                    "Verify kubectl is installed and in PATH",
                    "Check PVC has sufficient space for the image",
                    "Ensure uploader pod is running and has write permissions",
                    f"Check pod logs: kubectl logs -n {self.namespace} {uploader_name}",
                ],
                qcow2_path=qcow2_path,
                namespace=self.namespace,
                pod_name=uploader_name,
                stderr=cp_result.stderr,
            )

        self.logger.info("✅ Image uploaded to PVC")

        # Cleanup temporary raw file
        if raw_tmp and Path(raw_tmp).exists():
            Path(raw_tmp).unlink(missing_ok=True)
            self.logger.info("Cleaned up temporary raw file")

        # Delete uploader pod
        try:
            self.core_api.delete_namespaced_pod(name=uploader_name, namespace=self.namespace)
            self.logger.info("Cleaned up uploader pod")
        except ApiException as e:
            self.logger.debug(f"Uploader pod cleanup skipped (HTTP {e.status}): {e.reason}")

    def _create_vm(self) -> bool:
        """Create KubeVirt VirtualMachine resource.

        On HTTP 409 (name already taken), pick a new ``{base}-{random}`` name and
        retry so this deploy does not attach to an unrelated existing VM.
        """
        # Use runStrategy instead of deprecated spec.running
        run_strategy = "Always" if self.auto_start else "Halted"

        container_image = getattr(self, "_container_disk_image", None)
        if container_image:
            volume: dict[str, Any] = {
                "name": "rootdisk",
                "containerDisk": {"image": container_image, "imagePullPolicy": "Never"},
            }
            self.logger.info("Using containerDisk: %s", container_image)
        else:
            volume = {
                "name": "rootdisk",
                "persistentVolumeClaim": {"claimName": self.pvc_name},
            }

        original_vm = self.vm_name
        last_exc: ApiException | None = None

        for attempt in range(16):
            if attempt > 0:
                self.vm_name = sanitize_k8s_dns_subdomain(
                    f"{original_vm}-{secrets.token_hex(4)}",
                    max_len=63,
                )
                self.logger.info(
                    "VirtualMachine name was taken — trying new name %r (attempt %d/16)",
                    self.vm_name,
                    attempt + 1,
                )

            self.logger.info("➡️ Creating VirtualMachine: %s", self.vm_name)

            vm = build_kubevirt_vm_manifest(
                vm_name=self.vm_name,
                namespace=self.namespace,
                run_strategy=run_strategy,
                volume=volume,
                root_disk_bus=self.root_disk_bus,
                memory=self.memory,
                cpu_cores=self.cpu_cores,
                args=self.args,
            )
            if is_windows_guest(self.args):
                self.logger.info(
                    "KubeVirt VM manifest includes Windows guest hints "
                    "(labels, Hyper-V, auto graphics, RDP port %d)",
                    WINDOWS_RDP_PORT,
                )
            else:
                self.logger.info(
                    "KubeVirt VM manifest includes Linux guest hints (labels, os-variant, SSH port %d)",
                    LINUX_SSH_PORT,
                )

            try:
                self.custom_api.create_namespaced_custom_object(
                    group="kubevirt.io",
                    version="v1",
                    namespace=self.namespace,
                    plural="virtualmachines",
                    body=vm,
                )
                self.logger.info("✅ Created VirtualMachine: %s", self.vm_name)
                return True
            except ApiException as e:
                last_exc = e
                if e.status == 409:
                    continue
                raise

        raise InfrastructureError(
            code=69,
            msg=f"Could not create a VirtualMachine after 16 name attempts (last name={self.vm_name!r})",
        ).with_context(
            solutions=[
                "Delete or rename the conflicting VirtualMachine in the namespace",
                "Or set a unique k8s_vm_name in config",
            ],
            namespace=self.namespace,
            last_error=str(last_exc) if last_exc else "",
        ) from last_exc

    def _start_vm(self):
        """Start the VirtualMachine using runStrategy."""
        self.logger.info(f"➡️ Starting VM: {self.vm_name}")

        patch = {"spec": {"runStrategy": "Always"}}
        try:
            self.custom_api.patch_namespaced_custom_object(
                group="kubevirt.io",
                version="v1",
                namespace=self.namespace,
                plural="virtualmachines",
                name=self.vm_name,
                body=patch,
            )
            self.logger.info(f"✅ VM started: {self.vm_name}")
        except ApiException as e:
            self.logger.exception(f"Failed to start VM: {e}")
            raise

    def _wait_for_vm(self, timeout=300):
        """Wait for VM to be ready."""
        self.logger.info(f"➡️ Waiting for VM to be ready (timeout: {timeout}s)")

        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                vmi = self.custom_api.get_namespaced_custom_object(
                    group="kubevirt.io",
                    version="v1",
                    namespace=self.namespace,
                    plural="virtualmachineinstances",
                    name=self.vm_name,
                )

                phase = vmi.get("status", {}).get("phase", "")
                if phase == "Running":
                    # Check ready condition
                    conditions = vmi.get("status", {}).get("conditions", [])
                    for cond in conditions:
                        if cond.get("type") == "Ready" and cond.get("status") == "True":
                            ip = vmi.get("status", {}).get("interfaces", [{}])[0].get("ipAddress", "N/A")
                            self.logger.info("✅ VM is ready!")
                            self.logger.info(f"   Phase: {phase}")
                            self.logger.info(f"   IP: {ip}")
                            return True

                self.logger.info(f"   VM phase: {phase}, waiting...")
                time.sleep(5)

            except ApiException as e:
                if e.status != 404:
                    raise
                # VMI not created yet, keep waiting
                time.sleep(5)

        self.logger.warning(f"⚠️  VM did not become ready within {timeout}s")
        return False

    def _virtctl_argv_prefix(self) -> list[str]:
        virtctl = shutil.which("virtctl") or "virtctl"
        cmd = [virtctl]
        if not self._loaded_incluster:
            kcfg = self._kubeconfig_resolved_path or self._find_kubeconfig()
            if kcfg and Path(kcfg).is_file():
                cmd.extend(["--kubeconfig", kcfg])
        return cmd

    def _capture_serial_boot_output(self, *, timeout_s: int = 45) -> str:
        """Best-effort serial console capture for firmware boot-failure heuristics."""
        if not shutil.which("virtctl"):
            return ""
        cmd = [
            *self._virtctl_argv_prefix(),
            "console",
            self.vm_name,
            "-n",
            self.namespace,
            f"--timeout={max(5, timeout_s)}",
        ]
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout_s + 15,
                env=self._kubectl_env_for_host(),
                check=False,
            )
            return (proc.stdout or "") + (proc.stderr or "")
        except (subprocess.TimeoutExpired, OSError) as exc:
            self.logger.debug("Serial boot probe skipped: %s", exc)
            return ""

    def _patch_vm_firmware(self, *, uefi: bool) -> None:
        """Patch VM template firmware (BIOS ↔ UEFI) before restart."""
        if uefi:
            secure = bool(getattr(self.args, "win_secure_boot", False))
            firmware: dict[str, Any] = {
                "bootloader": {"efi": {"secureBoot": secure}},
            }
            domain_patch: dict[str, Any] = {"firmware": firmware}
            if secure:
                domain_patch["features"] = {"smm": {"enabled": True}}
        else:
            domain_patch = {"firmware": {"bootloader": {"bios": {}}}}

        patch = {
            "spec": {
                "template": {
                    "spec": {
                        "domain": domain_patch,
                    }
                }
            }
        }
        self.custom_api.patch_namespaced_custom_object(
            group="kubevirt.io",
            version="v1",
            namespace=self.namespace,
            plural="virtualmachines",
            name=self.vm_name,
            body=patch,
        )
        self.args.uefi = uefi
        self.logger.info("Patched VM firmware → %s", "UEFI" if uefi else "BIOS")

    def _maybe_firmware_fallback_after_deploy(self) -> None:
        """
        If serial console shows firmware boot failure, retry once with alternate firmware.

        Skipped when firmware_mode is an explicit user override (bios/uefi).
        """
        user_mode = (getattr(self.args, "firmware_mode", None) or "auto").strip().lower()
        if user_mode in ("bios", "uefi"):
            self.logger.info(
                "Firmware fallback skipped (explicit firmware_mode=%s)",
                user_mode,
            )
            return

        alternate = getattr(self.args, "firmware_alternate", None)
        if not alternate:
            return

        time.sleep(8)
        current_uefi = bool(getattr(self.args, "uefi", False))
        serial = self._capture_serial_boot_output(timeout_s=40)
        if not serial_indicates_boot_failure(serial, current_uefi=current_uefi):
            if serial.strip():
                self.logger.info("Serial boot probe: no firmware failure pattern detected")
            return

        alt_uefi = alternate == "uefi"
        self.logger.warning(
            "Guest boot failure detected with %s firmware — retrying with %s",
            "UEFI" if current_uefi else "BIOS",
            "UEFI" if alt_uefi else "BIOS",
        )

        self._virtctl_stop_vm()
        self._wait_until_vmi_gone()
        self._patch_vm_firmware(uefi=alt_uefi)
        self._start_vm()
        if self.wait_ready:
            self._wait_for_vm(timeout=240)
        retry_serial = self._capture_serial_boot_output(timeout_s=35)
        if serial_indicates_boot_failure(retry_serial, current_uefi=alt_uefi):
            self.logger.warning(
                "Firmware fallback to %s still shows boot errors in serial console — "
                "check disk boot entries or set firmware_mode explicitly",
                alternate,
            )
        else:
            self.logger.info("✅ Firmware fallback to %s completed", alternate.upper())

    def _get_vmi_guest_ip(self) -> str | None:
        """Return the primary guest IP from the VMI status, if the instance exists."""
        try:
            vmi = self.custom_api.get_namespaced_custom_object(
                group="kubevirt.io",
                version="v1",
                namespace=self.namespace,
                plural="virtualmachineinstances",
                name=self.vm_name,
            )
        except ApiException:
            return None
        for iface in vmi.get("status", {}).get("interfaces") or []:
            if iface.get("name") == "default":
                ip = (iface.get("ipAddress") or "").strip()
                if ip:
                    return ip
        return None

    def _log_windows_rdp_access_hints(self, *, guest_ip: str | None = None) -> None:
        """Log how to reach Windows RDP after deploy (NodePort, console, firstboot)."""
        self.logger.info("─" * 60)
        self.logger.info("Windows RDP access (after first guest boot + hyper2kvm-firstboot)")
        self.logger.info(
            "  Firstboot log on guest: C:\\Windows\\Temp\\hyper2kvm-firstboot.log "
            "(marker: C:\\hyper2kvm\\firstboot.done)"
        )
        self.logger.info(
            "  Console: virtctl console %s -n %s",
            self.vm_name,
            self.namespace,
        )
        if guest_ip:
            self.logger.info(
                "  VMI pod/guest IP %s:%d — verify after firstboot: nc -vz %s %d",
                guest_ip,
                WINDOWS_RDP_PORT,
                guest_ip,
                WINDOWS_RDP_PORT,
            )
        else:
            self.logger.info(
                "  VM spec exposes TCP %d on the masquerade interface (ready after firstboot)",
                WINDOWS_RDP_PORT,
            )

        node_ips: list[str] = []
        try:
            nodes = self.core_api.list_node()
            for node in nodes.items:
                for addr in node.status.addresses or []:
                    if addr.type in ("ExternalIP", "InternalIP"):
                        node_ips.append(addr.address)
                        break
        except ApiException:
            pass
        node_ips = list(dict.fromkeys(node_ips))[:3]

        rdp_svc_logged = False
        try:
            svcs = self.core_api.list_namespaced_service(namespace=self.namespace)
            for svc in svcs.items:
                name = svc.metadata.name or ""
                labels = svc.metadata.labels or {}
                name_match = self.vm_name in name
                label_match = labels.get("v9s.io/vm-name") == self.vm_name
                rdp_match = "rdp" in name.lower() or labels.get("v9s.io/rdp-expose") == "true"
                if not (name_match or label_match) or not rdp_match:
                    continue
                for port in svc.spec.ports or []:
                    if port.port != WINDOWS_RDP_PORT:
                        continue
                    rdp_svc_logged = True
                    if port.node_port:
                        hosts = node_ips or ["<node-ip>"]
                        for host in hosts:
                            self.logger.info(
                                "  NodePort RDP: %s:%d (service %s)",
                                host,
                                port.node_port,
                                name,
                            )
                    elif svc.spec.cluster_ip:
                        self.logger.info(
                            "  ClusterIP RDP: %s:%d (service %s) — use NodePort or port-forward",
                            svc.spec.cluster_ip,
                            port.port,
                            name,
                        )
        except ApiException as e:
            self.logger.debug("RDP service discovery failed: %s", e)

        if not rdp_svc_logged:
            self.logger.info(
                "  No RDP NodePort service found for %s — create one or use virtctl console",
                self.vm_name,
            )
        self.logger.info(
            "  Port-forward example: kubectl -n %s port-forward svc/<rdp-service> 3389:%d",
            self.namespace,
            WINDOWS_RDP_PORT,
        )
        self.logger.info("─" * 60)

    def _deploy_novnc(self) -> str | None:
        """Deploy noVNC web console as a Pod + Service proxying to the VM's VNC."""
        self.logger.info(f"➡️ Deploying noVNC web console for {self.vm_name}")

        novnc_name = f"{self.vm_name}-novnc"
        node_port = self.novnc_port

        # Pod: runs websockify + noVNC, proxying to the KubeVirt VNC via virtctl
        # Uses the KubeVirt subresource API to connect VNC directly
        novnc_pod = {
            "apiVersion": "v1",
            "kind": "Pod",
            "metadata": {
                "name": novnc_name,
                "namespace": self.namespace,
                "labels": {
                    "app": novnc_name,
                    "hyper2kvm.io/component": "novnc",
                    "hyper2kvm.io/vm": self.vm_name,
                },
            },
            "spec": {
                "serviceAccountName": "default",
                "containers": [
                    {
                        "name": "novnc",
                        "image": "ghcr.io/novnc/novnc:latest",
                        "ports": [{"containerPort": 6080, "name": "novnc"}],
                        "env": [
                            {"name": "VM_NAME", "value": self.vm_name},
                            {"name": "VM_NAMESPACE", "value": self.namespace},
                        ],
                        "command": ["/bin/sh", "-c"],
                        "args": [
                            "cd /usr/share/novnc && "
                            "websockify --web . 6080 "
                            "--target-config=/tmp/vnc-target || "
                            "websockify --web . 6080 localhost:5900"
                        ],
                        "resources": {
                            "requests": {"cpu": "100m", "memory": "128Mi"},
                            "limits": {"cpu": "500m", "memory": "256Mi"},
                        },
                    },
                    {
                        "name": "vnc-proxy",
                        "image": "quay.io/kubevirt/virtctl:latest",
                        "command": ["virtctl"],
                        "args": [
                            "vnc",
                            self.vm_name,
                            "--proxy-only",
                            "--port",
                            "5900",
                            "-n",
                            self.namespace,
                        ],
                        "ports": [{"containerPort": 5900, "name": "vnc"}],
                        "resources": {
                            "requests": {"cpu": "50m", "memory": "64Mi"},
                            "limits": {"cpu": "200m", "memory": "128Mi"},
                        },
                    },
                ],
            },
        }

        # Service: expose noVNC via NodePort (auto-allocate if port=0)
        port_spec: dict[str, Any] = {
            "name": "novnc",
            "protocol": "TCP",
            "port": 6080,
            "targetPort": 6080,
        }
        if node_port > 0:
            port_spec["nodePort"] = node_port

        novnc_svc = {
            "apiVersion": "v1",
            "kind": "Service",
            "metadata": {
                "name": novnc_name,
                "namespace": self.namespace,
                "labels": {
                    "app": novnc_name,
                    "hyper2kvm.io/component": "novnc",
                },
            },
            "spec": {
                "type": "NodePort",
                "selector": {"app": novnc_name},
                "ports": [port_spec],
            },
        }

        try:
            # Create pod
            try:
                self.core_api.create_namespaced_pod(
                    namespace=self.namespace,
                    body=novnc_pod,
                )
                self.logger.info(f"✅ Created noVNC pod: {novnc_name}")
            except ApiException as e:
                if e.status == 409:
                    self.logger.info(f"noVNC pod already exists: {novnc_name}")
                else:
                    raise

            # Create service (K8s auto-allocates NodePort from --service-node-port-range)
            allocated_port = node_port
            try:
                svc = self.core_api.create_namespaced_service(
                    namespace=self.namespace,
                    body=novnc_svc,
                )
                allocated_port = svc.spec.ports[0].node_port
                self.logger.info(f"✅ Created noVNC service: {novnc_name} (NodePort: {allocated_port})")
            except ApiException as e:
                if e.status == 409:
                    # Already exists — read back the allocated port
                    existing = self.core_api.read_namespaced_service(
                        name=novnc_name,
                        namespace=self.namespace,
                    )
                    allocated_port = existing.spec.ports[0].node_port
                    self.logger.info(
                        f"noVNC service already exists: {novnc_name} (NodePort: {allocated_port})"
                    )
                else:
                    raise

            # Determine node IP for access URL
            node_ip = "localhost"
            try:
                nodes = self.core_api.list_node()
                for node in nodes.items:
                    for addr in node.status.addresses or []:
                        if addr.type in ("ExternalIP", "InternalIP"):
                            node_ip = addr.address
                            break
                    if node_ip != "localhost":
                        break
            except Exception as e:
                self.logger.debug(f"Could not determine node IP for noVNC URL: {e}")

            url = f"http://{node_ip}:{allocated_port}/vnc.html"
            self.logger.info(f"✅ noVNC console available at: {url}")
            return url

        except Exception as e:
            self.logger.warning(f"Failed to deploy noVNC: {e}")
            self.logger.info(
                "You can still access the console via: virtctl vnc %s -n %s", self.vm_name, self.namespace
            )
            return None


def deploy_to_kubernetes(logger, args, qcow2_path: str) -> dict[str, Any]:
    """
    Deploy migrated VM to Kubernetes/k3s.

    Args:
        logger: Logger instance
        args: Parsed arguments
        qcow2_path: Path to the QCOW2 image

    Returns:
        Deployment details dictionary
    """
    deployer = KubernetesDeployer(logger, args)
    return deployer.deploy(qcow2_path)
