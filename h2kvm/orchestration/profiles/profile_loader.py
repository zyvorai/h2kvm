# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""Migration profile loader with inheritance and merging support."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from h2kvm.config.config_loader import Config
from h2kvm.core.exceptions import ProfileError

from .profile_cache import ProfileCache, get_global_cache

try:
    import yaml  # type: ignore

    YAML_AVAILABLE = True
except ImportError:
    YAML_AVAILABLE = False


class ProfileLoader:
    """
    Loads and merges migration profiles with inheritance support.

    Profiles provide reusable configuration templates for common migration scenarios:
    - production: Full fixes, compression, validation
    - testing: Minimal fixes, fast conversion
    - minimal: Bare minimum processing

    Profiles support inheritance via 'extends' field.
    """

    def __init__(
        self,
        logger: logging.Logger | None = None,
        enable_cache: bool = True,
        cache: ProfileCache | None = None,
    ):
        """
        Initialize ProfileLoader.

        Args:
            logger: Logger instance
            enable_cache: Enable profile caching (default: True)
            cache: Custom cache instance (default: use global cache)
        """
        self.logger = logger or logging.getLogger(__name__)
        self.enable_cache = enable_cache

        # If cache is explicitly provided, use it
        # If enable_cache is False, create a disabled cache instance
        # Otherwise, use global cache
        if cache is not None:
            self.cache = cache
        elif not enable_cache:
            self.cache = ProfileCache(enabled=False, logger=self.logger)
        else:
            self.cache = get_global_cache(enabled=True)

        self._builtin_profiles_cache: dict[str, dict[str, Any]] | None = None

    def load_profile(self, profile_name: str, custom_profile_path: Path | None = None) -> dict[str, Any]:
        """
        Load a profile by name, checking custom path first, then built-ins.

        Args:
            profile_name: Profile name (e.g., "production", "testing")
            custom_profile_path: Optional path to custom profiles directory

        Returns:
            Resolved profile configuration with inheritance applied

        Raises:
            ProfileError: If profile not found or invalid
        """
        self.logger.debug(f"Loading profile: {profile_name}")

        # Generate cache key (includes custom path for differentiation)
        cache_key = profile_name
        if custom_profile_path:
            cache_key = f"{custom_profile_path}:{profile_name}"

        # Check cache first
        cached_profile = self.cache.get(cache_key)
        if cached_profile is not None:
            return cached_profile.copy()

        # Try custom profile path first
        if custom_profile_path:
            profile_path = Path(custom_profile_path) / f"{profile_name}.yaml"
            if profile_path.exists():
                self.logger.debug("Loading custom profile: %s", profile_path)
                profile_data = self._load_and_resolve(profile_path, custom_dir=Path(custom_profile_path))
                # Cache custom profile with source path
                self.cache.put(cache_key, profile_data, source_path=profile_path)
                return profile_data

        # Try built-in profiles
        builtin_profiles = self._load_builtin_profiles()
        if profile_name in builtin_profiles:
            self.logger.debug("Loading built-in profile: %s", profile_name)
            profile_data = builtin_profiles[profile_name].copy()
            resolved_profile = self._resolve_inheritance(profile_data, builtin_profiles)
            # Cache built-in profile (no source path = never expires)
            self.cache.put(cache_key, resolved_profile, source_path=None)
            return resolved_profile

        raise ProfileError(
            msg=f"Profile '{profile_name}' not found. "
            f"Available built-in profiles: {list(builtin_profiles.keys())}"
        )

    def _load_builtin_profiles(self) -> dict[str, dict[str, Any]]:
        """Load built-in profiles from YAML file."""
        if self._builtin_profiles_cache is not None:
            return self._builtin_profiles_cache

        # Find builtin_profiles.yaml in the same directory as this module
        builtin_path = Path(__file__).parent / "builtin_profiles.yaml"

        if not builtin_path.exists():
            self.logger.warning("Built-in profiles file not found: %s", builtin_path)
            self._builtin_profiles_cache = {}
            return self._builtin_profiles_cache

        try:
            if not YAML_AVAILABLE:
                raise ProfileError(msg="PyYAML not installed. Install with: pip install PyYAML")

            with open(builtin_path, encoding="utf-8") as f:
                profiles_data = yaml.safe_load(f) or {}

            if not isinstance(profiles_data, dict):
                raise ProfileError(msg=f"Built-in profiles file must contain a dictionary: {builtin_path}")

            self._builtin_profiles_cache = profiles_data
            self.logger.debug(
                "Loaded %d built-in profiles: %s", len(profiles_data), list(profiles_data.keys())
            )

            return self._builtin_profiles_cache

        except Exception as e:
            raise ProfileError(msg=f"Failed to load built-in profiles: {e}", cause=e) from e

    def _load_and_resolve(self, profile_path: Path, custom_dir: Path | None = None) -> dict[str, Any]:
        """Load a profile from file and resolve inheritance.

        Args:
            profile_path: Path to the profile file
            custom_dir: Optional directory containing custom profiles for inheritance resolution
        """
        try:
            if not YAML_AVAILABLE:
                raise ProfileError(msg="PyYAML not installed. Install with: pip install PyYAML")

            with open(profile_path, encoding="utf-8") as f:
                if profile_path.suffix.lower() == ".json":
                    profile_data = json.load(f)
                else:
                    profile_data = yaml.safe_load(f) or {}

            if not isinstance(profile_data, dict):
                raise ProfileError(msg=f"Profile must be a dictionary: {profile_path}")

            # Resolve inheritance
            builtin_profiles = self._load_builtin_profiles()
            return self._resolve_inheritance(profile_data, builtin_profiles, custom_dir=custom_dir)

        except Exception as e:
            raise ProfileError(msg=f"Failed to load profile from {profile_path}: {e}") from e

    def _resolve_inheritance(
        self,
        profile_data: dict[str, Any],
        available_profiles: dict[str, dict[str, Any]],
        _visited: set[str] | None = None,
        custom_dir: Path | None = None,
    ) -> dict[str, Any]:
        """
        Resolve profile inheritance using 'extends' field.

        Args:
            profile_data: Profile configuration
            available_profiles: Dictionary of available profiles
            _visited: Set of visited profile names (for cycle detection)
            custom_dir: Optional directory to search for custom parent profiles

        Returns:
            Resolved profile with parent configurations merged

        Raises:
            ProfileError: If circular inheritance detected
        """
        if _visited is None:
            _visited = set()

        # Check for 'extends' field
        parent_name = profile_data.get("extends")
        if not parent_name:
            # No inheritance, return as-is
            return profile_data

        # Detect circular inheritance
        if parent_name in _visited:
            raise ProfileError(msg=f"Circular inheritance detected: {parent_name} already visited")

        # Load parent profile - check custom dir first if provided
        parent_data = None
        if custom_dir:
            parent_path = custom_dir / f"{parent_name}.yaml"
            if parent_path.exists():
                # Load custom parent profile
                try:
                    if not YAML_AVAILABLE:
                        raise ProfileError(msg="PyYAML not installed")
                    with open(parent_path, encoding="utf-8") as f:
                        parent_data = yaml.safe_load(f) or {}
                except Exception as e:
                    raise ProfileError(
                        msg=f"Failed to load parent profile '{parent_name}' from {parent_path}: {e}"
                    ) from e

        # If not found in custom dir, check available_profiles (built-ins)
        if parent_data is None:
            if parent_name not in available_profiles:
                raise ProfileError(msg=f"Parent profile '{parent_name}' not found (extended by profile)")
            parent_data = available_profiles[parent_name].copy()

        # Recursively resolve parent's inheritance
        _visited.add(parent_name)
        resolved_parent = self._resolve_inheritance(
            parent_data, available_profiles, _visited, custom_dir=custom_dir
        )
        _visited.remove(parent_name)

        # Merge: child overrides parent
        merged = self._merge_profiles(resolved_parent, profile_data)

        # Remove 'extends' from final result
        merged.pop("extends", None)

        return merged

    def _merge_profiles(self, base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
        """
        Deep merge two profile configurations.

        Args:
            base: Base profile configuration
            override: Override profile configuration

        Returns:
            Merged configuration with override taking precedence
        """
        # Use Config.merge_dicts from existing codebase
        return Config.merge_dicts(base, override)

    def apply_overrides(self, profile: dict[str, Any], overrides: dict[str, Any]) -> dict[str, Any]:
        """
        Apply user-specified overrides to a profile.

        Args:
            profile: Base profile configuration
            overrides: User override configuration

        Returns:
            Profile with overrides applied
        """
        if not overrides:
            return profile

        self.logger.debug(f"Applying overrides: {list(overrides.keys())} keys")

        return self._merge_profiles(profile, overrides)

    def list_builtin_profiles(self, custom_path: Path | None = None) -> list[str]:
        """
        Get list of available profile names.

        Args:
            custom_path: Optional path to custom profiles directory

        Returns:
            Sorted list of profile names (built-in + custom if path provided)
        """
        # Start with built-in profiles
        builtin_profiles = self._load_builtin_profiles()
        profile_names = set(builtin_profiles.keys())

        # Add custom profiles if path provided
        if custom_path:
            custom_dir = Path(custom_path)
            if custom_dir.exists() and custom_dir.is_dir():
                for file_path in custom_dir.glob("*.yaml"):
                    profile_names.add(file_path.stem)

        return sorted(profile_names)

    def get_cache_statistics(self) -> dict[str, Any]:
        """
        Get profile cache statistics.

        Returns:
            Dictionary with cache statistics
        """
        return self.cache.get_statistics()

    def log_cache_statistics(self) -> None:
        """Log profile cache statistics."""
        self.cache.log_statistics()

    def get_profile_info(self, profile_name: str) -> dict[str, Any]:
        """
        Get profile metadata and configuration.

        Args:
            profile_name: Profile name

        Returns:
            Dictionary with profile info (description, configuration)
        """
        profile = self.load_profile(profile_name)

        return {
            "name": profile_name,
            "description": profile.get("description", "No description"),
            "extends": profile.get("extends"),
            "configuration": profile,
        }
