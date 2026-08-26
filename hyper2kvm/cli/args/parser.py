# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# hyper2kvm/cli/args/parser.py
"""Main argument parser with config file integration."""

from __future__ import annotations

import argparse
import sys
from typing import TYPE_CHECKING, Any

from hyper2kvm.cli.system_config import load_system_config, merge_with_system_config
from hyper2kvm.config.config_loader import Config
from hyper2kvm.core.logger import c
from hyper2kvm.core.utils import U

from .builder import HelpFormatter, _build_epilog
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
    _add_libvirt_xml_knobs,
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
from .helpers import (
    _materialize_virtio_config_json_if_needed,
    _materialize_win_net_json_if_needed,
)
from .validators import validate_args

if TYPE_CHECKING:
    from collections.abc import Sequence


def build_parser() -> argparse.ArgumentParser:
    """Build the top-level hyper2kvm argument parser with all option groups registered."""
    epilog = _build_epilog()

    p = argparse.ArgumentParser(
        description=c("hyper2kvm: Ultimate VMware → KVM/QEMU Converter + Fixer", "green", ["bold"]),
        formatter_class=HelpFormatter,
        epilog=epilog,
    )

    _add_global_config_logging(p)
    _add_project_control(p)
    _add_global_operation_flags(p)

    _add_flatten_convert(p)
    _add_fixing_behavior(p)
    _add_windows_virtio_definitions(p)
    _add_windows_network_override(p)
    _add_luks_knobs(p)

    _add_tests(p)
    _add_domain_emission(p)

    _add_batch_knobs(p)
    _add_daemon_flags(p)
    _add_ovf_ova_knobs(p)
    _add_ami_extraction_knobs(p)
    _add_libvirt_xml_knobs(p)

    _add_input_paths(p)
    _add_ssh_fetch_knobs(p)
    _add_systemd_gen(p)

    _add_vsphere_core_knobs(p)
    _add_govc_knobs(p)
    _add_ovftool_knobs(p)
    _add_vsphere_export_and_download_knobs(p)

    _add_azure_knobs(p)

    # Kubernetes/k3s deployment
    _add_kubernetes_deployment(p)

    # OpenStack Glance / Nova
    _add_openstack_deployment(p)

    # zkvm (Terminal User Interface)
    _add_zkvm_flags(p)

    # AI migration intelligence
    _add_ai_flags(p)

    return p


def _build_preparser() -> argparse.ArgumentParser:
    pre = argparse.ArgumentParser(add_help=False)
    pre.add_argument("--config", action="append", default=[])
    pre.add_argument("-v", "--verbose", action="count", default=0)
    pre.add_argument("--log-file", dest="log_file", default=None)
    pre.add_argument("--log-format", dest="log_format", default="text", choices=["text", "json"])
    pre.add_argument("--dump-config", action="store_true")
    pre.add_argument("--dump-args", action="store_true")
    return pre


def _load_merged_config(logger: Any, cfgs: Sequence[str]) -> dict[str, Any]:
    # Load system-wide config as base layer
    system_config = load_system_config(logger)

    if not cfgs:
        # No user config, return system config only
        return system_config

    # Load user configs
    expanded = Config.expand_configs(logger, list(cfgs))
    user_config = Config.load_many(logger, expanded)

    # Merge system config with user config (user takes precedence)
    return merge_with_system_config(user_config, logger)


def parse_args_with_config(
    argv: Sequence[str] | None = None,
    logger: Any = None,
) -> tuple[argparse.Namespace, dict[str, Any], Any]:
    # pylint: disable=too-many-locals
    # Multi-phase parse (preparse / config-merge / full-parse / validate /
    # materialize) needs its own local per phase.
    """
    New-project policy:
      - No CLI subcommands.
      - YAML drives `cmd` and (for vsphere) `vs_action`.
      - CLI provides overrides/toggles.

    Flow:
      Phase 0: parse ONLY global flags needed to locate config/logging
      Phase 1: load+merge config files
      Phase 2: apply config as defaults onto the parser
      Phase 3: full parse to get final args
      Phase 4: validate using merged config + args
      Phase 5: materialize inline JSON overrides into workdir (side-effect, after validation)
    """
    # Enable shell completion via argcomplete if available
    try:
        # pylint: disable-next=import-outside-toplevel
        import argcomplete  # optional dependency, kept lazy so hyper2kvm imports fine without it installed

        argcomplete_available = True
    except ImportError:
        argcomplete_available = False

    if argv is None:
        argv = sys.argv[1:]
    argv = list(argv)

    parser = build_parser()

    # Enable argcomplete for shell completion
    if argcomplete_available:
        argcomplete.autocomplete(parser)

    pre = _build_preparser()
    args0, _rest = pre.parse_known_args(argv)

    if logger is None:
        # pylint: disable-next=import-outside-toplevel  # local import to avoid cycles
        from hyper2kvm.core.logger import Log

        logger = Log.setup(
            getattr(args0, "verbose", 0),
            getattr(args0, "log_file", None),
            json_logs=getattr(args0, "log_format", "text") == "json",
        )

    conf = _load_merged_config(logger, getattr(args0, "config", None) or [])

    if getattr(args0, "dump_config", False):
        print(U.json_dump(conf))
        raise SystemExit(0)

    # Apply config as defaults so CLI can override.
    Config.apply_as_defaults(logger, parser, conf)

    args = parser.parse_args(argv)

    if getattr(args0, "dump_args", False):
        sensitive_keys = {
            "vc_password",
            "govc_password",
            "luks_passphrase",
            "password",
            "token",
            "secret",
            "key",
        }
        safe_args = {}
        for k, v in vars(args).items():
            if any(s in k.lower() for s in sensitive_keys) and v is not None:
                safe_args[k] = "***REDACTED***"
            else:
                safe_args[k] = v
        print(U.json_dump(safe_args))
        raise SystemExit(0)

    validate_args(args, conf)

    # Side-effect stage: if win_net_json is used, write it under workdir and set args.win_net_override.
    _materialize_win_net_json_if_needed(args, conf, logger)

    # Side-effect stage: if virtio_config_json is used, write it under workdir and set args.virtio_config_path.
    _materialize_virtio_config_json_if_needed(args, conf, logger)

    return args, conf, logger
