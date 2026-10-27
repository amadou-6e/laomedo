"""Internal OTLP controls; real Docker/Claude proof is separate."""
import json
from pathlib import Path
import tempfile
import unittest
from urllib.request import Request,urlopen
from urllib.error import HTTPError
from laomedo.activity.claude_telemetry import ClaudeTelemetry
from laomedo.activity.agent_activity.projection import project

try:
 from opentelemetry.proto.collector.logs.v1.logs_service_pb2 import ExportLogsServiceRequest
 OBSERVABILITY_AVAILABLE=True
except ImportError:
 OBSERVABILITY_AVAILABLE=False

@unittest.skipUnless(OBSERVABILITY_AVAILABLE,"observability optional dependencies are not installed")
class ClaudeTelemetryTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
  self.receiver=ClaudeTelemetry(self.root,run_id='run',thread_id='session',turn_id='turn')
  self.addCleanup(self.temp.cleanup);self.addCleanup(self.receiver.close)
 def post(self,path,message,token=None):
  return urlopen(Request('http://127.0.0.1:'+str(self.receiver.server.server_port)+path,data=message.SerializeToString(),headers={'Authorization':'Bearer '+(token or self.receiver.token),'Content-Type':'application/x-protobuf'}),timeout=5)
 def test_logs_traces_metrics_scoping_and_redaction(self):
  from opentelemetry.proto.collector.logs.v1.logs_service_pb2 import ExportLogsServiceRequest
  from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceRequest
  from opentelemetry.proto.collector.metrics.v1.metrics_service_pb2 import ExportMetricsServiceRequest
  logs=ExportLogsServiceRequest();log=logs.resource_logs.add().scope_logs.add().log_records.add();log.body.string_value='secret'
  for key,value in [('event.name','api_request'),('session.id','session'),('user.email','private@example.com'),('prompt','secret prompt')]:
   attr=log.attributes.add();attr.key=key;attr.value.string_value=value
  spans=ExportTraceServiceRequest();span=spans.resource_spans.add().scope_spans.add().spans.add();span.name='claude_code.llm_request';span.trace_id=b'a'*16;span.span_id=b'b'*8
  metrics=ExportMetricsServiceRequest();metric=metrics.resource_metrics.add().scope_metrics.add().metrics.add();metric.name='claude_code.token.usage';metric.sum.data_points.add().as_int=12
  for path,message in [('/v1/logs',logs),('/v1/traces',spans),('/v1/metrics',metrics)]:
   with self.post(path,message) as response:self.assertEqual(response.status,200)
  records=[json.loads(line) for line in (self.root/'otel-events.jsonl').read_text().splitlines()];values=[r['event']['params'] for r in records]
  self.assertEqual({v['signal'] for v in values},{'log','span','metric'})
  self.assertTrue(all(v['attributes']['conversation.id']=='session' and v['attributes']['turn.id']=='turn' for v in values))
  self.assertNotIn('secret',json.dumps(records));self.assertNotIn('private@example',json.dumps(records))
  view=project([{'raw':r,'received_at':r['received_at']} for r in records],root_thread='session');self.assertEqual(len(view['telemetry']),3);self.assertIsNone(view['usage'])
 def test_local_authenticated_capability_not_in_argv(self):
  from opentelemetry.proto.collector.logs.v1.logs_service_pb2 import ExportLogsServiceRequest
  self.assertEqual(self.receiver.server.server_address[0],'127.0.0.1')
  with self.assertRaises(HTTPError) as refused:self.post('/v1/logs',ExportLogsServiceRequest(),token='wrong')
  self.assertEqual(refused.exception.code,401);self.assertNotIn(self.receiver.token,' '.join(self.receiver.docker_arguments()))
  self.assertIn('OTEL_LOG_USER_PROMPTS=0',self.receiver.environment.read_text());self.assertIn('OTEL_LOG_TOOL_CONTENT=0',self.receiver.environment.read_text())
 def test_conflicting_native_session_is_not_silently_relabelled(self):
  value=self.receiver.record({'session.id':'different'},signal='log',name='event');self.assertTrue(value['scope_conflict']);self.assertEqual(value['attributes']['session.id'],'different')
 def test_close_removes_environment_and_releases_receiver(self):
  receiver=ClaudeTelemetry(self.root,run_id='next',thread_id='session',turn_id='next');env=receiver.environment;receiver.close();self.assertFalse(env.exists());self.assertFalse(receiver.thread.is_alive())

 def test_tool_scope_uses_explicit_native_call_ids_only(self):
  record=self.receiver.record({'tool_use_id':'call-123','gen_ai.tool.call.id':'call-123'},signal='span',name='claude_code.tool')
  self.assertEqual(record['attributes']['call.id'],'call-123')
  conflict=self.receiver.record({'tool_use_id':'call-one','gen_ai.tool.call.id':'call-two'},signal='span',name='claude_code.tool')
  self.assertTrue(conflict['scope_conflict']);self.assertNotIn('call.id',conflict['attributes'])

 def test_invalid_authenticated_export_marks_capture_failed_without_persisting_payload(self):
  req=Request('http://127.0.0.1:'+str(self.receiver.server.server_port)+'/v1/logs',data=b'\xff',headers={'Authorization':'Bearer '+self.receiver.token,'Content-Type':'application/x-protobuf'})
  with self.assertRaises(HTTPError) as refused:urlopen(req,timeout=5)
  self.assertEqual(refused.exception.code,400);self.assertTrue(self.receiver.failed)
  self.assertEqual((self.root/'otel-events.jsonl').read_text(),'')

 def test_export_capacity_is_bounded_and_does_not_write_partial_batch(self):
  from opentelemetry.proto.collector.logs.v1.logs_service_pb2 import ExportLogsServiceRequest
  logs=ExportLogsServiceRequest();scope=logs.resource_logs.add().scope_logs.add()
  for _ in range(4097):scope.log_records.add()
  with self.assertRaises(HTTPError) as refused:self.post('/v1/logs',logs)
  self.assertEqual(refused.exception.code,400);self.assertTrue(self.receiver.failed)
  self.assertEqual((self.root/'otel-events.jsonl').read_text(),'')

 def test_shutdown_bounds_an_interrupted_authenticated_upload(self):
  import socket,threading,time
  receiver=ClaudeTelemetry(self.root,run_id='stalled',thread_id='session',turn_id='stalled')
  before=set(threading.enumerate());client=socket.create_connection(receiver.server.server_address,timeout=2)
  try:
   client.sendall(('POST /v1/logs HTTP/1.1\r\nHost: localhost\r\nAuthorization: Bearer '+receiver.token+'\r\nContent-Length: 20\r\n\r\n').encode())
   deadline=time.monotonic()+2
   while time.monotonic()<deadline and not (set(threading.enumerate())-before):time.sleep(.01)
   closed=threading.Thread(target=receiver.close,daemon=True);closed.start();closed.join(7)
   bounded=not closed.is_alive()
  finally:
   client.close()
   if 'closed' in locals():closed.join(3)
   else:receiver.close()
  self.assertTrue(bounded,'Upload handler must not outlive bounded receiver shutdown')
  self.assertFalse(receiver.environment.exists());self.assertFalse(receiver.thread.is_alive())

 def test_rejected_authenticated_lengths_mark_capture_failed(self):
  import http.client
  for length in [None,0,8*1024*1024+1]:
   self.receiver.failed=False
   client=http.client.HTTPConnection(*self.receiver.server.server_address,timeout=5)
   try:
    client.putrequest('POST','/v1/logs');client.putheader('Authorization','Bearer '+self.receiver.token)
    if length is not None:client.putheader('Content-Length',str(length))
    client.endheaders();response=client.getresponse();self.assertEqual(response.status,413);response.read()
    self.assertTrue(self.receiver.failed)
   finally:client.close()
  self.assertEqual((self.root/'otel-events.jsonl').read_text(),'')
