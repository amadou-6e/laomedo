"""Execute the one connected Agent through native Langflow loop machinery."""
import json
from contextlib import aclosing
from lfx.execution import aget_default_coordinator
from lfx.schema import Data, Message
from types import MethodType
from lfx.graph.vertex.base import Vertex


def _build_pr_params(vertex):
    Vertex.build_params(vertex)
    # The return socket is controlled by this component's isolated loop body,
    # not an eager input dependency. Keep the edge for topology/port selection.
    if feedback_edge(vertex.custom_component) is not None:
        field = feedback_edge(vertex.custom_component).target_handle.field_name
        vertex.raw_params.pop(field, None)
        vertex.params.pop(field, None)


def bind_feedback_parameters(vertex):
    """Adapt the pinned runtime's eager loop-input resolution for this node only."""
    vertex.build_params = MethodType(_build_pr_params, vertex)
    # The pinned sorter chooses an arbitrary vertex for a closed cycle. That
    # can start the Agent without context in the editor's full-flow build.
    vertex.graph.sort_vertices = MethodType(_sort_pr_vertices, vertex.graph)


def _sort_pr_vertices(graph, stop_component_id=None, start_component_id=None):
    from lfx.graph.graph.base import Graph
    controllers = [v for v in graph.vertices
        if getattr(getattr(v, 'custom_component', None), 'name', None) in {'LaomedoGitHubPR', 'LaomedoSkill'}
        and feedback_edge(v.custom_component) is not None]
    if len(controllers) > 1:
        raise ValueError('pr_agent_loop_invalid')
    if len(controllers) == 1:
        controller = controllers[0]
        feedback = feedback_edge(controller.custom_component)
        if stop_component_id is not None:
            reachable, pending = set(), [controller.id]
            while pending:
                current = pending.pop()
                if current in reachable:
                    continue
                reachable.add(current)
                pending.extend(edge.target_id for edge in graph.get_vertex(current).outgoing_edges)
            if stop_component_id not in reachable:
                return Graph.sort_vertices(graph, stop_component_id, start_component_id)
        if start_component_id in (None, controller.id, feedback.source_id):
            start_component_id = controller.id
    first_layer = Graph.sort_vertices(graph, stop_component_id, start_component_id)
    # Independent Skill roots must not make the controller disappear behind
    # the feedback cycle. Starting it explicitly seeds that cycle, while keeping
    # every ordinary root scheduled as before.
    if len(controllers) == 1 and start_component_id == controllers[0].id:
        if controllers[0].id not in first_layer:
            first_layer = [controllers[0].id, *first_layer]
    return first_layer


def skill_input_vertices(controller, agent):
    """Only independent read-only Skill outputs may accompany feedback Task."""
    selected = set()
    tasks = 0
    for edge in agent.incoming_edges:
        if edge.source_id == controller.id:
            if edge.target_handle.field_name != 'task' or edge.source_handle.name != 'task':
                raise ValueError('pr_agent_loop_invalid')
            tasks += 1
            continue
        source = controller.graph.get_vertex(edge.source_id)
        template = source.full_data['data']['node']['template']
        if (edge.target_handle.field_name != 'skill_reference' or
                edge.source_handle.name != 'skill' or source.data.get('type') != 'LaomedoSkill' or
                source.incoming_edges or template.get('operation', {}).get('value') or
                str(template.get('edit_request', {}).get('value') or '').strip()):
            raise ValueError('pr_agent_loop_invalid')
        selected.add(source.id)
        if len(selected) > 16:
            raise ValueError('pr_agent_loop_invalid')
    if tasks != 1:
        raise ValueError('pr_agent_loop_invalid')
    return selected


def feedback_edge(component):
    vertex = getattr(component, '_vertex', None)
    if vertex is None:
        return None
    legacy = [edge for edge in vertex.incoming_edges if edge.target_handle.field_name == 'task']
    operations = [edge for edge in vertex.incoming_edges if edge.target_handle.field_name == 'operation']
    if len(operations) > 1:
        raise ValueError('pr_agent_loop_invalid')
    starts = [edge for edge in vertex.outgoing_edges if edge.source_handle.name == 'task']
    # An ordinary upstream operation stays eager. Only the return from the
    # Agent consuming this PR's context is controlled feedback.
    returns = [edge for edge in operations if any(start.target_id == edge.source_id for start in starts)]
    if operations and starts and not returns:
        pending = [edge.target_id for edge in starts]
        seen = {vertex.id}
        while pending:
            current = pending.pop()
            if current in seen:
                continue
            seen.add(current)
            if current == operations[0].source_id:
                raise ValueError('pr_agent_loop_invalid')
            pending.extend(edge.target_id for edge in vertex.graph.get_vertex(current).outgoing_edges)
    edges = legacy + returns
    if not edges:
        return None
    if len(edges) != 1 or (returns and len(operations) != 1) or (legacy and operations):
        raise ValueError('pr_agent_loop_invalid')
    source = vertex.graph.get_vertex(edges[0].source_id)
    # Preserve independent read-only Skill references in the isolated body.
    # Refuse other upstream inputs rather than silently dropping them.
    skill_input_vertices(vertex, source)
    return edges[0]


def operation_value(value):
    if isinstance(value, Message):
        value = value.text
    elif isinstance(value, Data):
        value = value.data
    if isinstance(value, dict) and 'action' not in value and isinstance(value.get('text'), str):
        value = value['text']
    if isinstance(value, str):
        if len(value.encode('utf-8')) > 1024 * 1024:
            raise ValueError('pr_operation_invalid')
        try:
            value = json.loads(value)
        except (TypeError, ValueError):
            raise ValueError('pr_operation_invalid') from None
    if not isinstance(value, dict) or value.get('action') not in {'modify','close'}:
        raise ValueError('pr_operation_invalid')
    return value


async def agent_operation(component, seed, decoder=operation_value, with_provenance=False):
    feedback = feedback_edge(component)
    starts = [edge for edge in component._vertex.outgoing_edges if edge.source_handle.name == 'task']
    body = {feedback.source_id} if feedback is not None else set()
    if (feedback is None or len(starts) != 1 or body != {feedback.source_id} or
            starts[0].target_id != feedback.source_id):
        raise ValueError('pr_agent_loop_invalid')
    start = starts[0]
    body |= skill_input_vertices(component._vertex, component.graph.get_vertex(feedback.source_id))
    selected = None
    async with component.graph.create_subgraph(body) as subgraph:
        for node in subgraph._vertices:
            if node['id'] == start.target_id:
                node['data']['node']['template'][start.target_handle.field_name]['value'] = seed
        subgraph.prepare()
        subgraph.get_vertex(start.target_id).update_raw_params({start.target_handle.field_name:seed}, overwrite=True)
        coordinator = await aget_default_coordinator()
        async with aclosing(coordinator.stream(subgraph, event_manager=component._event_manager)) as stream:
            async for result in stream:
                if getattr(result, 'valid', True) is False:
                    raise ValueError('pr_agent_failed')
                if getattr(getattr(result, 'vertex', None), 'id', None) == feedback.source_id:
                    outputs = result.result_dict.outputs
                    if feedback.source_handle.name in outputs:
                        output = outputs[feedback.source_handle.name]
                        selected = output.get('message') if isinstance(output, dict) else getattr(output,'message',None)
        provenance = getattr(subgraph.get_vertex(start.target_id).custom_component, '_last_reference', None)
    operation = decoder(selected)
    return (operation, provenance) if with_provenance else operation
