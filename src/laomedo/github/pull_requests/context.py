"""Validate the single PR graph handoff without introducing write authority."""

import json
from pydantic import ValidationError
from laomedo.github.pull_requests.models import PRContext
from laomedo.github.pull_requests.models import PRContextOperation
from laomedo.github.pull_requests.models import PRContextOutcome
from laomedo.github.pull_requests.models import GitHubPullRequest


def context_value(value):
    """Decode Data/Message-compatible input and reject malformed or failed handoffs.

    Returns a typed context, never a provider capability. Raw operation JSON is
    accepted only with the normal explicit request/grant fields; isolated feedback
    uses its existing host-stamped decoder instead.
    """
    if hasattr(value, "data"):
        value = value.data
    if isinstance(value, dict) and set(value) == {"text"}:
        value = value["text"]
    if isinstance(value, str):
        if len(value.encode("utf-8")) > 1024 * 1024:
            raise ValueError("pr_context_invalid")
        try:
            value = json.loads(value)
        except ValueError:
            raise ValueError("pr_context_invalid") from None
    if isinstance(value, dict) and "action" in value:
        value = {"operation": value}
    try:
        result = PRContext.model_validate(value)
    except (ValidationError, TypeError):
        raise ValueError("pr_context_invalid") from None
    if isinstance(result.operation, PRContextOutcome) and result.operation.status in {
        "failed",
        "unknown",
    }:
        raise ValueError("pr_context_upstream_failed")
    if result.pr is None and not isinstance(result.operation, PRContextOperation):
        raise ValueError("pr_context_invalid")
    return result


def task_text(value):
    """Format a successful complete PR result for an Agent, refusing other Data.

    Snapshot body/title remain untrusted task content. No result status or raw
    exception is converted into an Agent instruction. Ordinary text/Message input
    adaptation stays with the Agent's existing path.
    """
    context = context_value(value)
    if not isinstance(context.pr, GitHubPullRequest) or not isinstance(
        context.operation, PRContextOutcome
    ):
        raise ValueError("pr_context_invalid")
    pr = context.pr
    return f"PR: {pr.url}\nTitle: {pr.title}\nState: {pr.state}\nLabels: {', '.join(pr.labels)}\n\n{pr.body}"
