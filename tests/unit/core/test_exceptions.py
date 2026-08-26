# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""Tests for h2kvm.core.exceptions."""

from __future__ import annotations

import pytest

from h2kvm.core.exceptions import (
    AzureError,
    BootloaderFixerError,
    ConfigurationError,
    CommandError,
    DiskConversionError,
    Fatal,
    FixerError,
    H2KvmError,
    InfrastructureError,
    LVMError,
    ManifestError,
    ProviderError,
    StorageError,
    VMwareError,
    _clamp_exit_code,
    _is_secret_key,
    _one_line,
    _redact_secrets,
    _safe_int,
    create_helpful_error,
    format_exception_for_cli,
    wrap_fatal,
    wrap_vmware,
)


# ============================================================================
# _safe_int
# ============================================================================


class TestSafeInt:
    def test_valid_int(self):
        assert _safe_int(42) == 42

    def test_valid_string_number(self):
        assert _safe_int("10") == 10

    def test_zero(self):
        assert _safe_int(0) == 0

    def test_float_truncates(self):
        assert _safe_int(3.9) == 3

    def test_invalid_string_returns_default(self):
        assert _safe_int("abc") == 1

    def test_invalid_string_custom_default(self):
        assert _safe_int("abc", default=99) == 99

    def test_none_returns_default(self):
        assert _safe_int(None) == 1

    def test_object_returns_default(self):
        assert _safe_int(object()) == 1

    def test_bool_true(self):
        # bool is a subclass of int in Python; int(True) == 1
        assert _safe_int(True) == 1

    def test_negative(self):
        assert _safe_int(-5) == -5


# ============================================================================
# _clamp_exit_code
# ============================================================================


class TestClampExitCode:
    def test_valid_zero(self):
        assert _clamp_exit_code(0) == 0

    def test_valid_255(self):
        assert _clamp_exit_code(255) == 255

    def test_valid_middle(self):
        assert _clamp_exit_code(42) == 42

    def test_negative_raises(self):
        with pytest.raises(ValueError, match="range 0-255"):
            _clamp_exit_code(-1)

    def test_above_255_raises(self):
        with pytest.raises(ValueError, match="range 0-255"):
            _clamp_exit_code(256)

    def test_non_integer_type_raises(self):
        with pytest.raises(ValueError, match="must be an integer"):
            _clamp_exit_code("not-a-number")  # type: ignore[arg-type]


# ============================================================================
# _one_line
# ============================================================================


class TestOneLine:
    def test_simple_string(self):
        assert _one_line("hello") == "hello"

    def test_strips_whitespace(self):
        assert _one_line("  hello  ") == "hello"

    def test_replaces_newlines(self):
        assert _one_line("line1\nline2\nline3") == "line1 line2 line3"

    def test_replaces_carriage_returns(self):
        assert _one_line("line1\rline2") == "line1 line2"

    def test_collapses_multiple_spaces(self):
        assert _one_line("a   b    c") == "a b c"

    def test_empty_string(self):
        assert _one_line("") == ""

    def test_none_input(self):
        assert _one_line(None) == ""  # type: ignore[arg-type]

    def test_truncation_at_default_limit(self):
        long = "x" * 700
        result = _one_line(long)
        assert len(result) == 600
        assert result.endswith("...")

    def test_custom_limit(self):
        result = _one_line("a" * 50, limit=20)
        assert len(result) == 20
        assert result.endswith("...")

    def test_exactly_at_limit(self):
        s = "a" * 600
        result = _one_line(s)
        assert result == s  # No truncation when exactly at limit


# ============================================================================
# _is_secret_key
# ============================================================================


class TestIsSecretKey:
    @pytest.mark.parametrize(
        "key",
        [
            "password",
            "db_password",
            "PASSWORD",
            "token",
            "api_token",
            "apikey",
            "API_KEY",
            "api_key",
            "auth_header",
            "cookie",
            "session_id",
            "bearer_token",
            "private_key",
            "secret",
            "passwd",
            "my_pass_phrase",
        ],
    )
    def test_secret_keys_detected(self, key):
        assert _is_secret_key(key) is True

    @pytest.mark.parametrize(
        "key",
        [
            "hostname",
            "disk_path",
            "vm_name",
            "cpu_count",
            "memory_mb",
        ],
    )
    def test_non_secret_keys_not_detected(self, key):
        assert _is_secret_key(key) is False

    def test_none_input(self):
        assert _is_secret_key(None) is False  # type: ignore[arg-type]

    def test_empty_string(self):
        assert _is_secret_key("") is False


