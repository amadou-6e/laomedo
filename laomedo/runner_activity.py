"""Bounded native notification feed. Never exposes account/RPC response records."""
import json
from datetime import datetime, timezone


def notification(event):
    if not isinstance(event, dict):
        return False
    method = event.get('method', '')
    return isinstance(method, str) and (
        method in {'thread/started', 'thread/tokenUsage/updated', 'turn/started',
                   'turn/completed', 'turn/failed', 'error'}
        or method.startswith(('item/', 'turn/plan/', 'turn/diff/')))


def receipt(event):
    return {'received_at': datetime.now(timezone.utc).isoformat(), 'event': event}


def read_feed(path, *, after=0, limit=100, tail=False, before=None):
    """Physical line cursor; incomplete writes are retried, not consumed."""
    if after < 0 or not 1 <= limit <= 200:
        raise ValueError('invalid_activity_cursor')
    events = []
    cursor = 0
    baseline = {}
    page_bytes = 0
    has_more = False
    if path.exists():
        with path.open('rb') as source:
            while True:
                if before is not None and cursor >= before:
                    break
                line = source.readline(2*1024*1024+1)
                if len(line)>2*1024*1024:
                    raise ValueError('activity_record_too_large')
                if not line.endswith(b'\n'):
                    break
                if events and page_bytes+len(line)>2*1024*1024:
                    has_more = True
                    break
                cursor += 1
                if tail:
                    value = json.loads(line)
                    event = value.get('event',{})
                    if event.get('method') == 'thread/tokenUsage/updated':
                        params=event.get('params',{})
                        baseline[params.get('threadId','unknown')]=params.get('tokenUsage')
                    continue
                if cursor <= after:
                    continue
                value = json.loads(line)
                events.append({'cursor': cursor, **value})
                page_bytes += len(line)
                if len(events) >= limit:
                    has_more = True
                    break
    return {'events': events, 'next_after': max(cursor, after), 'usage_baseline':baseline,'has_more':has_more}


def line_count(path):
    if not path.exists():
        return 0
    with path.open('rb') as source:
        return sum(1 for line in source if line.endswith(b'\n'))
