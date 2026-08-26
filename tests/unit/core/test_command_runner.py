# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""Tests for CommandResult, CommandRunner.run, run_checked, run_silent."""

from __future__ import annotations

import subprocess
from unittest.mock import Mock, patch

import pytest

from h2kvm.core.command_runner import CommandResult, CommandRunner
from h2kvm.core.exceptions import CommandError


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def runner():
    """CommandRunner with defaults and no dry-run."""
    return CommandRunner(dry_run=False)


@pytest.fixture
def dry_runner():
    """CommandRunner in dry-run mode."""
    return CommandRunner(dry_run=True)


@pytest.fixture
def retry_runner():
    """CommandRunner configured with retries and short backoff."""
    return CommandRunner(default_retries=2, retry_delay=1.0, retry_backoff=2.0)


def _make_process(returncode=0, stdout="", stderr=""):
    """Helper: create a mock subprocess.CompletedProcess."""
    proc = Mock()
    proc.returncode = returncode
    proc.stdout = stdout
    proc.stderr = stderr
    return proc


# ===========================================================================
# CommandResult dataclass
# ===========================================================================


class TestCommandResult:
    def test_success_when_exit_code_zero(self):
        r = CommandResult(command="ls", exit_code=0, stdout="", stderr="", duration=0.1)
        assert r.success is True

    def test_success_when_exit_code_nonzero(self):
        r = CommandResult(command="ls", exit_code=1, stdout="", stderr="", duration=0.1)
        assert r.success is False

    def test_failed_when_exit_code_nonzero(self):
        r = CommandResult(command="ls", exit_code=1, stdout="", stderr="err", duration=0.2)
        assert r.failed is True

    def test_failed_when_exit_code_zero(self):
        r = CommandResult(command="ls", exit_code=0, stdout="", stderr="", duration=0.0)
        assert r.failed is False

    def test_retries_default_zero(self):
        r = CommandResult(command="ls", exit_code=0, stdout="", stderr="", duration=0.0)
        assert r.retries == 0

    def test_raise_for_status_noop_on_success(self):
        r = CommandResult(command="ls", exit_code=0, stdout="ok", stderr="", duration=0.1)
        r.raise_for_status()  # should not raise

    def test_raise_for_status_raises_command_error(self):
        r = CommandResult(command="bad", exit_code=1, stdout="out", stderr="err", duration=0.5)
        with pytest.raises(CommandError) as exc_info:
            r.raise_for_status()
        err = exc_info.value
        assert err.code == 1
        assert "bad" in err.msg
        assert err.context["command"] == "bad"
        assert err.context["exit_code"] == 1
        assert err.context["stdout"] == "out"
        assert err.context["stderr"] == "err"
        assert err.context["duration"] == 0.5

    def test_raise_for_status_truncates_long_stdout(self):
        long_out = "x" * 1000
        r = CommandResult(command="c", exit_code=2, stdout=long_out, stderr="", duration=0.0)
        with pytest.raises(CommandError) as exc_info:
            r.raise_for_status()
        assert len(exc_info.value.context["stdout"]) == 500

    def test_raise_for_status_truncates_long_stderr(self):
        long_err = "e" * 1000
        r = CommandResult(command="c", exit_code=3, stdout="", stderr=long_err, duration=0.0)
        with pytest.raises(CommandError) as exc_info:
            r.raise_for_status()
        assert len(exc_info.value.context["stderr"]) == 500

    def test_raise_for_status_handles_empty_stdout_stderr(self):
        r = CommandResult(command="c", exit_code=1, stdout="", stderr="", duration=0.0)
        with pytest.raises(CommandError) as exc_info:
            r.raise_for_status()
        assert exc_info.value.context["stdout"] == ""
        assert exc_info.value.context["stderr"] == ""


# ===========================================================================
# CommandRunner.__init__
# ===========================================================================


class TestCommandRunnerInit:
    def test_default_logger_created(self):
        runner = CommandRunner()
        assert runner.logger is not None

    def test_custom_logger(self):
        logger = Mock()
        runner = CommandRunner(logger=logger)
        assert runner.logger is logger

    def test_default_values(self):
        runner = CommandRunner()
        assert runner.dry_run is False
        assert runner.default_timeout == 300.0
        assert runner.default_retries == 0
        assert runner.retry_delay == 1.0
        assert runner.retry_backoff == 2.0


