from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import re
import subprocess
import tarfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from urllib.parse import unquote

MANIFEST_FILENAME = "PUBLIC_EXPORT_MANIFEST.json"
CHECKSUM_FILENAME = "PUBLIC_EXPORT_SHA256SUMS.txt"

EXCLUDED_ROOT_NAMES = frozenset(
    {
        ".build-venv",
        ".git",
        ".idea",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".venv",
        "__pycache__",
        "artifacts",
        "data",
        "env",
        "exports",
        "htmlcov",
        "reports",
        "screenshots",
        "temp",
        "tmp",
        "venv",
    }
)
EXCLUDED_ROOT_PREFIXES = ("build-", "build_", "dist-", "dist_", "release-", "release_")
EXCLUDED_ROOT_EXACT = frozenset({"build", "dist", "release"})
EXCLUDED_PUBLIC_PATHS = frozenset(
    {
        ".github/workflows/deploy-template.yml",
        "docs/DEPENDENCY_AUDIT.md",
        "docs/PRE_PUBLICATION_RED_TEAM.md",
        "docs/RESET_HANDOFF.md",
        "docs/V02_MIGRATION.md",
        "packaging/windows/CHART-DARK-FINAL-CHECKLIST.md",
        "packaging/windows/HK-PRODUCT-PREVIEW-CHECKLIST.md",
        "packaging/windows/RC1-TEST-CHECKLIST.md",
        "packaging/windows/USABILITY-MOBILE-PREVIEW-CHECKLIST.md",
    }
)
EXCLUDED_SUFFIXES = (
    ".dll",
    ".err.log",
    ".exe",
    ".log",
    ".out.log",
    ".pyd",
    ".pyc",
    ".pyo",
    ".zip",
)
SENSITIVE_FILENAMES = frozenset(
    {
        ".env",
        "id_ed25519",
        "id_rsa",
        "secrets.toml",
    }
)
SENSITIVE_SUFFIXES = (".cer", ".crt", ".key", ".p12", ".pem", ".pfx")
PUBLIC_ENV_TEMPLATE = ".env.example"
SYNTHETIC_USER_NAMES = frozenset({"exampleuser", "sampleuser", "testuser", "user", "username"})
TEXT_SUFFIXES = frozenset(
    {
        ".bat",
        ".cjs",
        ".cfg",
        ".css",
        ".csv",
        ".html",
        ".ini",
        ".js",
        ".jsx",
        ".json",
        ".md",
        ".mjs",
        ".ps1",
        ".py",
        ".spec",
        ".svg",
        ".toml",
        ".txt",
        ".ts",
        ".tsx",
        ".xml",
        ".yaml",
        ".yml",
    }
)
TEXT_FILENAMES = frozenset(
    {
        ".dockerignore",
        ".env.example",
        ".gitignore",
        ".prettierignore",
        "Dockerfile",
        "LICENSE",
    }
)

MARKDOWN_LINK_RE = re.compile(r"!?\[[^\]]*]\(([^)]+)\)")
WINDOWS_USER_PATH_RE = re.compile(r"(?i)\b[A-Z]:[\\/]+Users[\\/]+(?P<user>[^\\/\s\"'<>]+)")
UNIX_HOME_PATH_RE = re.compile(r"(?i)(?:^|[\s\"'])/(?:Users|home)/(?P<user>[^/\s\"'<>]+)")
EMAIL_RE = re.compile(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b")
SECRET_PATTERNS = {
    "AWS access key": re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"),
    "GitHub token": re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9_]{20,}|github_pat_[A-Za-z0-9_]{20,})\b"),
    "JWT": re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b"),
    "OpenAI API key": re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    "private key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"),
    "quoted credential": re.compile(
        r"""(?ix)
        \b(?:api[_-]?key|access[_-]?token|refresh[_-]?token|password|passwd|secret|cookie)
        \b\s*[:=]\s*["'][^"']{8,}["']
        """
    ),
}


class PublicExportError(RuntimeError):
    pass


@dataclass(frozen=True)
class ExportEntry:
    path: str
    content: bytes
    mode: int

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.content).hexdigest()


