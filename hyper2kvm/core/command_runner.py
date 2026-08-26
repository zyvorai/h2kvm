# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""
Command execution utilities with retry, logging, and error handling.

This module provides a standardized way to execute shell commands with:
- Automatic retry with exponential backoff
- Timeout handling
- Structured logging (command, stdout, stderr, exit code)
- Error capture and formatting
- Sudo support
- Dry-run mode support
"""

from __future__ import annotations

import logging
import subprocess
import time
from dataclasses import dataclass

from .exceptions import CommandError


@dataclass
class CommandResult:
    """Result of a command execution."""

    command: str
    exit_code: int
    stdout: str
    stderr: str
    duration: float
    retries: int = 0

    @property
    def success(self) -> bool:
        """Check if command succeeded."""
        return self.exit_code == 0

    @property
    def failed(self) -> bool:
        """Check if command failed."""
        return self.exit_code != 0

    def raise_for_status(self) -> None:
        """Raise exception if command failed."""
        if self.failed:
            detail = ""
            if self.stderr:
                detail = f"\n    Output: {self.stderr[:300].strip()}"
            elif self.stdout:
                detail = f"\n    Output: {self.stdout[:300].strip()}"
            raise CommandError(
                code=self.exit_code,
                msg=(
                    f"Command failed (exit code {self.exit_code}): {self.command}{detail}\n"
                    f"    Ran for {self.duration:.1f}s. Check that the command is installed "
                    "and has correct permissions."
                ),
                context={
                    "command": self.command,
                    "exit_code": self.exit_code,
                    "stdout": self.stdout[:500] if self.stdout else "",
                    "stderr": self.stderr[:500] if self.stderr else "",
                    "duration": self.duration,
                },
            )


class CommandRunner:
    """
    Utility for executing shell commands with retry and error handling.

    Features:
    - Automatic retry with exponential backoff
    - Timeout enforcement
    - Structured logging
    - Error capture
    - Sudo support
    - Dry-run mode

    Example:
        runner = CommandRunner(logger=logger, dry_run=False)

        # Simple execution
        result = runner.run("ls -la /tmp")

        # With retry
        result = runner.run("mount /dev/sda1 /mnt", retries=3)

        # With sudo
        result = runner.run("systemctl restart sshd", use_sudo=True)

        # Check for errors
        if result.failed:
            logger.error(f"Command failed: {result.stderr}")
    """

    def __init__(  # pylint: disable=too-many-arguments,too-many-positional-arguments
        self,
        logger: logging.Logger | None = None,
        dry_run: bool = False,
        default_timeout: float = 300.0,
        default_retries: int = 0,
        retry_delay: float = 1.0,
        retry_backoff: float = 2.0,
    ):
        """
        Initialize command runner.

        Args:
            logger: Logger instance for command output
            dry_run: If True, log commands without executing
            default_timeout: Default timeout in seconds (None = no timeout)
            default_retries: Default number of retries on failure
            retry_delay: Initial delay between retries in seconds
            retry_backoff: Backoff multiplier for retry delay
        """
        self.logger = logger or logging.getLogger(__name__)
        self.dry_run = dry_run
        self.default_timeout = default_timeout
        self.default_retries = default_retries
        self.retry_delay = retry_delay
        self.retry_backoff = retry_backoff

    # Core exec path: sudo/timeout/retry/dry-run handling is inherently one cohesive flow.
    # pylint: disable=too-many-arguments,too-many-positional-arguments
    # pylint: disable=too-many-locals,too-many-branches,too-many-statements
    def run(
        self,
        command: str | list[str],
        use_sudo: bool = False,
        timeout: float | None = None,
        retries: int | None = None,
        check: bool = False,
        capture_output: bool = True,
        shell: bool = True,
        cwd: str | None = None,
        env: dict | None = None,
    ) -> CommandResult:
        """
        Execute a shell command with retry logic.

        Args:
            command: Command string or list of arguments
            use_sudo: Prepend 'sudo' to command
            timeout: Timeout in seconds (None = default, 0 = no timeout)
            retries: Number of retries on failure (None = default)
            check: Raise exception if command fails
            capture_output: Capture stdout/stderr
            shell: Execute via shell (if command is string)
            cwd: Working directory
            env: Environment variables

        Returns:
            CommandResult with execution details

        Raises:
            CommandError: If check=True and command fails
        """
        # Prepare command
        if isinstance(command, list):
            cmd_str = " ".join(command)
            cmd_exec = command
        else:
            cmd_str = command
            cmd_exec = command if shell else command.split()

        # Add sudo if requested
        if use_sudo:
            cmd_exec = ["sudo", *cmd_exec] if isinstance(cmd_exec, list) else f"sudo {cmd_exec}"
            cmd_str = f"sudo {cmd_str}"

        # Set defaults
        if timeout is None:
            timeout = self.default_timeout
        if timeout == 0:
            timeout = None

        if retries is None:
            retries = self.default_retries

        # Dry run
        if self.dry_run:
            self.logger.info("[DRY RUN] Would execute: %s", cmd_str)
            return CommandResult(
                command=cmd_str,
                exit_code=0,
                stdout="",
                stderr="[dry-run mode]",
                duration=0.0,
                retries=0,
            )

        # Execute with retry
        attempt = 0
        delay = self.retry_delay

        while attempt <= retries:
            try:
                self.logger.debug("Executing (attempt %d/%d): %s", attempt + 1, retries + 1, cmd_str)
                start_time = time.time()

                process = subprocess.run(
                    cmd_exec,
                    capture_output=capture_output,
                    text=True,
                    timeout=timeout,
                    shell=shell if isinstance(cmd_exec, str) else False,
                    cwd=cwd,
                    env=env,
                    check=False,
                )

                duration = time.time() - start_time

                result = CommandResult(
                    command=cmd_str,
                    exit_code=process.returncode,
                    stdout=process.stdout if capture_output else "",
                    stderr=process.stderr if capture_output else "",
                    duration=duration,
                    retries=attempt,
                )

                # Log result
                if result.success:
                    self.logger.debug(
                        "Command succeeded (exit=%s, duration=%.2fs): %s",
                        result.exit_code, duration, cmd_str,
                    )
                else:
                    self.logger.warning(
                        "Command failed (exit=%s, duration=%.2fs): %s\nstderr: %s",
                        result.exit_code, duration, cmd_str, result.stderr[:500],
                    )

                # Check for errors
                if check and result.failed:
                    raise CommandError(
                        code=result.exit_code,
                        msg=f"Command failed: {cmd_str}",
                        context={
                            "command": cmd_str,
                            "exit_code": result.exit_code,
                            "stdout": result.stdout[:500] if result.stdout else "",
                            "stderr": result.stderr[:500] if result.stderr else "",
                            "duration": result.duration,
                        },
                    )

                # Retry on non-zero exit codes when retries are configured
                if result.failed and attempt < retries:
                    self.logger.info(
                        "Command exited with code %s, retrying (%d/%d)...",
                        result.exit_code, attempt + 1, retries,
                    )
                    time.sleep(delay)
                    delay *= self.retry_backoff
                    attempt += 1
                    continue

                return result

            except subprocess.TimeoutExpired as e:
                self.logger.exception("Command timed out after %ss: %s", timeout, cmd_str)
                if attempt >= retries:
                    raise CommandError(
                        code=124,  # Standard timeout exit code
                        msg=(
                            f"Command timed out after {timeout}s: {cmd_str}\n"
                            f"    The operation did not complete within the allowed time.\n"
                            f"    Try increasing the timeout or check if the target is responding."
                        ),
                        cause=e,
                        context={"command": cmd_str, "timeout": timeout},
                    ) from e

            except Exception as e:  # pylint: disable=broad-exception-caught
                # Must survive any unexpected subprocess/launch failure and retry rather than abort.
                self.logger.exception("Command execution error: %s", e)
                if attempt >= retries:
                    raise

            # Retry with backoff
            if attempt < retries:
                self.logger.info("Retrying in %.1fs...", delay)
                time.sleep(delay)
                delay *= self.retry_backoff
                attempt += 1
            else:
                break

        # Should not reach here, but handle gracefully
        raise CommandError(
            code=1,
            msg=f"Command failed after {retries + 1} attempts: {cmd_str}",
            context={"command": cmd_str, "retries": retries + 1},
        )

    def run_checked(
        self,
        command: str | list[str],
        **kwargs,
    ) -> CommandResult:
        """
        Execute command and raise exception if it fails.

        Convenience wrapper for run(check=True).

        Args:
            command: Command to execute
            **kwargs: Additional arguments for run()

        Returns:
            CommandResult

        Raises:
            CommandError: If command fails
        """
        return self.run(command, check=True, **kwargs)

    def run_silent(
        self,
        command: str | list[str],
        **kwargs,
    ) -> tuple[int, str, str]:
        """
        Execute command and return exit code, stdout, stderr tuple.

        Legacy compatibility method.

        Args:
            command: Command to execute
            **kwargs: Additional arguments for run()

        Returns:
            Tuple of (exit_code, stdout, stderr)
        """
        result = self.run(command, **kwargs)
        return result.exit_code, result.stdout, result.stderr