# ===========================================================================
# CommandRunner.run  --  basic execution
# ===========================================================================


class TestRunBasic:
    @patch("h2kvm.core.command_runner.time")
    @patch("h2kvm.core.command_runner.subprocess.run")
    def test_run_string_command_success(self, mock_subproc, mock_time, runner):
        mock_time.time.side_effect = [0.0, 1.5]
        mock_subproc.return_value = _make_process(0, "output", "")

        result = runner.run("echo hello")

        assert result.success is True
        assert result.exit_code == 0
        assert result.stdout == "output"
        assert result.stderr == ""
        assert result.duration == 1.5
        assert result.command == "echo hello"

    @patch("h2kvm.core.command_runner.time")
    @patch("h2kvm.core.command_runner.subprocess.run")
    def test_run_list_command(self, mock_subproc, mock_time, runner):
        mock_time.time.side_effect = [0.0, 0.1]
        mock_subproc.return_value = _make_process(0, "ok", "")

        result = runner.run(["ls", "-la"])

        assert result.command == "ls -la"
        # When command is a list, shell should be False
        call_kwargs = mock_subproc.call_args
        assert call_kwargs[1]["shell"] is False

    @patch("h2kvm.core.command_runner.time")
    @patch("h2kvm.core.command_runner.subprocess.run")
    def test_run_failed_command_no_check(self, mock_subproc, mock_time, runner):
        mock_time.time.side_effect = [0.0, 0.2]
        mock_subproc.return_value = _make_process(1, "", "error msg")

        result = runner.run("false")

        assert result.failed is True
        assert result.exit_code == 1
        assert result.stderr == "error msg"


# ===========================================================================
# CommandRunner.run  --  dry-run mode
# ===========================================================================


class TestRunDryRun:
    def test_dry_run_returns_success(self, dry_runner):
        result = dry_runner.run("dangerous command")

        assert result.success is True
        assert result.exit_code == 0
        assert result.stderr == "[dry-run mode]"
        assert result.stdout == ""
        assert result.duration == 0.0
        assert result.retries == 0

    def test_dry_run_preserves_command_string(self, dry_runner):
        result = dry_runner.run("rm -rf /")
        assert result.command == "rm -rf /"

    @patch("h2kvm.core.command_runner.subprocess.run")
    def test_dry_run_does_not_call_subprocess(self, mock_subproc, dry_runner):
        dry_runner.run("echo hello")
        mock_subproc.assert_not_called()


# ===========================================================================
# CommandRunner.run  --  sudo
# ===========================================================================


class TestRunSudo:
    @patch("h2kvm.core.command_runner.time")
    @patch("h2kvm.core.command_runner.subprocess.run")
    def test_sudo_prepended_to_string(self, mock_subproc, mock_time, runner):
        mock_time.time.side_effect = [0.0, 0.1]
        mock_subproc.return_value = _make_process(0, "", "")

        result = runner.run("systemctl restart sshd", use_sudo=True)

        assert result.command == "sudo systemctl restart sshd"
        # subprocess.run should receive the sudo-prefixed command
        call_args = mock_subproc.call_args[0][0]
        assert call_args.startswith("sudo ")

    @patch("h2kvm.core.command_runner.time")
    @patch("h2kvm.core.command_runner.subprocess.run")
    def test_sudo_prepended_to_list(self, mock_subproc, mock_time, runner):
        mock_time.time.side_effect = [0.0, 0.1]
        mock_subproc.return_value = _make_process(0, "", "")

        result = runner.run(["mount", "/dev/sda1", "/mnt"], use_sudo=True)

        assert result.command == "sudo mount /dev/sda1 /mnt"
        call_args = mock_subproc.call_args[0][0]
        assert call_args == ["sudo", "mount", "/dev/sda1", "/mnt"]

    def test_sudo_in_dry_run(self, dry_runner):
        result = dry_runner.run("systemctl stop nginx", use_sudo=True)
        assert result.command == "sudo systemctl stop nginx"


