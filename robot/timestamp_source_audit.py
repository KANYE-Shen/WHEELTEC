"""Offline usb_cam source audit and REVIEW-ONLY patch bundle.

No network, ROS imports, subprocess, driver installation, or in-place patching.
Only three pinned timestamp-bearing files are recognized, not an entire release.
Unknown/vendor-modified trees deliberately require a new source-level review.
"""
from __future__ import annotations
import argparse
import difflib
import hashlib
import json
from pathlib import Path

EVIDENCE = Path(__file__).resolve().parents[1] / "setup/verification/2026-10-28-night/g0-timestamp"
MANIFEST_SHA256 = "736f4ebbaa6e831cb987f08ad517ba63b2aef98f66efb9c7564fb3a3343a06b3"


def _manifest():
    data = (EVIDENCE / "fixture-manifest.json").read_bytes()
    if hashlib.sha256(data).hexdigest() != MANIFEST_SHA256:
        raise ValueError("Pinned fixture manifest changed; review provenance before continuing")
    return json.loads(data)


def _integer(value, name, upper=None):
    if type(value) is not int or value < 0 or (upper is not None and value >= upper):
        raise ValueError(f"Invalid nonnegative integer {name}")
    return value


def epoch_shift_us(epoch_sec, epoch_usec, monotonic_sec, monotonic_nsec):
    """Integer model of PR267 plus ee0a2f7; no message rewriting.

    Positive nanoseconds round half up to nearest microsecond, matching std::round.
    A carry at 999999500 ns is intentional and stays in the total microseconds.
    Paired clock-read latency/clock steps are NOT solved by this arithmetic model.
    """
    epoch_sec = _integer(epoch_sec, "epoch_sec")
    epoch_usec = _integer(epoch_usec, "epoch_usec", 1_000_000)
    monotonic_sec = _integer(monotonic_sec, "monotonic_sec")
    monotonic_nsec = _integer(monotonic_nsec, "monotonic_nsec", 1_000_000_000)
    return epoch_sec * 1_000_000 + epoch_usec - (monotonic_sec * 1_000_000 + (monotonic_nsec + 500) // 1000)


def image_timestamp(buffer_sec, buffer_usec, shift_us):
    """Integer oracle for positive-epoch V4L2 MONOTONIC buffers only."""
    buffer_sec = _integer(buffer_sec, "buffer_sec")
    buffer_usec = _integer(buffer_usec, "buffer_usec", 1_000_000)
    if type(shift_us) is not int:
        raise ValueError("shift_us must be an integer")
    total = buffer_sec * 1_000_000 + buffer_usec + shift_us
    if total < 0:
        raise ValueError("Negative output epoch not supported by candidate C++ division")
    sec, usec = divmod(total, 1_000_000)
    return sec, usec * 1000


def audit_source(source):
    """Read only; exact-byte fingerprints, never version-string guesses."""
    source = Path(source)
    manifest = _manifest()
    files = {}
    for rel in manifest["files"]:
        path = source / rel
        try:
            if path.is_symlink():
                raise ValueError("symbolic source file")
            files[rel] = {"sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
        except (OSError, ValueError) as exc:
            files[rel] = {"sha256": None, "error": str(exc)}
    states = [state for state in ("legacy", "pr267", "candidate")
              if all(files[rel]["sha256"] == hashes[state] for rel, hashes in manifest["files"].items())]
    state = states[0] if len(states) == 1 else "unknown"
    return {"source": str(source.resolve()), "state": state, "files": files,
            "scope": "three timestamp-bearing files only; not full release or installed binary",
            "can_prepare_review_bundle": state in ("legacy", "pr267"),
            "deployment_ready": False, "real_robot_verified": False}


def prepare_patch(source, output, fixtures=None):
    """Create a new review directory; source is NEVER changed."""
    source, output = Path(source).resolve(), Path(output).resolve()
    fixtures = Path(fixtures) if fixtures is not None else EVIDENCE / "fixtures"
    if output == source or source in output.parents or output in source.parents:
        raise ValueError("Review output and source must be disjoint")
    if output.exists():
        raise ValueError("Refusing to overwrite existing review output")
    audit = audit_source(source)
    if not audit["can_prepare_review_bundle"]:
        raise ValueError("Source unknown/mixed/already candidate: collect source and review manually")
    manifest = _manifest()
    contents = {}
    patch = []
    # Validate every candidate byte before creating any output.
    for rel, hashes in manifest["files"].items():
        data = (fixtures / "candidate" / rel).read_bytes()
        if hashlib.sha256(data).hexdigest() != hashes["candidate"]:
            raise ValueError(f"Candidate fixture checksum mismatch: {rel}")
        contents[rel] = data
        patch.extend(difflib.unified_diff((source / rel).read_text().splitlines(True),
                     data.decode().splitlines(True), fromfile="a/" + rel, tofile="b/" + rel))
    # Check that the audited source has not changed while preparing the bundle.
    if audit_source(source)["files"] != audit["files"]:
        raise ValueError("Source changed during preparation")
    output.mkdir(parents=True, exist_ok=False)
    for rel, data in contents.items():
        target = output / "candidate" / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    (output / "candidate.patch").write_text("".join(patch), encoding="utf-8", newline="")
    result = {"source_audit": audit, "source_modified": False,
              "candidate_origin": {key: manifest[key] for key in ("pr267_commit", "unit_fix_commit")},
              "deployment_ready": False, "real_robot_verified": False,
              "next_step": "Manual review against collected installed driver source; no deploy authorization"}
    (output / "review.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="Locally collected source tree; never a robot address")
    parser.add_argument("--prepare", type=Path, help="Explicit NEW offline review directory; never changes source")
    args = parser.parse_args()
    try:
        result = prepare_patch(args.source, args.prepare) if args.prepare else audit_source(args.source)
    except (ValueError, OSError) as exc:
        print(json.dumps({"error": str(exc), "deployment_ready": False}))
        return 2
    print(json.dumps(result, indent=2))
    return 1 if result.get("state") == "unknown" else 0


if __name__ == "__main__":
    raise SystemExit(main())
