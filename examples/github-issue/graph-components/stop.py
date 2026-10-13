from lfx.custom.custom_component.component import Component
from lfx.io import DataInput, Output
from lfx.schema import Data
class ReviewIssueProposal(Component):
    display_name = 'Review or recover - no issue writes'
    name = 'ReviewIssueProposal'
    icon = 'ShieldAlert'
    inputs = [DataInput(name='outcome', display_name='Outcome')]
    outputs = [Output(name='result', display_name='Outcome', method='result_output')]
    def result_output(self) -> Data:
        return Data(data=getattr(self.outcome, 'data', self.outcome))
