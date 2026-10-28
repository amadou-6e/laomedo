"""Observed OpenCode message snapshots, scoped to one accepted runner attempt.

These are native HTTP records, not a claim that an SSE stream was captured.
"""

from copy import deepcopy
from datetime import datetime
from datetime import timezone
from decimal import Decimal
import json
import laomedo.activity.agent_activity.cost as _agent_activity_cost
import laomedo.activity.opencode.utils as _opencode_utils
import laomedo.activity.runner.feed as _runner_feed
import math


def retain_messages(root, session, messages, parent=None, writer=None):
    event = {
        "method": "opencode/messageSnapshot",
        "params": {
            "sessionID": session,
            "messages": _opencode_utils.sanitized(messages),
            "parentSessionID": parent,
        },
    }
    retained = (
        len(
            (json.dumps(_runner_feed.receipt(event), ensure_ascii=False) + "\n").encode(
                "utf8"
            )
        )
        <= 1024 * 1024
    )
    if not retained:
        event = {"method": "opencode/captureLimit", "params": {"sessionID": session}}
    if writer is None:
        import laomedo.activity.opencode.events as _opencode_events

        writer = _opencode_events.NativeCapture(root, session)
    writer.append(event)
    return retained


def _at(value, fallback):
    if type(value) not in {int, float}:
        return fallback
    try:
        return datetime.fromtimestamp(value / 1000, timezone.utc).isoformat()
    except (ValueError, OverflowError, OSError):
        return fallback


def _object(value):
    return value if isinstance(value, dict) else {}


