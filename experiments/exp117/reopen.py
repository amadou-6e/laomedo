"""Reopen the exact host binding read-only in a fresh process."""
import argparse
import json
import sqlite3
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument('--state', type=Path, required=True)
parser.add_argument('--reopen-host', action='store_true')
args = parser.parse_args()
path = args.state.expanduser().resolve() / 'join.sqlite3'
with sqlite3.connect(path.as_uri() + '?mode=ro', uri=True) as db:
    db.row_factory = sqlite3.Row
    rows = [dict(row) for row in db.execute('''SELECT
        c.client_request_id,c.run_id,c.invocation_id,c.flow_id,
        c.graph_run_id,r.trace_id,r.status,r.dispatch_attempts,
        w.runner_request_id,w.runner_request_hash,w.runner_run_id,
        w.runner_provider,w.runner_raw_event_ref
        FROM langflow_client_requests c JOIN runs r ON r.run_id=c.run_id
        JOIN workflow_invocations w ON w.invocation_id=c.invocation_id''')]
print(json.dumps(rows))