# ===========================================================================
# CommandRunner.run  --  timeout handling
# ===========================================================================


class TestRunTimeout:
    @patch("h2kvm.core.command_runner.time")
    @patch("h2kvm.core.command_runner.subprocess.run")
    def test_default_timeout_used(self, mock_subproc, mock_time, runner):
        mock_time.time.side_effect = [0.0, 0.1]
        mock_subproc.return_value = _make_process(0, "", "")

        runner.run("cmd")

        call_kwargs = mock_subproc.call_args[1]
        assert call_kwargs["timeout"] == 300.0

    @patch("h2kvm.core.command_runner.time")
    @patch("h2kvm.core.command_runner.subprocess.run")
    def test_custom_timeout(self, mock_subproc, mock_time, runner):
        mock_time.time.side_effect = [0.0, 0.1]
        mock_subproc.return_value = _make_process(0, "", "")

        runner.run("cmd", timeout=60.0)

        call_kwargs = mock_subproc.call_args[1]
        assert call_kwargs["timeout"] == 60.0

    @patch("h2kvm.core.command_runner.time")
    @patch("h2kvm.core.command_runner.subprocess.run")
    def test_timeout_zero_means_no_timeout(self, mock_subproc, mock_time, runner):
        mock_time.time.side_effect = [0.0, 0.1]
        mock_subproc.return_value = _make_process(0, "", "")

        runner.run("cmd", timeout=0)

        call_kwargs = mock_subproc.call_args[1]
        assert call_kwargs["timeout"] is None

    @patch("h2kvm.core.command_runner.time")
    @patch("h2kvm.core.command_runner.subprocess.run")
    def test_timeout_expired_raises_command_error(self, mock_subproc, mock_time, runner):
        mock_time.time.side_effect = [0.0]
        mock_subproc.side_effect = subprocess.TimeoutExpired("cmd", 10)

        with pytest.raises(CommandError) as exc_info:
            runner.run("long_cmd", timeout=10)

        assert exc_info.value.code == 124
        assert "timed out" in exc_info.value.msg
        assert exc_info.value.context["command"] == "long_cmd"
        assert exc_info.value.context["timeout"] == 10


# ===========================================================================
# CommandRunner.run  --  check mode
# ===========================================================================


class TestRunCheck:
    @patch("h2kvm.core.command_runner.time")
    @patch("h2kvm.core.command_runner.subprocess.run")
    def test_check_true_raises_on_failure(self, mock_subproc, mock_time, runner):
        mock_time.time.side_effect = [0.0, 0.1]
        mock_subproc.return_value = _make_process(1, "out", "err")

        with pytest.raises(CommandError) as exc_info:
            runner.run("failing", check=True)

        err = exc_info.value
        assert err.code == 1
        assert err.context["command"] == "failing"
        assert err.context["stdout"] == "out"
        assert err.context["stderr"] == "err"

    @patch("h2kvm.core.command_runner.time")
    @patch("h2kvm.core.command_runner.subprocess.run")
    def test_check_true_no_raise_on_success(self, mock_subproc, mock_time, runner):
        mock_time.time.side_effect = [0.0, 0.1]
        mock_subproc.return_value = _make_process(0, "ok", "")

        result = runner.run("good", check=True)
        assert result.success is True

    @patch("h2kvm.core.command_runner.time")
    @patch("h2kvm.core.command_runner.subprocess.run")
    def test_check_false_returns_result_on_failure(self, mock_subproc, mock_time, runner):
        mock_time.time.side_effect = [0.0, 0.1]
        mock_subproc.return_value = _make_process(2, "", "err")

        result = runner.run("failing", check=False)
        assert result.failed is True
        assert result.exit_code == 2

    @patch("h2kvm.core.command_runner.time")
    @patch("h2kvm.core.command_runner.subprocess.run")
    def test_check_truncates_long_output_in_error(self, mock_subproc, mock_time, runner):
        mock_time.time.side_effect = [0.0, 0.1]
        mock_subproc.return_value = _make_process(1, "o" * 1000, "e" * 1000)

        with pytest.raises(CommandError) as exc_info:
            runner.run("cmd", check=True)

        assert len(exc_info.value.context["stdout"]) == 500
        assert len(exc_info.value.context["stderr"]) == 500