@dataclass(frozen=True)
class PublicExportResult:
    destination: Path
    source_revision: str
    file_count: int
    total_bytes: int
    excluded_paths: tuple[str, ...]
    relative_link_count: int
    mermaid_block_count: int
    initialized_git: bool
    created_commit: bool


def _run_git(
    repo_root: Path,
    *args: str,
    input_bytes: bytes | None = None,
) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        ["git", "-C", str(repo_root), *args],
        input=input_bytes,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        shell=False,
        check=False,
    )


def _require_git_success(
    result: subprocess.CompletedProcess[bytes],
    *,
    action: str,
) -> bytes:
    if result.returncode != 0:
        detail = result.stderr.decode("utf-8", errors="replace").strip()
        raise PublicExportError(f"{action} failed: {detail or 'git returned a non-zero status'}")
    return result.stdout


def resolve_repository_root(repo_root: Path) -> Path:
    candidate = repo_root.expanduser().resolve()
    result = _run_git(candidate, "rev-parse", "--show-toplevel")
    output = _require_git_success(result, action="locating the Git repository")
    actual = Path(output.decode("utf-8", errors="strict").strip()).resolve()
    if actual != candidate:
        raise PublicExportError("the source path must be the repository root")
    return actual


def resolve_revision(repo_root: Path, revision: str) -> str:
    result = _run_git(repo_root, "rev-parse", "--verify", f"{revision}^{{commit}}")
    output = _require_git_success(result, action=f"resolving revision {revision!r}")
    value = output.decode("ascii", errors="strict").strip().lower()
    if not re.fullmatch(r"[0-9a-f]{40}", value):
        raise PublicExportError("Git returned an invalid commit identifier")
    return value


def validate_repository_path(path_text: str) -> PurePosixPath:
    if not path_text or "\\" in path_text:
        raise PublicExportError(f"unsafe repository path: {path_text!r}")
    path = PurePosixPath(path_text)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise PublicExportError(f"unsafe repository path: {path_text!r}")
    if ":" in path.parts[0]:
        raise PublicExportError(f"unsafe repository path: {path_text!r}")
    return path


def is_sensitive_source_path(path: PurePosixPath) -> bool:
    name = path.name.casefold()
    if name == PUBLIC_ENV_TEMPLATE:
        return False
    if name in SENSITIVE_FILENAMES or name.startswith(".env."):
        return True
    return name.endswith(SENSITIVE_SUFFIXES)


def should_export_path(path: PurePosixPath) -> bool:
    if path.as_posix() in EXCLUDED_PUBLIC_PATHS:
        return False
    root = path.parts[0].casefold()
    if root in EXCLUDED_ROOT_NAMES or root in EXCLUDED_ROOT_EXACT:
        return False
    if len(path.parts) > 1 and root.startswith(EXCLUDED_ROOT_PREFIXES):
        return False
    if any(part.casefold() in {"__pycache__", ".git"} for part in path.parts):
        return False
    lowered = path.as_posix().casefold()
    if lowered.endswith(EXCLUDED_SUFFIXES):
        return False
    if path.name.casefold() == "sha256sums.txt":
        return False
    return True


def _is_text_path(path: PurePosixPath) -> bool:
    return path.name in TEXT_FILENAMES or path.suffix.casefold() in TEXT_SUFFIXES


def _normalized_export_content(path: PurePosixPath, content: bytes) -> bytes:
    if not _is_text_path(path):
        return content
    return content.replace(b"\r\n", b"\n").replace(b"\r", b"\n")


