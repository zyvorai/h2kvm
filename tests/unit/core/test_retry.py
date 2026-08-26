# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""Tests for h2kvm/core/retry.py — retry_with_backoff decorator and retry_operation."""

from __future__ import annotations

import logging
from unittest.mock import MagicMock, patch

import pytest

from h2kvm.core.retry import retry_operation, retry_with_backoff


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_flaky(fail_times: int, exc: type[Exception] = RuntimeError, value: str = "ok"):
    """Return a callable that fails *fail_times* then succeeds with *value*."""
    call_count = {"n": 0}

    def fn():
        call_count["n"] += 1
        if call_count["n"] <= fail_times:
            raise exc(f"fail #{call_count['n']}")
        return value

    fn.call_count = call_count  # type: ignore[attr-defined]
    return fn


# ---------------------------------------------------------------------------
# retry_with_backoff — decorator
# ---------------------------------------------------------------------------


class TestRetryWithBackoffFirstSuccess:
    @patch("h2kvm.core.retry.time.sleep")
    @patch("h2kvm.core.retry.random.uniform", return_value=0.0)
    def test_first_attempt_success_no_sleep(self, _mock_rand, mock_sleep):
        @retry_with_backoff(max_attempts=3)
        def succeeds():
            return 42

        assert succeeds() == 42
        mock_sleep.assert_not_called()


class TestRetryWithBackoffRetries:
    @patch("h2kvm.core.retry.time.sleep")
    @patch("h2kvm.core.retry.random.uniform", return_value=0.0)
    def test_retry_after_failures(self, _mock_rand, mock_sleep):
        counter = {"n": 0}

        @retry_with_backoff(max_attempts=5, jitter_s=0)
        def flaky():
            counter["n"] += 1
            if counter["n"] <= 2:
                raise RuntimeError("boom")
            return "done"

        assert flaky() == "done"
        assert counter["n"] == 3
        assert mock_sleep.call_count == 2

    @patch("h2kvm.core.retry.time.sleep")
    @patch("h2kvm.core.retry.random.uniform", return_value=0.0)
    def test_exhausted_raises_last(self, _mock_rand, mock_sleep):
        counter = {"n": 0}

        @retry_with_backoff(max_attempts=3, jitter_s=0)
        def always_fails():
            counter["n"] += 1
            raise ValueError(f"fail #{counter['n']}")

        with pytest.raises(ValueError, match="fail #3"):
            always_fails()
        assert counter["n"] == 3


class TestRetryWithBackoffExceptionFilter:
    @patch("h2kvm.core.retry.time.sleep")
    @patch("h2kvm.core.retry.random.uniform", return_value=0.0)
    def test_catches_only_specified_exception(self, _mock_rand, mock_sleep):
        counter = {"n": 0}

        @retry_with_backoff(max_attempts=5, exceptions=ValueError, jitter_s=0)
        def raises_value():
            counter["n"] += 1
            if counter["n"] <= 2:
                raise ValueError("bad")
            return "ok"

        assert raises_value() == "ok"
        assert counter["n"] == 3

    @patch("h2kvm.core.retry.time.sleep")
    @patch("h2kvm.core.retry.random.uniform", return_value=0.0)
    def test_unmatched_exception_propagates_immediately(self, _mock_rand, mock_sleep):
        @retry_with_backoff(max_attempts=5, exceptions=ValueError, jitter_s=0)
        def raises_type():
            raise TypeError("wrong type")

        with pytest.raises(TypeError, match="wrong type"):
            raises_type()
        mock_sleep.assert_not_called()