# ===========================================================================
# CommandRunner.run  --  retry logic
# ===========================================================================


class TestRunRetry:
    @patch("h2kvm.core.command_runner.time")
    @patch("h2kvm.core.command_runner.subprocess.run")
    def test_no_retry_by_default(self, mock_subproc, mock_time, runner):
        """With default retries=0 and no check, a failed command returns immediately."""
        mock_time.time.side_effect = [0.0, 0.1]
        mock_subproc.return_value = _make_process(1, "", "fail")

        result = runner.run("cmd")

        assert mock_subproc.call_count == 1
        assert result.retries == 0

    @patch("h2kvm.core.command_runner.time")
    @patch("h2kvm.core.command_runner.subprocess.run")
    def test_retry_on_nonzero_exit_with_retries(self, mock_subproc, mock_time, runner):
        """With retries>0, non-zero exit codes are retried even without check=True."""
        mock_time.time.side_effect = [0.0, 0.1] * 5
        mock_time.sleep = lambda x: None
        mock_subproc.return_value = _make_process(1, "", "fail")

        result = runner.run("cmd", retries=3)

        # Non-zero exit code retried up to retries+1 times
        assert mock_subproc.call_count == 4  # 1 initial + 3 retries
        assert result.failed is True

    @patch("h2kvm.core.command_runner.time")
    @patch("h2kvm.core.command_runner.subprocess.run")
    def test_retry_with_check_succeeds_on_second_attempt(self, mock_subproc, mock_time, runner):
        """check=True raises CommandError on failure, which triggers retry."""
        mock_time.time.side_effect = [0.0, 0.1, 0.2, 0.3]
        mock_time.sleep = Mock()
        mock_subproc.side_effect = [
            _make_process(1, "", "fail"),
            _make_process(0, "ok", ""),
        ]

        result = runner.run("cmd", retries=1, check=True)

        assert result.success is True
        assert result.retries == 1
        assert mock_subproc.call_count == 2
        mock_time.sleep.assert_called_once_with(1.0)

    @patch("h2kvm.core.command_runner.time")
    @patch("h2kvm.core.command_runner.subprocess.run")
    def test_retry_exponential_backoff_with_timeout(self, mock_subproc, mock_time, retry_runner):
        """TimeoutExpired triggers retry with exponential backoff delays."""
        # time.time() calls: attempt 0 start, attempt 1 start, attempt 2 start + end
        mock_time.time.side_effect = [0.0, 0.1, 0.2, 0.3]
        mock_time.sleep = Mock()
        mock_subproc.side_effect = [
            subprocess.TimeoutExpired("cmd", 5),
            subprocess.TimeoutExpired("cmd", 5),
            _make_process(0, "ok", ""),
        ]

        result = retry_runner.run("cmd")

        assert result.success is True
        assert result.retries == 2
        assert mock_time.sleep.call_count == 2
        # First retry delay=1.0, second delay=1.0*2.0=2.0
        mock_time.sleep.assert_any_call(1.0)
        mock_time.sleep.assert_any_call(2.0)

    @patch("h2kvm.core.command_runner.time")
    @patch("h2kvm.core.command_runner.subprocess.run")
    def test_retry_exhausted_raises_with_check(self, mock_subproc, mock_time, runner):
        """When all retries fail with check=True, the final exception propagates."""
        mock_time.time.side_effect = [0.0, 0.1, 0.2, 0.3]
        mock_time.sleep = Mock()
        mock_subproc.return_value = _make_process(1, "", "always fail")

        with pytest.raises(CommandError):
            runner.run("cmd", retries=1, check=True)

        assert mock_subproc.call_count == 2

    @patch("h2kvm.core.command_runner.time")
    @patch("h2kvm.core.command_runner.subprocess.run")
    def test_retry_with_timeout_expired_then_success(self, mock_subproc, mock_time, runner):
        """TimeoutExpired on first attempt, success on second."""
        mock_time.time.side_effect = [0.0, 0.1, 0.2]
        mock_time.sleep = Mock()
        mock_subproc.side_effect = [
            subprocess.TimeoutExpired("cmd", 10),
            _make_process(0, "ok", ""),
        ]

        result = runner.run("cmd", retries=1, timeout=10)

        assert result.success is True
        assert mock_subproc.call_count == 2
        mock_time.sleep.assert_called_once()

    @patch("h2kvm.core.command_runner.time")
    @patch("h2kvm.core.command_runner.subprocess.run")
    def test_retry_timeout_exhausted_raises(self, mock_subproc, mock_time, runner):
        """All retry attempts time out -- raises CommandError with code=124."""
        mock_time.time.side_effect = [0.0, 0.1]
        mock_time.sleep = Mock()
        mock_subproc.side_effect = [
            subprocess.TimeoutExpired("cmd", 10),
            subprocess.TimeoutExpired("cmd", 10),
        ]

        with pytest.raises(CommandError) as exc_info:
            runner.run("cmd", retries=1, timeout=10)

        assert exc_info.value.code == 124

    @patch("h2kvm.core.command_runner.time")
    @patch("h2kvm.core.command_runner.subprocess.run")
    def test_default_retries_used_with_timeout(self, mock_subproc, mock_time, retry_runner):
        """When retries=None, the runner's default_retries (2) is used."""
        mock_time.time.side_effect = [0.0, 0.1, 0.2, 0.3]
        mock_time.sleep = Mock()
        mock_subproc.side_effect = [
            subprocess.TimeoutExpired("cmd", 5),
            subprocess.TimeoutExpired("cmd", 5),
            subprocess.TimeoutExpired("cmd", 5),
        ]

        with pytest.raises(CommandError) as exc_info:
            retry_runner.run("cmd", retries=None)

        # default_retries=2, so 3 total attempts (0, 1, 2)
        assert mock_subproc.call_count == 3
        assert exc_info.value.code == 124

    @patch("h2kvm.core.command_runner.time")
    @patch("h2kvm.core.command_runner.subprocess.run")
    def test_retry_records_attempt_count(self, mock_subproc, mock_time, runner):
        """The retries field in CommandResult reflects the attempt number."""
        mock_time.time.side_effect = [0.0, 0.1, 0.2]
        mock_time.sleep = Mock()
        mock_subproc.side_effect = [
            subprocess.TimeoutExpired("cmd", 5),
            _make_process(0, "ok", ""),
        ]

        result = runner.run("cmd", retries=2)

        assert result.retries == 1  # second attempt (0-indexed)


