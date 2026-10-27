"""Local OTLP receiver bound to one runner launch, with an attribute allowlist."""
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import secrets
import threading

ALLOWED = frozenset({'conversation.id','thread.id','thread_id','turn.id','turn_id',
    'call.id','call_id','event.name','model','model_name','gen_ai.request.model',
    'gen_ai.response.model','input_token_count','output_token_count',
    'cached_input_token_count','reasoning_output_token_count','tool_name','duration_ms',
    'cached_token_count','cache_write_token_count','reasoning_token_count',
    'sender_thread_id','receiver_thread_id','communication_id','event.timestamp','event.kind'})


def attributes(values):
    result={}
    for pair in values:
        if pair.key not in ALLOWED:
            continue
        kind=pair.value.WhichOneof('value')
        if kind in {'string_value','int_value','double_value','bool_value'}:
            result[pair.key]=getattr(pair.value,kind)
    return result


class LaunchTelemetry:
    def __init__(self, directory, *, provenance='runtime-reported'):
        from opentelemetry.proto.collector.logs.v1.logs_service_pb2 import ExportLogsServiceRequest
        from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceRequest
        token=secrets.token_urlsafe(32)
        self.token=token
        self.output=(directory/'otel-events.jsonl').open('a',encoding='utf-8')
        self.lock=threading.Lock()
        owner=self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args):
                pass
            def do_POST(self):
                if not secrets.compare_digest(self.headers.get('Authorization',''),'Bearer '+token):
                    self.send_error(401);return
                if self.path not in {'/v1/logs','/v1/traces'}:
                    self.send_error(404);return
                try:
                    length=int(self.headers.get('Content-Length','0'))
                    if not 0<length<=8*1024*1024:
                        self.send_error(413);return
                    message=ExportLogsServiceRequest() if self.path=='/v1/logs' else ExportTraceServiceRequest()
                    message.ParseFromString(self.rfile.read(length))
                    records=[]
                    for resource in message.resource_logs if self.path=='/v1/logs' else message.resource_spans:
                        for scope in resource.scope_logs if self.path=='/v1/logs' else resource.scope_spans:
                            for record in scope.log_records if self.path=='/v1/logs' else scope.spans:
                                value={'signal':'log' if self.path=='/v1/logs' else 'span',
                                    'provenance':provenance,
                                    'trace_id':record.trace_id.hex(),'span_id':record.span_id.hex(),
                                    'attributes':attributes(record.attributes)}
                                if self.path=='/v1/traces':
                                    value.update(name=record.name,parent_span_id=record.parent_span_id.hex(),
                                        started_ns=str(record.start_time_unix_nano),ended_ns=str(record.end_time_unix_nano),
                                        status=record.status.code)
                                else:
                                    value['timestamp_ns']=str(record.time_unix_nano)
                                records.append(value)
                    with owner.lock:
                        for value in records:
                            owner.output.write(json.dumps({'received_at':datetime.now(timezone.utc).isoformat(),
                                'event':{'method':'otel/record','params':value}})+'\n')
                        owner.output.flush()
                    self.send_response(200)
                    self.send_header('Content-Type','application/x-protobuf')
                    self.send_header('Content-Length','0');self.end_headers()
                except Exception:
                    self.send_error(400)
        self.server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        self.server.daemon_threads=True
        self.server.timeout=10
        threading.Thread(target=self.server.serve_forever,daemon=True).start()

    def arguments(self):
        base='http://host.docker.internal:'+str(self.server.server_port)
        def exporter(signal):
            return '{otlp-http={endpoint="'+base+'/v1/'+signal+'",protocol="binary",headers={Authorization="Bearer '+self.token+'"}}}'
        return ['-c','otel.exporter='+exporter('logs'),'-c','otel.trace_exporter='+exporter('traces'),
                '-c','otel.log_user_prompt=false']

    def close(self):
        self.server.shutdown();self.server.server_close()
        with self.lock:
            self.output.close()
