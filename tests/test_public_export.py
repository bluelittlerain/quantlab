from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from prepare_public_repository import (  # noqa: E402
    CHECKSUM_FILENAME,
    EXCLUDED_PUBLIC_PATHS,
    MANIFEST_FILENAME,
    PublicExportError,
    prepare_public_repository,
    validate_repository_path,
)


def run_git(repo: Path, *args: str, input_bytes: bytes | None = None) -> str:
    completed = subprocess.run(
        ["git", "-C", str(repo), *args],
        input=input_bytes,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        shell=False,
        check=False,
    )
    if completed.returncode != 0:
        raise AssertionError(completed.stderr.decode("utf-8", errors="replace"))
    return completed.stdout.decode("utf-8", errors="replace").strip()


def create_repository(root: Path, files: dict[str, bytes | str]) -> Path:
    repo = root / "source"
    repo.mkdir()
    run_git(repo, "init", "--initial-branch=main")
    run_git(repo, "config", "core.autocrlf", "false")
    run_git(repo, "config", "user.name", "Public Export Test")
    run_git(repo, "config", "user.email", "public-export-test@example.invalid")
    for path_text, content in files.items():
        path = repo / Path(*path_text.split("/"))
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, bytes):
            path.write_bytes(content)
        else:
            path.write_text(content, encoding="utf-8", newline="\n")
    run_git(repo, "add", "--all", "--force")
    run_git(repo, "commit", "-m", "test fixture")
    return repo


def exported_file_hashes(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file() and ".git" not in path.relative_to(root).parts
    }


