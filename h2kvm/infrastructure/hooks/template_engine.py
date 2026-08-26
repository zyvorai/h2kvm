# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""Template variable substitution engine for hooks."""

from __future__ import annotations

import logging
import re
from typing import Any


class TemplateEngine:
    """
    Simple template variable substitution engine.

    Supports Jinja2-style variable syntax: {{ variable_name }}
    Provides safe substitution with type conversion and default values.
    """

    def __init__(self, logger: logging.Logger | None = None):
        self.logger = logger or logging.getLogger(__name__)
        # Pattern to match {{ variable_name }}
        self.pattern = re.compile(r"\{\{\s*(\w+)\s*\}\}")

    def substitute(
        self,
        template: str,
        variables: dict[str, Any],
        strict: bool = False,
    ) -> str:
        """
        Substitute variables in a template string.

        Args:
            template: Template string with {{ variable }} placeholders
            variables: Dictionary of variable name -> value mappings
            strict: If True, raise error on missing variables. If False, leave unmatched.

        Returns:
            String with variables substituted

        Raises:
            ValueError: If strict=True and variable not found
        """

        def replacer(match: re.Match) -> str:
            var_name = match.group(1)

            if var_name in variables:
                value = variables[var_name]
                # Convert to string (None becomes empty string)
                return str(value) if value is not None else ""

            # Variable not found
            if strict:
                raise ValueError(f"Variable '{var_name}' not found in context")

            # Leave placeholder as-is in non-strict mode
            self.logger.warning(f"Variable '{var_name}' not found, leaving placeholder")
            return match.group(0)

        return self.pattern.sub(replacer, template)

    def substitute_dict(
        self,
        template_dict: dict[str, Any],
        variables: dict[str, Any],
        strict: bool = False,
    ) -> dict[str, Any]:
        """
        Recursively substitute variables in a dictionary.

        Args:
            template_dict: Dictionary with template strings
            variables: Variable name -> value mappings
            strict: Strict mode flag

        Returns:
            Dictionary with all string values substituted
        """
        result = {}

        for key, value in template_dict.items():
            if isinstance(value, str):
                # Substitute string values
                result[key] = self.substitute(value, variables, strict)
            elif isinstance(value, dict):
                # Recursively process nested dicts
                result[key] = self.substitute_dict(value, variables, strict)
            elif isinstance(value, list):
                # Process list items
                result[key] = [
                    self.substitute(item, variables, strict) if isinstance(item, str) else item
                    for item in value
                ]
            else:
                # Keep non-string values as-is
                result[key] = value

        return result

    def substitute_list(
        self,
        template_list: list[Any],
        variables: dict[str, Any],
        strict: bool = False,
    ) -> list[Any]:
        """
        Substitute variables in all strings in a list.

        Args:
            template_list: List with template strings
            variables: Variable name -> value mappings
            strict: Strict mode flag

        Returns:
            List with all string values substituted
        """
        result = []

        for item in template_list:
            if isinstance(item, str):
                # Substitute string values
                result.append(self.substitute(item, variables, strict))
            elif isinstance(item, dict):
                # Recursively process nested dicts
                result.append(self.substitute_dict(item, variables, strict))
            elif isinstance(item, list):
                # Recursively process nested lists
                result.append(self.substitute_list(item, variables, strict))
            else:
                # Keep non-string values as-is
                result.append(item)

        return result

    def extract_variables(self, template: str) -> list[str]:
        """
        Extract all variable names from a template.

        Args:
            template: Template string

        Returns:
            List of variable names found in template
        """
        matches = self.pattern.findall(template)
        return list(set(matches))  # Unique variable names

    def validate_template(
        self,
        template: str,
        required_variables: list[str],
    ) -> tuple[bool, list[str]]:
        """
        Validate that template contains all required variables.

        Args:
            template: Template string
            required_variables: List of required variable names

        Returns:
            Tuple of (is_valid, missing_variables)
        """
        found_vars = set(self.extract_variables(template))
        required_set = set(required_variables)
        missing = required_set - found_vars

        return (len(missing) == 0, sorted(missing))


def create_hook_context(
    manifest_or_stage: dict[str, Any] | str | None = None,
    vm_name: str | None = None,
    source_path: str | None = None,
    output_path: str | None = None,
    stage: str | None = None,
    **extra: Any,
) -> dict[str, Any]:
    """
    Create a standard context dictionary for hook variable substitution.

    Can be called in multiple ways:
    1. With manifest dict: create_hook_context(manifest, **extra)
    2. Legacy positional: create_hook_context(stage, vm_name, source_path, output_path, **extra)
    3. Legacy keyword: create_hook_context(stage="pre_fix", vm_name="vm", **extra)

    Args:
        manifest_or_stage: Either a manifest dictionary or a stage name string (optional)
        vm_name: VM name (used in legacy mode)
        source_path: Source disk path (used in legacy mode)
        output_path: Output disk path (can be passed in both modes)
        stage: Stage name (keyword argument for backward compatibility)
        **extra: Additional context variables

    Returns:
        Dictionary of context variables
    """
    import os
    import time
    from pathlib import Path

    # Determine if we're in manifest mode or legacy mode
    if isinstance(manifest_or_stage, dict):
        # Manifest mode - extract information from manifest
        manifest = manifest_or_stage

        # Extract VM information from manifest
        source = manifest.get("source", {})
        vm_name_from_manifest = source.get("vm_name", "unknown")
        vm_id = source.get("vm_id", "")

        # Extract output information
        output = manifest.get("output", {})
        output_directory = output.get("directory", "")
        output_format = output.get("format", "")

        # Extract source_path from first disk if available
        disks = manifest.get("disks", [])
        source_path_from_manifest = ""
        if disks:
            source_path_from_manifest = disks[0].get("local_path", "")

        # Use manifest values, but allow override from parameters
        if stage is None:
            stage = extra.pop("stage", "unknown")
        vm_name = vm_name or vm_name_from_manifest
        source_path = source_path or source_path_from_manifest

        # Add manifest-specific fields to extra
        if vm_id:
            extra["vm_id"] = vm_id
        if output_directory:
            extra["output_directory"] = output_directory
        if output_format:
            extra["output_format"] = output_format

    # Legacy mode
    # If stage keyword arg provided, use it; otherwise use manifest_or_stage (positional)
    elif stage is None:
        stage = manifest_or_stage if manifest_or_stage is not None else "unknown"

    context = {
        # Stage information
        "stage": stage,
        "timestamp": int(time.time()),
        "timestamp_iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        # VM information
        "vm_name": vm_name or "unknown",
        # Paths
        "source_path": source_path or "",
        "output_path": output_path or "",
        # Derived path information
        "source_dir": str(Path(source_path).parent) if source_path else ".",
        "source_filename": str(Path(source_path).name) if source_path else "",
        "output_dir": str(Path(output_path).parent) if output_path else ".",
        "output_filename": str(Path(output_path).name) if output_path else "",
        # Environment
        "user": os.environ.get("USER", "unknown"),
        "hostname": os.environ.get("HOSTNAME", "unknown"),
        "pwd": str(Path.cwd()),
    }

    # Add any extra context variables
    context.update(extra)

    return context
