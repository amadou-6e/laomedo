"""Host-owned, atomic multi-file skill proposals with append-only commit history.

The SQLite journal is trusted local state, not a signed or tamper-proof audit log.
Tree revisions retain byte identity; commit identities retain editing history even
when a later edit returns to the same bytes. No operation promotes canonical latest.
"""
from copy import deepcopy
from contextlib import contextmanager
from datetime import datetime, timezone
import difflib
import hashlib
import json
from pathlib import Path
import secrets
import sqlite3
import time
from uuid import uuid4

from laomedo.skills.skill_store import SkillStore, SkillStoreError, ConflictError, _safe_relative, _canonical_json, validate_policy, validate_draft, inventory, tree_hash, patch_for
from laomedo.skills.skill_sources import _bundle
from laomedo.skills.skill_inspection import inspect_skill
from laomedo.skills.skill_summary import summary_authoring, has_description


def proposal(value):
    """Only content and explanation can be supplied by a model."""
    value = getattr(value, 'data', getattr(value, 'text', value))
    if isinstance(value, dict) and set(value) == {'text'}:
        value = value['text']
    if isinstance(value, str):
        if len(value.encode()) > 4 * 1024 * 1024:
            raise SkillStoreError('skill_operation_invalid')
        try:
            value = json.loads(value)
        except ValueError:
            raise SkillStoreError('skill_operation_invalid') from None
    if (not isinstance(value, dict) or set(value) != {'action', 'message', 'files'} or
            value['action'] != 'modify' or not isinstance(value['message'], str) or
            not 1 <= len(value['message']) <= 2000 or not isinstance(value['files'], list) or
            not 1 <= len(value['files']) <= 128):
        raise SkillStoreError('skill_operation_invalid')
    seen = set()
    for edit in value['files']:
        if not isinstance(edit, dict) or set(edit) != {'path', 'content'}:
            raise SkillStoreError('skill_operation_invalid')
        path = _safe_relative(edit['path'])
        if (path.casefold() in seen or len(path) > 512 or
                edit['content'] is not None and (not isinstance(edit['content'], str) or
                    len(edit['content'].encode()) > 512 * 1024)):
            raise SkillStoreError('skill_operation_invalid')
        seen.add(path.casefold())
    return deepcopy(value)


