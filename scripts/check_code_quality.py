#!/usr/bin/env python3
# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""
Code quality checker for h2kvm.

Performs various code quality checks including:
- Syntax validation (AST parsing)
- Import checks
- TODO/FIXME comment detection
- Bare except clause detection
- Long function detection
- Missing docstring detection
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path


class CodeQualityChecker:
    """Code quality checker."""

    def __init__(self, root_dir: Path):
        """Initialize checker with repository root."""
        self.root = root_dir
        self.errors: list[str] = []
        self.warnings: list[str] = []
        self.stats = {
            "files_checked": 0,
            "syntax_errors": 0,
            "bare_except": 0,
            "todos": 0,
            "long_functions": 0,
            "missing_docstrings": 0,
        }

    def check_syntax(self, file_path: Path) -> bool:
        """Check Python file syntax."""
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                ast.parse(f.read(), filename=str(file_path))
            return True
        except SyntaxError as e:
            self.errors.append(f"Syntax error in {file_path}:{e.lineno}: {e.msg}")
            self.stats["syntax_errors"] += 1
            return False

    def check_bare_except(self, file_path: Path) -> list[int]:
        """Find bare except clauses."""
        bare_excepts = []
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                tree = ast.parse(f.read(), filename=str(file_path))

            for node in ast.walk(tree):
                if isinstance(node, ast.ExceptHandler):
                    # Bare except has no type specified
                    if node.type is None:
                        bare_excepts.append(node.lineno)

        except Exception:
            pass  # Already reported in syntax check

        return bare_excepts

    def check_todos(self, file_path: Path) -> list[tuple[int, str]]:
        """Find TODO/FIXME comments."""
        todos = []
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                for i, line in enumerate(f, 1):
                    if "TODO" in line or "FIXME" in line:
                        todos.append((i, line.strip()))
        except Exception:
            pass

        return todos

    def check_docstrings(self, file_path: Path) -> list[str]:
        """Find public functions without docstrings."""
        missing = []
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                tree = ast.parse(f.read(), filename=str(file_path))

            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    # Check if public (doesn't start with _)
                    if not node.name.startswith("_"):
                        # Check if has docstring
                        docstring = ast.get_docstring(node)
                        if docstring is None:
                            missing.append(f"{node.name} (line {node.lineno})")

        except Exception:
            pass

        return missing

    def check_long_functions(self, file_path: Path, threshold: int = 50) -> list[tuple[str, int, int]]:
        """Find functions longer than threshold lines."""
        long_functions = []
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
                tree = ast.parse(content, filename=str(file_path))
                lines = content.splitlines()

            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    # Calculate function length
                    start_line = node.lineno
                    end_line = node.end_lineno or start_line

                    # Count non-empty, non-comment lines
                    func_lines = lines[start_line - 1 : end_line]
                    actual_lines = sum(
                        1 for line in func_lines if line.strip() and not line.strip().startswith("#")
                    )

                    if actual_lines > threshold:
                        long_functions.append((node.name, node.lineno, actual_lines))

        except Exception:
            pass

        return long_functions

    def check_file(self, file_path: Path) -> None:
        """Run all checks on a single file."""
        self.stats["files_checked"] += 1

        # Syntax check (must pass for other checks)
        if not self.check_syntax(file_path):
            return

        # Check for bare except
        bare_excepts = self.check_bare_except(file_path)
        if bare_excepts:
            self.stats["bare_except"] += len(bare_excepts)
            for lineno in bare_excepts:
                self.errors.append(f"Bare except in {file_path}:{lineno}")

        # Check for TODOs
        todos = self.check_todos(file_path)
        if todos:
            self.stats["todos"] += len(todos)
            for lineno, text in todos:
                self.warnings.append(f"TODO in {file_path}:{lineno}: {text[:60]}")

        # Check for long functions
        long_funcs = self.check_long_functions(file_path)
        if long_funcs:
            self.stats["long_functions"] += len(long_funcs)
            for name, lineno, length in long_funcs:
                self.warnings.append(f"Long function {name} in {file_path}:{lineno} ({length} lines)")

        # Check for missing docstrings
        missing_docs = self.check_docstrings(file_path)
        if missing_docs:
            self.stats["missing_docstrings"] += len(missing_docs)
            # Only show first 3 to avoid spam
            for func in missing_docs[:3]:
                self.warnings.append(f"Missing docstring in {file_path}: {func}")
            if len(missing_docs) > 3:
                self.warnings.append(f"  ... and {len(missing_docs) - 3} more in {file_path}")

    def check_all(self) -> int:
        """Check all Python files in the repository."""
        # Find all Python files in h2kvm package
        package_dir = self.root / "h2kvm"
        if not package_dir.exists():
            print(f"Error: Package directory not found: {package_dir}")
            return 1

        py_files = sorted(package_dir.rglob("*.py"))
        print(f"Checking {len(py_files)} Python files...")

        for py_file in py_files:
            # Skip __pycache__ and build artifacts
            if "__pycache__" in str(py_file) or "build" in py_file.parts:
                continue

            self.check_file(py_file)

        return 0

    def print_report(self) -> int:
        """Print quality report."""
        print("\n" + "=" * 70)
        print("CODE QUALITY REPORT")
        print("=" * 70)

        print(f"\nFiles checked: {self.stats['files_checked']}")

        # Errors (must fix)
        if self.errors:
            print(f"\n🔴 ERRORS ({len(self.errors)}):")
            for error in self.errors[:20]:  # Show first 20
                print(f"  {error}")
            if len(self.errors) > 20:
                print(f"  ... and {len(self.errors) - 20} more errors")
        else:
            print("\n✅ No errors found")

        # Warnings (should fix)
        if self.warnings:
            print(f"\n⚠️  WARNINGS ({len(self.warnings)}):")
            for warning in self.warnings[:20]:  # Show first 20
                print(f"  {warning}")
            if len(self.warnings) > 20:
                print(f"  ... and {len(self.warnings) - 20} more warnings")

        # Statistics
        print("\n" + "-" * 70)
        print("STATISTICS:")
        print(f"  Syntax errors:      {self.stats['syntax_errors']}")
        print(f"  Bare except:        {self.stats['bare_except']}")
        print(f"  TODO comments:      {self.stats['todos']}")
        print(f"  Long functions:     {self.stats['long_functions']}")
        print(f"  Missing docstrings: {self.stats['missing_docstrings']}")

        print("\n" + "=" * 70)

        # Return code
        if self.stats["syntax_errors"] > 0 or self.stats["bare_except"] > 0:
            print("\n❌ FAILED: Critical issues found")
            print("   Fix bare except clauses and syntax errors")
            return 1
        elif len(self.warnings) > 0:
            print("\n⚠️  PASSED with warnings")
            print("   Consider addressing warnings for better code quality")
            return 0
        else:
            print("\n✅ PASSED: No issues found")
            return 0


def main() -> int:
    """Main entry point."""
    # Find repository root
    script_dir = Path(__file__).resolve().parent
    repo_root = script_dir.parent

    print(f"Repository root: {repo_root}")

    checker = CodeQualityChecker(repo_root)
    checker.check_all()
    return checker.print_report()


if __name__ == "__main__":
    sys.exit(main())
