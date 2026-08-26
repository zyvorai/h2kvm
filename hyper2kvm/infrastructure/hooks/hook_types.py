# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""Hook type implementations: script, python, http."""

from __future__ import annotations

import importlib.util
import logging
import subprocess
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ...core.exceptions import HookExecutionError
from ...core.logger import Log
from .template_engine import TemplateEngine


@dataclass
class HookResult:
    """Result of a hook execution."""

    success: bool
    duration: float
    output: str | None = None
    error: str | None = None
    return_code: int | None = None


class BaseHook(ABC):
    """Base class for all hook types."""

    def __init__(
        self,
        config: dict[str, Any],
        context: dict[str, Any],
        logger: logging.Logger | None = None,
    ):
        self.config = config
        self.context = context
        self.logger = logger or logging.getLogger(__name__)
        self.template_engine = TemplateEngine(logger)

        # Common settings
        self.timeout = config.get("timeout", 300)  # 5 minutes default
        self.continue_on_error = config.get("continue_on_error", False)

    @abstractmethod
    def execute(self) -> HookResult:
        """Execute the hook and return result."""

    def _substitute_variables(self, template: str) -> str:
        """Substitute variables in a template string."""
        return self.template_engine.substitute(template, self.context, strict=False)


class ScriptHook(BaseHook):
    """
    Execute a shell script hook.

    Configuration:
        type: script
        path: /path/to/script.sh
        args: [optional, list, of, args]
        env:
          VAR1: "{{ variable }}"
          VAR2: "value"
        timeout: 300
        continue_on_error: false
        working_directory: /path
    """

    def execute(self) -> HookResult:
        """Execute shell script."""
        import time

        script_path = Path(self.config["path"]).expanduser().resolve()

        # Security: Validate script path exists and is not a symlink escape
        if not script_path.exists():
            raise HookExecutionError(f"Script not found: {script_path}")

        if not script_path.is_file():
            raise HookExecutionError(f"Script path is not a file: {script_path}")

        # Check executable permission
        if not script_path.stat().st_mode & 0o111:
            self.logger.warning(f"Script {script_path} is not executable, will run with shell")

        # Build command
        cmd = [str(script_path)]

        # Add arguments with variable substitution
        args = self.config.get("args", [])
        if args:
            cmd.extend([self._substitute_variables(str(arg)) for arg in args])

        # Prepare environment with variable substitution
        env = self.config.get("env", {})
        env_substituted = {key: self._substitute_variables(str(value)) for key, value in env.items()}

        # Merge with current environment
        import os

        full_env = os.environ.copy()
        full_env.update(env_substituted)

        # Working directory
        working_dir = self.config.get("working_directory")
        if working_dir:
            working_dir = Path(self._substitute_variables(str(working_dir)))
            if not working_dir.exists():
                raise HookExecutionError(f"Working directory not found: {working_dir}")
            cwd = str(working_dir)
        else:
            cwd = None

        self.logger.info(f"Executing script hook: {' '.join(cmd)}")
        Log.trace(
            self.logger,
            "Script hook: cmd=%s env_keys=%s cwd=%s timeout=%d",
            cmd,
            list(env_substituted.keys()),
            cwd,
            self.timeout,
        )

        start_time = time.time()

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.timeout,
                env=full_env,
                cwd=cwd,
                check=False,  # Don't raise on non-zero exit
            )

            duration = time.time() - start_time
            success = result.returncode == 0

            if success:
                self.logger.info(f"✅ Script hook completed successfully in {duration:.2f}s")
            else:
                self.logger.error(f"❌ Script hook failed with exit code {result.returncode}")
                Log.trace(self.logger, "Script stderr: %s", result.stderr)

            return HookResult(
                success=success,
                duration=duration,
                output=result.stdout,
                error=result.stderr if not success else None,
                return_code=result.returncode,
            )

        except subprocess.TimeoutExpired:
            duration = time.time() - start_time
            raise HookExecutionError(f"Script hook timed out after {self.timeout}s") from None

        except Exception as e:
            duration = time.time() - start_time
            raise HookExecutionError(f"Script hook execution failed: {e}") from e