class TestRetryWithBackoffBackoff:
    @patch("h2kvm.core.retry.time.sleep")
    @patch("h2kvm.core.retry.random.uniform", return_value=0.0)
    def test_exponential_backoff(self, _mock_rand, mock_sleep):
        counter = {"n": 0}

        @retry_with_backoff(max_attempts=5, base_backoff_s=2.0, max_backoff_s=100.0, jitter_s=0)
        def always_fails():
            counter["n"] += 1
            raise RuntimeError("fail")

        with pytest.raises(RuntimeError):
            always_fails()

        sleep_times = [call.args[0] for call in mock_sleep.call_args_list]
        # attempt 1: 2*2^0=2, attempt 2: 2*2^1=4, attempt 3: 2*2^2=8, attempt 4: 2*2^3=16
        assert sleep_times == [2.0, 4.0, 8.0, 16.0]

    @patch("h2kvm.core.retry.time.sleep")
    @patch("h2kvm.core.retry.random.uniform", return_value=0.0)
    def test_capped_backoff(self, _mock_rand, mock_sleep):
        counter = {"n": 0}

        @retry_with_backoff(max_attempts=5, base_backoff_s=2.0, max_backoff_s=5.0, jitter_s=0)
        def always_fails():
            counter["n"] += 1
            raise RuntimeError("fail")

        with pytest.raises(RuntimeError):
            always_fails()

        sleep_times = [call.args[0] for call in mock_sleep.call_args_list]
        # 2, 4, 5 (capped from 8), 5 (capped from 16)
        assert sleep_times == [2.0, 4.0, 5.0, 5.0]

    @patch("h2kvm.core.retry.time.sleep")
    @patch("h2kvm.core.retry.random.uniform", return_value=0.5)
    def test_jitter_added(self, mock_rand, mock_sleep):
        counter = {"n": 0}

        @retry_with_backoff(max_attempts=3, base_backoff_s=1.0, max_backoff_s=100.0, jitter_s=2.0)
        def always_fails():
            counter["n"] += 1
            raise RuntimeError("fail")

        with pytest.raises(RuntimeError):
            always_fails()

        sleep_times = [call.args[0] for call in mock_sleep.call_args_list]
        # attempt 1: 1*2^0 + 0.5 = 1.5, attempt 2: 1*2^1 + 0.5 = 2.5
        assert sleep_times == [1.5, 2.5]
        # random.uniform called with (0, jitter_s)
        for call in mock_rand.call_args_list:
            assert call.args == (0, 2.0)

    @patch("h2kvm.core.retry.time.sleep")
    def test_no_jitter(self, mock_sleep):
        counter = {"n": 0}

        @retry_with_backoff(max_attempts=3, base_backoff_s=1.0, max_backoff_s=100.0, jitter_s=0)
        def always_fails():
            counter["n"] += 1
            raise RuntimeError("fail")

        with pytest.raises(RuntimeError):
            always_fails()

        sleep_times = [call.args[0] for call in mock_sleep.call_args_list]
        # No jitter => exact exponential values
        assert sleep_times == [1.0, 2.0]


class TestRetryWithBackoffLogging:
    @patch("h2kvm.core.retry.time.sleep")
    @patch("h2kvm.core.retry.random.uniform", return_value=0.0)
    def test_logger_warning_on_retry(self, _mock_rand, mock_sleep):
        logger = MagicMock(spec=logging.Logger)
        counter = {"n": 0}

        @retry_with_backoff(max_attempts=3, logger=logger, jitter_s=0)
        def flaky():
            counter["n"] += 1
            if counter["n"] <= 1:
                raise RuntimeError("oops")
            return "ok"

        assert flaky() == "ok"
        # Should have logged a WARNING for the retry
        logger.log.assert_called_once()
        args = logger.log.call_args
        assert args[0][0] == logging.WARNING

    @patch("h2kvm.core.retry.time.sleep")
    @patch("h2kvm.core.retry.random.uniform", return_value=0.0)
    def test_logger_error_on_final_failure(self, _mock_rand, mock_sleep):
        logger = MagicMock(spec=logging.Logger)

        @retry_with_backoff(max_attempts=2, logger=logger, jitter_s=0)
        def always_fails():
            raise RuntimeError("fail")

        with pytest.raises(RuntimeError):
            always_fails()

        # Last call should be ERROR level
        last_call = logger.log.call_args_list[-1]
        assert last_call[0][0] == logging.ERROR

    @patch("h2kvm.core.retry.time.sleep")
    @patch("h2kvm.core.retry.random.uniform", return_value=0.0)
    def test_no_logger_works(self, _mock_rand, mock_sleep):
        counter = {"n": 0}

        @retry_with_backoff(max_attempts=3, logger=None, jitter_s=0)
        def flaky():
            counter["n"] += 1
            if counter["n"] <= 1:
                raise RuntimeError("oops")
            return "ok"

        # Should not raise and should not crash due to missing logger
        assert flaky() == "ok"


class TestRetryWithBackoffMisc:
    @patch("h2kvm.core.retry.time.sleep")
    @patch("h2kvm.core.retry.random.uniform", return_value=0.0)
    def test_preserves_return_value(self, _mock_rand, mock_sleep):
        @retry_with_backoff()
        def returns_dict():
            return {"key": [1, 2, 3]}

        assert returns_dict() == {"key": [1, 2, 3]}

    @patch("h2kvm.core.retry.time.sleep")
    @patch("h2kvm.core.retry.random.uniform", return_value=0.0)
    def test_max_attempts_one_raises_immediately(self, _mock_rand, mock_sleep):
        @retry_with_backoff(max_attempts=1, jitter_s=0)
        def always_fails():
            raise RuntimeError("instant")

        with pytest.raises(RuntimeError, match="instant"):
            always_fails()
        mock_sleep.assert_not_called()

    def test_preserves_function_name(self):
        @retry_with_backoff()
        def my_special_function():
            pass

        assert my_special_function.__name__ == "my_special_function"


# ---------------------------------------------------------------------------
# retry_operation — function-based API
# ---------------------------------------------------------------------------


class TestRetryOperationFirstSuccess:
    @patch("h2kvm.core.retry.time.sleep")
    @patch("h2kvm.core.retry.random.uniform", return_value=0.0)
    def test_first_attempt_success(self, _mock_rand, mock_sleep):
        result = retry_operation(lambda: "hello", max_attempts=3, jitter_s=0)
        assert result == "hello"
        mock_sleep.assert_not_called()


