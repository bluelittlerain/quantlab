from __future__ import annotations

import copy
import hashlib
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import release_guard as guard  # noqa: E402

SHA = "a" * 40
TAG_OBJECT = "b" * 40
TAG = "v0.2.1"
REPO = "example/quantlab"
ZIP = f"QuantLab-{TAG}-windows-x64.zip"
EXPECTED = {
    "schema": 1,
    "repository": REPO,
    "repository_id": 12,
    "run_id": 123,
    "run_attempt": 2,
    "tag": TAG,
    "tag_object": TAG_OBJECT,
    "source_sha": SHA,
    "artifact_id": 456,
}


class FakeGitHub:
    repository = REPO

    def __init__(self) -> None:
        self.ref = {"object": {"type": "tag", "sha": TAG_OBJECT}}
        self.tag = {"object": {"type": "commit", "sha": SHA}}
        self.release = None
        self.run = {
            "repository": {"full_name": REPO, "id": 12},
            "path": ".github/workflows/release.yml",
            "event": "push",
            "head_sha": SHA,
            "status": "completed",
            "conclusion": "success",
            "run_attempt": 2,
        }
        self.artifacts = {
            "total_count": 1,
            "artifacts": [{"id": 456, "name": f"windows-release-{SHA}-2", "expired": False}],
        }

    def get(self, path: str, *, missing_ok: bool = False):
        if path == f"git/ref/tags/{TAG}":
            return self.ref
        if path == f"git/tags/{TAG_OBJECT}":
            return self.tag
        if path == f"releases/tags/{TAG}" and missing_ok:
            return self.release
        if path == "actions/runs/123":
            return self.run
        if path == f"actions/runs/123/artifacts?name=windows-release-{SHA}-2&per_page=100":
            return self.artifacts
        raise AssertionError(f"Unexpected API request: {path}")


