# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

# hyper2kvm/cli/wizard.py
"""
Interactive migration wizard.

Provides step-by-step guided migration setup.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class WizardStep(Enum):
    """Wizard steps."""

    WELCOME = "welcome"
    SOURCE_SELECTION = "source_selection"
    TARGET_SELECTION = "target_selection"
    MIGRATION_OPTIONS = "migration_options"
    VALIDATION_OPTIONS = "validation_options"
    REVIEW = "review"
    CONFIRM = "confirm"


@dataclass
class WizardResult:
    """
    Wizard result.

    Attributes:
        completed: Whether wizard completed successfully
        cancelled: Whether wizard was cancelled
        config: Migration configuration from wizard
        steps_completed: Number of steps completed
    """

    completed: bool
    cancelled: bool
    config: dict[str, Any] = field(default_factory=dict)
    steps_completed: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "completed": self.completed,
            "cancelled": self.cancelled,
            "config": self.config,
            "steps_completed": self.steps_completed,
        }


class MigrationWizard:
    """
    Interactive migration wizard.

    Guides users through migration setup with step-by-step prompts.
    """

    def __init__(self, log: logging.Logger | None = None):
        """
        Initialize migration wizard.

        Args:
            log: Logger instance
        """
        self.logger = log or logging.getLogger(__name__)
        self._config: dict[str, Any] = {}
        self._current_step = 0

    def run(self, interactive: bool = True) -> WizardResult:
        """
        Run interactive wizard.

        Args:
            interactive: Enable interactive prompts (False for testing)

        Returns:
            Wizard result with configuration
        """
        self.logger.info("Starting migration wizard...")

        if interactive:
            self._print_welcome()

        # Step 1: Source selection
        if not self._step_source_selection(interactive):
            return WizardResult(completed=False, cancelled=True, steps_completed=0)
        self._current_step += 1

        # Step 2: Target selection
        if not self._step_target_selection(interactive):
            return WizardResult(completed=False, cancelled=True, steps_completed=1)
        self._current_step += 1

        # Step 3: Migration options
        if not self._step_migration_options(interactive):
            return WizardResult(completed=False, cancelled=True, steps_completed=2)
        self._current_step += 1

        # Step 4: Validation options
        if not self._step_validation_options(interactive):
            return WizardResult(completed=False, cancelled=True, steps_completed=3)
        self._current_step += 1

        # Step 5: Review and confirm
        if interactive and not self._step_review_and_confirm():
            return WizardResult(completed=False, cancelled=True, steps_completed=4)
        self._current_step += 1

        self.logger.info("Wizard completed successfully")

        return WizardResult(
            completed=True,
            cancelled=False,
            config=self._config.copy(),
            steps_completed=self._current_step,
        )

    def _print_welcome(self) -> None:
        """Print welcome message."""
        print("\n" + "=" * 60)
        print("  Hyper2KVM Migration Wizard")
        print("=" * 60)
        print("\nThis wizard will guide you through VM migration setup.")
        print("You can cancel at any time by pressing Ctrl+C.\n")

    def _step_source_selection(self, interactive: bool) -> bool:
        """
        Step 1: Source VM selection.

        Args:
            interactive: Enable interactive prompts

        Returns:
            True to continue, False to cancel
        """
        if interactive:
            print("\n[Step 1/5] Source VM Selection")
            print("-" * 40)

            source_path = input("Enter source VM disk image path: ").strip()

            if not source_path:
                print("Error: Source path is required")
                return False

            # Validate source exists
            if not Path(source_path).exists():
                print(f"Warning: Source path does not exist: {source_path}")
                confirm = input("Continue anyway? (y/n): ").strip().lower()
                if confirm != "y":
                    return False
        else:
            # Non-interactive mode (for testing)
            source_path = self._config.get("source_path", "/dev/null")

        self._config["source_path"] = source_path
        self._config["source_format"] = "qcow2"  # Default, could prompt

        return True

    def _step_target_selection(self, interactive: bool) -> bool:
        """
        Step 2: Target configuration.

        Args:
            interactive: Enable interactive prompts

        Returns:
            True to continue, False to cancel
        """
        if interactive:
            print("\n[Step 2/5] Target Configuration")
            print("-" * 40)

            target_path = input("Enter target VM path (optional, press Enter to skip): ").strip()
            self._config["target_path"] = target_path if target_path else None

            target_format = input("Target format (qcow2/raw/vmdk) [qcow2]: ").strip() or "qcow2"
            self._config["target_format"] = target_format
        else:
            self._config["target_path"] = self._config.get("target_path")
            self._config["target_format"] = self._config.get("target_format", "qcow2")

        return True

    def _step_migration_options(self, interactive: bool) -> bool:
        """
        Step 3: Migration options.

        Args:
            interactive: Enable interactive prompts

        Returns:
            True to continue, False to cancel
        """
        if interactive:
            print("\n[Step 3/5] Migration Options")
            print("-" * 40)

            readonly = input("Mount source read-only? (y/n) [y]: ").strip().lower()
            self._config["readonly"] = readonly != "n"

            create_snapshot = input("Create pre-migration snapshot? (y/n) [y]: ").strip().lower()
            self._config["create_snapshot"] = create_snapshot != "n"

            fix_bootloader = input("Fix bootloader? (y/n) [y]: ").strip().lower()
            self._config["fix_bootloader"] = fix_bootloader != "n"

            fix_network = input("Fix network configuration? (y/n) [y]: ").strip().lower()
            self._config["fix_network"] = fix_network != "n"

            stabilize_fstab = input("Stabilize fstab entries? (y/n) [y]: ").strip().lower()
            self._config["stabilize_fstab"] = stabilize_fstab != "n"
        else:
            self._config["readonly"] = self._config.get("readonly", True)
            self._config["create_snapshot"] = self._config.get("create_snapshot", True)
            self._config["fix_bootloader"] = self._config.get("fix_bootloader", True)
            self._config["fix_network"] = self._config.get("fix_network", True)
            self._config["stabilize_fstab"] = self._config.get("stabilize_fstab", True)

        return True

    def _step_validation_options(self, interactive: bool) -> bool:
        """
        Step 4: Validation options.

        Args:
            interactive: Enable interactive prompts

        Returns:
            True to continue, False to cancel
        """
        if interactive:
            print("\n[Step 4/5] Validation Options")
            print("-" * 40)

            run_validation = input("Run post-migration validation? (y/n) [y]: ").strip().lower()
            self._config["run_validation"] = run_validation != "n"

            if self._config["run_validation"]:
                check_services = input("  Validate services? (y/n) [y]: ").strip().lower()
                self._config["validate_services"] = check_services != "n"

                check_network = input("  Validate network? (y/n) [y]: ").strip().lower()
                self._config["validate_network"] = check_network != "n"

                check_databases = input("  Validate databases? (y/n) [y]: ").strip().lower()
                self._config["validate_databases"] = check_databases != "n"
        else:
            self._config["run_validation"] = self._config.get("run_validation", True)
            self._config["validate_services"] = self._config.get("validate_services", True)
            self._config["validate_network"] = self._config.get("validate_network", True)
            self._config["validate_databases"] = self._config.get("validate_databases", True)

        return True

    def _step_review_and_confirm(self) -> bool:
        """
        Step 5: Review and confirm.

        Returns:
            True to confirm, False to cancel
        """
        print("\n[Step 5/5] Review Configuration")
        print("-" * 40)
        print("\nMigration Configuration:")
        print(f"  Source: {self._config.get('source_path')}")
        print(f"  Target: {self._config.get('target_path', 'Not specified')}")
        print(f"  Format: {self._config.get('target_format')}")
        print(f"  Read-only: {self._config.get('readonly')}")
        print(f"  Create snapshot: {self._config.get('create_snapshot')}")
        print(f"  Fix bootloader: {self._config.get('fix_bootloader')}")
        print(f"  Fix network: {self._config.get('fix_network')}")
        print(f"  Stabilize fstab: {self._config.get('stabilize_fstab')}")
        print(f"  Run validation: {self._config.get('run_validation')}")

        confirm = input("\nProceed with migration? (y/n): ").strip().lower()
        return confirm == "y"

    def get_config(self) -> dict[str, Any]:
        """Get wizard configuration."""
        return self._config.copy()