# ============================================================================
# _redact_secrets
# ============================================================================


class TestRedactSecrets:
    def test_redacts_dict_secret_key(self):
        result = _redact_secrets({"password": "hunter2", "host": "vm1"})
        assert result["password"] == "***REDACTED***"
        assert result["host"] == "vm1"

    def test_non_dict_passthrough(self):
        assert _redact_secrets(42) == 42
        assert _redact_secrets("hello") == "hello"

    def test_nested_dict_redaction(self):
        obj = {"outer": {"api_key": "abc123", "name": "test"}}
        result = _redact_secrets(obj)
        assert result["outer"]["api_key"] == "***REDACTED***"
        assert result["outer"]["name"] == "test"

    def test_list_of_dicts(self):
        obj = [{"token": "secret"}, {"host": "vm1"}]
        result = _redact_secrets(obj)
        assert result[0]["token"] == "***REDACTED***"
        assert result[1]["host"] == "vm1"

    def test_tuple_preserved(self):
        obj = ({"secret": "val"},)
        result = _redact_secrets(obj)
        assert isinstance(result, tuple)
        assert result[0]["secret"] == "***REDACTED***"

    def test_empty_dict(self):
        assert _redact_secrets({}) == {}

    def test_deeply_nested(self):
        obj = {"a": {"b": {"c": {"private_key": "deep"}}}}
        result = _redact_secrets(obj)
        assert result["a"]["b"]["c"]["private_key"] == "***REDACTED***"


# ============================================================================
# H2KvmError - construction and __post_init__
# ============================================================================


class TestH2KvmErrorConstruction:
    def test_defaults(self):
        err = H2KvmError()
        assert err.code == 1
        assert err.msg == "error"
        assert err.cause is None
        assert err.context == {}

    def test_custom_fields(self):
        cause = ValueError("boom")
        err = H2KvmError(code=42, msg="disk failed", cause=cause, context={"disk": "/dev/sda"})
        assert err.code == 42
        assert err.msg == "disk failed"
        assert err.cause is cause
        assert err.context == {"disk": "/dev/sda"}

    def test_code_clamped_via_safe_int(self):
        err = H2KvmError(code="not_a_number")  # type: ignore[arg-type]
        # _safe_int("not_a_number") -> 1, _clamp_exit_code(1) -> 1
        assert err.code == 1

    def test_code_out_of_range_raises(self):
        with pytest.raises(ValueError, match="range 0-255"):
            H2KvmError(code=999)

    def test_msg_normalized_to_one_line(self):
        err = H2KvmError(msg="line1\nline2\nline3")
        assert "\n" not in err.msg
        assert err.msg == "line1 line2 line3"

    def test_empty_msg_uses_class_name(self):
        err = H2KvmError(msg="")
        assert err.msg == "H2KvmError"

    def test_none_context_defaults_to_empty_dict(self):
        err = H2KvmError(context=None)
        assert err.context == {}

    def test_is_exception(self):
        err = H2KvmError()
        assert isinstance(err, Exception)

    def test_args_tuple(self):
        err = H2KvmError(msg="test message")
        assert err.args == ("test message",)

    def test_super_init_called_with_msg(self):
        err = H2KvmError(msg="hello")
        # Exception.__init__ sets args
        assert str(Exception.__str__(err)) == "hello"

    def test_eq_false_means_identity_equality(self):
        a = H2KvmError(code=1, msg="same")
        b = H2KvmError(code=1, msg="same")
        assert a != b
        assert a == a


# ============================================================================
# with_context
# ============================================================================


class TestWithContext:
    def test_adds_context(self):
        err = H2KvmError()
        result = err.with_context(vm="test-vm", disk="/dev/sda")
        assert result is err  # returns self
        assert err.context == {"vm": "test-vm", "disk": "/dev/sda"}

    def test_updates_existing_context(self):
        err = H2KvmError(context={"a": 1})
        err.with_context(b=2)
        assert err.context == {"a": 1, "b": 2}

    def test_overwrites_existing_key(self):
        err = H2KvmError(context={"a": 1})
        err.with_context(a=99)
        assert err.context["a"] == 99

    def test_chaining(self):
        err = H2KvmError()
        result = err.with_context(a=1).with_context(b=2)
        assert result is err
        assert err.context == {"a": 1, "b": 2}