def project(events, *, root_thread=None, model=None):
    parents = {root_thread: None} if root_thread else {}
    native_events = []
    catalogs = {}
    telemetry = []
    titles = {}
    for event in events:
        raw = _object(event.get("raw"))
        native = _object(raw.get("event", raw))
        params = _object(native.get("params"))
        native_events.append((native, raw.get("received_at", event["received_at"])))
    # Correlate only native parent relationships, never a model's claimed ID.
    for _ in range(len(native_events) + 1):
        changed = False
        for native, _ in native_events:
            params = _object(native.get("params"))
            value = _object(params.get("event"))
            info = (
                _object(_object(value.get("properties")).get("info"))
                if value.get("type") in {"session.created", "session.updated"}
                else {}
            )
            if native.get("method") == "opencode/sessionSnapshot":
                info = _object(params.get("session"))
            if isinstance(info.get("id"), str) and isinstance(info.get("title"), str):
                titles[info["id"]] = info["title"]
            if info.get("parentID") in parents and info.get("id") not in parents:
                parents[info["id"]] = info["parentID"]
                changed = True
        if not changed:
            break
    messages = {}
    checkpoints = []
    for native, received in native_events:
        method = native.get("method")
        params = _object(native.get("params"))
        if method == "otel/record":
            if _object(params.get("attributes")).get("conversation.id") in parents:
                telemetry.append(params)
            continue
        if method == "opencode/modelCatalog":
            catalogs[params.get("model")] = params.get("rates")
            continue
        if method == "opencode/messageSnapshot" and params.get("sessionID") in parents:
            checkpoints.append((params, received))
        if method != "opencode/event":
            continue
        value = _object(params.get("event"))
        props = _object(value.get("properties"))
        kind = value.get("type")
        session = params.get("sessionID")
        if session not in parents:
            continue
        info = _object(props.get("info"))
        part = _object(props.get("part"))
        identity = (
            info.get("id")
            if kind == "message.updated"
            else props.get("messageID") or part.get("messageID")
        )
        if not isinstance(identity, str):
            continue
        message, _ = messages.setdefault(
            identity,
            ({"info": {"id": identity, "sessionID": session}, "parts": []}, received),
        )
        if kind == "message.updated" and info.get("sessionID") == session:
            message["info"] = deepcopy(info)
        elif kind == "message.part.updated" and part.get("sessionID") == session:
            message["parts"] = [
                p for p in message["parts"] if p.get("id") != part.get("id")
            ] + [deepcopy(part)]
        elif kind == "message.part.delta" and props.get("field") in {"text"}:
            target = next(
                (p for p in message["parts"] if p.get("id") == props.get("partID")),
                None,
            )
            if target is not None and isinstance(props.get("delta"), str):
                target["text"] = target.get("text", "") + props["delta"]
        elif kind == "message.removed":
            messages.pop(identity, None)
            continue
        elif kind == "message.part.removed":
            message["parts"] = [
                p for p in message["parts"] if p.get("id") != props.get("partID")
            ]
        messages[identity] = (message, received)
    # HTTP completion checkpoints are authoritative even if an older SSE frame
    # was received later by the reader thread.
    for params, received in checkpoints:
        for message in params.get("messages", []):
            if not isinstance(message, dict):
                continue
            info = _object(message.get("info"))
            if info.get("sessionID") == params["sessionID"] and isinstance(
                info.get("id"), str
            ):
                messages[info["id"]] = (deepcopy(message), received)
    turns = {}
    items = []
    totals = []
    points = []
    thread_totals = {}
    thread_costs = {}
    models = {}
    costs = []
    turn_totals = {}
    turn_costs = {}
    for identity, (message, received) in messages.items():
        info = message["info"]
        role = info.get("role")
        times = _object(info.get("time"))
        thread = info.get("sessionID")
        if role not in {"user", "assistant"}:
            continue
        turn_id = identity if role == "user" else info.get("parentID")
        started = _at(times.get("created"), received)
        ended = _at(times.get("completed"), None)
        if turn_id:
            turn = turns.setdefault(
                (thread, turn_id),
                {
                    "id": turn_id,
                    "thread": thread,
                    "started": started,
                    "ended": None,
                    "status": "running",
                },
            )
            turn["started"] = min(turn["started"], started)
            if ended:
                turn.update(
                    ended=max(turn.get("ended") or ended, ended),
                    status="failed" if info.get("error") else "completed",
                )
        parts = message.get("parts", [])
        if not isinstance(parts, list):
            parts = []
        text = "\n".join(
            part.get("text", "")
            for part in parts
            if isinstance(part, dict) and part.get("type") == "text"
        )
        # Retain the original native record in every projected message source.
        if text or role == "user":
            item = {
                "id": identity,
                "type": "userMessage" if role == "user" else "agentMessage",
                "text": text,
                "native": message,
                "provider": "opencode",
            }
            items.append(
                {
                    "id": identity,
                    "thread": thread,
                    "turn": turn_id,
                    "started": started,
                    "ended": ended if role == "assistant" else started,
                    "item": item,
                }
            )
        for part in parts:
            if not isinstance(part, dict) or part.get("type") != "tool":
                continue
            state = _object(part.get("state"))
            native_time = _object(state.get("time"))
            inputs = state.get("input") or {}
            command = inputs.get("command") if isinstance(inputs, dict) else None
            item = {
                "id": part.get("id") or part.get("callID"),
                "type": "commandExecution" if isinstance(command, str) else "toolCall",
                "toolName": part.get("tool"),
                "native": part,
                "provider": "opencode",
                "status": state.get("status"),
            }
            if isinstance(command, str):
                output = state.get("output")
                exit_code = _object(state.get("metadata")).get("exit")
                # The isolated command worker returns a JSON result envelope.
                # Keep the native part intact while rendering stdout/stderr as text.
                try:
                    result = json.loads(output) if isinstance(output, str) else None
                except (ValueError, TypeError):
                    result = None
                if (
                    isinstance(result, dict)
                    and isinstance(result.get("stdout"), str)
                    and isinstance(result.get("stderr"), str)
                    and type(result.get("exit_code")) is int
                ):
                    output = result["stdout"] + result["stderr"]
                    exit_code = result["exit_code"]
                item.update(
                    command=command, aggregatedOutput=output, exitCode=exit_code
                )
            if part.get("tool") == "task":
                child = _object(state.get("metadata")).get("sessionId")
                if child in parents and parents[child] == thread:
                    item.update(type="collabAgentSpawnToolCall", agentThreadId=child)
            if not item["id"]:
                continue
            items.append(
                {
                    "id": item["id"],
                    "thread": thread,
                    "turn": turn_id,
                    "started": _at(native_time.get("start"), started),
                    "ended": _at(native_time.get("end"), ended),
                    "item": item,
                }
            )
        if role == "assistant":
            tokens = info.get("tokens")
            cache = _object(tokens.get("cache")) if isinstance(tokens, dict) else {}
            values = (
                [tokens.get(key) for key in ("input", "output", "reasoning")]
                if isinstance(tokens, dict)
                else []
            )
            values.extend(cache.get(key) for key in ("read", "write"))
            if len(values) != 5 or any(
                type(value) is not int or value < 0 for value in values
            ):
                totals.append(None)
                thread_totals.setdefault(thread, []).append(None)
                turn_totals.setdefault((thread, turn_id), []).append(None)
                continue
            fresh, output, reasoning, read, write = values
            # OpenCode stores non-cached input and non-reasoning output separately.
            usage = {
                "inputTokens": fresh + read + write,
                "cachedInputTokens": read,
                "cacheWriteInputTokens": write,
                "outputTokens": output + reasoning,
                "reasoningOutputTokens": reasoning,
                "totalTokens": fresh + read + write + output + reasoning,
            }
            totals.append(usage)
            thread_totals.setdefault(thread, []).append(usage)
            turn_totals.setdefault((thread, turn_id), []).append(usage)
            effective = "/".join(
                value if isinstance(value, str) else ""
                for value in (info.get("providerID"), info.get("modelID"))
            )
            models[thread] = (
                effective
                if info.get("modelID")
                else (model if thread == root_thread else None)
            )
            item_cost = estimate_native(
                models[thread], usage, catalogs.get(models[thread])
            )
            costs.append(item_cost)
            thread_costs.setdefault(thread, []).append(item_cost)
            turn_costs.setdefault((thread, turn_id), []).append(item_cost)
            cumulative = (
                {
                    key: sum(total[key] for total in thread_totals[thread])
                    for key in usage
                }
                if all(total is not None for total in thread_totals[thread])
                else None
            )
            if cumulative is not None:
                values = turn_totals[(thread, turn_id)]
                turn_usage = (
                    {key: sum(value[key] for value in values) for key in usage}
                    if all(value is not None for value in values)
                    else None
                )
                points.append(
                    {
                        "at": ended or received,
                        "thread": thread,
                        "turn": turn_id,
                        "usage": cumulative,
                        "cost": sum_costs(thread_costs[thread], models[thread]),
                        "turn_usage": turn_usage,
                        "turn_cost": (
                            sum_costs(turn_costs[(thread, turn_id)], models[thread])
                            if turn_usage is not None
                            else {"amount": None}
                        ),
                    }
                )
    usage = (
        {key: sum(total[key] for total in totals) for key in totals[0]}
        if totals and all(total is not None for total in totals)
        else None
    )
    per_thread = {
        thread: (
            {key: sum(total[key] for total in values) for key in values[0]}
            if values and all(v is not None for v in values)
            else None
        )
        for thread, values in thread_totals.items()
    }
    if set(parents) - set(per_thread):
        usage = None
    cost = sum_costs(costs, model)
    if usage is None:
        cost.update(amount=None, reason="Inclusive token usage is incomplete.")
    cost.update(
        per_thread={
            thread: sum_costs(thread_costs.get(thread, []), models.get(thread))
            for thread in parents
        },
        model_provenance={
            thread: "native OpenCode assistant response metadata" for thread in models
        },
    )
    projected_turns = []
    for (thread, turn_id), lane in turns.items():
        values = turn_totals.get((thread, turn_id), [])
        turn_usage = (
            {key: sum(value[key] for value in values) for key in values[0]}
            if values and all(value is not None for value in values)
            else None
        )
        turn_cost = (
            sum_costs(turn_costs.get((thread, turn_id), []), models.get(thread))
            if turn_usage is not None
            else {"amount": None}
        )
        projected_turns.append({**lane, "usage": turn_usage, "cost": turn_cost})
    return {
        "turns": projected_turns,
        "items": sorted(items, key=lambda item: item["started"]),
        "threads": [
            {
                "id": thread,
                "parent": parent,
                **({"title": titles[thread]} if thread in titles else {}),
            }
            for thread, parent in parents.items()
        ],
        "usage": usage,
        "usage_by_thread": per_thread,
        "usage_points": points,
        "telemetry": telemetry,
        "telemetry_coverage": (
            "observed adapter OTLP spans from native OpenCode records; completeness reported on invocation"
            if telemetry
            else "not observed; historical/native OpenCode HTTP message snapshots may have no telemetry"
        ),
        "uncorrelated_thread_count": 0,
        "clock": "native message timestamps; runner receipt fallback",
        "cost": cost,
        "cost_reason": cost.get("reason") or cost["basis"],
    }


