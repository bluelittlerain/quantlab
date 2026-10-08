"""Fail-closed provenance checks for manually publishing a verified Windows candidate."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

EVIDENCE = "release-evidence.json"
SCHEMA = 1


class ReleaseError(ValueError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ReleaseError(message)


def validate_identity(tag: str, sha: str) -> None:
    require(bool(re.fullmatch(r"v\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?", tag)), "Invalid tag")
    require(bool(re.fullmatch(r"[0-9a-f]{40}", sha)), "Expected a full lowercase commit SHA")


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], text=True, timeout=30).strip()


def file_hash(path: Path) -> str:
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def candidate_hashes(directory: Path, tag: str) -> dict[str, str]:
    zip_name = f"QuantLab-{tag}-windows-x64.zip"
    names = (zip_name, "SHA256SUMS.txt", f"RELEASE-NOTES-{tag}.md")
    require(directory.is_dir(), "Candidate directory is missing")
    require(
        {path.name for path in directory.iterdir()} <= {*names, EVIDENCE},
        "Unexpected candidate files",
    )
    for name in names:
        path = directory / name
        require(path.is_file() and not path.is_symlink(), f"Missing or unsafe asset: {name}")
    hashes = {name: file_hash(directory / name) for name in names}
    checksums = (directory / "SHA256SUMS.txt").read_text(encoding="ascii").strip()
    require(checksums == f"{hashes[zip_name]} *{zip_name}", "ZIP SHA256SUMS mismatch")
    return hashes


def record(directory: Path, tag: str, sha: str, tag_object: str) -> None:
    validate_identity(tag, sha)
    ref = f"refs/tags/{tag}"
    require(git("cat-file", "-t", ref) == "tag", "Release requires an annotated tag")
    require(git("rev-parse", "HEAD") == sha, "Build checkout differs from approved SHA")
    require(git("rev-parse", f"{ref}^{{commit}}") == sha, "Tag commit changed during build")
    require(git("rev-parse", ref) == tag_object, "Tag object changed during build")
    evidence = {
        "schema": SCHEMA,
        "repository": os.environ["GITHUB_REPOSITORY"],
        "repository_id": int(os.environ["GITHUB_REPOSITORY_ID"]),
        "run_id": int(os.environ["GITHUB_RUN_ID"]),
        "run_attempt": int(os.environ["GITHUB_RUN_ATTEMPT"]),
        "tag": tag,
        "tag_object": tag_object,
        "source_sha": sha,
        "assets": candidate_hashes(directory, tag),
    }
    (directory / EVIDENCE).write_text(
        json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
    )


class GitHub:
    def __init__(self, repository: str, token: str) -> None:
        require(bool(re.fullmatch(r"[\w.-]+/[\w.-]+", repository)), "Invalid repository")
        self.repository = repository
        self.token = token

    def get(self, path: str, *, missing_ok: bool = False):
        request = Request(
            f"https://api.github.com/repos/{self.repository}/{path}",
            headers={
                "Authorization": f"Bearer {self.token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        try:
            with urlopen(request, timeout=30) as response:
                return json.load(response)
        except HTTPError as error:
            if missing_ok and error.code == 404:
                return None
            raise ReleaseError(f"GitHub validation failed (HTTP {error.code})") from None


def inspect_candidate(api: GitHub, tag: str, sha: str, run_id: int) -> dict:
    validate_identity(tag, sha)
    require(run_id > 0, "Invalid build run ID")
    ref = api.get(f"git/ref/tags/{tag}")["object"]
    require(ref["type"] == "tag", "Release requires an existing annotated tag")
    target = api.get(f"git/tags/{ref['sha']}")["object"]
    require(target["type"] == "commit" and target["sha"] == sha, "Tag/SHA mismatch")
    require(api.get(f"releases/tags/{tag}", missing_ok=True) is None, "Release already exists")

    run = api.get(f"actions/runs/{run_id}")
    require(run["repository"]["full_name"] == api.repository, "Build repository mismatch")
    require(run["path"] == ".github/workflows/release.yml", "Not a Windows Release build")
    require(run["event"] in {"push", "workflow_dispatch"}, "Untrusted build event")
    require(
        run["status"] == "completed" and run["conclusion"] == "success",
        "Build and all release gates must complete successfully before approval",
    )
    if run["event"] == "push":
        require(run["head_sha"] == sha, "Tag-push build SHA mismatch")

    expected_name = f"windows-release-{sha}-{run['run_attempt']}"
    # Filter server-side and reject ambiguous/expired artifacts, including rerun leftovers.
    artifacts = api.get(f"actions/runs/{run_id}/artifacts?name={expected_name}&per_page=100")
    matches = artifacts["artifacts"]
    require(artifacts["total_count"] == len(matches) == 1, "Expected one verified candidate")
    artifact = matches[0]
    require(artifact["name"] == expected_name and not artifact["expired"], "Invalid artifact")
    return {
        "schema": SCHEMA,
        "repository": api.repository,
        "repository_id": run["repository"]["id"],
        "run_id": run_id,
        "run_attempt": run["run_attempt"],
        "tag": tag,
        "tag_object": ref["sha"],
        "source_sha": sha,
        "artifact_id": artifact["id"],
    }


def verify_evidence(directory: Path, expected: dict, artifact_id: int) -> None:
    require(expected["artifact_id"] == artifact_id, "Candidate artifact changed after approval")
    evidence = json.loads((directory / EVIDENCE).read_text(encoding="utf-8"))
    for key, value in expected.items():
        if key != "artifact_id":
            require(evidence.get(key) == value, f"Candidate provenance mismatch: {key}")
    require(
        evidence.get("assets") == candidate_hashes(directory, expected["tag"]),
        "Candidate bytes differ from the verified build",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("record", "inspect", "verify"))
    parser.add_argument("--tag", required=True)
    parser.add_argument("--sha", required=True)
    parser.add_argument("--directory", type=Path, default=Path("candidate"))
    parser.add_argument("--tag-object")
    parser.add_argument("--run-id", type=int)
    parser.add_argument("--artifact-id", type=int)
    args = parser.parse_args()
    try:
        if args.command == "record":
            record(args.directory, args.tag, args.sha, args.tag_object)
        else:
            require(args.run_id is not None, "Build run ID is required")
            api = GitHub(os.environ["GITHUB_REPOSITORY"], os.environ["GH_TOKEN"])
            expected = inspect_candidate(api, args.tag, args.sha, args.run_id)
            if args.command == "verify":
                verify_evidence(args.directory, expected, args.artifact_id)
            else:
                with Path(os.environ["GITHUB_OUTPUT"]).open("a", encoding="utf-8") as handle:
                    handle.write(f"artifact_id={expected['artifact_id']}\n")
        print("RELEASE_GUARD_OK")
    except (ReleaseError, KeyError, OSError, ValueError, subprocess.SubprocessError) as error:
        # Do not expose HTTP bodies, credentials, or runner-local paths.
        message = str(error) if isinstance(error, ReleaseError) else type(error).__name__
        parser.exit(1, f"RELEASE_GUARD_FAILED: {message}\n")


if __name__ == "__main__":
    main()
