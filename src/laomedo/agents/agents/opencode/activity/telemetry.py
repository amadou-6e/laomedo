"""Real OTLP spans derived from observed OpenCode records, never native SDK claims."""

from datetime import datetime
from datetime import timezone
import laomedo.agents.activity.runner.feed as _runner_feed
import laomedo.agents.activity.runner.settings as _runner_settings


def export_attempt(root, start, session, model):
    if _runner_settings.Settings().otel != "1":
        return False
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.trace import set_span_in_context
    import requests
    import laomedo.agents.activity.runner.telemetry as _runner_telemetry
    import laomedo.agents.activity.projection as _activity_projection

    records = []
    cursor = start
    while True:
        page = _runner_feed.read_feed(
            root / "activity-events.jsonl", after=cursor, limit=200
        )
        records.extend(
            {"raw": item["event"], "received_at": item["received_at"]}
            for item in page["events"]
        )
        if len(records) > 10000:
            raise ValueError("opencode_telemetry_projection_limit")
        cursor = page["next_after"]
        if not page["has_more"]:
            break
    projection = _activity_projection.project(records, root_thread=session, model=model)
    before = _runner_feed.line_count(root / "otel-events.jsonl")
    receiver = _runner_telemetry.LaunchTelemetry(
        root, provenance="adapter-observed OpenCode activity"
    )
    provider = TracerProvider()
    http = requests.Session()
    http.trust_env = False
    try:
        exporter = OTLPSpanExporter(
            endpoint=f"http://127.0.0.1:{receiver.server.server_port}/v1/traces",
            headers={"Authorization": "Bearer " + receiver.token},
            timeout=5,
            session=http,
        )
        provider.add_span_processor(SimpleSpanProcessor(exporter))
        tracer = provider.get_tracer("laomedo.opencode.observer", "1")
        end = int(datetime.now(timezone.utc).timestamp() * 1_000_000_000)

        def ns(value):
            return (
                int(datetime.fromisoformat(value).timestamp() * 1_000_000_000)
                if value
                else end
            )

        invocation = tracer.start_span(
            "opencode.invocation",
            attributes={"conversation.id": session, "event.kind": "adapter-observed"},
            start_time=min(
                (ns(lane["started"]) for lane in projection["turns"]), default=end
            ),
        )
        thread_spans = {}
        try:
            for thread in projection["threads"]:
                identity = thread["id"]
                usage = projection["usage_by_thread"].get(identity) or {}
                cost = projection["cost"].get("per_thread", {}).get(identity) or {}
                attrs = {"conversation.id": identity, "event.kind": "adapter-observed"}
                if thread["parent"]:
                    attrs["sender_thread_id"] = thread["parent"]
                if cost.get("model"):
                    attrs["model"] = cost["model"]
                for source, target in [
                    ("inputTokens", "input_token_count"),
                    ("outputTokens", "output_token_count"),
                    ("cachedInputTokens", "cached_input_token_count"),
                    ("reasoningOutputTokens", "reasoning_output_token_count"),
                ]:
                    if source in usage:
                        attrs[target] = usage[source]
                lanes = [
                    lane for lane in projection["turns"] if lane["thread"] == identity
                ]
                started = min((ns(lane["started"]) for lane in lanes), default=end)
                thread_spans[identity] = tracer.start_span(
                    "opencode.session",
                    context=set_span_in_context(invocation),
                    attributes=attrs,
                    start_time=started,
                )
            turns = {}
            for lane in projection["turns"]:
                key = lane["thread"], lane["id"]
                turns[key] = tracer.start_span(
                    "opencode.turn",
                    context=set_span_in_context(thread_spans[lane["thread"]]),
                    attributes={
                        "conversation.id": lane["thread"],
                        "turn.id": lane["id"],
                    },
                    start_time=ns(lane["started"]),
                )
            for lane in projection["items"]:
                item = lane["item"]
                attrs = {"conversation.id": lane["thread"], "call.id": lane["id"]}
                if item.get("toolName"):
                    attrs["tool_name"] = item["toolName"]
                parent = (
                    turns.get((lane["thread"], lane["turn"]))
                    or thread_spans[lane["thread"]]
                )
                span = tracer.start_span(
                    "opencode." + item["type"],
                    context=set_span_in_context(parent),
                    attributes=attrs,
                    start_time=ns(lane["started"]),
                )
                span.end(end_time=max(ns(lane["started"]), ns(lane["ended"])))
            for lane in projection["turns"]:
                turns[lane["thread"], lane["id"]].end(
                    end_time=max(ns(lane["started"]), ns(lane["ended"]))
                )
            for thread, span in thread_spans.items():
                ended = max(
                    (
                        ns(lane["ended"])
                        for lane in projection["turns"]
                        if lane["thread"] == thread
                    ),
                    default=end,
                )
                span.end(end_time=ended)
        finally:
            invocation.end()
        if not provider.force_flush(timeout_millis=5000):
            raise RuntimeError("opencode_telemetry_flush_unverified")
    finally:
        provider.shutdown()
        http.close()
        receiver.close()
    expected = (
        1
        + len(projection["threads"])
        + len(projection["turns"])
        + len(projection["items"])
    )
    if _runner_feed.line_count(root / "otel-events.jsonl") - before != expected:
        raise RuntimeError("opencode_telemetry_export_incomplete")
    return True
