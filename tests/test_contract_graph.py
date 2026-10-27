import json
from copy import deepcopy
from types import SimpleNamespace
import unittest
from laomedo.agents.contract_graph import downstream_requirements, verified_route_submission
from laomedo.agents.output_contract import requirements

FORM={'schema_version':1,'fields':[]}


def edge(source,target,output='submission',field='agent_submission'):
    return {'source':source,'target':target,'data':{'sourceHandle':{'name':output},'targetHandle':{'fieldName':field}}}


def runtime(edges=None):
    agent=SimpleNamespace()
    contract=SimpleNamespace()
    av=SimpleNamespace(id='agent',data={'type':'LaomedoCodexAgent'},custom_component=agent)
    cv=SimpleNamespace(id='contract',data={'type':'LaomedoOutputContract','node':{'template':{'requirements_json':{'value':json.dumps(FORM)}}}},custom_component=contract)
    graph=SimpleNamespace(edges=[SimpleNamespace(to_data=lambda e=e: e) for e in (edges or [edge('agent','contract'),edge('contract','dest','success','routed')])])
    vertices={'agent':av,'contract':cv}
    graph.get_vertex=vertices.__getitem__
    av.graph=cv.graph=graph
    agent._vertex=av;agent.graph=graph;contract._vertex=cv
    return agent,contract,cv,graph,vertices


class ContractGraphTests(unittest.TestCase):
    def test_dynamic_form_refuses(self):
        a,_,_,_,_=runtime([edge('agent','contract'),edge('issue','contract','task','requirements_json')])
        with self.assertRaisesRegex(ValueError,'dynamic_output'):
            downstream_requirements(a)

    def test_multiple_contracts_refuse(self):
        a,_,cv,g,vertices=runtime([edge('agent','contract'),edge('agent','second')])
        vertices['second']=deepcopy(cv)
        with self.assertRaisesRegex(ValueError,'ambiguous_downstream'):
            downstream_requirements(a)

    def test_multiple_agents_refuse(self):
        a,_,_,_,_=runtime([edge('agent','contract'),edge('other','contract')])
        with self.assertRaisesRegex(ValueError,'ambiguous_output_contract_agent'):
            downstream_requirements(a)

    def test_conflicting_explicit_pin_refuses(self):
        a,_,_,_,_=runtime()
        with self.assertRaisesRegex(ValueError,'conflicting_downstream'):
            downstream_requirements(a,requirements({'schema_version':1,'fields':[{'name':'x','type':'string'}]}))

    def test_pin_is_frozen_and_forged_delivery_refused(self):
        a,c,cv,_,_=runtime()
        selected=downstream_requirements(a)
        selected['requirements_revision']='mutated'
        self.assertEqual(a._downstream_contract_binding[1],requirements(FORM))
        original={'run_reference':{'run_id':'bound'},'executor_status':'unknown','evidence_complete':False}
        a._contract_submission=deepcopy(original)
        self.assertEqual(verified_route_submission(c,original),original)
        forged={**original,'executor_status':'completed','evidence_complete':True}
        with self.assertRaisesRegex(ValueError,'evidence_mismatch'):
            verified_route_submission(c,forged)

    def test_no_contract_preserves_existing_operation(self):
        a,_,_,g,_=runtime();g.edges=[]
        self.assertIsNone(downstream_requirements(a))

    def test_next_preparation_clears_previous_submission(self):
        a,_,_,_,_=runtime();a._contract_submission={'old':'record'}
        downstream_requirements(a)
        self.assertIsNone(a._contract_submission)