def estimate_native(model, usage, rates):
    metadata = {
        "currency": "USD",
        "model": model,
        "catalog_date": None,
        "source": None,
        "basis": "API-equivalent estimate from the pinned OpenCode runtime catalog; not a Go subscription charge or invoice",
        "source_record": {
            "endpoint": "/provider",
            "runtime": "1.18.33",
            "provenance": "runtime-reported catalog",
        },
    }

    def unknown(reason):
        return {**metadata, "amount": None, "reason": reason}

    if not isinstance(rates, dict):
        return _agent_activity_cost.estimate(model, usage)
    if not isinstance(usage, dict):
        return unknown("Token usage is unavailable.")
    keys = ("inputTokens", "cachedInputTokens", "cacheWriteInputTokens", "outputTokens")
    if any(type(usage.get(k)) is not int or usage[k] < 0 for k in keys):
        return unknown("Token categories are incomplete.")
    if (
        usage["cachedInputTokens"] + usage["cacheWriteInputTokens"]
        > usage["inputTokens"]
    ):
        return unknown("Input categories overlap.")
    selected = rates
    tiers = rates.get("tiers", [])
    if not isinstance(tiers, list):
        return unknown("Runtime context price tiers are invalid.")
    if any(
        not isinstance(tier, dict)
        or not isinstance(tier.get("tier"), dict)
        or type(tier["tier"].get("size")) is not int
        for tier in tiers
    ):
        return unknown("Runtime context price tiers are invalid.")
    for tier in sorted(tiers, key=lambda value: value["tier"]["size"]):
        condition = tier["tier"]
        if (
            condition.get("type") == "context"
            and type(condition.get("size")) is int
            and usage["inputTokens"] > condition["size"]
        ):
            selected = tier
    values = [
        selected.get("input"),
        _object(selected.get("cache")).get("read"),
        _object(selected.get("cache")).get("write"),
        selected.get("output"),
    ]
    if any(
        type(v) not in {int, float} or not math.isfinite(v) or v < 0 for v in values
    ):
        return unknown("Runtime price categories are incomplete.")
    inputs, read, write, output = (usage[k] for k in keys)
    amount = sum(
        Decimal(str(rate)) * tokens
        for rate, tokens in zip(values, [inputs - read - write, read, write, output])
    ) / Decimal(1000000)
    return {**metadata, "amount": float(amount), "reason": None}


def sum_costs(values, model):
    base = values[-1] if values else _agent_activity_cost.estimate(model, None)
    return {
        **base,
        "model": model,
        "amount": (
            sum(value["amount"] for value in values)
            if values and all(v["amount"] is not None for v in values)
            else None
        ),
        "reason": (
            None
            if values and all(v["amount"] is not None for v in values)
            else "Every included request requires observed model, token categories and matching price metadata."
        ),
    }
