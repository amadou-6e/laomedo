"""Authenticated loopback requests with strict admission and safe JSON replies."""

from http.server import BaseHTTPRequestHandler
import json
import secrets
from pydantic import ValidationError
from laomedo.skills.operations.settings import MANUAL_ERROR_CODES
from laomedo.skills.registry.errors import SkillStoreError


class SkillOperationRequestHandler(BaseHTTPRequestHandler):
    """Authenticate and route one request using only its server instance bindings."""

    def log_message(self, *_):
        """Suppress access-log content so request paths and source data do not enter default HTTP logs."""
        pass

    def reply(self, status, value):
        """Send a no-store JSON response with the supplied status and explicit content length."""
        data = json.dumps(value).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        """Authenticate, admit exact route/fields and dispatch to the bound service using safe response categories."""
        if not secrets.compare_digest(
            self.headers.get("Authorization", ""), "Bearer " + self.server._token
        ):
            self.reply(401, {"error_category": "unauthorized"})
            return
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if (
                self.headers.get("Content-Type", "").split(";")[0] != "application/json"
                or not 0 < size <= 4 * 1024 * 1024
            ):
                raise ValueError("skill_request_invalid")
            body = json.loads(self.rfile.read(size))
            action = self.path.removeprefix("/v1/skill-operations/")
            fields = {
                "prepare": {"skill_id", "revision_id", "commit_id"},
                "apply": {"ticket", "operation", "editor"},
                "history": {"skill_id", "revision_id", "before"},
                "diff": {"skill_id", "commit_id"},
                "compare": {"skill_id", "commit_id", "revision_id"},
                "editor": {"skill_id", "revision_id"},
                "save": {
                    "request_id",
                    "skill_id",
                    "revision_id",
                    "commit_id",
                    "operation",
                },
                "publish": {"skill_id", "revision_id", "commit_id", "expected_latest"},
            }
            if (
                action not in fields
                or self.path != "/v1/skill-operations/" + action
                or not isinstance(body, dict)
                or set(body) != fields[action]
            ):
                raise ValueError("skill_request_invalid")
            owner = (
                self.server.manual
                if action in {"editor", "save", "publish"}
                else self.server.operations
            )
            self.reply(200, getattr(owner, action)(**body))
        except Exception as exc:
            # Never disclose parser data, source paths, tickets or tracebacks.
            if self.path in {
                "/v1/skill-operations/" + name for name in ("editor", "save", "publish")
            }:
                code = str(exc) if isinstance(exc, SkillStoreError) else ""
                if code not in MANUAL_ERROR_CODES:
                    if code in {
                        "skill_base_changed",
                        "base_revision_changed",
                        "reviewed_ref_mismatch",
                    }:
                        code = "skill_manual_stale"
                    elif code == "skill_edit_not_authorized":
                        code = "skill_manual_not_authorized"
                    elif code == "skill_ticket_expired":
                        code = "skill_manual_save_expired"
                    elif code in {
                        "skill_edit_policy_denied",
                        "skill_summary_required",
                        "skill_edit_no_change",
                    }:
                        code = "skill_manual_policy_denied"
                    elif code in {
                        "invalid_skill_id",
                        "invalid_revision_id",
                        "unsafe_relative_path",
                        "skill_operation_invalid",
                        "skill_file_missing",
                    } or (
                        not isinstance(exc, SkillStoreError)
                        and isinstance(exc, (ValidationError, ValueError, TypeError))
                    ):
                        code = "skill_manual_invalid"
                    else:
                        code = "skill_manual_unavailable"
                self.reply(400, {"error_category": code})
            else:
                self.reply(400, {"error_category": "skill_operation_refused"})
