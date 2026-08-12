from __future__ import annotations

import argparse
import re
from importlib.metadata import Distribution, distributions
from pathlib import Path
from typing import Iterable

LICENSE_PREFIXES = ("license", "licence", "copying", "notice")


def _normalized_name(distribution: Distribution) -> str:
    return distribution.metadata.get("Name", "").strip()


def _is_license_file(path_text: str) -> bool:
    filename = path_text.replace("\\", "/").rsplit("/", 1)[-1].lower()
    return filename.startswith(LICENSE_PREFIXES)


def _read_license_text(path: Path) -> str | None:
    if not path.is_file():
        return None
    content = path.read_bytes()
    if b"\x00" in content:
        return None
    return content.decode("utf-8-sig", errors="replace").replace("\r\n", "\n").strip()


def _license_metadata(distribution: Distribution) -> tuple[str, ...]:
    values: list[str] = []
    for field in ("License-Expression", "License"):
        value = distribution.metadata.get(field, "").strip()
        if value and value.upper() != "UNKNOWN":
            values.append(f"{field}: {value}")
    classifiers = sorted(
        value
        for value in distribution.metadata.get_all("Classifier", [])
        if value.startswith("License ::")
    )
    values.extend(f"Classifier: {value}" for value in classifiers)
    return tuple(dict.fromkeys(values))


def _license_files(distribution: Distribution) -> tuple[tuple[str, str], ...]:
    entries: list[tuple[str, str]] = []
    for package_path in sorted(distribution.files or (), key=lambda item: str(item).lower()):
        relative_path = str(package_path).replace("\\", "/")
        if not _is_license_file(relative_path):
            continue
        text = _read_license_text(Path(distribution.locate_file(package_path)))
        if text:
            entries.append((relative_path, text))
    return tuple(entries)


def render_third_party_notices(
    installed_distributions: Iterable[Distribution],
    *,
    excluded_names: frozenset[str] = frozenset(),
) -> str:
    excluded = {name.casefold() for name in excluded_names}
    unique: dict[str, Distribution] = {}
    for distribution in installed_distributions:
        name = _normalized_name(distribution)
        if name and name.casefold() not in excluded:
            unique.setdefault(name.casefold(), distribution)

    lines = [
        "QuantLab Third-Party Notices",
        "============================",
        "",
        (
            "Generated from the locked Windows build environment. "
            "Build-only packages may be listed in addition to runtime packages."
        ),
        "",
    ]
    for key in sorted(unique):
        distribution = unique[key]
        name = _normalized_name(distribution)
        version = distribution.version
        lines.extend((f"## {name} {version}", ""))
        metadata_values = _license_metadata(distribution)
        license_files = _license_files(distribution)
        if metadata_values:
            lines.extend(metadata_values)
            lines.append("")
        if license_files:
            for relative_path, text in license_files:
                safe_path = re.sub(r"^[A-Za-z]:", "", relative_path)
                lines.extend((f"### {safe_path}", "", text, ""))
        elif not metadata_values:
            lines.extend(
                ("No license text was exposed by the installed distribution metadata.", "")
            )
    return "\n".join(lines).rstrip() + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--exclude", action="append", default=[])
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    text = render_third_party_notices(
        distributions(),
        excluded_names=frozenset(args.exclude),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(text, encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
