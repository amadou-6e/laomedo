from lfx.custom.custom_component.component import Component
from lfx.io import DataInput, Output
from lfx.schema import Data
class ConfirmedUpdateRoute(Component):
    display_name = 'If update confirmed'
    name = 'ConfirmedUpdateRoute'
    icon = 'Split'
    inputs = [DataInput(name='operations',display_name='Operations'),DataInput(name='update_result',display_name='Update result')]
    outputs = [Output(name='operation',display_name='Close Operation',method='close_operation')]
    def close_operation(self) -> Data:
        result=getattr(self.update_result,'data',self.update_result)
        if not isinstance(result,dict) or result.get('operation',{}).get('status')!='succeeded':
            self.stop('operation');return Data(data={})
        operations=getattr(self.operations,'data',self.operations)
        return Data(data=operations['close'])
