"""Project native notifications without summing cumulative token snapshots."""

KEYS = (
    "inputTokens",
    "cachedInputTokens",
    "cacheWriteInputTokens",
    "outputTokens",
    "reasoningOutputTokens",
    "totalTokens",
)


def _parent(thread):
    parent = thread.get("parentThreadId")
    if not parent:
        source = thread.get("source")
        sub = source.get("subAgent", {}) if isinstance(source, dict) else {}
        spawn = sub.get("thread_spawn", {}) if isinstance(sub, dict) else {}
        parent = spawn.get("parent_thread_id") if isinstance(spawn, dict) else None
    return parent if isinstance(parent, str) and parent else None


def _telemetry(record):
    """Normalize explicit native aliases; never correlate by time or label."""
    attrs = dict(record.get("attributes") or {})
    conflict = False
    for target, aliases in {
        "conversation.id": ("thread.id", "thread_id"),
        "turn.id": ("turn_id",),
        "call.id": ("call_id",),
    }.items():
        values = {
            attrs[key]
            for key in (target, *aliases)
            if isinstance(attrs.get(key), str) and attrs[key]
        }
        if len(values) == 1:
            attrs[target] = values.pop()
        elif len(values) > 1:
            conflict = True
    # Retain conflicting native attributes for inspection/export. Only the
    # scoped projection excludes them; All activity still contains the record.
    return {
        **record,
        "attributes": attrs,
        **({"scope_conflict": True} if conflict else {}),
    }


