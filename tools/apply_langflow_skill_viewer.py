"""Apply the small viewer overlay to the exact upstream Langflow revision."""
from pathlib import Path
import argparse
import shutil
import subprocess

UPSTREAM = "fec71dca901949c09ed4d63315804337cd2eb13d"
ROOT = Path(__file__).resolve().parents[1]

def replace_once(source, old, new):
    if source.count(old) != 1:
        raise SystemExit("pinned_error_presentation_anchor_missing: " + old[:80])
    return source.replace(old, new)


def apply(checkout):
    checkout = checkout.resolve()
    revision = subprocess.check_output(["git", "-C", str(checkout), "rev-parse", "HEAD"], text=True).strip()
    if revision != UPSTREAM:
        raise SystemExit("pinned_langflow_checkout_required")
    overlay = ROOT / "frontend/langflow-skill-viewer"
    patch = overlay / "upstream.patch"
    target = checkout / "src/frontend/src/modals/skillFilesModal"
    if target.exists() or subprocess.check_output(["git", "-C", str(checkout), "status", "--porcelain"]).strip():
        raise SystemExit("clean_upstream_checkout_required")
    subprocess.run(["git", "-C", str(checkout), "apply", "--check", str(patch)], check=True)
    subprocess.run(["git", "-C", str(checkout), "apply", str(patch)], check=True)
    agent_target = checkout / "src/frontend/src/CustomNodes/GenericNode/components/RenderInputParameters"
    shutil.copy2(overlay / "RenderAgentInputParameters.tsx", agent_target / "index.tsx")
    shutil.copy2(overlay / "AgentAdvancedControls.tsx", agent_target / "AgentAdvancedControls.tsx")
    shutil.copy2(overlay / "AgentAdvancedControls.test.tsx", agent_target / "AgentAdvancedControls.test.tsx")
    target.mkdir()
    shutil.copy2(overlay / "SkillFilesModal.tsx", target / "index.tsx")
    shutil.copy2(overlay / "SkillActions.tsx", target / "SkillActions.tsx")
    shutil.copy2(overlay / "SkillActions.test.tsx", target / "SkillActions.test.tsx")
    shutil.copy2(overlay / "SkillNavigation.tsx", target / "SkillNavigation.tsx")
    shutil.copy2(overlay / "SkillNavigation.test.tsx", target / "SkillNavigation.test.tsx")
    shutil.copy2(overlay / "SkillOverview.tsx", target / "SkillOverview.tsx")
    shutil.copy2(overlay / "SkillOverview.test.tsx", target / "SkillOverview.test.tsx")
    shutil.copy2(overlay / "SkillFileDiff.tsx", target / "SkillFileDiff.tsx")
    shutil.copy2(overlay / "SkillFileDiff.test.tsx", target / "SkillFileDiff.test.tsx")
    shutil.copy2(overlay / "SkillHistory.tsx", target / "SkillHistory.tsx")
    shutil.copy2(overlay / "SkillHistory.test.tsx", target / "SkillHistory.test.tsx")
    shutil.copy2(overlay / "SkillSplitPane.tsx", target / "SkillSplitPane.tsx")
    shutil.copy2(overlay / "SkillSplitPane.test.tsx", target / "SkillSplitPane.test.tsx")
    shutil.copy2(overlay / "selection.ts", target / "selection.ts")
    shutil.copy2(overlay / "MONACO-LICENSE.txt", checkout / "src/frontend/public/monaco-LICENSE.txt")
    issue_target = checkout / "src/frontend/src/modals/issueViewerModal"
    issue_target.mkdir()
    shutil.copy2(overlay / "IssueViewerModal.tsx", issue_target / "index.tsx")
    pr_target = checkout / "src/frontend/src/modals/prViewerModal"
    pr_target.mkdir()
    shutil.copy2(overlay / "PRViewerModal.tsx", pr_target / "index.tsx")
    activity_target = checkout / "src/frontend/src/modals/agentActivity"
    activity_target.mkdir()
    shutil.copy2(overlay / "AgentActivity.tsx", activity_target / "index.tsx")
    agents_patch = overlay / "agents.patch"
    # HEAD stays pinned; patch context tolerates whitespace differences, including Windows CRLF.
    subprocess.run(["git", "-C", str(checkout), "apply", "--ignore-space-change", "--check", str(agents_patch)], check=True)
    subprocess.run(["git", "-C", str(checkout), "apply", "--ignore-space-change", str(agents_patch)], check=True)
    agents_target = checkout / "src/frontend/src/modals/graphAgents"
    agents_target.mkdir()
    shutil.copy2(overlay / "AgentActivityNavigation.ts", checkout / "src/frontend/src/stores/agentActivityStore.ts")
    shutil.copy2(overlay / "GraphAgents.tsx", agents_target / "index.tsx")
    shutil.copy2(overlay / "GraphAgents.test.tsx", agents_target / "index.test.tsx")
    recovery_target = checkout / "src/frontend/src/components/laomedoRecovery"
    recovery_target.mkdir()
    for name in ("RunnerRecovery.tsx", "RunnerRecovery.test.tsx", "RecoveryPopup.tsx", "RecoveryPopup.test.tsx"):
        shutil.copy2(overlay / name, recovery_target / name)
    error_target = checkout / "src/frontend/src/components/laomedoErrors"
    error_target.mkdir()
    for name in ("nodeErrors.ts", "node-error-catalog.json", "NodeErrorNotice.tsx", "nodeErrors.test.ts", "NodeErrorNotice.test.tsx"):
        shutil.copy2(overlay / name, error_target / name)
    status_path = checkout / "src/frontend/src/CustomNodes/GenericNode/components/NodeStatus/index.tsx"
    status_source = status_path.read_text(encoding="utf-8")
    status_source = 'import NodeErrorNotice from "@/components/laomedoErrors/NodeErrorNotice";\nimport { hasLaomedoFailure } from "@/components/laomedoErrors/nodeErrors";\n' + status_source
    marker = '{showNodeStatus && (\n            <ShadTooltip'
    if status_source.count(marker) != 1:
        raise SystemExit("pinned_node_status_error_anchor_missing")
    status_source = replace_once(status_source, marker, '''{showNodeStatus && (
            data.type?.startsWith("Laomedo") && (conditionError || hasLaomedoFailure(validationStatus)) ?
            <NodeErrorNotice message={validationString} status={validationStatus} context={{
              nodeId, nodeType: data.type, nodeLabel: display_name,
              operation: data.node?.template?.operation?.value,
              savedReferences: [data.node?.template?.run_reference?.value, data.node?.template?.run_reference_json?.value],
            }} /> : <ShadTooltip''')
    marker = '  const conditionError = buildStatus === BuildStatus.ERROR;'
    replacement = '  const scopedFlowError = useFlowStore((state) => state.nodes?.length === 1 && state.nodes[0].id === nodeId && data.type?.startsWith("Laomedo") ? state.buildInfo?.error?.[0] : undefined);\n  const conditionError = buildStatus === BuildStatus.ERROR;'
    if status_source.count(marker) != 1:
        raise SystemExit("pinned_node_error_scope_anchor_missing")
    status_source = replace_once(status_source, marker, replacement)
    status_source = replace_once(status_source, 'conditionSuccess || conditionError || conditionInactive;', 'conditionSuccess || conditionError || conditionInactive || Boolean(scopedFlowError);')
    status_source = replace_once(status_source, '(conditionError || hasLaomedoFailure(validationStatus))', '(conditionError || Boolean(scopedFlowError) || hasLaomedoFailure(validationStatus))')
    status_source = replace_once(status_source, 'message={validationString} status={validationStatus}', 'message={scopedFlowError || validationString} status={validationStatus}')
    status_path.write_text(status_source, encoding="utf-8")
    alerts_path = checkout / "src/frontend/src/stores/alertStore.ts"
    alerts = alerts_path.read_text(encoding="utf-8")
    alerts = 'import { describeLaomedoAlert } from "@/components/laomedoErrors/nodeErrors";\nimport useFlowStore from "@/stores/flowStore";\n' + alerts
    marker = 'setErrorData: (newState: { title: string; list?: Array<string> }) => {'
    if alerts.count(marker) != 1:
        raise SystemExit("pinned_error_alert_anchor_missing")
    alerts = replace_once(alerts, marker, marker + '\n    const formatted = describeLaomedoAlert(newState, useFlowStore.getState().nodes?.some(node => node.data.type?.startsWith("Laomedo")));\n    const diagnosticCode = formatted.diagnosticCode;\n    newState = { title: formatted.title, list: formatted.list };')
    marker = '      get().addNotificationToHistory(notification);'
    if alerts.count(marker) != 3:
        raise SystemExit("pinned_notification_history_anchor_missing")
    alerts = alerts.replace(marker, '      get().addNotificationToHistory(diagnosticCode ? { ...notification, list: [...(notification.list ?? []), "Diagnostic code: " + diagnosticCode] } : notification);', 1)
    alerts_path.write_text(alerts, encoding="utf-8")
    flow_error_path = checkout / "src/frontend/src/pages/FlowPage/components/flowBuildingComponent/index.tsx"
    flow_error = flow_error_path.read_text(encoding="utf-8")
    flow_error = 'import RecoveryPopup from "@/components/laomedoRecovery/RecoveryPopup";\nimport { isRunnerConnectionError } from "@/components/laomedoRecovery/RunnerRecovery";\nimport NodeErrorNotice from "@/components/laomedoErrors/NodeErrorNotice";\nimport { isKnownNodeError } from "@/components/laomedoErrors/nodeErrors";\n' + flow_error
    marker = '  const errorButtonsRef = useRef<HTMLDivElement>(null);'
    replacement = '  const graphNodes = useFlowStore((state) => state.nodes ?? []);\n  const affectedNode = graphNodes.length === 1 && graphNodes[0].data.type?.startsWith("Laomedo") ? graphNodes[0] : undefined;\n  const descriptiveError = buildInfo?.error?.find(message => isKnownNodeError(message, graphNodes.some(node => node.data.type?.startsWith("Laomedo")))) ?? (affectedNode ? buildInfo?.error?.[0] : undefined);\n  const errorButtonsRef = useRef<HTMLDivElement>(null);'
    if flow_error.count(marker) != 1:
        raise SystemExit("pinned_flow_error_anchor_missing")
    flow_error = replace_once(flow_error, marker, replacement)
    flow_error = replace_once(flow_error, '                                  <Button size="sm" onClick={handleRetry}>', '                                  {!descriptiveError && <Button size="sm" onClick={handleRetry}>')
    flow_error = replace_once(flow_error, '{t("flowBuild.retry")}\n                                  </Button>', '{t("flowBuild.retry")}\n                                  </Button>}')
    flow_error = replace_once(flow_error, 'className="max-h-48 overflow-y-auto"', 'className="max-h-[60vh] overflow-y-auto"')
    flow_error = replace_once(flow_error, '                        <Markdown\n', '                        {descriptiveError ? <NodeErrorNotice inline message={descriptiveError} context={{\n                          nodeId: affectedNode?.id, nodeType: affectedNode?.data.type, nodeLabel: affectedNode?.data.node?.display_name,\n                          operation: affectedNode?.data.node?.template?.operation?.value,\n                          savedReferences: [affectedNode?.data.node?.template?.run_reference?.value, affectedNode?.data.node?.template?.run_reference_json?.value],\n                        }} /> : <Markdown\n')
    flow_error = replace_once(flow_error, '                        </Markdown>', '                        </Markdown>}')
    flow_error = replace_once(flow_error, 'className="absolute right-0 font-mono text-xs"', 'className={cn("absolute right-0 font-mono text-xs", descriptiveError && "hidden")}')
    flow_error = replace_once(flow_error, '  return (\n    <AnimatePresence mode="wait">', '  if (!isBuilding && descriptiveError && isRunnerConnectionError(descriptiveError) && !dismissed) {\n    return <RecoveryPopup message={descriptiveError} onDismiss={() => { setBuildInfo(null); setDismissed(false); }} context={{\n      nodeId: affectedNode?.id, nodeType: affectedNode?.data.type, nodeLabel: affectedNode?.data.node?.display_name,\n      operation: affectedNode?.data.node?.template?.operation?.value,\n      savedReferences: [affectedNode?.data.node?.template?.run_reference?.value, affectedNode?.data.node?.template?.run_reference_json?.value],\n    }} />;\n  }\n  return (\n    <AnimatePresence mode="wait">')
    flow_error_path.write_text(flow_error, encoding="utf-8")
    outcome_patch = overlay / "runner-outcomes.patch"
    subprocess.run(["git", "-C", str(checkout), "apply", "--ignore-space-change", "--check", str(outcome_patch)], check=True)
    subprocess.run(["git", "-C", str(checkout), "apply", "--ignore-space-change", str(outcome_patch)], check=True)
    print("pinned_skill_viewer_overlay_applied")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("checkout", type=Path)
    apply(parser.parse_args().checkout)
