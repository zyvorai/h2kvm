# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""Main entry point for hyper2kvm CLI application."""

# hyper2kvm/__main__.py
from __future__ import annotations

import sys

from .cli.args import parse_args_with_config
from .core.exceptions import Fatal, Hyper2KvmError, format_exception_for_cli
from .orchestration.manifest.orchestrator import ManifestOrchestrator
from .orchestration.orchestrator import Orchestrator


def main() -> None:  # pylint: disable=too-many-branches,too-many-statements
    # CLI entrypoint necessarily dispatches between the manifest-driven and
    # traditional workflows, each with its own Fatal/Hyper2KvmError/generic
    # exception handling; splitting it would hurt readability more than help.
    """
    Main entry point for hyper2kvm CLI.

    Parses command-line arguments, configures logging, and orchestrates the
    VM migration workflow. Supports both traditional workflow and manifest-driven
    batch migrations.

    Exit codes:
        0: Success
        1: General failure
        2+: Specific error codes from Fatal exceptions

    Raises:
        Fatal: For critical errors that should terminate execution

    Examples:
        $ h2kvmctl --config migration.yaml
        $ h2kvmctl --manifest batch-migration.json
    """
    try:
        args, _conf, logger = parse_args_with_config()
        verbose = getattr(args, "verbose", 0)

        # Check for manifest-driven workflow
        if hasattr(args, "manifest") and args.manifest:
            # Use manifest-driven pipeline
            try:
                orchestrator = ManifestOrchestrator(args.manifest, logger)
                orchestrator.run()
                rc = 0
            except Fatal as e:
                # Fatal exceptions: always show user-friendly message
                error_msg = format_exception_for_cli(e, verbose=verbose)
                logger.exception(error_msg)
                # Only show traceback in verbose mode
                if verbose >= 2:
                    logger.exception("Full traceback:")
                rc = e.code
            except Hyper2KvmError as e:
                # Project exceptions: show user-friendly message with context
                error_msg = format_exception_for_cli(e, verbose=verbose)
                logger.exception("Manifest pipeline failed: %s", error_msg)
                if verbose >= 2:
                    logger.exception("Full traceback:")
                rc = e.code
            except Exception as e:  # pylint: disable=broad-exception-caught
                # Top-level CLI catch-all: any unexpected failure in the
                # manifest pipeline must still exit cleanly with a message
                # rather than crash with a raw traceback.
                if verbose >= 1:
                    logger.exception("Manifest pipeline failed: %s", e)
                else:
                    logger.exception("Manifest pipeline failed: %s", e)
                    logger.exception("Run with -v or -vv for more details")
                rc = 1
        else:
            # Use traditional workflow
            try:
                Orchestrator(logger, args).run()
                rc = 0
            except Fatal as e:
                # Fatal exceptions: always show user-friendly message
                error_msg = format_exception_for_cli(e, verbose=verbose)
                logger.exception(error_msg)
                # Only show traceback in verbose mode
                if verbose >= 2:
                    logger.exception("Full traceback:")
                rc = e.code
            except Hyper2KvmError as e:
                # Project exceptions: show user-friendly message with context
                error_msg = format_exception_for_cli(e, verbose=verbose)
                logger.exception("Migration failed: %s", error_msg)
                if verbose >= 2:
                    logger.exception("Full traceback:")
                rc = e.code
            except Exception as e:  # pylint: disable=broad-exception-caught
                # Top-level CLI catch-all: any unexpected failure in the
                # migration workflow must still exit cleanly with a message
                # rather than crash with a raw traceback.
                if verbose >= 1:
                    logger.exception("Migration failed: %s", e)
                else:
                    logger.exception("Migration failed: %s", e)
                    logger.exception("Run with -v or -vv for more details")
                rc = 1

        sys.exit(int(rc))

    except Fatal as e:
        # Fatal exception during config loading or other early init
        # Already logged by the code that raised it, just exit cleanly
        sys.exit(e.code)


if __name__ == "__main__":
    main()
