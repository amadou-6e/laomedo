"""Extract a content-free structural report from this probe's private receipts."""
from collections import Counter
from datetime import datetime
import argparse
import hashlib
import json
from pathlib import Path
import re
from opentelemetry.proto.collector.logs.v1.logs_service_pb2 import ExportLogsServiceRequest
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceRequest
from google.protobuf.message import DecodeError


def analyze(private, output):
    native=[json.loads(line) for line in (private/'native.jsonl').read_text(encoding='utf-8').splitlines()]
    completed=[record['native']['params'] for record in native if record['native'].get('method')=='item/completed']
    tools=[params for params in completed if params['item']['type']=='commandExecution']
    usage=[{'received_at':record['received_at'],'thread_id':record['native']['params'].get('threadId'),
            'turn_id':record['native']['params'].get('turnId'),'usage':record['native']['params']['tokenUsage']}
           for record in native if record['native'].get('method')=='thread/tokenUsage/updated']
    names=Counter();span_count=0;parent_count=0;span_timed=0;log_traces=0;source_times=0;attribute_times=0
    models=set()
    otel_call_ids=set();native_call_ids={params['item']['id'] for params in tools};attribute_kinds={}
    for path in sorted(private.glob('otlp-*.pb')):
        # Read both protobuf schemas only when their top-level resource shape
        # validates a populated scope payload. Unknown wire fields are ignored.
        logs=ExportLogsServiceRequest();traces=ExportTraceServiceRequest()
        try:logs.ParseFromString(path.read_bytes())
        except DecodeError:logs.Clear()
        try:traces.ParseFromString(path.read_bytes())
        except DecodeError:traces.Clear()
        for resource in logs.resource_logs:
            for scope in resource.scope_logs:
                for record in scope.log_records:
                    attributes={attr.key:attr.value for attr in record.attributes}
                    if 'event.name' not in attributes:continue
                    candidate=attributes.get('event.name')
                    name=candidate.string_value if candidate else record.event_name
                    if re.fullmatch(r'codex\.[a-zA-Z0-9_.]+',name):names[name]+=1
                    else:names['other_or_unnamed']+=1
                    source_times+=bool(record.time_unix_nano)
                    clock=attributes.get('event.timestamp')
                    if clock and clock.string_value:
                        try:datetime.fromisoformat(clock.string_value.replace('Z','+00:00'));attribute_times+=1
                        except ValueError:pass
                    model=attributes.get('model')
                    if model and re.fullmatch(r'gpt-[A-Za-z0-9._-]+',model.string_value):models.add(model.string_value)
                    log_traces+=bool(record.trace_id)
                    for key,value in attributes.items():attribute_kinds[key]=value.WhichOneof('value')
                    value=attributes.get('call_id')
                    if value and value.string_value:otel_call_ids.add(value.string_value)
        for resource in traces.resource_spans:
            for scope in resource.scope_spans:
                for span in scope.spans:
                    if len(span.trace_id)!=16 or len(span.span_id)!=8:continue
                    span_count+=1;parent_count+=bool(span.parent_span_id)
                    span_timed+=bool(span.start_time_unix_nano and span.end_time_unix_nano>=span.start_time_unix_nano)
    report={'native_message_types':dict(Counter(params['item']['type'] for params in completed)),
        'tool_calls_with_command':sum(bool(params['item'].get('command')) for params in tools),
        'tool_results_with_output':sum('aggregatedOutput' in params['item'] for params in tools),
        'tool_exit_codes':[params['item'].get('exitCode') for params in tools],
        'distinct_native_turns':len({record['native']['params']['turn']['id'] for record in native if record['native'].get('method')=='turn/started'}),
        'usage_updates':usage,'otel_event_counts':dict(names),'otel_logs_with_trace_id':log_traces,
        'otel_logs_with_source_timestamp':source_times,'otel_logs_with_event_timestamp_attribute':attribute_times,
        'observed_models':sorted(models),'otel_spans':span_count,
        'otel_spans_with_parent_id':parent_count,'otel_spans_with_start_end':span_timed,
        'matching_native_otel_tool_call_ids':len(native_call_ids & otel_call_ids),
        'correlation_warning':'A same-thread match is not a graph-run/invocation match; no inferred parent or billing identity.',
        'raw_content_exported':False,'native_sha256':hashlib.sha256((private/'native.jsonl').read_bytes()).hexdigest(),
        'analyzer_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    output.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'native_turns':report['distinct_native_turns'],'tool_calls':len(tools),'otel_spans':span_count,'matching_tool_ids':report['matching_native_otel_tool_call_ids']}))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--private',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();analyze(args.private,args.output)
