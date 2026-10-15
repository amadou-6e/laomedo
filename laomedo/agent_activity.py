"""Owner-scoped native activity receipts; inspection never starts an agent."""
from contextlib import contextmanager
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sqlite3
from uuid import uuid4


def now():
    return datetime.now(timezone.utc).isoformat()


class ActivityStore:
    def __init__(self, path, *, read_only=False):
        self.path = Path(path).resolve()
        self.read_only = read_only
        if read_only:
            if not self.path.is_file():
                raise LookupError('agent_activity_not_found')
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.db() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS agent_activity_runs (
                  id TEXT PRIMARY KEY, owner TEXT NOT NULL, flow TEXT NOT NULL,
                  node TEXT NOT NULL, provider TEXT NOT NULL, started TEXT NOT NULL,
                  ended TEXT, status TEXT NOT NULL, stream_state TEXT NOT NULL,
                  reason TEXT, native_session TEXT, usage TEXT);
                CREATE INDEX IF NOT EXISTS activity_owner ON agent_activity_runs(owner,flow,node,started);
                CREATE TABLE IF NOT EXISTS agent_activity_receipts (
                  run TEXT NOT NULL, sequence INTEGER NOT NULL, received TEXT NOT NULL,
                  raw TEXT NOT NULL, PRIMARY KEY(run,sequence));
            ''')

    @contextmanager
    def db(self):
        db = sqlite3.connect(self.path.as_uri()+'?mode=ro',uri=True,timeout=15) if self.read_only else sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def start(self, owner, flow, node, provider='codex-cli'):
        if not all(isinstance(v,str) and v and len(v)<=200 for v in (owner,flow,node)):
            raise ValueError('agent_activity_identity_required')
        run = str(uuid4())
        with self.db() as db:
            db.execute('INSERT INTO agent_activity_runs VALUES (?,?,?,?,?,?,NULL,?,?,NULL,NULL,NULL)',
                       (run,owner,flow,node,provider,now(),'running','partial'))
        return run

    def append(self, run, event):
        if not isinstance(event,dict):
            raise ValueError('agent_activity_event_invalid')
        raw=json.dumps(event,ensure_ascii=False)
        with self.db() as db:
            record=db.execute('SELECT ended FROM agent_activity_runs WHERE id=?',(run,)).fetchone()
            if record is None or record['ended'] is not None:
                raise ValueError('agent_activity_closed')
            seq=db.execute('SELECT COALESCE(MAX(sequence),0)+1 FROM agent_activity_receipts WHERE run=?',(run,)).fetchone()[0]
            db.execute('INSERT INTO agent_activity_receipts VALUES (?,?,?,?)',(run,seq,now(),raw))
            if event.get('type')=='thread.started' and isinstance(event.get('thread_id'),str):
                db.execute('UPDATE agent_activity_runs SET native_session=? WHERE id=?',(event['thread_id'],run))
            if event.get('type')=='turn.completed' and isinstance(event.get('usage'),dict):
                db.execute('UPDATE agent_activity_runs SET usage=? WHERE id=?',(json.dumps(event['usage']),run))

    def finish(self, run, status, *, complete=False, reason=None):
        if status not in {'completed','failed','cancelled','timed_out'}:
            raise ValueError('agent_activity_status_invalid')
        with self.db() as db:
            db.execute('UPDATE agent_activity_runs SET ended=?,status=?,stream_state=?,reason=? WHERE id=? AND ended IS NULL',
                       (now(),status,'complete' if complete else 'partial',reason,run))

    def runs(self, owner, flow, node):
        with self.db() as db:
            rows=db.execute('''SELECT r.*, (SELECT COUNT(*) FROM agent_activity_receipts e WHERE e.run=r.id) event_count
                FROM agent_activity_runs r WHERE owner=? AND flow=? AND node=? ORDER BY started DESC,id DESC LIMIT 50''',
                (owner,flow,node)).fetchall()
        return [self._summary(row) for row in rows]

    @staticmethod
    def _summary(row):
        result=dict(row)
        for key in ('owner','flow','node'): result.pop(key,None)
        result['usage']=json.loads(result['usage']) if result['usage'] is not None else None
        result['action_uniqueness']='uncertain'
        return result

    def read(self, owner, flow, node, run, after=0, limit=100):
        with self.db() as db:
            row=db.execute('SELECT * FROM agent_activity_runs WHERE owner=? AND flow=? AND node=? AND id=?',
                           (owner,flow,node,run)).fetchone()
            if row is None: raise LookupError('agent_activity_not_found')
            count=db.execute('SELECT COUNT(*) FROM agent_activity_receipts WHERE run=?',(run,)).fetchone()[0]
            rows=db.execute('SELECT sequence,received,raw FROM agent_activity_receipts WHERE run=? AND sequence>? ORDER BY sequence LIMIT ?',
                            (run,after,limit)).fetchall()
        events=[]
        for item in rows:
            raw=json.loads(item['raw'])
            events.append({'sequence':item['sequence'],'received_at':item['received'],
                           'kind':raw.get('type','unknown'),'provenance':'observed','raw':raw})
        return {'run':{**self._summary(row),'event_count':count},'events':events,
                'next_after':events[-1]['sequence'] if events else after,
                'has_more':bool(events and events[-1]['sequence']<count)}


def capture_for(component):
    """Opt-in host configuration; refuse dispatch if configured capture cannot reserve."""
    path=os.environ.get('LAOMEDO_AGENT_ACTIVITY_DB')
    if not path: return None
    graph=component.graph
    store=ActivityStore(path)
    run=store.start(str(component._user_id or ''),str(graph.flow_id or ''),component._vertex.id)
    return store,run