class ReleaseGuardTests(unittest.TestCase):
    def setUp(self) -> None:
        self.api = FakeGitHub()
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        (self.directory / ZIP).write_bytes(b"fixed archive fixture")
        digest = hashlib.sha256(b"fixed archive fixture").hexdigest()
        (self.directory / "SHA256SUMS.txt").write_text(f"{digest} *{ZIP}", encoding="ascii")
        (self.directory / f"RELEASE-NOTES-{TAG}.md").write_text("# Release\n", encoding="utf-8")
        self.evidence = {key: value for key, value in EXPECTED.items() if key != "artifact_id"}
        self.evidence["assets"] = guard.candidate_hashes(self.directory, TAG)
        self.write_evidence()

    def write_evidence(self) -> None:
        (self.directory / guard.EVIDENCE).write_text(json.dumps(self.evidence), encoding="utf-8")

    def inspect(self):
        return guard.inspect_candidate(self.api, TAG, SHA, 123)

    def test_completed_exact_tag_build_passes(self) -> None:
        self.assertEqual(self.inspect(), EXPECTED)
        guard.verify_evidence(self.directory, EXPECTED, 456)

    def test_dispatch_checks_tag_evidence_not_workflow_branch_head(self) -> None:
        self.api.run.update(event="workflow_dispatch", head_sha="c" * 40)
        self.assertEqual(self.inspect(), EXPECTED)
        guard.verify_evidence(self.directory, EXPECTED, 456)

    def test_pending_failed_or_cancelled_build_cannot_race_publication(self) -> None:
        for status, conclusion in (
            ("in_progress", None),
            ("queued", None),
            ("completed", "failure"),
            ("completed", "cancelled"),
            ("completed", "timed_out"),
            ("completed", "skipped"),
        ):
            with self.subTest(status=status, conclusion=conclusion):
                self.api.run.update(status=status, conclusion=conclusion)
                with self.assertRaises(guard.ReleaseError):
                    self.inspect()

    def test_wrong_workflow_repository_event_or_push_sha_is_rejected(self) -> None:
        for changes in (
            {"path": ".github/workflows/ci.yml"},
            {"repository": {"full_name": "other/quantlab", "id": 999}},
            {"event": "pull_request"},
            {"head_sha": "c" * 40},
        ):
            with self.subTest(changes=changes):
                self.api = FakeGitHub()
                self.api.run.update(changes)
                with self.assertRaises(guard.ReleaseError):
                    self.inspect()

    def test_lightweight_or_moved_tag_is_rejected(self) -> None:
        self.api.ref["object"]["type"] = "commit"
        with self.assertRaises(guard.ReleaseError):
            self.inspect()
        self.api = FakeGitHub()
        self.api.tag["object"]["sha"] = "c" * 40
        with self.assertRaises(guard.ReleaseError):
            self.inspect()

    def test_existing_release_is_never_overwritten(self) -> None:
        self.api.release = {"id": 1, "draft": False}
        with self.assertRaisesRegex(guard.ReleaseError, "already exists"):
            self.inspect()

    def test_expired_ambiguous_missing_or_old_attempt_artifact_is_rejected(self) -> None:
        for change in ("expired", "duplicate", "missing", "old-attempt"):
            with self.subTest(change=change):
                self.api = FakeGitHub()
                if change == "expired":
                    self.api.artifacts["artifacts"][0]["expired"] = True
                elif change == "duplicate":
                    self.api.artifacts["total_count"] = 2
                elif change == "missing":
                    self.api.artifacts = {"total_count": 0, "artifacts": []}
                else:
                    self.api.artifacts["artifacts"][0]["name"] = f"windows-release-{SHA}-1"
                with self.assertRaises(guard.ReleaseError):
                    self.inspect()

    def test_provenance_fields_cannot_be_substituted(self) -> None:
        for key in EXPECTED:
            if key == "artifact_id":
                continue
            with self.subTest(key=key):
                expected = copy.deepcopy(EXPECTED)
                expected[key] = "different"
                with self.assertRaisesRegex(guard.ReleaseError, "provenance mismatch"):
                    guard.verify_evidence(self.directory, expected, 456)

    def test_replaced_artifact_id_is_rejected(self) -> None:
        with self.assertRaisesRegex(guard.ReleaseError, "artifact changed"):
            guard.verify_evidence(self.directory, EXPECTED, 789)

    def test_corrupt_zip_or_checksum_is_rejected(self) -> None:
        (self.directory / ZIP).write_bytes(b"changed archive")
        with self.assertRaisesRegex(guard.ReleaseError, "SHA256SUMS mismatch"):
            guard.verify_evidence(self.directory, EXPECTED, 456)
        digest = guard.file_hash(self.directory / ZIP)
        (self.directory / "SHA256SUMS.txt").write_text(f"{digest} *{ZIP}", encoding="ascii")
        with self.assertRaisesRegex(guard.ReleaseError, "bytes differ"):
            guard.verify_evidence(self.directory, EXPECTED, 456)

    def test_notes_and_unexpected_files_are_checked(self) -> None:
        (self.directory / f"RELEASE-NOTES-{TAG}.md").write_text("changed", encoding="utf-8")
        with self.assertRaisesRegex(guard.ReleaseError, "bytes differ"):
            guard.verify_evidence(self.directory, EXPECTED, 456)
        (self.directory / "debug.log").write_text("unexpected", encoding="utf-8")
        with self.assertRaisesRegex(guard.ReleaseError, "Unexpected candidate files"):
            guard.verify_evidence(self.directory, EXPECTED, 456)

    def test_missing_assets_and_evidence_fail_closed(self) -> None:
        (self.directory / ZIP).unlink()
        with self.assertRaisesRegex(guard.ReleaseError, "Missing or unsafe asset"):
            guard.verify_evidence(self.directory, EXPECTED, 456)
        (self.directory / guard.EVIDENCE).unlink()
        with self.assertRaises(FileNotFoundError):
            guard.verify_evidence(self.directory, EXPECTED, 456)

    def test_untrusted_tag_or_sha_cannot_enter_api_or_output(self) -> None:
        for tag, sha in (("../main", SHA), (TAG, "main"), (TAG + "\ninjected", SHA)):
            with self.subTest(tag=tag, sha=sha), self.assertRaises(guard.ReleaseError):
                guard.inspect_candidate(self.api, tag, sha, 123)

    def test_record_binds_artifacts_to_actual_checkout_and_ci_run(self) -> None:
        environment = {
            "GITHUB_REPOSITORY": REPO,
            "GITHUB_REPOSITORY_ID": "12",
            "GITHUB_RUN_ID": "123",
            "GITHUB_RUN_ATTEMPT": "2",
        }
        with (
            patch.dict(os.environ, environment),
            patch.object(guard, "git", side_effect=["tag", SHA, SHA, TAG_OBJECT]),
        ):
            guard.record(self.directory, TAG, SHA, TAG_OBJECT)
        guard.verify_evidence(self.directory, EXPECTED, 456)

    def test_record_rejects_checkout_or_tag_changes(self) -> None:
        for answers in (
            ["commit"],
            ["tag", "c" * 40],
            ["tag", SHA, "c" * 40],
            ["tag", SHA, SHA, "c" * 40],
        ):
            with (
                patch.object(guard, "git", side_effect=answers),
                self.assertRaises(guard.ReleaseError),
            ):
                guard.record(self.directory, TAG, SHA, TAG_OBJECT)


if __name__ == "__main__":
    unittest.main()