def _archive_entries(repo_root: Path, revision: str) -> tuple[list[ExportEntry], tuple[str, ...]]:
    archive_result = _run_git(repo_root, "archive", "--format=tar", revision)
    archive_bytes = _require_git_success(archive_result, action="creating the Git archive")

    entries: list[ExportEntry] = []
    excluded: list[str] = []
    seen_paths: set[str] = set()
    with tarfile.open(fileobj=io.BytesIO(archive_bytes), mode="r:") as archive:
        for member in archive.getmembers():
            path = validate_repository_path(member.name.rstrip("/"))
            normalized = path.as_posix()
            if normalized in seen_paths:
                raise PublicExportError(f"duplicate archive path: {normalized}")
            seen_paths.add(normalized)
            if member.isdir():
                continue
            if member.issym() or member.islnk():
                raise PublicExportError(f"symbolic and hard links are not allowed: {normalized}")
            if not member.isfile():
                raise PublicExportError(f"unsupported archive entry type: {normalized}")
            if is_sensitive_source_path(path):
                raise PublicExportError(
                    f"tracked sensitive file must be removed first: {normalized}"
                )
            if not should_export_path(path):
                excluded.append(normalized)
                continue
            handle = archive.extractfile(member)
            if handle is None:
                raise PublicExportError(f"could not read archive entry: {normalized}")
            content = _normalized_export_content(path, handle.read())
            entries.append(ExportEntry(normalized, content, member.mode))

    entries.sort(key=lambda item: item.path)
    return entries, tuple(sorted(excluded))


def _is_text_entry(entry: ExportEntry) -> bool:
    return _is_text_path(PurePosixPath(entry.path))


def _machine_identity_markers(extra_markers: tuple[str, ...]) -> tuple[str, ...]:
    values = list(extra_markers)
    for name in ("USERNAME", "USER"):
        value = os.environ.get(name, "").strip()
        if len(value) >= 3:
            values.append(value)
    return tuple(dict.fromkeys(value.casefold() for value in values if value.strip()))


def _scan_export_entries(
    entries: list[ExportEntry],
    *,
    forbidden_texts: tuple[str, ...],
) -> None:
    identity_markers = _machine_identity_markers(forbidden_texts)
    findings: list[str] = []
    for entry in entries:
        if not _is_text_entry(entry):
            raw_text = entry.content.decode("latin-1", errors="ignore")
            if WINDOWS_USER_PATH_RE.search(raw_text) or UNIX_HOME_PATH_RE.search(raw_text):
                findings.append(f"{entry.path}: embedded local home path")
            continue
        if b"\x00" in entry.content:
            findings.append(f"{entry.path}: expected text file contains binary data")
            continue
        text = entry.content.decode("utf-8-sig", errors="replace")
        for line_number, line in enumerate(text.splitlines(), 1):
            folded = line.casefold()
            if any(marker in folded for marker in identity_markers):
                findings.append(f"{entry.path}:{line_number}: local identity marker")
            for path_pattern in (WINDOWS_USER_PATH_RE, UNIX_HOME_PATH_RE):
                for match in path_pattern.finditer(line):
                    user_name = match.group("user").casefold()
                    if user_name not in SYNTHETIC_USER_NAMES:
                        findings.append(f"{entry.path}:{line_number}: local home path")
            for email in EMAIL_RE.findall(line):
                domain = email.rsplit("@", 1)[-1].casefold()
                if not domain.endswith((".example", ".invalid", ".localhost", ".test")):
                    findings.append(f"{entry.path}:{line_number}: email address")
            for label, pattern in SECRET_PATTERNS.items():
                if pattern.search(line):
                    findings.append(f"{entry.path}:{line_number}: possible {label}")
    if findings:
        unique = "\n".join(f"- {value}" for value in sorted(set(findings)))
        raise PublicExportError(f"public-content security scan failed:\n{unique}")


def _normalize_relative_link(markdown_path: str, target: str) -> str | None:
    value = unquote(target.strip())
    if value.startswith("<") and value.endswith(">"):
        value = value[1:-1]
    if not value or value.startswith("#"):
        return None
    if re.match(r"(?i)^(?:https?|mailto|tel|data):", value):
        return None
    path_text = value.split("#", 1)[0].replace("\\", "/")
    if not path_text:
        return None
    base = PurePosixPath(markdown_path).parent
    parts: list[str] = []
    for part in (base / path_text).parts:
        if part in {"", "."}:
            continue
        if part == "..":
            if not parts:
                raise PublicExportError(
                    f"{markdown_path}: relative link escapes the repository: {target}"
                )
            parts.pop()
        else:
            parts.append(part)
    if not parts:
        return None
    return PurePosixPath(*parts).as_posix()


