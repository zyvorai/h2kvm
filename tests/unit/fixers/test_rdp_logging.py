# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""RDP pre-check logging helpers."""

import logging

from h2kvm.fixers.windows.rdp import log_rdp_precheck_summary, service_start_label


def test_service_start_label():
    assert service_start_label(2) == "Automatic"
    assert service_start_label(3) == "Manual"
    assert service_start_label(None) == "unknown"


def test_log_rdp_precheck_summary_emits_registry_and_term(caplog):
    caplog.set_level(logging.INFO)
    logger = logging.getLogger("test.rdp")
    log_rdp_precheck_summary(
        logger,
        {
            "registry_allows_rdp": True,
            "fdeny_ts_connections": 0,
            "term_service_start": 3,
            "term_service_start_label": "Manual",
            "rdp_enabled": False,
            "rdp_port": 3389,
            "warnings": ["TermService Start=3 (Manual) — RDP may not listen until firstboot runs"],
        },
        firstboot_planned=True,
    )
    text = caplog.text
    assert "registry_allow=True" in text
    assert "TermService=Manual" in text
    assert "Firstboot will enable" in text
