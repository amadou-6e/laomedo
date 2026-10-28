from copy import deepcopy
import json
import laomedo.agents.contracts.output as _contracts_output

ROUTES = {"success", "failure", "rejection", "recovery"}


def _edges(graph):
    return [edge.to_data() for edge in graph.edges]


def _handle(edge, side, key):
    return edge.get("data", {}).get(side + "Handle", {}).get(key)


def downstream_requirements(agent, explicit=None):
    """Resolve static downstream form through native graph metadata, never build it."""
    vertex = getattr(agent, "_vertex", None)
    agent._downstream_contract_binding = None
    agent._contract_submission = None
    if vertex is None:
        return explicit
    graph = agent.graph
    edges = _edges(graph)
    contracts = []
    for edge in edges:
        if (
            edge.get("source") != vertex.id
            or _handle(edge, "source", "name") != "submission"
            or _handle(edge, "target", "fieldName") != "agent_submission"
        ):
            continue
        target = graph.get_vertex(edge["target"])
        if target.data.get("type") == "LaomedoOutputContract":
            contracts.append(target)
    if not contracts:
        return explicit
    if len(contracts) != 1:
        raise ValueError("ambiguous_downstream_output_contract")
    contract = contracts[0]
    integrated = any(
        edge.get("source") == contract.id and _handle(edge, "source", "name") in ROUTES
        for edge in edges
    )
    # Existing explicit-precheck flows retain their downstream drift rejection.
    if explicit is not None and not integrated:
        return explicit
    if any(
        edge.get("target") == contract.id
        and _handle(edge, "target", "fieldName") == "requirements_json"
        for edge in edges
    ):
        raise ValueError("dynamic_output_contract_requirements_unsupported")
    sources = [
        edge
        for edge in edges
        if edge.get("target") == contract.id
        and _handle(edge, "target", "fieldName") == "agent_submission"
    ]
    if len(sources) != 1:
        raise ValueError("ambiguous_output_contract_agent")
    raw = contract.data["node"]["template"]["requirements_json"]["value"]
    try:
        selected = _contracts_output.requirements(json.loads(raw))
    except (TypeError, ValueError):
        raise ValueError("invalid_downstream_output_requirements") from None
    if explicit is not None and selected != explicit:
        raise ValueError("conflicting_downstream_output_requirements")
    agent._downstream_contract_binding = (contract.id, deepcopy(selected))
    return selected


def verified_route_submission(contract, envelope):
    """Use this invocation's adapter-retained runner envelope, not editable Data."""
    vertex = getattr(contract, "_vertex", None)
    if vertex is None:
        raise ValueError("integrated_contract_agent_binding_required")
    graph = vertex.graph
    sources = [
        edge
        for edge in _edges(graph)
        if edge.get("target") == vertex.id
        and _handle(edge, "target", "fieldName") == "agent_submission"
    ]
    if len(sources) != 1 or _handle(sources[0], "source", "name") != "submission":
        raise ValueError("integrated_contract_agent_binding_required")
    source = graph.get_vertex(sources[0]["source"])
    if not getattr(source.custom_component, "supports_output_requirements", False):
        raise ValueError("integrated_contract_codex_agent_required")
    agent = source.custom_component
    binding = getattr(agent, "_downstream_contract_binding", None)
    retained = getattr(agent, "_contract_submission", None)
    if (
        binding is None
        or binding[0] != vertex.id
        or retained is None
        or retained != envelope
    ):
        raise ValueError("integrated_contract_runner_evidence_mismatch")
    return deepcopy(retained)


def route_destination(validation):
    submission = validation["agent_submission"]
    if (
        submission.get("executor_status") != "completed"
        or submission.get("evidence_complete") is not True
    ):
        return "recovery"
    if validation["contract_status"] != "accepted":
        return "rejection"
    outcome = submission.get("task_outcome")
    return outcome if outcome in {"success", "failure"} else "recovery"
