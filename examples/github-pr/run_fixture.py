"""Run the actual Langflow graph against an injected fake REST provider."""
import asyncio
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch
from lfx.graph.graph.base import Graph
from laomedo.github.pull_requests.github_pr_gateway import GitHubPRGateway
from laomedo.host.mediation.github_mediation import MediationStore
from laomedo.github.transport.github_rest_transport import GitHubRestTransport

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tests'))
from test_live_github_pr import FakeGitHub
spec = importlib.util.spec_from_file_location('pr_fixture_builder', Path(__file__).with_name('build_flow.py'))
builder = importlib.util.module_from_spec(spec); spec.loader.exec_module(builder)


async def run():
    with tempfile.TemporaryDirectory() as directory:
        fake = FakeGitHub()
        store = MediationStore(Path(directory) / 'mediation.db')
        _, token = store.issue(run_id='fixture-run', invocation_id='fixture-invoke', repository='owner/repo',
            operations={'pr_node_update'}, branch='demo', target_prs={1:'main'}, ttl_seconds=60)
        gateway = GitHubPRGateway({'owner/repo':GitHubRestTransport('owner/repo', lambda:'DUMMY-TOKEN', opener=fake)},
            store, lambda ref: {'token':token,'run_id':'fixture-run','repository':'owner/repo'} if ref == 'fixture-grant' else None)
        def request(action, **body):
            return gateway.discover(**body) if action == 'discover' else gateway.execute(**body)
        outcomes = []
        with patch('laomedo.github.pull_requests.github_pr_client.pr_request', side_effect=request):
            for _ in range(2):
                graph = Graph.from_payload(builder.build())
                outcome = await graph.arun(inputs=[{}], outputs=['pr'])
                outcomes.append(str(outcome))
        assert fake.prs[1]['title'] == 'PR operation verified'
        assert fake.prs[1]['body'] == 'Updated through the two-node PR/Agent loop.'
        assert len(fake.writes) == 1, fake.writes
        assert all('succeeded' in outcome for outcome in outcomes), outcomes
        return {'provider':'fake', 'model_turns':0, 'live_writes':0, 'graph_runs':2,
                'fixture_mutations':len(fake.writes), 'operation_status':'succeeded',
                'title':fake.prs[1]['title'], 'nodes':2, 'edges':2}


if __name__ == '__main__': print(json.dumps(asyncio.run(run()), indent=2))
