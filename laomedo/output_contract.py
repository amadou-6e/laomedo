"""Declarative output checks shared by native precheck and the graph evaluator."""

from copy import deepcopy
import hashlib
import json
import re

MAX_CONTRACT_BYTES = 65536
MAX_SUBMISSION_BYTES = 262144
MAX_FIELDS = 64
TYPES = {"string", "integer", "number", "boolean", "object", "array"}
CHECKS = {"nonempty", "enum", "minimum", "maximum", "min_length", "max_length"}


def _encoded(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def requirements(specification):
    """Validate and copy a closed requirements form before calculating its pin."""
    try:
        encoded = _encoded(specification)
    except (ValueError, TypeError, OverflowError, RecursionError):
        raise ValueError("invalid_output_requirements") from None
    if (len(encoded) > MAX_CONTRACT_BYTES or not isinstance(specification, dict) or
            set(specification) != {"schema_version", "fields"} or
            type(specification["schema_version"]) is not int or specification["schema_version"] != 1 or
            not isinstance(specification["fields"], list) or len(specification["fields"]) > MAX_FIELDS):
        raise ValueError("invalid_output_requirements")
    names = set()
    for field in specification["fields"]:
        if (not isinstance(field, dict) or set(field) - {"name", "type", "required", "checks"} or
                not isinstance(field.get("name"), str) or
                not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,63}", field["name"]) or
                field["name"] in names or not isinstance(field.get("type"), str) or field["type"] not in TYPES or
                type(field.get("required", False)) is not bool or
                not isinstance(field.get("checks", {}), dict)):
            raise ValueError("invalid_output_field")
        names.add(field["name"])
        checks = field.get("checks", {})
        if field["name"] == "task_outcome" and (
                field["type"] != "string" or checks.get("enum") != ["success", "failure"]):
            raise ValueError("reserved_task_outcome_field")
        if set(checks) - CHECKS:
            raise ValueError("unsupported_output_check")
        for name, value in checks.items():
            if name == "nonempty":
                valid = type(value) is bool and field["type"] in {"string", "array", "object"}
            elif name == "enum":
                valid = (isinstance(value, list) and 1 <= len(value) <= 64 and
                         all(item is None or type(item) in {str, int, float, bool} for item in value))
            elif name in {"minimum", "maximum"}:
                valid = type(value) in {int, float} and field["type"] in {"integer", "number"}
            else:
                valid = type(value) is int and 0 <= value <= MAX_SUBMISSION_BYTES and field["type"] in {"string", "array"}
            if not valid:
                raise ValueError("invalid_output_check")
        for lower, upper in (("minimum", "maximum"), ("min_length", "max_length")):
            if lower in checks and upper in checks and checks[lower] > checks[upper]:
                raise ValueError("invalid_output_check_bounds")
    return {"schema_version": "laomedo.output-requirements.v1",
            "requirements": deepcopy(specification),
            "requirements_revision": "sha256:" + hashlib.sha256(encoded).hexdigest()}


def verify_requirements(reference):
    if not isinstance(reference, dict) or set(reference) != {"schema_version", "requirements", "requirements_revision"}:
        raise ValueError("invalid_output_requirements_reference")
    pinned = requirements(reference["requirements"])
    if reference != pinned:
        raise ValueError("output_requirements_revision_mismatch")
    return pinned


def evaluate(reference, submission):
    reference = verify_requirements(reference)
    errors = []
    def reject(path, code):
        if len(errors) < MAX_FIELDS:
            errors.append({"path": path, "code": code})
    try:
        encoded = _encoded(submission)
        if len(encoded) > MAX_SUBMISSION_BYTES:
            reject("", "submission_too_large")
    except (ValueError, TypeError, OverflowError, RecursionError):
        reject("", "invalid_json_value")
    if not errors and not isinstance(submission, dict):
        reject("", "object_required")
    if not errors:
        for field in reference["requirements"]["fields"]:
            name, kind = field["name"], field["type"]
            path = "/" + name
            if name not in submission:
                if field.get("required", False):
                    reject(path, "required")
                continue
            value = submission[name]
            valid = {"string": type(value) is str, "integer": type(value) is int,
                     "number": type(value) in {int, float}, "boolean": type(value) is bool,
                     "object": type(value) is dict, "array": type(value) is list}[kind]
            if not valid:
                reject(path, "type_mismatch")
                continue
            for check, target in field.get("checks", {}).items():
                if check == "nonempty":
                    failed = target and not (value.strip() if isinstance(value, str) else value)
                elif check == "enum":
                    failed = not any(type(value) is type(item) and value == item for item in target)
                elif check == "minimum":
                    failed = value < target
                elif check == "maximum":
                    failed = value > target
                elif check == "min_length":
                    failed = len(value) < target
                else:
                    failed = len(value) > target
                if failed:
                    reject(path, check)
    return {"schema_version": "laomedo.output-validation.v1",
            "requirements_revision": reference["requirements_revision"],
            "contract_status": "rejected" if errors else "accepted", "errors": errors}


def evaluate_envelope(reference, envelope):
    if not isinstance(envelope, dict) or envelope.get("schema_version") != "laomedo.agent-submission.v1":
        raise ValueError("agent_submission_envelope_required")
    result = evaluate(reference, envelope.get("submission"))
    if envelope.get("requirements_revision") != reference["requirements_revision"]:
        code = "requirements_unbound" if envelope.get("requirements_revision") is None else "requirements_revision_mismatch"
        result.update(contract_status="rejected", errors=[{"path": "", "code": code}])
    else:
        submission = envelope.get("submission")
        outcome = submission.get("task_outcome") if isinstance(submission, dict) else None
        if outcome not in {"success", "failure"}:
            outcome = "unknown"
        if envelope.get("executor_status") != "completed" and outcome == "success":
            outcome = "unknown"
        if envelope.get("task_outcome") != outcome:
            result.update(contract_status="rejected", errors=[{"path": "/task_outcome", "code": "task_outcome_mismatch"}])
    result["agent_submission"] = deepcopy(envelope)
    return result


def dynamic_tool(reference):
    reference = verify_requirements(reference)
    return {"type": "function", "name": "laomedo_output_precheck",
            "description": "Precheck the proposed output form before handoff. Correct rejected fields within this request. Requirements: " + _encoded(reference).decode(),
            "inputSchema": {"type": "object", "properties": {
                "requirements_revision": {"type": "string"}, "submission": {"type": "object"}},
                "required": ["requirements_revision", "submission"], "additionalProperties": False}}


def precheck_response(reference, params, thread_id):
    """Return a native dynamic-tool response without echoing submitted values."""
    reference = verify_requirements(reference)
    arguments = params.get("arguments")
    if (params.get("tool") != "laomedo_output_precheck" or params.get("namespace") is not None or
            params.get("threadId") != thread_id or not isinstance(arguments, dict) or
            set(arguments) != {"requirements_revision", "submission"} or
            arguments.get("requirements_revision") != reference["requirements_revision"]):
        result = {"schema_version": "laomedo.output-validation.v1",
                  "requirements_revision": reference["requirements_revision"],
                  "contract_status": "rejected", "errors": [{"path": "", "code": "precheck_binding_mismatch"}]}
    else:
        result = evaluate(reference, arguments["submission"])
    return {"success": True, "contentItems": [{"type": "inputText", "text": _encoded(result).decode()}]}