# ===========================================================================
# CommandRunner.run  --  capture_output, shell, cwd, env
# ===========================================================================


class TestRunOptions:
    @patch("h2kvm.core.command_runner.time")
    @patch("h2kvm.core.command_runner.subprocess.run")
    def test_capture_output_false(self, mock_subproc, mock_time, runner):
        mock_time.time.side_effect = [0.0, 0.1]
        mock_subproc.return_value = _make_process(0, "ignored", "ignored")

        result = runner.run("cmd", capture_output=False)

        call_kwargs = mock_subproc.call_args[1]
        assert call_kwargs["capture_output"] is False
        assert result.stdout == ""
        assert result.stderr == ""

    @patch("h2kvm.core.command_runner.time")
    @patch("h2kvm.core.command_runner.subprocess.run")
    def test_cwd_passed_through(self, mock_subproc, mock_time, runner):
        mock_time.time.side_effect = [0.0, 0.1]
        mock_subproc.return_value = _make_process(0, "", "")

        runner.run("ls", cwd="/tmp")

        call_kwargs = mock_subproc.call_args[1]
        assert call_kwargs["cwd"] == "/tmp"

    @patch("h2kvm.core.command_runner.time")
    @patch("h2kvm.core.command_runner.subprocess.run")
    def test_env_passed_through(self, mock_subproc, mock_time, runner):
        mock_time.time.side_effect = [0.0, 0.1]
        mock_subproc.return_value = _make_process(0, "", "")
        custom_env = {"FOO": "bar"}

        runner.run("cmd", env=custom_env)

        call_kwargs = mock_subproc.call_args[1]
        assert call_kwargs["env"] == {"FOO": "bar"}

    @patch("h2kvm.core.command_runner.time")
    @patch("h2kvm.core.command_runner.subprocess.run")
    def test_shell_false_splits_string(self, mock_subproc, mock_time, runner):
        mock_time.time.side_effect = [0.0, 0.1]
        mock_subproc.return_value = _make_process(0, "", "")

        runner.run("ls -la /tmp", shell=False)

        call_args = mock_subproc.call_args[0][0]
        assert call_args == ["ls", "-la", "/tmp"]
        call_kwargs = mock_subproc.call_args[1]
        assert call_kwargs["shell"] is False


