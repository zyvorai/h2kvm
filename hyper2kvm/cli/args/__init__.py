# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# hyper2kvm/cli/args/__init__.py
"""
Argument parser modules for hyper2kvm CLI.

This package provides backward compatibility by re-exporting all public symbols
from the split modules.
"""

from __future__ import annotations

# Re-export HelpFormatter and builder functions
from .builder import HelpFormatter, _build_epilog

# Re-export all argument group builders
from .groups import (
    _add_ai_flags,
    _add_ami_extraction_knobs,
    _add_azure_knobs,
    _add_batch_knobs,
    _add_daemon_flags,
    _add_domain_emission,
    _add_fixing_behavior,
    _add_flatten_convert,
    _add_global_config_logging,
    _add_global_operation_flags,
    _add_govc_knobs,
    _add_input_paths,
    _add_kubernetes_deployment,
    _add_luks_knobs,
    _add_openstack_deployment,
    _add_ovf_ova_knobs,
    _add_ovftool_knobs,
    _add_project_control,
    _add_ssh_fetch_knobs,
    _add_systemd_gen,
    _add_tests,
    _add_vsphere_core_knobs,
    _add_vsphere_export_and_download_knobs,
    _add_windows_network_override,
    _add_windows_virtio_definitions,
    _add_zkvm_flags,
)

# Re-export helper functions
from .helpers import (
    _materialize_virtio_config_json_if_needed,
    _materialize_win_net_json_if_needed,
    _merged_cmd,
    _merged_get,
    _merged_secret,
    _merged_vs_action,
    _require,
    _resolve_workdir,
)

# Re-export main parser functions
from .parser import _build_preparser, _load_merged_config, build_parser, parse_args_with_config

# Re-export validator functions
from .validators import (
    _pick_vsphere_vm_name,
    _validate_cmd_ami,
    _validate_cmd_azure,
    _validate_cmd_fetch_and_fix,
    _validate_cmd_live_fix,
    _validate_cmd_local,
    _validate_cmd_ova,
    _validate_cmd_ovf,
    _validate_cmd_vhd,
    _validate_cmd_vsphere,
    _validate_json_object_file,
    _validate_json_object_inline,
    _validate_virtio_config_inputs,
    _validate_vsphere_action_requirements,
    _validate_vsphere_control_plane,
    _validate_vsphere_download_transport,
    _validate_vsphere_identity,
    _validate_win_net_override_inputs,
    validate_args,
    validate_deploy_exclusive,
)

__all__ = [
    # Builder
    "HelpFormatter",
    # Groups
    "_add_ai_flags",
    "_add_ami_extraction_knobs",
    "_add_azure_knobs",
    "_add_batch_knobs",
    "_add_daemon_flags",
    "_add_domain_emission",
    "_add_fixing_behavior",
    "_add_flatten_convert",
    "_add_global_config_logging",
    "_add_global_operation_flags",
    "_add_govc_knobs",
    "_add_input_paths",
    "_add_kubernetes_deployment",
    "_add_luks_knobs",
    "_add_openstack_deployment",
    "_add_ovf_ova_knobs",
    "_add_ovftool_knobs",
    "_add_project_control",
    "_add_ssh_fetch_knobs",
    "_add_systemd_gen",
    "_add_tests",
    "_add_vsphere_core_knobs",
    "_add_vsphere_export_and_download_knobs",
    "_add_windows_network_override",
    "_add_windows_virtio_definitions",
    "_add_zkvm_flags",
    "_build_epilog",
    # Parser
    "_build_preparser",
    "_load_merged_config",
    # Helpers
    "_materialize_virtio_config_json_if_needed",
    "_materialize_win_net_json_if_needed",
    "_merged_cmd",
    "_merged_get",
    "_merged_secret",
    "_merged_vs_action",
    # Validators
    "_pick_vsphere_vm_name",
    "_require",
    "_resolve_workdir",
    "_validate_cmd_ami",
    "_validate_cmd_azure",
    "_validate_cmd_fetch_and_fix",
    "_validate_cmd_live_fix",
    "_validate_cmd_local",
    "_validate_cmd_ova",
    "_validate_cmd_ovf",
    "_validate_cmd_vhd",
    "_validate_cmd_vsphere",
    "_validate_json_object_file",
    "_validate_json_object_inline",
    "_validate_virtio_config_inputs",
    "_validate_vsphere_action_requirements",
    "_validate_vsphere_control_plane",
    "_validate_vsphere_download_transport",
    "_validate_vsphere_identity",
    "_validate_win_net_override_inputs",
    "build_parser",
    "parse_args_with_config",
    "validate_args",
    "validate_deploy_exclusive",
]
