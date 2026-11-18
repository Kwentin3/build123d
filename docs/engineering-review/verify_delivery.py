"""Verify this acceptance manifest against raw Git blobs, never checkout bytes.

Run from a Git clone; --ref is resolved once. No CAD code or dependencies run.
The selected manifest lists the checked files; this is not whole-tree coverage.
"""

import argparse
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import subprocess
import zipfile

MANIFEST = "docs/engineering-review/acceptance.json"
GROUPS = ("source_sha256", "artifact_sha256")


def git(repo, *args):
    return subprocess.check_output(["git", "-C", str(repo), *args], stderr=subprocess.PIPE)


def blob(repo, commit, path):
    return git(repo, "show", f"{commit}:{path}")


def verify(repo, ref):
    commit = git(repo, "rev-parse", "--verify", "--end-of-options", f"{ref}^{{commit}}").decode().strip()
    raw = blob(repo, commit, MANIFEST)
    manifest = json.loads(raw)
    scope = manifest["delivery_hash_scope"]
    if (scope["representation"] != "raw-git-blob-bytes-v1" or
            scope["normalization"] != "none" or tuple(scope["groups"]) != GROUPS):
        raise ValueError("Unsupported delivery hash scope")
    errors, counts = [], {}
    for group in GROUPS:
        counts[group] = len(manifest[group])
        for path, expected in manifest[group].items():
            if path == MANIFEST:
                raise ValueError("The manifest cannot hash itself")
            actual = sha256(blob(repo, commit, path)).hexdigest()
            if actual != expected:
                errors.append(dict(group=group, path=path, expected=expected, actual=actual))

    history = manifest["windows_execution_snapshot"]
    if history["path"] not in manifest["artifact_sha256"]:
        raise ValueError("Historical snapshot must be bound by the delivery manifest")
    with zipfile.ZipFile(BytesIO(blob(repo, commit, history["path"]))) as archive:
        if archive.testzip() is not None:
            raise ValueError("Historical snapshot CRC failed")
        historical_raw = archive.read(MANIFEST)
        historical = json.loads(historical_raw)
        original_raw = blob(repo, history["original_published_commit"], MANIFEST)
        if historical != json.loads(original_raw):
            errors.append(dict(path=history["path"], reason="Historical acceptance values changed"))
        history_count = 0
        for group in GROUPS:
            for path, expected in historical[group].items():
                actual = sha256(archive.read(path)).hexdigest()
                history_count += 1
                if actual != expected:
                    errors.append(dict(group="windows_snapshot/" + group, path=path,
                                       expected=expected, actual=actual))
        if history_count != history["source_artifact_bindings"]:
            raise ValueError("Unexpected number of historical bindings")
    return dict(status="FAIL" if errors else "PASS", commit=commit,
                manifest_path=MANIFEST, manifest_git_blob_sha256=sha256(raw).hexdigest(),
                representation=scope["representation"], normalization="none", counts=counts,
                delivery_bindings=sum(counts.values()), historical_bindings=history_count,
                historical_windows_manifest_sha256=sha256(historical_raw).hexdigest(),
                original_git_manifest_sha256=sha256(original_raw).hexdigest(),
                historical_reference_commit=history["original_published_commit"], errors=errors)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ref", required=True, help="Published commit or fetched Git ref to verify")
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path, help="Optional local verification receipt")
    args = parser.parse_args()
    try:
        result = verify(args.repo, args.ref)
    except (OSError, ValueError, KeyError, zipfile.BadZipFile, subprocess.CalledProcessError) as exc:
        print(json.dumps(dict(status="ERROR", error=str(exc)), ensure_ascii=True, indent=2))
        return 2
    encoded = json.dumps(result, ensure_ascii=True, indent=2) + "\n"
    if args.output:
        args.output.write_bytes(encoded.encode("utf-8"))
    print(encoded, end="")
    return int(result["status"] != "PASS")


if __name__ == "__main__":
    raise SystemExit(main())
