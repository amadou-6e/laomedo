"""Deterministic Agent fixture: no model, credentials or provider calls."""
from lfx.custom.custom_component.component import Component
from lfx.io import MessageInput; from lfx.io import DropdownInput; from lfx.io import Output
from lfx.schema import Data


class PRFixtureAgent(Component):
    display_name = 'Agent (fixture)'
    description = 'Read the PR task and return one operation. This is a deterministic fixture, not a model.'
    name = 'PRFixtureAgent'
    inputs = [MessageInput(name='task',display_name='PR Task',required=True),
              DropdownInput(name='action',display_name='Operation',value='modify',options=['modify','close','invalid','fail'])]
    outputs = [Output(name='preview',display_name='Received PR',method='preview_output',group_outputs=True),
               Output(name='operation',display_name='Operation',method='operation_output',group_outputs=True)]

    def preview_output(self) -> Data:
        return Data(data={'text':self.task.text})

    def operation_output(self) -> Data:
        self.update_ctx({'pr_fixture_agent_calls':self.ctx.get('pr_fixture_agent_calls',0)+1,
                         'pr_fixture_agent_task':self.task.text})
        if self.action == 'fail':
            raise ValueError('fixture_agent_failure')
        if self.action == 'invalid':
            return Data(data={'unexpected':'not an operation'})
        operation = {'action':self.action}
        if self.action == 'modify':
            operation['changes'] = {'title':'PR operation verified','body':'Updated through the two-node PR/Agent loop.'}
        return Data(data=operation)