class TestRetryOperationRetries:
    @patch("h2kvm.core.retry.time.sleep")
    @patch("h2kvm.core.retry.random.uniform", return_value=0.0)
    def test_retry_after_failures(self, _mock_rand, mock_sleep):
        fn = _make_flaky(2, value="recovered")
        result = retry_operation(fn, max_attempts=5, jitter_s=0)
        assert result == "recovered"
        assert fn.call_count["n"] == 3
        assert mock_sleep.call_count == 2


class TestRetryOperationExhausted:
    @patch("h2kvm.core.retry.time.sleep")
    @patch("h2kvm.core.retry.random.uniform", return_value=0.0)
    def test_exhausted_raises(self, _mock_rand, mock_sleep):
        fn = _make_flaky(10, value="never")
        with pytest.raises(RuntimeError, match="fail #3"):
            retry_operation(fn, max_attempts=3, jitter_s=0)


class TestRetryOperationExceptionFilter:
    @patch("h2kvm.core.retry.time.sleep")
    @patch("h2kvm.core.retry.random.uniform", return_value=0.0)
    def test_catches_only_specified_exception(self, _mock_rand, mock_sleep):
        fn = _make_flaky(2, exc=ValueError, value="ok")
        result = retry_operation(fn, max_attempts=5, exceptions=ValueError, jitter_s=0)
        assert result == "ok"

    @patch("h2kvm.core.retry.time.sleep")
    @patch("h2kvm.core.retry.random.uniform", return_value=0.0)
    def test_unmatched_exception_propagates(self, _mock_rand, mock_sleep):
        def raises_type():
            raise TypeError("nope")

        with pytest.raises(TypeError, match="nope"):
            retry_operation(raises_type, max_attempts=5, exceptions=ValueError, jitter_s=0)
        mock_sleep.assert_not_called()


class TestRetryOperationBackoff:
    @patch("h2kvm.core.retry.time.sleep")
    @patch("h2kvm.core.retry.random.uniform", return_value=0.0)
    def test_exponential_backoff(self, _mock_rand, mock_sleep):
        fn = _make_flaky(4)
        with pytest.raises(RuntimeError):
            retry_operation(fn, max_attempts=4, base_backoff_s=2.0, max_backoff_s=100.0, jitter_s=0)

        sleep_times = [call.args[0] for call in mock_sleep.call_args_list]
        assert sleep_times == [2.0, 4.0, 8.0]

    @patch("h2kvm.core.retry.time.sleep")
    @patch("h2kvm.core.retry.random.uniform", return_value=0.0)
    def test_capped_backoff(self, _mock_rand, mock_sleep):
        fn = _make_flaky(4)
        with pytest.raises(RuntimeError):
            retry_operation(fn, max_attempts=4, base_backoff_s=2.0, max_backoff_s=5.0, jitter_s=0)

        sleep_times = [call.args[0] for call in mock_sleep.call_args_list]
        assert sleep_times == [2.0, 4.0, 5.0]


class TestRetryOperationLogging:
    @patch("h2kvm.core.retry.time.sleep")
    @patch("h2kvm.core.retry.random.uniform", return_value=0.0)
    def test_logger_warning_on_retry(self, _mock_rand, mock_sleep):
        logger = MagicMock(spec=logging.Logger)
        fn = _make_flaky(1, value="ok")
        result = retry_operation(fn, max_attempts=3, logger=logger, operation_name="test_op", jitter_s=0)
        assert result == "ok"
        logger.log.assert_called_once()
        assert logger.log.call_args[0][0] == logging.WARNING

    @patch("h2kvm.core.retry.time.sleep")
    @patch("h2kvm.core.retry.random.uniform", return_value=0.0)
    def test_logger_error_on_exhaustion(self, _mock_rand, mock_sleep):
        logger = MagicMock(spec=logging.Logger)
        fn = _make_flaky(10)
        with pytest.raises(RuntimeError):
            retry_operation(fn, max_attempts=2, logger=logger, jitter_s=0)

        last_call = logger.log.call_args_list[-1]
        assert last_call[0][0] == logging.ERROR


class TestRetryOperationMisc:
    @patch("h2kvm.core.retry.time.sleep")
    @patch("h2kvm.core.retry.random.uniform", return_value=0.0)
    def test_preserves_return_value(self, _mock_rand, mock_sleep):
        result = retry_operation(lambda: {"a": 1}, max_attempts=1, jitter_s=0)
        assert result == {"a": 1}

    @patch("h2kvm.core.retry.time.sleep")
    @patch("h2kvm.core.retry.random.uniform", return_value=0.0)
    def test_max_attempts_one_no_retry(self, _mock_rand, mock_sleep):
        def fails():
            raise RuntimeError("once")

        with pytest.raises(RuntimeError, match="once"):
            retry_operation(fails, max_attempts=1, jitter_s=0)
        mock_sleep.assert_not_called()
