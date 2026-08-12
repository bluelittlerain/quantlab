from __future__ import annotations

import argparse
import json
from collections import deque
from pathlib import Path
from typing import Any

LICENSE_PREFIXES = ("license", "licence", "copying", "notice")


def _read_package(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _dependency_path(package_root: Path, frontend_root: Path, name: str) -> Path:
    candidates = [package_root / "node_modules" / name]
    candidates.extend(
        ancestor / name
        for ancestor in (package_root, *package_root.parents)
        if ancestor.name == "node_modules"
    )
    candidates.append(frontend_root / "node_modules" / name)
    for candidate in candidates:
        if (candidate / "package.json").is_file():
            return candidate.resolve()
    raise RuntimeError(f"Installed frontend dependency is missing: {name}")


def _license_texts(package_root: Path) -> tuple[tuple[str, str], ...]:
    entries: list[tuple[str, str]] = []
    for path in sorted(package_root.iterdir(), key=lambda item: item.name.casefold()):
        if not path.is_file() or not path.name.casefold().startswith(LICENSE_PREFIXES):
            continue
        content = path.read_bytes()
        if b"\x00" in content:
            continue
        text = content.decode("utf-8-sig", errors="replace").replace("\r\n", "\n").strip()
        if text:
            entries.append((path.name, text))
    return tuple(entries)


def render_frontend_notices(frontend_root: Path) -> str:
    root_package = _read_package(frontend_root / "package.json")
    queue: deque[Path] = deque(
        _dependency_path(frontend_root / "node_modules", frontend_root, name)
        for name in sorted(root_package.get("dependencies", {}))
    )
    packages: dict[tuple[str, str], tuple[dict[str, Any], Path]] = {}
    visited: set[Path] = set()
    while queue:
        package_root = queue.popleft().resolve()
        if package_root in visited:
            continue
        visited.add(package_root)
        package = _read_package(package_root / "package.json")
        name = str(package.get("name", "")).strip()
        version = str(package.get("version", "")).strip()
        if not name or not version:
            raise RuntimeError("A frontend package is missing name or version metadata.")
        packages[(name, version)] = (package, package_root)
        dependencies = {
            **package.get("dependencies", {}),
            **package.get("optionalDependencies", {}),
        }
        for dependency in sorted(dependencies):
            try:
                queue.append(_dependency_path(package_root, frontend_root, dependency))
            except RuntimeError:
                if dependency not in package.get("optionalDependencies", {}):
                    raise

    lines = [
        "QuantLab Frontend Third-Party Notices",
        "======================================",
        "",
        "Generated from production dependencies reachable from frontend/package.json.",
        "",
    ]
    for name, version in sorted(packages, key=lambda item: (item[0].casefold(), item[1])):
        package, package_root = packages[(name, version)]
        lines.extend((f"## {name} {version}", ""))
        license_value = package.get("license") or package.get("licenses") or "Not specified"
        lines.extend((f"License metadata: {license_value}", ""))
        for filename, text in _license_texts(package_root):
            lines.extend((f"### {filename}", "", text, ""))
    return "\n".join(lines).rstrip() + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--frontend", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output = render_frontend_notices(args.frontend.resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(output, encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
