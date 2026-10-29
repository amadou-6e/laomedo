"""Internal regression checks for model invariants and unchanged wire/storage bytes."""
import json
from pathlib import Path
import tempfile
import unittest
from pydantic import BaseModel, ValidationError

from laomedo.host.leases.models import ContainerIdentity
from laomedo.skills.operations.models import EditorProvenance, FileEdit, SkillProposal
from laomedo.skills.operations.utils import proposal
from laomedo.skills.registry.errors import SkillStoreError
from laomedo.work_graph.models import Dependency, GraphSnapshot
from laomedo.agents.interface.models import AgentRequest


class CohesionModelTests(unittest.TestCase):
    def test_capture_binding_projects_the_existing_component_request_api(self):
        body = {'task': 'continue'}
        request = AgentRequest.from_component_request(('http://localhost/run/resume', body, 'POST'))
        bound = request.with_activity_attempt('invocation-1')
        self.assertEqual(body, {'task': 'continue'})
        self.assertEqual(bound.component_arguments(), ('http://localhost/run/resume', {
            'task': 'continue', 'activity_attempt_id': 'invocation-1'
        }, 'POST'))

    def test_saved_snapshot_keeps_its_identity_and_exact_saved_bytes(self):
        golden = Path(__file__).parent / 'fixtures/work-graph-pre-pydantic.json'
        snapshot = GraphSnapshot.from_dict(json.loads(golden.read_bytes()))
        self.assertIsInstance(snapshot, BaseModel)
        self.assertEqual(snapshot.snapshot_id, 'sha256:9f16758508a72ed163d87b938e5a6ad5c492db5a205878501e55593f700b5424')
        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual(snapshot.save(Path(directory)).read_bytes(), golden.read_bytes())

    def test_dependency_order_hash_and_immutable_snapshot_invariants(self):
        snapshot = GraphSnapshot.from_dict(json.loads((Path(__file__).parent / 'fixtures/work-graph-pre-pydantic.json').read_bytes()))
        edge = snapshot.dependencies[0]
        duplicate = Dependency.model_validate(edge.model_dump())
        self.assertEqual(hash(edge), hash(duplicate))
        self.assertEqual(len({edge, duplicate}), 1)
        changed = Dependency.model_validate({**edge.model_dump(), 'provenance': 'zzz'})
        self.assertLess(edge, changed)
        self.assertEqual(sorted([changed, edge]), [edge, changed])
        with self.assertRaises(ValidationError):
            snapshot.items[0].title = 'mutated'
        with self.assertRaises(ValidationError) as invalid_time:
            GraphSnapshot.model_validate({**snapshot.model_dump(), 'fetched_at': 'test-only-private-input'})
        self.assertNotIn('test-only-private-input', str(invalid_time.exception))
        with self.assertRaises(ValidationError):
            GraphSnapshot.model_validate({**snapshot.model_dump(), 'items': list(snapshot.items)})

    def test_multifile_proposal_roundtrips_the_existing_payload(self):
        payload = {'action': 'modify', 'message': 'Update both files', 'files': [
            {'path': 'SKILL.md', 'content': '# Skill\n'},
            {'path': 'references/obsolete.md', 'content': None}]}
        model = SkillProposal.from_payload(payload)
        self.assertIsInstance(model.files[0], FileEdit)
        self.assertEqual(model.to_payload(), payload)
        self.assertEqual(proposal(json.dumps(payload)), payload)
        self.assertEqual(EditorProvenance.from_payload({'kind': 'agent', 'run_id': 'run-1'}).to_payload(), {'kind': 'agent', 'run_id': 'run-1'})
        self.assertEqual(EditorProvenance.from_payload(None).to_payload(), {'kind': 'operator'})

    def test_invalid_proposals_keep_stable_codes_and_never_coerce(self):
        with self.assertRaisesRegex(SkillStoreError, 'skill_operation_invalid'):
            SkillProposal.from_payload({'action': 'modify', 'message': 123, 'files': []})
        with self.assertRaisesRegex(SkillStoreError, 'skill_agent_provenance_required'):
            EditorProvenance.from_payload({'kind': 'agent'})
        with self.assertRaises(ValidationError):
            FileEdit(path='../escape.md', content='bad')
        with self.assertRaises(ValidationError):
            FileEdit(path='safe.md', content=123)

    def test_capability_is_hidden_from_repr_validation_and_json_projection(self):
        planted = 'test-only-capability-do-not-log'
        identity = ContainerIdentity(name='exact-container', run_id='run-1', token=planted)
        self.assertNotIn(planted, repr(identity))
        self.assertNotIn(planted, identity.model_dump_json())
        with self.assertRaises(ValidationError) as caught:
            ContainerIdentity(name=123, run_id='run-1', token=planted)
        self.assertNotIn(planted, str(caught.exception))
        record = identity.registration(runner_pid=7, created_at=2.5, mediation=None)
        self.assertEqual(record, {'name': 'exact-container', 'run_id': 'run-1', 'token': planted,
                                  'runner_pid': 7, 'created_at': 2.5, 'mediation': None})