# ===========================================================================
# CommandRunner.run_checked
# ===========================================================================


class TestRunChecked:
    @patch("h2kvm.core.command_runner.time")
    @patch("h2kvm.core.command_runner.subprocess.run")
    def test_run_checked_raises_on_failure(self, mock_subproc, mock_time, runner):
        mock_time.time.side_effect = [0.0, 0.1]
        mock_subproc.return_value = _make_process(1, "", "err")

        with pytest.raises(CommandError):
            runner.run_checked("bad_cmd")

    @patch("h2kvm.core.command_runner.time")
    @patch("h2kvm.core.command_runner.subprocess.run")
    def test_run_checked_returns_result_on_success(self, mock_subproc, mock_time, runner):
        mock_time.time.side_effect = [0.0, 0.1]
        mock_subproc.return_value = _make_process(0, "output", "")

        result = runner.run_checked("good_cmd")

        assert result.success is True
        assert result.stdout == "output"

    @patch("h2kvm.core.command_runner.time")
    @patch("h2kvm.core.command_runner.subprocess.run")
    def test_run_checked_passes_kwargs(self, mock_subproc, mock_time, runner):
        mock_time.time.side_effect = [0.0, 0.1]
        mock_subproc.return_value = _make_process(0, "", "")

        runner.run_checked("cmd", use_sudo=True, timeout=60)

        call_args = mock_subproc.call_args[0][0]
        assert "sudo" in call_args
        assert mock_subproc.call_args[1]["timeout"] == 60


# ===========================================================================
# CommandRunner.run_silent
# ===========================================================================


class TestRunSilent:
    @patch("h2kvm.core.command_runner.time")
    @patch("h2kvm.core.command_runner.subprocess.run")
    def test_run_silent_returns_tuple(self, mock_subproc, mock_time, runner):
        mock_time.time.side_effect = [0.0, 0.1]
        mock_subproc.return_value = _make_process(0, "out", "err")

        exit_code, stdout, stderr = runner.run_silent("cmd")

        assert exit_code == 0
        assert stdout == "out"
        assert stderr == "err"

    @patch("h2kvm.core.command_runner.time")
    @patch("h2kvm.core.command_runner.subprocess.run")
    def test_run_silent_failure_tuple(self, mock_subproc, mock_time, runner):
        mock_time.time.side_effect = [0.0, 0.1]
        mock_subproc.return_value = _make_process(127, "", "not found")

        exit_code, stdout, stderr = runner.run_silent("missing_cmd")

        assert exit_code == 127
        assert stdout == ""
        assert stderr == "not found"

    @patch("h2kvm.core.command_runner.time")
    @patch("h2kvm.core.command_runner.subprocess.run")
    def test_run_silent_passes_kwargs(self, mock_subproc, mock_time, runner):
        mock_time.time.side_effect = [0.0, 0.1]
        mock_subproc.return_value = _make_process(0, "", "")

        runner.run_silent("cmd", use_sudo=True, cwd="/var")

        call_args = mock_subproc.call_args[0][0]
        assert "sudo" in call_args
        assert mock_subproc.call_args[1]["cwd"] == "/var"

    def test_run_silent_dry_run(self, dry_runner):
        exit_code, stdout, stderr = dry_runner.run_silent("cmd")

        assert exit_code == 0
        assert stderr == "[dry-run mode]"
