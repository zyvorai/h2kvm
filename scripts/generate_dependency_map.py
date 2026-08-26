#!/usr/bin/env python3
# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""Generate static dependency maps for hyper2kvm modules.

This script parses Python imports using ``ast`` and emits:
- JSON dependency graph (module-level + package-level)
- Markdown summary table

Only imports that resolve to ``hyper2kvm.*`` are tracked.
"""

from __future__ import annotations

import argparse
import ast
import json
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ROOT = ROOT / "hyper2kvm"
DEFAULT_JSON_OUT = ROOT / "docs" / "meta" / "dependency-map.json"
DEFAULT_MD_OUT = ROOT / "docs" / "meta" / "dependency-map.md"


def module_name_from_path(path: Path) -> str:
    rel = path.relative_to(ROOT).with_suffix("")
    parts = list(rel.parts)
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def resolve_relative_import(module: str, from_module: str, level: int) -> str:
    """Resolve a relative import target to an absolute module path."""
    parts = from_module.split(".")
    if level > 0:
        parts = parts[:-level]
    if module:
        parts.extend(module.split("."))
    return ".".join([p for p in parts if p])


def iter_python_files(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob("*.py") if "__pycache__" not in p.parts)


def collect_edges() -> set[tuple[str, str]]:
    edges: set[tuple[str, str]] = set()

    for path in iter_python_files(PACKAGE_ROOT):
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
        src_mod = module_name_from_path(path)

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    name = alias.name
                    if name.startswith("hyper2kvm"):
                        edges.add((src_mod, name))
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                if node.level:
                    target_mod = resolve_relative_import(module, src_mod, node.level)
                else:
                    target_mod = module

                if target_mod.startswith("hyper2kvm"):
                    edges.add((src_mod, target_mod))

    return edges


def top_package(module: str) -> str:
    parts = module.split(".")
    if len(parts) < 2:
        return "<root>"
    return parts[1]


def build_graph() -> dict:
    edges = sorted(collect_edges())
    modules = sorted({src for src, _ in edges} | {dst for _, dst in edges})

    package_edges_counter: Counter[tuple[str, str]] = Counter()
    out_degree: Counter[str] = Counter()
    in_degree: Counter[str] = Counter()

    for src, dst in edges:
        src_pkg = top_package(src)
        dst_pkg = top_package(dst)
        package_edges_counter[(src_pkg, dst_pkg)] += 1
        out_degree[src_pkg] += 1
        in_degree[dst_pkg] += 1

    package_edges = [
        {"from": s, "to": d, "count": c}
        for (s, d), c in sorted(package_edges_counter.items(), key=lambda x: (-x[1], x[0][0], x[0][1]))
    ]

    package_stats = sorted(
        {
            pkg: {
                "imports_out": out_degree[pkg],
                "imports_in": in_degree[pkg],
            }
            for pkg in set(out_degree) | set(in_degree)
        }.items()
    )

    return {
        "module_count": len(modules),
        "edge_count": len(edges),
        "modules": modules,
        "module_edges": [{"from": s, "to": d} for s, d in edges],
        "package_edges": package_edges,
        "package_stats": [{"package": pkg, **stats} for pkg, stats in package_stats],
    }


def to_markdown(graph: dict) -> str:
    lines: list[str] = []
    lines.append("# Dependency Map")
    lines.append("")
    lines.append(
        f"Generated from static imports in `hyper2kvm/` (modules: {graph['module_count']}, edges: {graph['edge_count']})."
    )
    lines.append("")

    lines.append("## Top Package Edges")
    lines.append("")
    lines.append("| From | To | Import Edges |")
    lines.append("|---|---:|---:|")
    for edge in graph["package_edges"][:100]:
        lines.append(f"| `{edge['from']}` | `{edge['to']}` | {edge['count']} |")
    lines.append("")

    lines.append("## Package Stats")
    lines.append("")
    lines.append("| Package | Outgoing Imports | Incoming Imports |")
    lines.append("|---|---:|---:|")
    for stat in graph["package_stats"]:
        lines.append(f"| `{stat['package']}` | {stat['imports_out']} | {stat['imports_in']} |")

    lines.append("")
    lines.append("_Only top 100 package edges shown in Markdown. Full graph is in JSON._")
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json-out", type=Path, default=DEFAULT_JSON_OUT)
    parser.add_argument("--md-out", type=Path, default=DEFAULT_MD_OUT)
    args = parser.parse_args()

    graph = build_graph()

    args.json_out.parent.mkdir(parents=True, exist_ok=True)
    args.md_out.parent.mkdir(parents=True, exist_ok=True)

    args.json_out.write_text(json.dumps(graph, indent=2) + "\n", encoding="utf-8")
    args.md_out.write_text(to_markdown(graph), encoding="utf-8")

    print(f"Wrote {args.json_out}")
    print(f"Wrote {args.md_out}")
    print(f"Modules: {graph['module_count']} | Edges: {graph['edge_count']}")


if __name__ == "__main__":
    main()