def project(events, *, root_thread=None, model=None):
    if any(
        receipt["raw"]
        .get("event", receipt["raw"])
        .get("method", "")
        .startswith("opencode/")
        for receipt in events
    ):
        from laomedo.agents.agents.opencode.activity.projection import (
            project as opencode_activity_projection_project,
        )

        return opencode_activity_projection_project(
            events, root_thread=root_thread, model=model
        )
    turns, items, threads, latest, baselines = {}, {}, {}, {}, {}
    points = []
    telemetry = []
    diagnostics = []
    previous = {}
    invalid_usage = set()
    turn_usage_by_key = {}
    turn_bases = {}
    for receipt in events:
        raw = receipt["raw"]
        if raw.get("method") == "capture/usageBaseline":
            baselines.update(
                {
                    key: (value or {}).get("total", {})
                    for key, value in raw["threads"].items()
                }
            )
            # Only runner-attested thread/start proves a zero boundary. An empty
            # resume history or a last-request counter is not such evidence.
            if raw.get("fresh_thread") is True and root_thread:
                baselines.setdefault(root_thread, dict.fromkeys(KEYS, 0))
            continue
        event = raw.get("event", raw)
        params = event.get("params", {})
        method = event.get("method", event.get("type", "unknown"))
        if method == "claude/result":
            diagnostics.append(params)
        if method == "otel/record":
            telemetry.append(_telemetry(params))
            continue
        timestamp = raw.get("received_at", receipt["received_at"])
        thread = params.get("threadId")
        turn = params.get("turn", {})
        turn_id = params.get("turnId") or turn.get("id")
        if method == "thread/started":
            value = params.get("thread", {})
            if value.get("id"):
                old = threads.get(value["id"], {})
                title = (
                    value.get("name")
                    or value.get("agentNickname")
                    or value.get("agentRole")
                )
                threads[value["id"]] = {
                    **old,
                    "id": value["id"],
                    "parent": _parent(value) or old.get("parent"),
                    **({"title": title} if isinstance(title, str) else {}),
                }
        if turn_id and (method.startswith("turn/") or method.startswith("item/")):
            key = (thread, turn_id)
            if method == "turn/started" and key not in turn_bases:
                baseline = previous.get(thread, baselines.get(thread))
                turn_bases[key] = dict(baseline) if isinstance(baseline, dict) else None
            lane = turns.setdefault(
                key,
                {
                    "id": turn_id,
                    "thread": thread,
                    "started": timestamp,
                    "ended": None,
                    "status": "running",
                },
            )
            if method in {"turn/completed", "turn/failed"}:
                lane.update(
                    ended=timestamp,
                    status=turn.get(
                        "status", "failed" if method == "turn/failed" else "completed"
                    ),
                )
        # Native message/output deltas are provisional until item/completed.
        # Late frames cannot overwrite the authoritative completed item.
        item_id = params.get("itemId")
        if isinstance(item_id, str) and isinstance(params.get("delta"), str):
            value = items.get((thread, item_id))
            field = {
                "item/agentMessage/delta": "text",
                "item/commandExecution/outputDelta": "aggregatedOutput",
            }.get(method)
            if value and field and not value["ended"]:
                text = value["item"].get(field)
                value["item"] = {
                    **value["item"],
                    field: (text if isinstance(text, str) else "") + params["delta"],
                }
        item = params.get("item")
        if isinstance(item, dict) and item.get("id"):
            key = (thread, item["id"])
            value = items.setdefault(
                key,
                {
                    "id": item["id"],
                    "thread": thread,
                    "turn": turn_id,
                    "started": timestamp,
                    "ended": None,
                    "item": item,
                },
            )
            if method == "item/updated" and value["ended"] is None:
                value["item"] = item
            if method == "item/completed":
                if value["ended"] and value["item"] != item:
                    value["conflicting_receipts"] = True
                value.update(ended=timestamp, item=item)
            child = item.get("agentThreadId")
            if child:
                threads[child] = {
                    **threads.get(child, {}),
                    "id": child,
                    "parent": thread,
                }
                if isinstance(item.get("agentPath"), str) and item["agentPath"].strip(
                    "/"
                ):
                    threads[child].setdefault(
                        "title", item["agentPath"].rstrip("/").rsplit("/", 1)[-1]
                    )
                if (
                    item.get("type") == "subAgentActivity"
                    and item.get("kind") == "started"
                    and method == "item/started"
                    and child not in previous
                    and not any(key[0] == child for key in turns)
                ):
                    # Native child creation precedes its first turn. Replayed
                    # starts cannot reset an already observed usage boundary.
                    baselines.setdefault(child, dict.fromkeys(KEYS, 0))
            if item.get("type") in {"collabAgentToolCall", "collabAgentSpawnToolCall"}:
                for child in item.get("receiverThreadIds", []):
                    threads.setdefault(child, {"id": child, "parent": thread})
        if method == "thread/tokenUsage/updated" and thread:
            total = params.get("tokenUsage", {}).get("total")
            if total is None and params.get("usage_scope") in {
                "native_session_cumulative",
                "terminal_receipt_unavailable",
            }:
                invalid_usage.add(thread)
                latest[thread] = None
            if isinstance(total, dict):
                base = baselines.get(thread, {})
                keys = KEYS
                delta = {
                    key: total[key] - base.get(key, 0)
                    for key in keys
                    if type(total.get(key)) is int and type(base.get(key, 0)) is int
                }
                if any(
                    type(total.get(key)) is int and total[key] < value
                    for key, value in previous.get(thread, {}).items()
                ):
                    invalid_usage.add(thread)
                previous[thread] = {
                    key: total[key] for key in keys if type(total.get(key)) is int
                }
                if thread in invalid_usage or any(
                    value < 0 for value in delta.values()
                ):
                    latest[thread] = None
                    if turn_id:
                        turn_usage_by_key[(thread, turn_id)] = None
                else:
                    latest[thread] = delta
                    from laomedo.agents.activity.cost import estimate

                    turn_base = turn_bases.get((thread, turn_id))
                    turn_usage = (
                        {
                            key: total[key] - turn_base[key]
                            for key in keys
                            if type(total.get(key)) is int
                            and type(turn_base.get(key)) is int
                        }
                        if isinstance(turn_base, dict)
                        else None
                    )
                    if turn_usage is not None and (
                        not turn_usage
                        or any(value < 0 for value in turn_usage.values())
                    ):
                        turn_usage = None
                    if turn_id:
                        turn_usage_by_key[(thread, turn_id)] = turn_usage
                    points.append(
                        {
                            "at": timestamp,
                            "thread": thread,
                            "turn": turn_id,
                            "turn_usage": turn_usage,
                            "usage": delta,
                            "cost": estimate(
                                model if thread == root_thread else None, delta
                            ),
                        }
                    )
    related = (
        {root_thread}
        if root_thread
        else set(latest) | {value["thread"] for value in turns.values()}
    )
    changed = True
    while changed:
        before = len(related)
        related.update(
            value["id"] for value in threads.values() if value["parent"] in related
        )
        changed = len(related) != before
    uncorrelated = set(latest) - related
    latest = {key: value for key, value in latest.items() if key in related}
    turns = {key: value for key, value in turns.items() if value["thread"] in related}
    items = {key: value for key, value in items.items() if value["thread"] in related}
    points = [point for point in points if point["thread"] in related]
    usage = None
    if latest and all(value is not None for value in latest.values()):
        usage = {
            key: sum(value[key] for value in latest.values())
            for key in (
                "inputTokens",
                "cachedInputTokens",
                "cacheWriteInputTokens",
                "outputTokens",
                "reasoningOutputTokens",
                "totalTokens",
            )
            if all(key in value for value in latest.values())
        }
    if related - set(latest):
        usage = None
    from laomedo.agents.activity.cost import estimate

    models = {root_thread: model} if root_thread and model else {}
    model_provenance = (
        {root_thread: "native runner effective model"} if root_thread and model else {}
    )
    observed_models = {}
    for record in telemetry:
        if record.get("scope_conflict"):
            continue
        attrs = record.get("attributes", {})
        thread = attrs.get("conversation.id")
        observed_model = attrs.get("model") or attrs.get("gen_ai.response.model")
        if isinstance(thread, str) and isinstance(observed_model, str):
            observed_models.setdefault(thread, set()).add(observed_model)
    for thread, values in observed_models.items():
        if thread in models and (len(values) != 1 or models[thread] not in values):
            models[thread] = None
        elif thread not in models and len(values) == 1:
            models[thread] = next(iter(values))
            model_provenance[thread] = (
                "runtime-reported OTLP metadata; not independently attested"
            )
    for point in points:
        point["cost"] = estimate(models.get(point["thread"]), point["usage"])
        point["turn_cost"] = estimate(
            models.get(point["thread"]), point.get("turn_usage")
        )
    # Child model and usage must be independently observed; do not price all
    # child activity at the parent's model or claim an inclusive known total.
    cost = estimate(models.get(root_thread), latest.get(root_thread))
    per_thread = {
        thread: estimate(models.get(thread), latest.get(thread)) for thread in related
    }
    if len(related) > 1:
        if all(value["amount"] is not None for value in per_thread.values()):
            cost = {
                **cost,
                "amount": sum(value["amount"] for value in per_thread.values()),
                "reason": None,
            }
        else:
            cost = {
                **cost,
                "amount": None,
                "reason": "Inclusive subagent pricing requires independently confirmed child models and usage.",
            }
    cost["per_thread"] = per_thread
    cost["model_provenance"] = model_provenance
    if any(thread != root_thread for thread in related):
        cost[
            "basis"
        ] += "; child model attribution is runtime-reported, not independently attested"
    cost_reason = cost.get("reason") or cost["basis"]
    projected_turns = [
        {
            **lane,
            "usage": turn_usage_by_key.get(key),
            "cost": estimate(models.get(lane["thread"]), turn_usage_by_key.get(key)),
        }
        for key, lane in turns.items()
    ]
    return {
        "turns": projected_turns,
        "items": list(items.values()),
        "threads": list(threads.values()),
        "diagnostics": [
            value for value in diagnostics if value.get("threadId") in related
        ],
        "telemetry": telemetry,
        "telemetry_coverage": (
            "observed; exporter flush completeness unverified"
            if telemetry
            else "not observed"
        ),
        "uncorrelated_thread_count": len(uncorrelated),
        "usage": usage,
        "usage_by_thread": latest,
        "usage_points": points,
        "clock": "runner receipt time",
        "cost": cost,
        "cost_reason": cost_reason,
    }