def _validate_links_and_mermaid(entries: list[ExportEntry]) -> tuple[int, int]:
    available = {entry.path for entry in entries}
    relative_link_count = 0
    mermaid_block_count = 0
    missing: list[str] = []
    for entry in entries:
        if PurePosixPath(entry.path).suffix.casefold() != ".md":
            continue
        text = entry.content.decode("utf-8-sig", errors="strict")
        inside_mermaid = False
        for line_number, line in enumerate(text.splitlines(), 1):
            stripped = line.strip()
            if not inside_mermaid and stripped.startswith("```mermaid"):
                inside_mermaid = True
                mermaid_block_count += 1
            elif inside_mermaid and stripped == "```":
                inside_mermaid = False
            if inside_mermaid and "\x00" in line:
                raise PublicExportError(f"{entry.path}:{line_number}: invalid NUL in Mermaid block")
        if inside_mermaid:
            raise PublicExportError(f"{entry.path}: unclosed Mermaid code block")

        for target in MARKDOWN_LINK_RE.findall(text):
            normalized = _normalize_relative_link(entry.path, target)
            if normalized is None:
                continue
            relative_link_count += 1
            if normalized not in available and not any(
                path.startswith(normalized.rstrip("/") + "/") for path in available
            ):
                missing.append(f"{entry.path} -> {target}")
    if missing:
        formatted = "\n".join(f"- {value}" for value in sorted(set(missing)))
        raise PublicExportError(f"broken relative links found:\n{formatted}")
    return relative_link_count, mermaid_block_count


def _validate_destination(repo_root: Path, destination: Path) -> Path:
    target = destination.expanduser().resolve()
    if target == repo_root or target.is_relative_to(repo_root):
        raise PublicExportError(
            "the public export destination must be outside the source repository"
        )
    if target.exists():
        if not target.is_dir():
            raise PublicExportError("the public export destination is not a directory")
        if any(target.iterdir()):
            raise PublicExportError("the public export destination must be empty")
    return target


