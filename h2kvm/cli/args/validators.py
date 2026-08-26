# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# h2kvm/cli/args/validators.py
"""Argument validation functions for CLI inputs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .helpers import _merged_cmd, _merged_get, _merged_secret, _merged_vs_action, _require

if TYPE_CHECKING:
    import argparse


def _validate_json_object_file(path: str, flag: str) -> None:
    if not Path(path).is_file():
        raise SystemExit(f"{flag} file not found: {path}\n    Verify the path exists and is a regular file.")
    try:
        with open(path, encoding="utf-8") as f:
            parsed = json.load(f)
        if not isinstance(parsed, dict):
            raise TypeError(
                'top-level JSON must be a JSON object (e.g., {"key": "value"}), not an array or scalar'
            )
    except Exception as e:
        raise SystemExit(
            f"{flag} is not a valid JSON object file: {path}\n"
            f"    Error: {e}\n"
            f'    The file must contain a JSON object like: {{"key": "value"}}'
        ) from e


def _validate_json_object_inline(js: str, flag: str) -> None:
    try:
        parsed = json.loads(js)
        if not isinstance(parsed, dict):
            raise TypeError(
                'top-level JSON must be a JSON object (e.g., {"key": "value"}), not an array or scalar'
            )
    except Exception as e:
        raise SystemExit(
            f"{flag} is not valid inline JSON: {e}\n"
            f'    Expected format: \'{{"key": "value"}}\'\n'
            f"    Ensure quotes are properly escaped for your shell."
        ) from e


def _validate_win_net_override_inputs(args: argparse.Namespace, conf: dict[str, Any]) -> None:
    """
    Validate Windows network override knobs without doing any filesystem writes.

    Rules:
      - win_net_override: file must exist and parse as JSON object (dict)
      - win_net_json: must parse as JSON object (dict)
      - both may be set, but win_net_override takes precedence downstream
    """
    p = _merged_get(args, conf, "win_net_override")
    js = _merged_get(args, conf, "win_net_json")

    if _require(p):
        _validate_json_object_file(str(p), "--win-net-override")

    if _require(js):
        _validate_json_object_inline(str(js), "--win-net-json")


def _validate_virtio_config_inputs(args: argparse.Namespace, conf: dict[str, Any]) -> None:
    """
    Validate VirtIO driver-definition config knobs.

    Rules:
      - virtio_config_path: file must exist; extension must be .json/.yaml/.yml
      - virtio_config_json: must parse as JSON object (dict)
    """
    pth = _merged_get(args, conf, "virtio_config_path")
    js = _merged_get(args, conf, "virtio_config_json")

    if _require(pth):
        path = str(pth)
        if not Path(path).is_file():
            raise SystemExit(
                f"--virtio-config file not found: {path}\n"
                f"    Provide a valid path to a VirtIO driver configuration file."
            )
        ext = Path(path).suffix.lower()
        if ext not in (".json", ".yaml", ".yml"):
            raise SystemExit(
                f"--virtio-config file has unsupported extension '{ext}': {path}\n"
                f"    Supported extensions: .json, .yaml, .yml"
            )

    if _require(js):
        _validate_json_object_inline(str(js), "--virtio-config-json")


def _pick_vsphere_vm_name(args: argparse.Namespace, conf: dict[str, Any]) -> str | None:
    vm_name = conf.get("vm_name")
    if not _require(vm_name):
        vm_name = getattr(args, "vm_name_vsphere", None)
    if not _require(vm_name):
        vms = getattr(args, "vs_vms", None)
        vm_name = getattr(args, "vs_vm", None) or (vms[0] if vms else None)
    return str(vm_name) if _require(vm_name) else None


def _validate_cmd_local(args: argparse.Namespace, conf: dict[str, Any]) -> None:
    if not _require(_merged_get(args, conf, "vmdk")):
        raise SystemExit("cmd=local: missing required `vmdk:` (YAML) or CLI override --vmdk")


def _validate_cmd_fetch_and_fix(args: argparse.Namespace, conf: dict[str, Any]) -> None:
    if not _require(_merged_get(args, conf, "host")):
        raise SystemExit("cmd=fetch-and-fix: missing required `host:` (YAML) or CLI --host")
    if not _require(_merged_get(args, conf, "remote")):
        raise SystemExit("cmd=fetch-and-fix: missing required `remote:` (YAML) or CLI --remote")


def _validate_cmd_ova(args: argparse.Namespace, conf: dict[str, Any]) -> None:
    if not _require(_merged_get(args, conf, "ova")):
        raise SystemExit("cmd=ova: missing required `ova:` (YAML) or CLI --ova")


def _validate_cmd_ovf(args: argparse.Namespace, conf: dict[str, Any]) -> None:
    if not _require(_merged_get(args, conf, "ovf")):
        raise SystemExit("cmd=ovf: missing required `ovf:` (YAML) or CLI --ovf")


def _validate_cmd_vhd(args: argparse.Namespace, conf: dict[str, Any]) -> None:
    if not _require(_merged_get(args, conf, "vhd")):
        raise SystemExit("cmd=vhd: missing required `vhd:` (YAML) or CLI --vhd")


def _validate_cmd_ami(args: argparse.Namespace, conf: dict[str, Any]) -> None:
    if not _require(_merged_get(args, conf, "ami")):
        raise SystemExit("cmd=ami: missing required `ami:` (YAML) or CLI --ami")


def _validate_cmd_raw(args: argparse.Namespace, conf: dict[str, Any]) -> None:
    """Validate raw command (raw disk image or tarball)."""
    # Accept multiple arg names for raw input
    raw_src = (
        _merged_get(args, conf, "raw")
        or _merged_get(args, conf, "img")
        or _merged_get(args, conf, "raw_src")
        or _merged_get(args, conf, "raw_path")
    )
    if not _require(raw_src):
        raise SystemExit(
            "cmd=raw: missing required raw disk input\n"
            "Provide one of: `raw:`, `img:`, `raw_src:`, or `raw_path:` (YAML)\n"
            "Or CLI: --raw <path>"
        )


def _validate_cmd_live_fix(args: argparse.Namespace, conf: dict[str, Any]) -> None:
    if not _require(_merged_get(args, conf, "host")):
        raise SystemExit("cmd=live-fix: missing required `host:` (YAML) or CLI --host")


def _validate_vsphere_identity(args: argparse.Namespace, conf: dict[str, Any]) -> tuple[str, str, str]:
    vcenter = _merged_get(args, conf, "vcenter")
    vc_user = _merged_get(args, conf, "vc_user")
    vc_password = _merged_secret(args, conf, "vc_password", "vc_password_env")

    if not _require(vcenter):
        raise SystemExit("cmd=vsphere: missing required `vcenter:` (YAML) or CLI --vcenter")
    if not _require(vc_user):
        raise SystemExit("cmd=vsphere: missing required `vc_user:` (YAML) or CLI --vc-user")
    if not _require(vc_password):
        raise SystemExit(
            "cmd=vsphere: missing vCenter password. Set `vc_password:` or `vc_password_env:` (or CLI equivalents)."
        )

    return str(vcenter), str(vc_user), str(vc_password)


def _validate_vsphere_control_plane(
    args: argparse.Namespace, conf: dict[str, Any], vcenter: str, vc_user: str, vc_password: str
) -> None:
    vs_cp = _merged_get(args, conf, "vs_control_plane")
    if not _require(vs_cp):
        vs_cp = conf.get("vs_control_plane") or "govc"
    vs_cp = str(vs_cp).strip().lower()

    govc_url = _merged_get(args, conf, "govc_url")
    govc_user = _merged_get(args, conf, "govc_user") or vc_user
    govc_password = _merged_secret(args, conf, "govc_password", "govc_password_env") or vc_password

    if not _require(govc_url) and _require(vcenter):
        govc_url = f"https://{str(vcenter).strip()}/sdk"

    if vs_cp in ("govc", "auto"):
        if not _require(govc_url):
            raise SystemExit("cmd=vsphere: vs_control_plane requires `govc_url:` (or it must be derivable).")
        if not _require(govc_user):
            raise SystemExit("cmd=vsphere: vs_control_plane requires `govc_user:` (or `vc_user:`).")
        if not _require(govc_password):
            raise SystemExit(
                "cmd=vsphere: vs_control_plane requires `govc_password:`/`govc_password_env:` (or `vc_password:`)."
            )

    elif vs_cp == "pyvmomi":
        return
    else:
        raise SystemExit(f"cmd=vsphere: invalid vs_control_plane={vs_cp!r} (use auto|govc|pyvmomi)")


def _validate_vsphere_download_transport(args: argparse.Namespace, conf: dict[str, Any]) -> str:
    dl = _merged_get(args, conf, "vs_download_transport")
    if not _require(dl):
        dl = conf.get("vs_download_transport")

    legacy = conf.get("vs_transport")
    if not _require(dl) and _require(legacy):
        dl = str(legacy).strip().lower()

    dl = str(dl).strip().lower() if _require(dl) else "https"
    if dl == "auto":
        dl = "https"
    if dl not in ("https", "http"):
        raise SystemExit(f"cmd=vsphere: invalid vs_download_transport={dl!r} (use https|http|auto)")
    return dl


def _validate_vsphere_action_requirements(  # pylint: disable=too-many-locals,too-many-branches
    args: argparse.Namespace, conf: dict[str, Any], act: str
) -> None:
    # Validates per-vs_action required fields; branches are inherent (one per distinct vs_action).
    vm_name = _pick_vsphere_vm_name(args, conf)

    name = conf.get("name")
    if not _require(name):
        name = getattr(args, "name_vsphere", None)

    label_or_index = conf.get("label_or_index")
    if not _require(label_or_index):
        label_or_index = getattr(args, "label_or_index", None)

    datastore = (
        conf.get("datastore") if _require(conf.get("datastore")) else getattr(args, "datastore", None)
    )
    ds_path = conf.get("ds_path") if _require(conf.get("ds_path")) else getattr(args, "ds_path", None)
    local_path = (
        conf.get("local_path") if _require(conf.get("local_path")) else getattr(args, "local_path", None)
    )

    needs_vm = {
        "vm_disks",
        "select_disk",
        "download_vm_disk",
        "cbt_sync",
        "create_snapshot",
        "enable_cbt",
        "query_changed_disk_areas",
        "download_only_vm",
        "vddk_download_disk",
        "export_vm",
        "ovftool_export",
    }
    if act in needs_vm and not _require(vm_name):
        raise SystemExit(
            f"cmd=vsphere vs_action={act}: missing required `vm_name:` (YAML) or CLI --vm_name (or --vs-vm)"
        )

    if act == "get_vm_by_name" and not _require(name):
        raise SystemExit(
            "cmd=vsphere vs_action=get_vm_by_name: missing required `name:` (YAML) or CLI --name"
        )

    if act == "select_disk" and not _require(label_or_index):
        raise SystemExit(
            "cmd=vsphere vs_action=select_disk: missing required `label_or_index:` (YAML) or CLI --label_or_index"
        )

    if act == "download_datastore_file":
        for k, vv in (("datastore", datastore), ("ds_path", ds_path), ("local_path", local_path)):
            if not _require(vv):
                raise SystemExit(
                    f"cmd=vsphere vs_action=download_datastore_file: missing required `{k}:` (YAML) or CLI --{k}"
                )

    if act in ("download_vm_disk", "vddk_download_disk", "cbt_sync") and not _require(local_path):
        raise SystemExit(
            f"cmd=vsphere vs_action={act}: missing required `local_path:` (YAML) or CLI --local_path"
        )

    if act == "download_only_vm":
        outd = conf.get("vs_output_dir")
        if not _require(outd):
            outd = getattr(args, "vs_output_dir", None) or getattr(args, "output_dir", None)
        if not _require(outd):
            raise SystemExit(
                "cmd=vsphere vs_action=download_only_vm: missing `vs_output_dir:` (or set --output-dir)."
            )

    if act == "query_changed_disk_areas":
        device_key = (
            conf.get("device_key") if _require(conf.get("device_key")) else getattr(args, "device_key", None)
        )
        disk = conf.get("disk") if _require(conf.get("disk")) else getattr(args, "disk", None)
        if not (_require(device_key) or _require(disk)):
            raise SystemExit(
                "cmd=vsphere vs_action=query_changed_disk_areas: must set `device_key:` OR `disk:` "
                "in YAML (or CLI overrides)."
            )

    if act == "ovftool_deploy":
        sp = conf.get("source_path")
        if not _require(sp):
            sp = getattr(args, "source_path", None)
        if not _require(sp):
            raise SystemExit(
                "cmd=vsphere vs_action=ovftool_deploy: missing required `source_path:` (YAML) or CLI --source-path"
            )


def _validate_cmd_vsphere(args: argparse.Namespace, conf: dict[str, Any]) -> None:
    vcenter, vc_user, vc_password = _validate_vsphere_identity(args, conf)
    _validate_vsphere_control_plane(args, conf, vcenter, vc_user, vc_password)

    act = _merged_vs_action(args, conf)
    if not _require(act):
        raise SystemExit("cmd=vsphere: missing required `vs_action:` (YAML) or CLI --vs-action")
    act = str(act).strip()

    _validate_vsphere_download_transport(args, conf)
    _validate_vsphere_action_requirements(args, conf, act)


def _validate_cmd_azure(args: argparse.Namespace, conf: dict[str, Any]) -> None:
    """
    Validate Azure command requirements.

    Rules:
      - Must have resource_group OR allow_all_rgs=true
      - If list_only=true, less strict validation
    """
    rg = _merged_get(args, conf, "azure_resource_group")
    allow_all = _merged_get(args, conf, "azure_allow_all_rgs")

    if not _require(rg) and not allow_all:
        raise SystemExit(
            "cmd=azure: missing required `azure_resource_group:` (YAML) or CLI --azure-resource-group. "
            "To search all resource groups, set `azure_allow_all_rgs: true` (dangerous)."
        )


def _flag_from_args_or_conf(args: argparse.Namespace, conf: dict[str, Any], key: str) -> bool:
    if bool(getattr(args, key, False)):
        return True
    return bool(conf.get(key))


def validate_deploy_exclusive(args: argparse.Namespace, conf: dict[str, Any]) -> None:
    """Reject incompatible deploy targets (remote upload vs local libvirt lock)."""
    deploy_k8s = _flag_from_args_or_conf(args, conf, "deploy_k8s")
    deploy_openstack = _flag_from_args_or_conf(args, conf, "deploy_openstack")
    libvirt_on = (
        _flag_from_args_or_conf(args, conf, "emit_domain_xml")
        or _flag_from_args_or_conf(args, conf, "virsh_define")
        or _flag_from_args_or_conf(args, conf, "libvirt_test")
    )

    if deploy_k8s and deploy_openstack:
        raise SystemExit(
            "deploy_k8s and deploy_openstack are mutually exclusive; enable only one remote deploy target."
        )
    if deploy_k8s and libvirt_on:
        raise SystemExit(
            "deploy_k8s (KubeVirt) cannot be combined with emit_domain_xml, virsh_define, or libvirt_test. "
            "Disable libvirt options or turn off Deploy to Kubernetes."
        )
    if deploy_openstack and libvirt_on:
        raise SystemExit(
            "deploy_openstack cannot be combined with emit_domain_xml, virsh_define, or libvirt_test. "
            "Disable libvirt options or turn off OpenStack deploy."
        )


def validate_args(args: argparse.Namespace, conf: dict[str, Any]) -> None:
    """
    New-project policy:
      - No CLI subcommands.
      - YAML drives the operation (cmd / vs_action), CLI can override.
      - Manifest-driven workflow bypasses cmd requirement.
    """
    # Check if using manifest-driven workflow
    if hasattr(args, "manifest") and args.manifest:
        # Manifest workflow doesn't require cmd validation
        # The manifest loader will handle all validation
        return

    cmd = _merged_cmd(args, conf)
    if not _require(cmd):
        raise SystemExit(
            "\n"
            "h2kvm: Ultimate VMware → KVM/QEMU Converter + Fixer\n"
            "\n"
            "ERROR: Missing required YAML key: `cmd:` (or `command:`)\n"
            "\n"
            "USAGE:\n"
            "    sudo python -m h2kvm --config <yaml-file>\n"
            "    sudo ./run.sh --config <yaml-file>\n"
            "\n"
            "YAML FILE MUST INCLUDE:\n"
            "    command: <cmd>\n"
            "\n"
            "SUPPORTED COMMANDS:\n"
            "    local           - Convert local VMDK file (alias: migrate)\n"
            "    fetch-and-fix   - Fetch from ESXi via SSH and convert\n"
            "    ova             - Extract and convert OVA archive\n"
            "    ovf             - Extract and convert OVF package\n"
            "    vhd             - Convert VHD/Azure disk\n"
            "    ami             - Extract and convert AMI/cloud tarball\n"
            "    raw             - Extract and convert raw disk image/tarball\n"
            "    live-fix        - Apply fixes to running VM via SSH\n"
            "    libvirt-xml     - Parse libvirt XML and generate manifest\n"
            "    vsphere         - vSphere/vCenter operations\n"
            "    azure           - Azure VM migration operations\n"
            "    daemon          - Watch directory for incoming VMs\n"
            "    generate-systemd - Generate systemd service unit\n"
            "\n"
            "QUICK START EXAMPLE (save as config.yaml):\n"
            "    command: local\n"
            "    vmdk: /path/to/vm.vmdk\n"
            "    output_dir: ./out\n"
            "    flatten: true\n"
            "    to_output: vm-fixed.qcow2\n"
            "    out_format: qcow2\n"
            "    compress: true\n"
            "    fstab_mode: stabilize-all\n"
            "    regen_initramfs: true\n"
            "\n"
            "Then run:\n"
            "    sudo python -m h2kvm --config config.yaml\n"
            "\n"
            "For detailed help and examples:\n"
            "    python -m h2kvm --help (requires --config)\n"
            "    less h2kvm/cli/help_texts.py\n"
            "\n"
            "Documentation:\n"
            "    docs/README.md\n"
            "    docs/98-Enhanced-Features.md\n"
        )

    # Set normalized command back to args.cmd (handles aliases like "migrate" → "local")
    args.cmd = cmd

    # Optional knobs validation (no side effects)
    _validate_win_net_override_inputs(args, conf)
    _validate_virtio_config_inputs(args, conf)
    validate_deploy_exclusive(args, conf)

    cmd_l = str(cmd).strip().lower()

    validators = {
        "local": _validate_cmd_local,
        "fetch-and-fix": _validate_cmd_fetch_and_fix,
        "ova": _validate_cmd_ova,
        "ovf": _validate_cmd_ovf,
        "vhd": _validate_cmd_vhd,
        "ami": _validate_cmd_ami,
        "raw": _validate_cmd_raw,
        "live-fix": _validate_cmd_live_fix,
        "libvirt-xml": lambda _a, _c: None,  # Handled by orchestrator
        "generate-systemd": lambda _a, _c: None,
        "daemon": lambda _a, _c: None,
        "vsphere": _validate_cmd_vsphere,
        "azure": _validate_cmd_azure,
    }

    fn = validators.get(cmd_l)
    if fn is None:
        valid_commands = ", ".join(sorted(validators.keys()))
        raise SystemExit(
            f"\nERROR: Unknown command: '{cmd}'\n"
            f"\n"
            f"SUPPORTED COMMANDS:\n"
            f"    {valid_commands}\n"
            f"\n"
            f"Please update your YAML config file:\n"
            f"    command: <one-of-the-above>\n"
        )
    fn(args, conf)