class PublicRepositoryExportTests(unittest.TestCase):
    def test_internal_publication_artifacts_are_excluded_by_exact_path(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            files: dict[str, str] = {
                "README.md": "# Fixture\n",
                "src/main.py": "VALUE = 1\n",
            }
            files.update({path: "internal\n" for path in EXCLUDED_PUBLIC_PATHS})
            repo = create_repository(root, files)
            destination = root / "public"

            result = prepare_public_repository(repo, destination)

            self.assertTrue((destination / "src" / "main.py").is_file())
            for path in EXCLUDED_PUBLIC_PATHS:
                self.assertFalse((destination / Path(*path.split("/"))).exists(), path)
            self.assertTrue(EXCLUDED_PUBLIC_PATHS.issubset(set(result.excluded_paths)))

    def test_export_contains_tracked_files_manifest_and_checksums(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = create_repository(
                root,
                {
                    ".gitignore": "build/\n.env\n",
                    "README.md": "[Architecture](docs/ARCHITECTURE.md)\n",
                    "RELEASE-NOTES-v0.2.1.md": "# Release notes\n",
                    "docs/ARCHITECTURE.md": "```mermaid\nflowchart LR\nA --> B\n```\n",
                    "src/main.py": "VALUE = 1\n",
                    "build/generated.txt": "excluded\n",
                    "release/package.zip": b"excluded",
                    "release-preview/generated.txt": "excluded\n",
                },
            )
            destination = root / "public"

            result = prepare_public_repository(repo, destination)

            self.assertFalse((destination / ".git").exists())
            self.assertTrue((destination / ".gitignore").is_file())
            self.assertTrue((destination / "RELEASE-NOTES-v0.2.1.md").is_file())
            self.assertTrue((destination / "src" / "main.py").is_file())
            self.assertFalse((destination / "build").exists())
            self.assertFalse((destination / "release").exists())
            self.assertFalse((destination / "release-preview").exists())
            self.assertEqual(
                set(result.excluded_paths),
                {
                    "build/generated.txt",
                    "release/package.zip",
                    "release-preview/generated.txt",
                },
            )
            manifest = json.loads((destination / MANIFEST_FILENAME).read_text("utf-8"))
            self.assertEqual(manifest["source_revision"], result.source_revision)
            self.assertEqual(manifest["file_count"], 5)
            self.assertEqual(manifest["relative_link_count"], 1)
            self.assertEqual(manifest["mermaid_block_count"], 1)
            checksums = (destination / CHECKSUM_FILENAME).read_text("ascii")
            self.assertIn("*README.md", checksums)
            self.assertIn(f"*{MANIFEST_FILENAME}", checksums)

    def test_two_exports_of_same_revision_are_byte_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = create_repository(
                root,
                {
                    ".gitignore": ".venv/\n",
                    "README.md": "# Fixture\n",
                    "src/main.py": "VALUE = 1\n",
                },
            )
            first = root / "first"
            second = root / "second"

            prepare_public_repository(repo, first)
            prepare_public_repository(repo, second)

            self.assertEqual(exported_file_hashes(first), exported_file_hashes(second))

    def test_text_files_are_normalized_to_lf(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = create_repository(
                root,
                {
                    "README.md": b"# Fixture\r\n\r\nText\r\n",
                    ".env.example": b"PROVIDER_API_KEY=\r\n",
                    "src/App.tsx": b"export const value = 1;\r\n",
                    "image.png": b"\x89PNG\r\n\x1a\nbinary\r\n",
                },
            )
            destination = root / "public"

            prepare_public_repository(repo, destination)

            self.assertEqual(
                (destination / "README.md").read_bytes(),
                b"# Fixture\n\nText\n",
            )
            self.assertEqual(
                (destination / "src" / "App.tsx").read_bytes(),
                b"export const value = 1;\n",
            )
            self.assertEqual(
                (destination / ".env.example").read_bytes(),
                b"PROVIDER_API_KEY=\n",
            )
            self.assertEqual(
                (destination / "image.png").read_bytes(),
                b"\x89PNG\r\n\x1a\nbinary\r\n",
            )

    def test_tracked_sensitive_filename_is_rejected_before_writing(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = create_repository(
                root,
                {
                    "README.md": "# Fixture\n",
                    ".env": "TOKEN=not-a-real-secret\n",
                },
            )
            destination = root / "public"

            with self.assertRaisesRegex(PublicExportError, "tracked sensitive file"):
                prepare_public_repository(repo, destination)

            self.assertFalse(destination.exists())

    def test_local_home_path_and_explicit_identity_marker_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            private_path = "".join(
                ("C:", "\\", "Users", "\\", "PersonalMachineOwner", "\\", "output.csv")
            )
            repo = create_repository(
                root,
                {
                    "README.md": (f"# Fixture\n{private_path}\nConfidentialMarker\n"),
                },
            )

            with self.assertRaisesRegex(PublicExportError, "security scan failed"):
                prepare_public_repository(
                    repo,
                    root / "public",
                    forbidden_texts=("ConfidentialMarker",),
                )

    def test_synthetic_windows_path_fixture_is_allowed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = create_repository(
                root,
                {
                    "README.md": "# Fixture\n",
                    "tests/test_paths.py": ('ERROR = r"C:\\Users\\ExampleUser\\response.json"\n'),
                },
            )

            result = prepare_public_repository(repo, root / "public")

            self.assertEqual(result.file_count, 2)

    def test_broken_relative_link_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = create_repository(
                root,
                {"README.md": "[Missing](docs/MISSING.md)\n"},
            )

            with self.assertRaisesRegex(PublicExportError, "broken relative links"):
                prepare_public_repository(repo, root / "public")

    def test_unclosed_mermaid_block_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = create_repository(
                root,
                {"README.md": "```mermaid\nflowchart LR\nA --> B\n"},
            )

            with self.assertRaisesRegex(PublicExportError, "unclosed Mermaid"):
                prepare_public_repository(repo, root / "public")

    def test_repository_path_traversal_and_windows_separator_are_rejected(self) -> None:
        for value in ("../escape.txt", "/absolute.txt", "folder\\escape.txt"):
            with self.subTest(value=value):
                with self.assertRaisesRegex(PublicExportError, "unsafe repository path"):
                    validate_repository_path(value)

    def test_symbolic_link_archive_entry_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = create_repository(root, {"README.md": "# Fixture\n"})
            blob = run_git(repo, "hash-object", "-w", "--stdin", input_bytes=b"README.md")
            run_git(repo, "update-index", "--add", "--cacheinfo", f"120000,{blob},latest")
            run_git(repo, "commit", "-m", "add symlink entry")

            with self.assertRaisesRegex(PublicExportError, "links are not allowed"):
                prepare_public_repository(repo, root / "public")

    def test_nonempty_destination_is_rejected_without_deleting_content(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = create_repository(root, {"README.md": "# Fixture\n"})
            destination = root / "public"
            destination.mkdir()
            sentinel = destination / "keep.txt"
            sentinel.write_text("keep", encoding="utf-8")

            with self.assertRaisesRegex(PublicExportError, "must be empty"):
                prepare_public_repository(repo, destination)

            self.assertEqual(sentinel.read_text("utf-8"), "keep")

    def test_destination_inside_source_repository_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = create_repository(root, {"README.md": "# Fixture\n"})

            with self.assertRaisesRegex(PublicExportError, "outside"):
                prepare_public_repository(repo, repo / "public-export")

    def test_git_initialization_does_not_commit_without_explicit_identity(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = create_repository(root, {"README.md": "# Fixture\n"})
            destination = root / "public"

            result = prepare_public_repository(repo, destination, initialize_git=True)

            self.assertTrue(result.initialized_git)
            self.assertFalse(result.created_commit)
            self.assertTrue((destination / ".git").is_dir())
            log = subprocess.run(
                ["git", "-C", str(destination), "log", "-1"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                shell=False,
                check=False,
            )
            self.assertNotEqual(log.returncode, 0)

    def test_commit_mode_requires_non_placeholder_author_information(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = create_repository(root, {"README.md": "# Fixture\n"})

            with self.assertRaisesRegex(PublicExportError, "requires both"):
                prepare_public_repository(repo, root / "missing", create_commit=True)
            with self.assertRaisesRegex(PublicExportError, "non-placeholder"):
                prepare_public_repository(
                    repo,
                    root / "placeholder",
                    create_commit=True,
                    author_name="Fixture",
                    author_email="fixture@example.invalid",
                )

    def test_commit_mode_creates_one_local_import_commit(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = create_repository(root, {"README.md": "# Fixture\n"})
            destination = root / "public"

            result = prepare_public_repository(
                repo,
                destination,
                create_commit=True,
                author_name="Audit Fixture",
                author_email="audit-fixture@invalid.test",
            )

            self.assertTrue(result.created_commit)
            self.assertEqual(run_git(destination, "rev-list", "--count", "HEAD"), "1")
            self.assertEqual(run_git(destination, "branch", "--show-current"), "main")


if __name__ == "__main__":
    unittest.main()
