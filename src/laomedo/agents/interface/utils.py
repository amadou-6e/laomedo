"""Pure public Agent outcome predicates shared by callers and execution."""

def terminal_record(record):
    """Stable terminal states shared by graph clients and asynchronous runner polling."""
    return (record.get("status") in {"completed", "cancelled", "failed", "timeout", "interrupted"}
            or record.get("status") == "unknown" and record.get("attempt_finished") is True)
