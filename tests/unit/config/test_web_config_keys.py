# Copyright (c) 2026 ZyvorAI Labs Private Limited.
# SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-H2KVM-Commercial
# https://zyvor.dev · info@zyvor.dev

"""The Go web backend writes a YAML config for h2kvmctl; its keys must be ones h2kvmctl reads."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from h2kvm.cli.args.parser import build_parser
from h2kvm.config.config_loader import Config

GO_CONFIG = Path(__file__).resolve().parents[3] / "web" / "internal" / "domain" / "config.go"


def _go_yaml_keys() -> list[str]:
    return re.findall(r'yaml:"([A-Za-z0-9_]+)[,"]', GO_CONFIG.read_text(encoding="utf-8"))


@pytest.mark.skipif(not GO_CONFIG.exists(), reason="web/ sources not present (installed package)")
def test_every_web_yaml_key_is_an_h2kvmctl_option():
    dests = Config._collect_argparse_dests(build_parser())
    # h2kvmctl folds aliases such as command -> cmd before it reads the config.
    aliased = set(Config._canonicalize_aliases({"command": "x"})) - {"command"}
    unknown = sorted(k for k in set(_go_yaml_keys()) if k not in dests and k != "command")
    assert not unknown, (
        f"web/internal/domain/config.go emits YAML keys h2kvmctl ignores: {unknown}. "
        f"Use the argparse destination as the yaml tag (aliases handled by the loader: {sorted(aliased)})."
    )
