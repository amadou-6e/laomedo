"""Internal SDK/receiver round trip; not live provider acceptance."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from laomedo.opencode_activity import retain_messages, project
from laomedo.opencode_telemetry import export_attempt
from laomedo.runner_activity import read_feed


try:
    import opentelemetry.sdk.trace
    import opentelemetry.exporter.otlp.proto.http.trace_exporter
except ImportError:
    OBSERVABILITY_SDK_AVAILABLE = False
else:
    OBSERVABILITY_SDK_AVAILABLE = True


class OpenCodeTelemetryTests(unittest.TestCase):
    @unittest.skipUnless(OBSERVABILITY_SDK_AVAILABLE, "observability optional dependencies are not installed")
    def test_real_sdk_otlp_roundtrip_has_adapter_provenance_without_prompt_content(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {'LAOMEDO_RUNNER_OTEL':'1','OTEL_SDK_DISABLED':'false'}):
            root=Path(directory)
            message={'info':{'id':'m','sessionID':'ses_root','role':'assistant','parentID':'u',
                            'time':{'created':1000,'completed':2000},'tokens':{'input':2,'output':1,'reasoning':0,'cache':{'read':0,'write':0}}},
                     'parts':[{'type':'text','text':'do not put this in spans'}]}
            retain_messages(root,'ses_root',[message])
            self.assertTrue(export_attempt(root,0,'ses_root','test/model'))
            records=read_feed(root/'otel-events.jsonl')['events']
            self.assertEqual(len(records),4)
            self.assertTrue(all(r['event']['params']['provenance'].startswith('adapter-observed') for r in records))
            self.assertNotIn('do not put this',json.dumps(records))
            projected=project([{'raw':r['event'],'received_at':r['received_at']} for r in records],root_thread='ses_root')
            # Generic dispatch only uses OpenCode projection when native evidence is present.
            self.assertEqual(len(projected['telemetry']),4)