# ============================================================================
# user_message
# ============================================================================


class TestUserMessage:
    def test_basic_message(self):
        err = H2KvmError(msg="something broke")
        assert err.user_message() == "something broke"

    def test_include_context_false_ignores_context(self):
        err = H2KvmError(msg="fail", context={"vm": "test"})
        result = err.user_message(include_context=False)
        assert "vm" not in result

    def test_include_context_true_shows_context(self):
        err = H2KvmError(msg="fail", context={"vm": "test"})
        result = err.user_message(include_context=True)
        assert "vm=" in result
        assert "'test'" in result

    def test_solutions_formatted(self):
        err = H2KvmError(
            msg="disk error",
            context={"solutions": ["Check disk space", "Run fsck"]},
        )
        result = err.user_message(include_context=True)
        assert "Solutions:" in result
        assert "1. Check disk space" in result
        assert "2. Run fsck" in result

    def test_causes_formatted(self):
        err = H2KvmError(
            msg="boot failed",
            context={"causes": ["Missing GRUB", "Wrong partition"]},
        )
        result = err.user_message(include_context=True)
        assert "Common causes:" in result
        assert "1. Missing GRUB" in result
        assert "2. Wrong partition" in result

    def test_doc_link_formatted(self):
        err = H2KvmError(
            msg="error",
            context={"doc_link": "https://example.com/docs"},
        )
        result = err.user_message(include_context=True)
        assert "Documentation: https://example.com/docs" in result

    def test_remaining_context_after_special_fields(self):
        err = H2KvmError(
            msg="error",
            context={"solutions": ["fix it"], "vm": "my-vm"},
        )
        result = err.user_message(include_context=True)
        assert "Solutions:" in result
        assert "vm=" in result

    def test_include_cause_true(self):
        cause = OSError("disk full")
        err = H2KvmError(msg="write failed", cause=cause)
        result = err.user_message(include_cause=True)
        assert "cause: OSError: disk full" in result

    def test_include_cause_false_ignores_cause(self):
        cause = OSError("disk full")
        err = H2KvmError(msg="write failed", cause=cause)
        result = err.user_message(include_cause=False)
        assert "cause" not in result

    def test_include_cause_when_none(self):
        err = H2KvmError(msg="oops")
        result = err.user_message(include_cause=True)
        assert "cause" not in result

    def test_empty_context_no_brackets(self):
        err = H2KvmError(msg="fail", context={})
        result = err.user_message(include_context=True)
        assert result == "fail"

    def test_all_special_fields_together(self):
        err = H2KvmError(
            msg="migration failed",
            context={
                "solutions": ["Retry"],
                "causes": ["Network"],
                "doc_link": "https://docs.example.com",
                "vm": "prod-1",
            },
            cause=RuntimeError("timeout"),
        )
        result = err.user_message(include_context=True, include_cause=True)
        assert "Solutions:" in result
        assert "Common causes:" in result
        assert "Documentation:" in result
        assert "vm=" in result
        assert "cause: RuntimeError: timeout" in result


# ============================================================================
# __str__
# ============================================================================


class TestStr:
    def test_str_returns_user_message(self):
        err = H2KvmError(msg="broken")
        assert str(err) == "broken"

    def test_str_does_not_include_context(self):
        err = H2KvmError(msg="fail", context={"vm": "test"})
        assert "vm" not in str(err)

    def test_str_does_not_include_cause(self):
        err = H2KvmError(msg="fail", cause=ValueError("inner"))
        assert "cause" not in str(err)


# ============================================================================
# to_dict
# ============================================================================