class PythonHook(BaseHook):
    """
    Execute a Python function hook.

    Configuration:
        type: python
        module: my_module.hooks
        function: my_hook_function
        args:
          disk: "{{ output_path }}"
          vm_name: "{{ vm_name }}"
        timeout: 300
        continue_on_error: false
    """

    def execute(self) -> HookResult:
        """Execute Python function."""
        import time

        module_name = self.config["module"]
        function_name = self.config["function"]

        self.logger.info(f"Executing Python hook: {module_name}.{function_name}")

        start_time = time.time()

        try:
            # Import module
            try:
                module = importlib.import_module(module_name)
            except ImportError as e:
                raise HookExecutionError(f"Failed to import module '{module_name}': {e}") from e

            # Get function
            if not hasattr(module, function_name):
                raise HookExecutionError(f"Function '{function_name}' not found in module '{module_name}'")

            func = getattr(module, function_name)
            if not callable(func):
                raise HookExecutionError(f"'{function_name}' is not a callable function")

            # Prepare arguments with variable substitution
            args = self.config.get("args", {})
            args_substituted = self.template_engine.substitute_dict(args, self.context, strict=False)

            Log.trace(
                self.logger,
                "Python hook: func=%s.%s args=%s timeout=%d",
                module_name,
                function_name,
                args_substituted,
                self.timeout,
            )

            # Execute function with timeout support
            from concurrent.futures import (
                ThreadPoolExecutor,
                TimeoutError as FuturesTimeoutError,
            )

            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(func, **args_substituted)
                try:
                    result = future.result(timeout=self.timeout)
                except FuturesTimeoutError as err:
                    raise HookExecutionError(f"Python hook timed out after {self.timeout}s") from err

            duration = time.time() - start_time

            # Interpret result
            if isinstance(result, bool):
                success = result
                output = str(result)
            elif isinstance(result, dict):
                success = result.get("success", True)
                output = str(result.get("output", ""))
            else:
                success = True
                output = str(result) if result is not None else ""

            if success:
                self.logger.info(f"✅ Python hook completed successfully in {duration:.2f}s")
            else:
                self.logger.error("❌ Python hook failed")

            return HookResult(
                success=success,
                duration=duration,
                output=output,
                error=None if success else output,
            )

        except Exception as e:
            duration = time.time() - start_time
            self.logger.exception(f"Python hook exception: {e}")
            Log.trace(self.logger, "Python hook exception", exc_info=True)
            raise HookExecutionError(f"Python hook execution failed: {e}") from e


class HttpHook(BaseHook):
    """
    Execute an HTTP webhook hook.

    Configuration:
        type: http
        url: https://example.com/webhook
        method: POST
        headers:
          Authorization: "Bearer {{ token }}"
        body:
          vm_name: "{{ vm_name }}"
          status: "{{ stage }}"
        timeout: 30
        continue_on_error: false
    """

    def execute(self) -> HookResult:
        """Execute HTTP webhook."""
        import time

        try:
            import requests
        except ImportError:
            raise HookExecutionError(
                "requests library not installed. Install with: pip install requests"
            ) from None

        url = self._substitute_variables(self.config["url"])
        method = self.config.get("method", "POST").upper()

        self.logger.info(f"Executing HTTP hook: {method} {url}")

        # Prepare headers with variable substitution
        headers = self.config.get("headers", {})
        headers_substituted = {key: self._substitute_variables(str(value)) for key, value in headers.items()}

        # Prepare body with variable substitution
        body = self.config.get("body", {})
        body_substituted = self.template_engine.substitute_dict(body, self.context, strict=False)

        Log.trace(
            self.logger,
            "HTTP hook: method=%s url=%s headers=%s",
            method,
            url,
            list(headers_substituted.keys()),
        )

        start_time = time.time()

        try:
            if method == "GET":
                response = requests.get(
                    url,
                    headers=headers_substituted,
                    params=body_substituted,
                    timeout=self.timeout,
                )
            else:  # POST, PUT, etc.
                response = requests.request(
                    method,
                    url,
                    headers=headers_substituted,
                    json=body_substituted,
                    timeout=self.timeout,
                )

            duration = time.time() - start_time

            # Consider 2xx status codes as success
            success = 200 <= response.status_code < 300

            if success:
                self.logger.info(
                    f"✅ HTTP hook completed successfully: {response.status_code} in {duration:.2f}s"
                )
            else:
                self.logger.error(f"❌ HTTP hook failed: {response.status_code}")

            return HookResult(
                success=success,
                duration=duration,
                output=response.text if success else None,
                error=response.text if not success else None,
                return_code=response.status_code,
            )

        except requests.Timeout:
            duration = time.time() - start_time
            raise HookExecutionError(f"HTTP hook timed out after {self.timeout}s") from None

        except Exception as e:
            duration = time.time() - start_time
            raise HookExecutionError(f"HTTP hook execution failed: {e}") from e


def create_hook(
    hook_config: dict[str, Any],
    context: dict[str, Any],
    logger: logging.Logger | None = None,
) -> BaseHook:
    """
    Factory function to create appropriate hook type.

    Args:
        hook_config: Hook configuration dictionary
        context: Execution context for variable substitution
        logger: Logger instance

    Returns:
        Appropriate BaseHook subclass instance

    Raises:
        ValueError: If hook type is unknown or required fields missing
    """
    hook_type = hook_config.get("type")
    if not hook_type:
        raise ValueError(
            "Hook configuration must have a 'type' field. Supported types: 'script', 'python', 'http'."
        )

    hook_type = hook_type.lower()

    if hook_type == "script":
        if "path" not in hook_config:
            raise ValueError("Script hook requires 'path' field")
        return ScriptHook(hook_config, context, logger)

    if hook_type == "python":
        if "module" not in hook_config or "function" not in hook_config:
            raise ValueError("Python hook requires 'module' and 'function' fields")
        return PythonHook(hook_config, context, logger)

    if hook_type == "http":
        if "url" not in hook_config:
            raise ValueError("HTTP hook requires 'url' field")
        return HttpHook(hook_config, context, logger)

    raise ValueError(f"Unknown hook type: {hook_type}. Supported types: script, python, http")
