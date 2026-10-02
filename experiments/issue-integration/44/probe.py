"""EXP-14 synthetic issue-publication acknowledgement-loss probe.

This is not the product GitHub publisher. It accepts only an explicitly reviewed
fixture and a caller-supplied fake HTTP URL; it never selects a real repository
endpoint or retries a possible external write after a crash.
"""

import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import tempfile
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


class ProbeError(ValueError):
    pass


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, pending_name = tempfile.mkstemp(prefix=".publication-", dir=path.parent)
    pending = Path(pending_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(record, stream, sort_keys=True)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(pending, path)
    finally:
        pending.unlink(missing_ok=True)


def prepare(path: Path, *, proposal_id: str, title: str, body: str,
            reviewed_by: str, decision: str,
            target_repository: str = "fixture/work") -> dict:
    """Persist a synthetic reviewed proposal before any possible POST."""
    if path.exists():
        raise ProbeError("intent_exists")
    if not proposal_id or not title or not reviewed_by or decision != "publish":
        raise ProbeError("not_reviewed_for_publication")
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", target_repository):
        raise ProbeError("invalid_target_repository")
    review_bytes = json.dumps({"title": title, "body": body,
                               "target_repository": target_repository}, sort_keys=True).encode()
    record = {
        "proposal_id": proposal_id,
        "reviewed_title": title,
        "reviewed_body": body,
        "target_repository": target_repository,
        "reviewed_hash": sha256(review_bytes).hexdigest(),
        "reviewed_by": reviewed_by,
        "reviewed_at": datetime.now(timezone.utc).isoformat(),
        "publication_decision": decision,
        "attempt_id": proposal_id + ":attempt-1",
        "status": "prepared",
    }
    _write(path, record)
    return record


def inspect(path: Path) -> dict:
    """Project persisted facts without inferring a remote result."""
    record = _read(path)
    status = record["status"]
    if status == "sending":
        status = "unknown"
    return {
        "proposal_id": record["proposal_id"],
        "attempt_id": record["attempt_id"],
        "status": status,
        "issue_number": record.get("issue_number") if status == "published" else None,
    }


def send_once(path: Path, fake_url: str, *, crash_at: str | None = None) -> None:
    """POST once to a localhost fake; os._exit marks deterministic crash points."""
    endpoint = urlsplit(fake_url)
    if (endpoint.scheme != "http" or endpoint.hostname != "127.0.0.1"
            or endpoint.port is None or endpoint.username or endpoint.password):
        raise ProbeError("fake_local_endpoint_required")
    record = _read(path)
    if record["status"] != "prepared":
        raise ProbeError("existing_attempt_requires_reconciliation")
    if record["publication_decision"] != "publish" or not record["reviewed_by"]:
        raise ProbeError("not_reviewed_for_publication")
    review_bytes = json.dumps({"title": record["reviewed_title"],
                               "body": record["reviewed_body"],
                               "target_repository": record["target_repository"]},
                              sort_keys=True).encode()
    if sha256(review_bytes).hexdigest() != record["reviewed_hash"]:
        raise ProbeError("reviewed_bytes_changed")
    record["status"] = "sending"
    _write(path, record)  # Conservative: even a crash just before POST is unknown.
    if crash_at == "before_send":
        os._exit(17)
    request = Request(
        fake_url, data=review_bytes, method="POST",
        headers={"Content-Type": "application/json",
                 "X-Proposal-Id": record["proposal_id"],
                 "X-Attempt-Id": record["attempt_id"]},
    )
    with urlopen(request, timeout=10) as response:
        if response.status != 201:
            raise ProbeError("fake_endpoint_rejected")
        result = json.load(response)
    if crash_at == "after_accept":
        os._exit(17)  # Server accepted but acknowledgement was not persisted.
    record["status"] = "published"
    record["issue_number"] = result["number"]
    _write(path, record)
    if crash_at == "after_response_recorded":
        os._exit(17)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("intent", type=Path)
    parser.add_argument("fake_url")
    parser.add_argument("--crash-at", choices=("before_send", "after_accept",
                                               "after_response_recorded"))
    args = parser.parse_args()
    send_once(args.intent, args.fake_url, crash_at=args.crash_at)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