class TestToDict:
    def test_basic_dict(self):
        err = H2KvmError(code=2, msg="disk error")
        d = err.to_dict()
        assert d["type"] == "H2KvmError"
        assert d["code"] == 2
        assert d["message"] == "disk error"
        assert d["context"] == {}

    def test_context_included(self):
        err = H2KvmError(msg="err", context={"disk": "/dev/sda"})
        d = err.to_dict()
        assert d["context"]["disk"] == "/dev/sda"

    def test_secrets_redacted_in_context(self):
        err = H2KvmError(msg="err", context={"password": "hunter2", "host": "vm1"})
        d = err.to_dict()
        assert d["context"]["password"] == "***REDACTED***"
        assert d["context"]["host"] == "vm1"

    def test_include_cause_true(self):
        cause = IOError("read error")
        err = H2KvmError(msg="fail", cause=cause)
        d = err.to_dict(include_cause=True)
        assert "cause" in d
        assert d["cause"]["type"] == "OSError"  # IOError is alias for OSError
        assert "read error" in d["cause"]["message"]

    def test_include_cause_false(self):
        err = H2KvmError(msg="fail", cause=ValueError("x"))
        d = err.to_dict(include_cause=False)
        assert "cause" not in d

    def test_include_cause_true_but_no_cause(self):
        err = H2KvmError(msg="fail")
        d = err.to_dict(include_cause=True)
        assert "cause" not in d

    def test_subclass_type_name(self):
        err = Fatal(msg="fatal")
        d = err.to_dict()
        assert d["type"] == "Fatal"


# ============================================================================
# Subclass hierarchy
# ============================================================================


class TestSubclassHierarchy:
    def test_fatal_is_h2kvm_error(self):
        assert issubclass(Fatal, H2KvmError)

    def test_vmware_error_is_h2kvm_error(self):
        assert issubclass(VMwareError, H2KvmError)

    def test_provider_error_is_h2kvm_error(self):
        assert issubclass(ProviderError, H2KvmError)

    def test_azure_error_is_provider_error(self):
        assert issubclass(AzureError, ProviderError)

    def test_fixer_error_is_h2kvm_error(self):
        assert issubclass(FixerError, H2KvmError)

    def test_bootloader_fixer_is_fixer_error(self):
        assert issubclass(BootloaderFixerError, FixerError)

    def test_storage_error_is_h2kvm_error(self):
        assert issubclass(StorageError, H2KvmError)

    def test_disk_conversion_is_storage_error(self):
        assert issubclass(DiskConversionError, StorageError)

    def test_lvm_error_is_storage_error(self):
        assert issubclass(LVMError, StorageError)

    def test_configuration_error_is_h2kvm_error(self):
        assert issubclass(ConfigurationError, H2KvmError)

    def test_manifest_error_is_configuration_error(self):
        assert issubclass(ManifestError, ConfigurationError)

    def test_command_error_is_h2kvm_error(self):
        assert issubclass(CommandError, H2KvmError)

    def test_all_subclasses_are_exceptions(self):
        for cls in (
            Fatal,
            VMwareError,
            ProviderError,
            AzureError,
            FixerError,
            BootloaderFixerError,
            StorageError,
            DiskConversionError,
            LVMError,
            ConfigurationError,
            ManifestError,
            CommandError,
        ):
            assert issubclass(cls, Exception), f"{cls.__name__} should be an Exception"


# ============================================================================
# wrap_fatal
# ============================================================================


class TestWrapFatal:
    def test_returns_fatal_instance(self):
        err = wrap_fatal("something broke")
        assert isinstance(err, Fatal)

    def test_message_set(self):
        err = wrap_fatal("boom")
        assert err.msg == "boom"

    def test_cause_attached(self):
        cause = OSError("no space")
        err = wrap_fatal("disk fail", cause)
        assert err.cause is cause

    def test_default_code(self):
        err = wrap_fatal("fail")
        assert err.code == 1

    def test_custom_code(self):
        err = wrap_fatal("fail", code=42)
        assert err.code == 42

    def test_context_from_kwargs(self):
        err = wrap_fatal("fail", vm="test-vm", disk="/dev/sda")
        assert err.context["vm"] == "test-vm"
        assert err.context["disk"] == "/dev/sda"

    def test_no_context_defaults_to_empty(self):
        err = wrap_fatal("fail")
        # wrap_fatal passes context=None when no kwargs -> __post_init__ sets {}
        assert err.context == {}


# ============================================================================
# wrap_vmware
# ============================================================================


class TestWrapVmware:
    def test_returns_vmware_error(self):
        err = wrap_vmware("vcenter fail")
        assert isinstance(err, VMwareError)

    def test_default_code_is_50(self):
        err = wrap_vmware("fail")
        assert err.code == 50

    def test_cause_and_context(self):
        cause = ConnectionError("timeout")
        err = wrap_vmware("connect failed", cause, host="esx1")
        assert err.cause is cause
        assert err.context["host"] == "esx1"