def _write_export(
    destination: Path,
    entries: list[ExportEntry],
    *,
    revision: str,
    excluded_paths: tuple[str, ...],
    relative_link_count: int,
    mermaid_block_count: int,
) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    file_rows = [
        {
            "path": entry.path,
            "bytes": len(entry.content),
            "sha256": entry.sha256,
        }
        for entry in entries
    ]
    manifest = {
        "format_version": 1,
        "source_revision": revision,
        "file_count": len(entries),
        "total_bytes": sum(len(entry.content) for entry in entries),
        "relative_link_count": relative_link_count,
        "mermaid_block_count": mermaid_block_count,
        "excluded_paths": list(excluded_paths),
        "files": file_rows,
        "generated_files": [MANIFEST_FILENAME, CHECKSUM_FILENAME],
    }
    manifest_bytes = (
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")

    for entry in entries:
        target = destination / Path(*PurePosixPath(entry.path).parts)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(entry.content)
        if os.name != "nt":
            target.chmod(entry.mode & 0o777)

    (destination / MANIFEST_FILENAME).write_bytes(manifest_bytes)
    checksum_rows = [f"{entry.sha256} *{entry.path}" for entry in entries]
    checksum_rows.append(f"{hashlib.sha256(manifest_bytes).hexdigest()} *{MANIFEST_FILENAME}")
    checksum_text = "\n".join(sorted(checksum_rows)) + "\n"
    (destination / CHECKSUM_FILENAME).write_text(
        checksum_text,
        encoding="ascii",
        newline="\n",
    )


def _initialize_git_repository(
    destination: Path,
    *,
    create_commit: bool,
    author_name: str | None,
    author_email: str | None,
) -> bool:
    init = subprocess.run(
        ["git", "init", "--initial-branch=main"],
        cwd=destination,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        shell=False,
        check=False,
    )
    _require_git_success(init, action="initializing the public Git repository")
    if not create_commit:
        return False
    if not author_name or not author_email:
        raise PublicExportError(
            "creating a commit requires both --author-name and --author-email; "
            "QuantLab will not guess an identity"
        )
    if author_email.casefold().endswith(("@example.invalid", "@example.com", "@example.org")):
        raise PublicExportError("creating a commit requires a non-placeholder author email")
    for key, value in (("user.name", author_name), ("user.email", author_email)):
        configured = subprocess.run(
            ["git", "config", "--local", key, value],
            cwd=destination,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=False,
            check=False,
        )
        _require_git_success(configured, action=f"setting {key}")
    for command, action in (
        (["git", "add", "--all"], "staging the public repository"),
        (["git", "commit", "-m", "chore: import QuantLab v0.2.1"], "creating the import commit"),
    ):
        completed = subprocess.run(
            command,
            cwd=destination,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=False,
            check=False,
        )
        _require_git_success(completed, action=action)
    return True


def prepare_public_repository(
    repo_root: Path,
    destination: Path,
    *,
    revision: str = "HEAD",
    forbidden_texts: tuple[str, ...] = (),
    initialize_git: bool = False,
    create_commit: bool = False,
    author_name: str | None = None,
    author_email: str | None = None,
) -> PublicExportResult:
    source = resolve_repository_root(repo_root)
    target = _validate_destination(source, destination)
    resolved_revision = resolve_revision(source, revision)
    entries, excluded_paths = _archive_entries(source, resolved_revision)
    if not entries:
        raise PublicExportError("the selected revision contains no public files")
    _scan_export_entries(entries, forbidden_texts=forbidden_texts)
    relative_link_count, mermaid_block_count = _validate_links_and_mermaid(entries)
    _write_export(
        target,
        entries,
        revision=resolved_revision,
        excluded_paths=excluded_paths,
        relative_link_count=relative_link_count,
        mermaid_block_count=mermaid_block_count,
    )
    created_commit = False
    if initialize_git or create_commit:
        created_commit = _initialize_git_repository(
            target,
            create_commit=create_commit,
            author_name=author_name,
            author_email=author_email,
        )
    return PublicExportResult(
        destination=target,
        source_revision=resolved_revision,
        file_count=len(entries),
        total_bytes=sum(len(entry.content) for entry in entries),
        excluded_paths=excluded_paths,
        relative_link_count=relative_link_count,
        mermaid_block_count=mermaid_block_count,
        initialized_git=initialize_git or create_commit,
        created_commit=created_commit,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create a history-free, locally audited QuantLab public repository export."
    )
    parser.add_argument("--source", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--revision", default="HEAD")
    parser.add_argument("--forbidden-text", action="append", default=[])
    parser.add_argument("--init-git", action="store_true")
    parser.add_argument("--commit", action="store_true")
    parser.add_argument("--author-name")
    parser.add_argument("--author-email")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        result = prepare_public_repository(
            args.source,
            args.output,
            revision=args.revision,
            forbidden_texts=tuple(args.forbidden_text),
            initialize_git=args.init_git,
            create_commit=args.commit,
            author_name=args.author_name,
            author_email=args.author_email,
        )
    except PublicExportError as error:
        print(f"PUBLIC_EXPORT_FAILED: {error}")
        return 1
    print("PUBLIC_EXPORT_OK")
    print(f"SOURCE_REVISION={result.source_revision}")
    print(f"FILES={result.file_count}")
    print(f"BYTES={result.total_bytes}")
    print(f"EXCLUDED={len(result.excluded_paths)}")
    print("NEXT_STEPS:")
    print("  1. Review PUBLIC_EXPORT_MANIFEST.json and PUBLIC_EXPORT_SHA256SUMS.txt.")
    if not result.initialized_git:
        print("  2. Run: git init --initial-branch=main")
        print("  3. Configure an explicit public author, then review and commit the import.")
    elif not result.created_commit:
        print("  2. Configure an explicit public author, then review and commit the import.")
    else:
        print("  2. Review the local import commit before configuring any remote.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