class SkillOperations:
    def __init__(self, store: SkillStore, database: Path, policies: dict):
        self.store = store
        self.database = Path(database)
        self.policies = deepcopy(policies)
        for policy in self.policies.values():
            validate_policy(policy)
        with self.connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS commits (
                    id TEXT PRIMARY KEY, skill TEXT NOT NULL, record TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS heads (skill TEXT PRIMARY KEY, id TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS requests (
                    ticket TEXT PRIMARY KEY, skill TEXT NOT NULL, base TEXT NOT NULL,
                    policy TEXT NOT NULL, expires REAL NOT NULL, monotonic REAL NOT NULL,
                    proposal TEXT, result TEXT);
            ''')

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.database, timeout=15)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def _commit(self, db, record):
        identity = 'sha256:' + hashlib.sha256(_canonical_json(record)).hexdigest()
        db.execute('INSERT INTO commits VALUES (?,?,?)',
                   (identity, record['skill_id'], json.dumps(record)))
        db.execute('INSERT INTO heads VALUES (?,?) ON CONFLICT(skill) DO UPDATE SET id=excluded.id',
                   (record['skill_id'], identity))
        return {'commit_id': identity, **record}

    def _read(self, db, skill, identity):
        row = db.execute('SELECT record FROM commits WHERE id=? AND skill=?', (identity, skill)).fetchone()
        if row is None:
            raise SkillStoreError('skill_commit_unavailable')
        record = json.loads(row['record'])
        if 'sha256:' + hashlib.sha256(_canonical_json(record)).hexdigest() != identity:
            raise SkillStoreError('skill_history_integrity_failure')
        return {'commit_id': identity, **record}

    def prepare(self, skill_id, revision_id, commit_id=''):
        policy = self.policies.get(skill_id)
        if policy is None:
            raise SkillStoreError('skill_edit_not_authorized')
        snapshot = inspect_skill(self.store.root, skill_id, revision_id)
        authoring = summary_authoring(snapshot)
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            head = db.execute('SELECT id FROM heads WHERE skill=?', (skill_id,)).fetchone()
            if head is None:
                if commit_id or self.store.revision(skill_id)['revision_id'] != revision_id:
                    raise ConflictError('skill_base_changed')
                head = {'id': self._commit(db, {'skill_id': skill_id, 'revision_id': revision_id,
                    'parent_commit': None, 'created_at': datetime.now(timezone.utc).isoformat(),
                    'message': 'Import existing immutable skill', 'files': [], 'patch': '',
                    'editor': {'kind': 'import'}, 'nonce': uuid4().hex})['commit_id']}
            base = self._read(db, skill_id, head['id'])
            if (base['revision_id'] != revision_id or
                    (commit_id != head['id'] if commit_id else base['parent_commit'] is not None)):
                raise ConflictError('skill_base_changed')
            ticket = secrets.token_hex(32)
            db.execute('INSERT INTO requests(ticket,skill,base,policy,expires,monotonic) VALUES (?,?,?,?,?,?)',
                       (ticket, skill_id, head['id'], json.dumps(policy), time.time()+300, time.monotonic()))
        return {'ticket': ticket, 'base_commit': head['id'], 'snapshot': snapshot,
                'policy': policy, **authoring}

    def apply(self, ticket, operation, editor=None):
        operation = proposal(operation)
        encoded = json.dumps(operation, sort_keys=True)
        if not isinstance(ticket, str) or len(ticket) != 64:
            raise SkillStoreError('skill_ticket_invalid')
        editor = {'kind': 'operator'} if editor is None else editor
        # Provenance is supplied by the authenticated backend, never the proposal.
        if (not isinstance(editor, dict) or editor.get('kind') not in {'operator', 'agent'} or
                set(editor) - {'kind', 'run_id', 'thread_id', 'turn_id', 'trace_ref'} or
                any(not isinstance(v, str) or len(v) > 512 for v in editor.values())):
            raise SkillStoreError('skill_editor_invalid')
        if editor['kind'] == 'agent' and not editor.get('run_id'):
            raise SkillStoreError('skill_agent_provenance_required')
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT * FROM requests WHERE ticket=?', (ticket,)).fetchone()
            if row is None:
                raise SkillStoreError('skill_ticket_invalid')
            elapsed = time.monotonic()-row['monotonic']
            if time.time() > row['expires'] or elapsed < 0 or elapsed > 300:
                raise SkillStoreError('skill_ticket_expired')
            policy = json.loads(row['policy'])
            if self.policies.get(row['skill']) != policy:
                raise SkillStoreError('skill_edit_not_authorized')
            if row['result']:
                if row['proposal'] != encoded:
                    raise ConflictError('skill_request_conflict')
                return json.loads(row['result'])
            head = db.execute('SELECT id FROM heads WHERE skill=?', (row['skill'],)).fetchone()
            if head['id'] != row['base']:
                raise ConflictError('skill_base_changed')
            base = self._read(db, row['skill'], row['base'])
            before = inventory(self.store._revision_dir(row['skill'], base['revision_id']) / 'bundle')
            self.store.revision(row['skill'], base['revision_id'])
            after = dict(before)
            for edit in operation['files']:
                if edit['content'] is None:
                    if edit['path'] not in after:
                        raise SkillStoreError('skill_file_missing')
                    del after[edit['path']]
                else:
                    after[edit['path']] = edit['content'].encode()
            if not has_description(after.get('SKILL.md', b'').decode('utf-8-sig')):
                raise SkillStoreError('skill_summary_required')
            _bundle(after)
            errors = validate_draft(before, after, policy)
            if errors:
                raise SkillStoreError('skill_edit_policy_denied')
            if after == before:
                raise SkillStoreError('skill_edit_no_change')
            draft = self.store.create_draft(row['skill'], base['revision_id'], policy)
            workspace = self.store.draft_workspace(draft['draft_id'])
            for path in before.keys() - after.keys():
                (workspace / path).unlink()
            # Remove now-empty folders; empty directory identity is unsupported.
            for folder in sorted((p for p in workspace.rglob('*') if p.is_dir()),
                                 key=lambda p: len(p.parts), reverse=True):
                if not any(folder.iterdir()):
                    folder.rmdir()
            for path, content in after.items():
                target = workspace / path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(content)
            frozen = self.store.freeze_draft(draft['draft_id'], editor_kind=editor['kind'],
                edit_run_id=editor.get('run_id'), trace_ref=editor.get('trace_ref'))
            if not frozen['promotion_eligible'] or frozen['proposed_tree_hash'] != tree_hash(after):
                raise SkillStoreError('skill_draft_validation_failed')
            revision = self.store._store_revision(row['skill'], self.store._draft(draft['draft_id'])/'frozen',
                                                   base['revision_id'], draft['draft_id'])
            record = self._commit(db, {'skill_id': row['skill'], 'revision_id': revision['revision_id'],
                'parent_commit': row['base'], 'created_at': datetime.now(timezone.utc).isoformat(),
                'message': operation['message'], 'files': frozen['changed_paths'],
                'patch': patch_for(before, after), 'editor': editor, 'draft_id': draft['draft_id'],
                'policy_ref': validate_policy(policy), 'nonce': uuid4().hex})
            result = {'status': 'proposed', 'promotion_performed': False, 'commit': record,
                      'skill': {key: revision[key] for key in ('skill_id', 'revision_id', 'tree_hash')}}
            db.execute('UPDATE requests SET proposal=?, result=? WHERE ticket=?',
                       (encoded, json.dumps(result), ticket))
            return result

    def history(self, skill_id, revision_id, before=''):
        inspect_skill(self.store.root, skill_id, revision_id)
        with self.connect() as db:
            head = db.execute('SELECT id FROM heads WHERE skill=?', (skill_id,)).fetchone()
            items, visited = [], set()
            current = before or (head['id'] if head else None)
            while current and len(items) < 100:
                if current in visited:
                    raise SkillStoreError('skill_history_limit')
                visited.add(current)
                record = self._read(db, skill_id, current)
                self.store.revision(skill_id, record['revision_id'])
                items.append({key: value for key, value in record.items() if key != 'patch'})
                current = record['parent_commit']
        return {'skill_id': skill_id, 'selected_revision': revision_id, 'commits': items, 'next': current}

    def diff(self, skill_id, commit_id):
        with self.connect() as db:
            record = self._read(db, skill_id, commit_id)
            snapshot = inspect_skill(self.store.root, skill_id, record['revision_id'])
            parent = self._read(db, skill_id, record['parent_commit']) if record['parent_commit'] else None
            after = inventory(self.store._revision_dir(skill_id, snapshot['revision_id'])/'bundle')
            before = (inventory(self.store._revision_dir(skill_id, parent['revision_id'])/'bundle')
                      if parent else after)
            if parent:
                inspect_skill(self.store.root, skill_id, parent['revision_id'])
            if patch_for(before, after) != record['patch']:
                raise SkillStoreError('skill_history_integrity_failure')
            return record

    def compare(self, skill_id, commit_id, revision_id):
        """Compare a historical snapshot to the viewer's pinned current bytes."""
        with self.connect() as db:
            commit = self._read(db, skill_id, commit_id)
        base = inspect_skill(self.store.root, skill_id, commit['revision_id'])
        current = inspect_skill(self.store.root, skill_id, revision_id)
        before = {file['path']: file for file in base['files']}
        after = {file['path']: file for file in current['files']}
        files, chunks = [], []
        for path in sorted(before.keys() | after.keys()):
            old, new = before.get(path), after.get(path)
            if old and new and old['file_hash'] == new['file_hash']:
                continue
            binary = any(file and file['kind'] == 'binary' for file in (old, new))
            files.append({'path': path, 'status': 'added' if old is None else 'deleted' if new is None else 'modified',
                'before_hash': old['file_hash'] if old else None,
                'after_hash': new['file_hash'] if new else None, 'binary': binary})
            chunks.append('diff --git a/'+path+' b/'+path+'\n')
            if binary:
                chunks.append('Binary files differ\n')
                continue
            # Keep actual lines readable; explicitly preserve missing-final-newline evidence.
            def lf_lines(text):
                parts = text.split('\n')
                return [part+'\n' for part in parts[:-1]] + ([parts[-1]] if parts[-1] else [])
            lines = list(difflib.unified_diff(
                lf_lines(old['text'] if old else ''),
                lf_lines(new['text'] if new else ''),
                fromfile='a/'+path if old else '/dev/null',
                tofile='b/'+path if new else '/dev/null'))
            for line in lines:
                chunks.append(line)
                if not line.endswith('\n'):
                    chunks.append('\n\\ No newline at end of file\n')
            if not lines:  # Added/deleted empty files still have a visible diff entry.
                chunks.append('--- '+('a/'+path if old else '/dev/null')+'\n')
                chunks.append('+++ '+('b/'+path if new else '/dev/null')+'\n')
        result = {'skill_id': skill_id, 'base_commit': {key: value for key, value in commit.items() if key != 'patch'},
                  'base_revision': commit['revision_id'], 'current_revision': revision_id,
                  'files': files, 'patch': ''.join(chunks)}
        if len(json.dumps(result).encode()) > 16 * 1024 * 1024:
            raise SkillStoreError('skill_diff_too_large')
        return result