# ============================================================================
# format_exception_for_cli
# ============================================================================


class TestFormatExceptionForCli:
    def test_verbose_0_just_message(self):
        err = H2KvmError(msg="disk error", context={"vm": "test"})
        result = format_exception_for_cli(err, verbose=0)
        assert result == "disk error"
        assert "vm" not in result

    def test_verbose_1_includes_context(self):
        err = H2KvmError(msg="disk error", context={"vm": "test"})
        result = format_exception_for_cli(err, verbose=1)
        assert "vm=" in result

    def test_verbose_1_no_cause(self):
        err = H2KvmError(msg="fail", cause=ValueError("inner"))
        result = format_exception_for_cli(err, verbose=1)
        assert "cause" not in result

    def test_verbose_2_includes_context_and_cause(self):
        err = H2KvmError(msg="fail", context={"vm": "x"}, cause=ValueError("inner"))
        result = format_exception_for_cli(err, verbose=2)
        assert "vm=" in result
        assert "cause: ValueError: inner" in result

    def test_non_project_exception_verbose_0(self):
        err = RuntimeError("something went wrong")
        result = format_exception_for_cli(err, verbose=0)
        assert result == "something went wrong"
        assert "RuntimeError" not in result

    def test_non_project_exception_verbose_2(self):
        err = RuntimeError("something went wrong")
        result = format_exception_for_cli(err, verbose=2)
        assert "RuntimeError: something went wrong" in result

    def test_non_project_exception_empty_message(self):
        err = RuntimeError("")
        result = format_exception_for_cli(err, verbose=0)
        assert result == "RuntimeError"


# ============================================================================
# create_helpful_error
# ============================================================================


class TestCreateHelpfulError:
    def test_returns_correct_type(self):
        err = create_helpful_error(Fatal, "bad thing")
        assert isinstance(err, Fatal)

    def test_message_set(self):
        err = create_helpful_error(Fatal, "bad thing")
        assert err.msg == "bad thing"

    def test_custom_code(self):
        err = create_helpful_error(Fatal, "fail", code=42)
        assert err.code == 42

    def test_solutions_in_context(self):
        err = create_helpful_error(Fatal, "fail", solutions=["fix it", "try again"])
        assert err.context["solutions"] == ["fix it", "try again"]

    def test_causes_in_context(self):
        err = create_helpful_error(Fatal, "fail", causes=["disk full"])
        assert err.context["causes"] == ["disk full"]

    def test_doc_link_formatted(self):
        err = create_helpful_error(Fatal, "fail", doc_link="troubleshooting.md")
        assert "troubleshooting.md" in err.context["doc_link"]
        assert err.context["doc_link"].startswith("https://github.com/ssahani/h2kvm/blob/main/docs/")

    def test_extra_context_kwargs(self):
        err = create_helpful_error(Fatal, "fail", vm="test-vm")
        assert err.context["vm"] == "test-vm"

    def test_no_optional_fields(self):
        err = create_helpful_error(VMwareError, "vcenter down")
        assert isinstance(err, VMwareError)
        assert "solutions" not in err.context
        assert "causes" not in err.context
        assert "doc_link" not in err.context

    def test_all_fields_together(self):
        err = create_helpful_error(
            StorageError,
            "disk conversion failed",
            code=10,
            solutions=["Retry"],
            causes=["Corrupt VMDK"],
            doc_link="storage.md",
            disk="/dev/sda",
        )
        assert isinstance(err, StorageError)
        assert err.code == 10
        assert err.context["solutions"] == ["Retry"]
        assert err.context["causes"] == ["Corrupt VMDK"]
        assert "storage.md" in err.context["doc_link"]
        assert err.context["disk"] == "/dev/sda"

    def test_user_message_includes_all_helpful_fields(self):
        err = create_helpful_error(
            Fatal,
            "VM not found",
            solutions=["Check name"],
            causes=["Typo"],
            doc_link="vms.md",
        )
        msg = err.user_message(include_context=True)
        assert "Solutions:" in msg
        assert "Common causes:" in msg
        assert "Documentation:" in msg
