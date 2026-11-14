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


def apply_pr_controls(checkout):
    """Install PR-only presentation without changing native selector semantics."""
    overlay = ROOT / "frontend/langflow-skill-viewer/github/pull_requests"
    frontend = checkout / "src/frontend/src"
    target = frontend / "CustomNodes/GenericNode/components/RenderInputParameters"
    for name in (
        "PRNodeControls.ts",
        "PRNodeControls.test.tsx",
        "PRSelectors.test.tsx",
    ):
        shutil.copy2(overlay / name, target / name)
    helper = "@/CustomNodes/GenericNode/components/RenderInputParameters/PRNodeControls"
    parameter = frontend / "components/core/parameterRenderComponent/index.tsx"
    source = (
        f'import {{ prChoicePlaceholder, prFieldTemplate }} from "{helper}";\n'
        + parameter.read_text(encoding="utf-8")
    )
    source = replace_once(
        source,
        "  const { t } = useTranslation();",
        "  templateData = prFieldTemplate(useFlowStore.getState().nodes.find(node => node.id === nodeId)?.data, name, templateData);\n  const { t } = useTranslation();",
    )
    source = replace_once(
        source,
        "placeholder: skillChoicePlaceholder(",
        "placeholder: prChoicePlaceholder(useFlowStore.getState().nodes.find(node => node.id === nodeId)?.data, name, skillChoicePlaceholder(",
    )
    source = replace_once(
        source,
        "name, placeholder || templateData?.placeholder),",
        "name, placeholder || templateData?.placeholder)),",
    )
    parameter.write_text(source, encoding="utf-8")
    multiselect = (
        frontend
        / "components/core/parameterRenderComponent/components/multiselectComponent/index.tsx"
    )
    source = (
        f'import {{ isPRNode, prChoicePlaceholder }} from "{helper}";\nimport useFlowStore from "@/stores/flowStore";\n'
        + multiselect.read_text(encoding="utf-8")
    )
    source = replace_once(source, "  disabled,", "  nodeId,\n  disabled,")
    source = replace_once(
        source,
        "  const { t } = useTranslation();",
        "  const nodeData = useFlowStore(state => state.nodes.find(node => node.id === nodeId)?.data);\n  const prNode = isPRNode(nodeData);\n  const refreshedOptions = prNode ? defaultOptions : undefined;\n  const { t } = useTranslation();",
    )
    source = replace_once(
        source,
        ': t("multiselect.chooseOption")}',
        ': prChoicePlaceholder(nodeData, "labels", t("multiselect.chooseOption"))}',
    )
    source = replace_once(source, "  }, [value]);", "  }, [value, refreshedOptions]);")
    source = replace_once(
        source,
        "Object.keys(options).length === 0 && !combobox",
        "Object.keys(options).length === 0 && !combobox && !prNode",
    )
    source = replace_once(
        source,
        "          {renderOptionsList()}",
        "          {renderOptionsList()}\n"
        '          {prNode && <Button type="button" variant="ghost" className="w-full justify-start" aria-label="Refresh Labels"\n'
        "            onClick={() => { setOpen(false); handleOnNewValue({ value: treatedValue }, { skipSnapshot: true }); }}>Refresh list</Button>}",
    )
    multiselect.write_text(source, encoding="utf-8")
    dropdown = frontend / "components/core/dropdownComponent/index.tsx"
    source = f'import {{ isPRNode }} from "{helper}";\n' + dropdown.read_text(
        encoding="utf-8"
    )
    source = replace_once(
        source,
        '    if (event.key === "Enter") {',
        '    if (event.key === "Enter" && !isPRNode(_nodes.find(node => node.id === nodeId)?.data)) {',
    )
    dropdown.write_text(source, encoding="utf-8")
    graph_utils = frontend / "utils/reactflowUtils.ts"
    source = (
        f'import {{ isPRFeedbackConnection }} from "{helper}";\n'
        + graph_utils.read_text(encoding="utf-8")
    )
    source = replace_once(
        source,
        "        if (!hasLoopComponent) {",
        "        if (!hasLoopComponent && !isPRFeedbackConnection(connection, nodesArray, edgesArray, scapeJSONParse)) {",
    )
    graph_utils.write_text(source, encoding="utf-8")
    edit_rows = frontend / "modals/editNodeModal/hooks/use-row-data.ts"
    source = f'import {{ isPRControlHidden }} from "{helper}";\n' + edit_rows.read_text(
        encoding="utf-8"
    )
    source = replace_once(
        source,
        "!isSkillControlHidden({ type: nodeType, node: nodeClass }, key) &&",
        "!isSkillControlHidden({ type: nodeType, node: nodeClass }, key) &&\n          !isPRControlHidden({ type: nodeType, node: nodeClass }, key) &&",
    )
    edit_rows.write_text(source, encoding="utf-8")
    inspection = (
        frontend
        / "pages/FlowPage/components/InspectionPanel/components/InspectionPanelFields.tsx"
    )
    source = (
        f'import {{ isPRControlHidden }} from "{helper}";\n'
        + inspection.read_text(encoding="utf-8")
    )
    source = replace_once(
        source,
        "if (isSkillControlHidden(data, templateField)) return false;",
        "if (isSkillControlHidden(data, templateField) || isPRControlHidden(data, templateField)) return false;",
    )
    inspection.write_text(source, encoding="utf-8")


def apply(checkout):
    checkout = checkout.resolve()
    revision = subprocess.check_output(
        ["git", "-C", str(checkout), "rev-parse", "HEAD"], text=True
    ).strip()
    if revision != UPSTREAM:
        raise SystemExit("pinned_langflow_checkout_required")
    overlay = ROOT / "frontend/langflow-skill-viewer"
    models_patch = overlay / "integration/claude-models.patch"
    patch = overlay / "integration/upstream.patch"
    target = checkout / "src/frontend/src/modals/skillFilesModal"
    if (
        target.exists()
        or subprocess.check_output(
            ["git", "-C", str(checkout), "status", "--porcelain"]
        ).strip()
    ):
        raise SystemExit("clean_upstream_checkout_required")
    subprocess.run(
        [
            "git",
            "-C",
            str(checkout),
            "apply",
            "--ignore-space-change",
            "--check",
            str(patch),
        ],
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(checkout), "apply", "--ignore-space-change", str(patch)],
        check=True,
    )
    file_patch = overlay / "integration/file-actions-dependencies.patch"
    subprocess.run(
        [
            "git",
            "-C",
            str(checkout),
            "apply",
            "--ignore-space-change",
            "--check",
            str(file_patch),
        ],
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(checkout), "apply", "--ignore-space-change", str(file_patch)],
        check=True,
    )
    subprocess.run(
        [
            "git",
            "-C",
            str(checkout),
            "apply",
            "--ignore-space-change",
            "--check",
            str(models_patch),
        ],
        check=True,
    )
    subprocess.run(
        [
            "git",
            "-C",
            str(checkout),
            "apply",
            "--ignore-space-change",
            str(models_patch),
        ],
        check=True,
    )
    selection_patch = overlay / "integration/claude-selection.patch"
    subprocess.run(
        [
            "git",
            "-C",
            str(checkout),
            "apply",
            "--ignore-space-change",
            "--check",
            str(selection_patch),
        ],
        check=True,
    )
    subprocess.run(
        [
            "git",
            "-C",
            str(checkout),
            "apply",
            "--ignore-space-change",
            str(selection_patch),
        ],
        check=True,
    )
    catalog_patch = overlay / "catalog-recovery.patch"
    subprocess.run(
        [
            "git",
            "-C",
            str(checkout),
            "apply",
            "--ignore-space-change",
            "--check",
            str(catalog_patch),
        ],
        check=True,
    )
    subprocess.run(
        [
            "git",
            "-C",
            str(checkout),
            "apply",
            "--ignore-space-change",
            str(catalog_patch),
        ],
        check=True,
    )
    shutil.copy2(
        overlay / "agents/controls/AgentModelSelection.test.ts",
        checkout / "src/frontend/src/CustomNodes/helpers/AgentModelSelection.test.ts",
    )
    shutil.copy2(
        overlay / "agents/controls/ClaudeModelDropdown.test.tsx",
        checkout
        / "src/frontend/src/components/core/dropdownComponent/ClaudeModelDropdown.test.tsx",
    )
    agent_target = (
        checkout
        / "src/frontend/src/CustomNodes/GenericNode/components/RenderInputParameters"
    )
    shutil.copy2(
        overlay / "agents/controls/RenderAgentInputParameters.tsx",
        agent_target / "index.tsx",
    )
    for name in ("SkillNodeControls.ts", "SkillNodeControls.test.tsx"):
        shutil.copy2(overlay / "skills/node" / name, agent_target / name)
    parameter = (
        checkout / "src/frontend/src/components/core/parameterRenderComponent/index.tsx"
    )
    source = (
        'import { skillChoicePlaceholder } from "@/CustomNodes/GenericNode/components/RenderInputParameters/SkillNodeControls";\n'
        + parameter.read_text(encoding="utf-8")
    )
    source = replace_once(
        source,
        "      placeholder: placeholder || templateData?.placeholder,",
        "      placeholder: skillChoicePlaceholder(useFlowStore.getState().nodes.find(node => node.id === nodeId)?.data, name, placeholder || templateData?.placeholder),",
    )
    parameter.write_text(source, encoding="utf-8")
    edit_rows = checkout / "src/frontend/src/modals/editNodeModal/hooks/use-row-data.ts"
    source = edit_rows.read_text(encoding="utf-8")
    source = (
        'import { isAgentControlHidden } from "@/CustomNodes/GenericNode/components/RenderInputParameters/AgentAdvancedControls";\n'
        'import { isSkillControlHidden } from "@/CustomNodes/GenericNode/components/RenderInputParameters/SkillNodeControls";\n'
        'import useFlowStore from "@/stores/flowStore";\n' + source
    )
    source = replace_once(
        source,
        "const useRowData = (nodeClass: APIClassType, open: boolean) => {\n",
        "const useRowData = (nodeClass: APIClassType, open: boolean, nodeId?: string) => {\n"
        "  const nodeType = useFlowStore(state => state.nodes.find(node => node.id === nodeId)?.data.type);\n",
    )
    source = replace_once(
        source,
        '          key.charAt(0) !== "_" &&\n',
        '          key.charAt(0) !== "_" &&\n'
        "          !isAgentControlHidden({ type: nodeType, node: nodeClass }, key) &&\n"
        "          !isSkillControlHidden({ type: nodeType, node: nodeClass }, key) &&\n",
    )
    source = replace_once(
        source, "  }, [open, nodeClass]);", "  }, [open, nodeClass, nodeType]);"
    )
    edit_rows.write_text(source, encoding="utf-8")
    edit_component = (
        checkout
        / "src/frontend/src/modals/editNodeModal/components/editNodeComponent/index.tsx"
    )
    source = replace_once(
        edit_component.read_text(encoding="utf-8"),
        "  const rowData = useRowData(nodeClass, open);",
        "  const rowData = useRowData(nodeClass, open, nodeId);",
    )
    edit_component.write_text(source, encoding="utf-8")
    inspection_fields = (
        checkout
        / "src/frontend/src/pages/FlowPage/components/InspectionPanel/components/InspectionPanelFields.tsx"
    )
    source = (
        'import { isAgentControlHidden } from "@/CustomNodes/GenericNode/components/RenderInputParameters/AgentAdvancedControls";\n'
        'import { isSkillControlHidden } from "@/CustomNodes/GenericNode/components/RenderInputParameters/SkillNodeControls";\n'
        + inspection_fields.read_text(encoding="utf-8")
    )
    source = replace_once(
        source,
        "      .filter((templateField) => {\n",
        "      .filter((templateField) => {\n"
        "        if (isAgentControlHidden(data, templateField)) return false;\n"
        "        if (isSkillControlHidden(data, templateField)) return false;\n",
    )
    inspection_fields.write_text(source, encoding="utf-8")
    apply_pr_controls(checkout)
    generic_node = checkout / "src/frontend/src/CustomNodes/GenericNode/index.tsx"
    source = generic_node.read_text(encoding="utf-8")
    source = (
        'import { skillNodeDescription } from "./components/RenderInputParameters/SkillNodeControls";\n'
        + source
    )
    source = replace_once(
        source,
        "                description={data.node?.description}\n",
        "                description={skillNodeDescription(data)}\n",
    )
    generic_node.write_text(source, encoding="utf-8")
    shutil.copy2(
        overlay / "agents/controls/AgentAdvancedControls.tsx",
        agent_target / "AgentAdvancedControls.tsx",
    )
    shutil.copy2(
        overlay / "agents/controls/AgentAdvancedControls.test.tsx",
        agent_target / "AgentAdvancedControls.test.tsx",
    )
    shutil.copy2(
        overlay / "skills/interface/CanvasQueryState.test.ts",
        checkout
        / "src/frontend/src/pages/FlowPage/components/PageComponent/__tests__/CanvasQueryState.test.ts",
    )
    shutil.copytree(
        overlay / "skills",
        target,
        ignore=shutil.ignore_patterns(
            "README.md", "node", "assets", "CanvasQueryState.test.ts"
        ),
    )
    (target / "index.tsx").write_text(
        'export { SkillViewerRequest as default } from "./interface/SkillViewer";\n',
        encoding="utf-8",
    )
    authenticated_page = (
        checkout / "src/frontend/src/pages/AppAuthenticatedPage/index.tsx"
    )
    authenticated = authenticated_page.read_text(encoding="utf-8")
    authenticated = replace_once(
        authenticated,
        'import { Outlet } from "react-router-dom";',
        'import { Outlet } from "react-router-dom";\n'
        'import SkillViewerProvider from "@/modals/skillFilesModal/interface/SkillViewer";',
    )
    authenticated = replace_once(
        authenticated, "    <>\n", "    <SkillViewerProvider>\n"
    )
    authenticated = replace_once(
        authenticated, "    </>\n", "    </SkillViewerProvider>\n"
    )
    authenticated_page.write_text(authenticated, encoding="utf-8")
    shutil.copy2(
        overlay / "skills/assets/MONACO-LICENSE.txt",
        checkout / "src/frontend/public/monaco-LICENSE.txt",
    )
    shutil.copy2(
        overlay / "skills/assets/skill-files-NOTICE.txt",
        checkout / "src/frontend/public/skill-files-NOTICE.txt",
    )
    shutil.copy2(
        overlay / "skills/assets/skill-icons-NOTICE.txt",
        checkout / "src/frontend/public/skill-icons-NOTICE.txt",
    )
    shutil.copytree(
        overlay / "github",
        checkout / "src/frontend/src/modals/github",
        ignore=shutil.ignore_patterns("README.md"),
    )
    activity_target = checkout / "src/frontend/src/modals/agentActivity"
    activity_target.mkdir()
    shutil.copy2(
        overlay / "agents/activity/AgentActivity.tsx", activity_target / "index.tsx"
    )
    agents_patch = overlay / "integration/agents.patch"
    # HEAD stays pinned; patch context tolerates whitespace differences, including Windows CRLF.
    subprocess.run(
        [
            "git",
            "-C",
            str(checkout),
            "apply",
            "--ignore-space-change",
            "--check",
            str(agents_patch),
        ],
        check=True,
    )
    subprocess.run(
        [
            "git",
            "-C",
            str(checkout),
            "apply",
            "--ignore-space-change",
            str(agents_patch),
        ],
        check=True,
    )
    agents_target = checkout / "src/frontend/src/modals/graphAgents"
    agents_target.mkdir()
    shutil.copy2(
        overlay / "agents/activity/AgentActivityNavigation.ts",
        checkout / "src/frontend/src/stores/agentActivityStore.ts",
    )
    for asset in (overlay / "agents/activity").iterdir():
        if asset.suffix in {".ts", ".tsx"} and asset.name not in {
            "AgentActivity.tsx",
            "AgentActivity.test.tsx",
            "AgentActivityNavigation.ts",
        }:
            shutil.copy2(asset, agents_target / asset.name)
    (agents_target / "index.tsx").write_text(
        'export { default } from "./GraphAgents";\n', encoding="utf-8"
    )
    recovery_target = checkout / "src/frontend/src/components/laomedoRecovery"
    recovery_target.mkdir()
    for name in (
        "RunnerRecovery.tsx",
        "RunnerRecovery.test.tsx",
        "RecoveryPopup.tsx",
        "RecoveryPopup.test.tsx",
        "PopupFrame.tsx",
    ):
        shutil.copy2(overlay / name, recovery_target / name)
    error_target = checkout / "src/frontend/src/components/laomedoErrors"
    error_target.mkdir()
    for name in (
        "nodeErrors.ts",
        "node-error-catalog.json",
        "NodeErrorNotice.tsx",
        "nodeErrors.test.ts",
        "NodeErrorNotice.test.tsx",
        "ErrorPopup.tsx",
        "ErrorPopup.test.tsx",
        "ErrorAlertMigration.test.tsx",
        "ApplicationErrorPopup.tsx",
        "CopyIcon.tsx",
        "ErrorExplanation.tsx",
    ):
        shutil.copy2(overlay / name, error_target / name)
    shutil.copy2(
        overlay / "ErrorAlert.tsx", checkout / "src/frontend/src/alerts/error/index.tsx"
    )
    status_path = (
        checkout
        / "src/frontend/src/CustomNodes/GenericNode/components/NodeStatus/index.tsx"
    )
    status_source = status_path.read_text(encoding="utf-8")
    status_source = (
        'import NodeErrorNotice from "@/components/laomedoErrors/NodeErrorNotice";\nimport { hasLaomedoFailure } from "@/components/laomedoErrors/nodeErrors";\n'
        + status_source
    )
    marker = "{showNodeStatus && (\n            <ShadTooltip"
    if status_source.count(marker) != 1:
        raise SystemExit("pinned_node_status_error_anchor_missing")
    status_source = replace_once(
        status_source,
        marker,
        """{showNodeStatus && (
            data.type?.startsWith("Laomedo") && (conditionError || hasLaomedoFailure(validationStatus)) ?
            <NodeErrorNotice message={validationString} status={validationStatus} context={{
              nodeId, nodeType: data.type, nodeLabel: display_name,
              operation: data.node?.template?.operation?.value,
              savedReferences: [data.node?.template?.run_reference?.value, data.node?.template?.run_reference_json?.value],
            }} /> : <ShadTooltip""",
    )
    marker = "  const conditionError = buildStatus === BuildStatus.ERROR;"
    replacement = '  const scopedFlowError = useFlowStore((state) => state.nodes?.length === 1 && state.nodes[0].id === nodeId && data.type?.startsWith("Laomedo") ? state.buildInfo?.error?.[0] : undefined);\n  const conditionError = buildStatus === BuildStatus.ERROR;'
    if status_source.count(marker) != 1:
        raise SystemExit("pinned_node_error_scope_anchor_missing")
    status_source = replace_once(status_source, marker, replacement)
    status_source = replace_once(
        status_source,
        "conditionSuccess || conditionError || conditionInactive;",
        "conditionSuccess || conditionError || conditionInactive || Boolean(scopedFlowError);",
    )
    status_source = replace_once(
        status_source,
        "(conditionError || hasLaomedoFailure(validationStatus))",
        "(conditionError || Boolean(scopedFlowError) || hasLaomedoFailure(validationStatus))",
    )
    status_source = replace_once(
        status_source,
        "message={validationString} status={validationStatus}",
        "message={scopedFlowError || validationString} status={validationStatus}",
    )
    status_path.write_text(status_source, encoding="utf-8")
    alerts_path = checkout / "src/frontend/src/stores/alertStore.ts"
    alerts = alerts_path.read_text(encoding="utf-8")
    alerts = (
        'import { describeLaomedoAlert } from "@/components/laomedoErrors/nodeErrors";\nimport useFlowStore from "@/stores/flowStore";\n'
        + alerts
    )
    marker = "setErrorData: (newState: { title: string; list?: Array<string> }) => {"
    if alerts.count(marker) != 1:
        raise SystemExit("pinned_error_alert_anchor_missing")
    alerts = replace_once(
        alerts,
        marker,
        marker
        + '\n    const flowErrors = useFlowStore.getState().buildInfo?.error ?? [];\n    const handledByFlow = (newState.list ?? []).some(message => flowErrors.includes(message));\n    const formatted = describeLaomedoAlert(newState, useFlowStore.getState().nodes?.some(node => node.data.type?.startsWith("Laomedo")));\n    const diagnosticCode = formatted.diagnosticCode;\n    const failure = formatted.failure;\n    newState = { title: formatted.title, list: formatted.list };',
    )
    marker = "      get().addNotificationToHistory(notification);"
    if alerts.count(marker) != 3:
        raise SystemExit("pinned_notification_history_anchor_missing")
    alerts = alerts.replace(
        marker,
        '      get().addNotificationToHistory(diagnosticCode ? { ...notification, list: [...(notification.list ?? []), "Diagnostic code: " + diagnosticCode] } : notification);',
        1,
    )
    alerts = replace_once(
        alerts, '        type: "error",', '        type: "error",\n        failure,'
    )
    alerts = alerts.replace(
        "      get().addNotificationToTempList(notification);",
        "      if (!handledByFlow) get().addNotificationToTempList(notification);",
        1,
    )
    alert_types = checkout / "src/frontend/src/types/alerts/index.ts"
    types = alert_types.read_text(encoding="utf-8")
    types = (
        'import type { NodeFailure } from "@/components/laomedoErrors/nodeErrors";\n'
        + types
    )
    types = types.replace(
        "export type ErrorAlertType = {",
        "export type ErrorAlertType = {\n  failure?: NodeFailure;",
    )
    types = types.replace(
        "export type AlertItemType = {",
        "export type AlertItemType = {\n  failure?: NodeFailure;",
    )
    alert_types.write_text(types, encoding="utf-8")
    area_path = checkout / "src/frontend/src/alerts/displayArea/index.tsx"
    area = area_path.read_text(encoding="utf-8")
    area = replace_once(
        area,
        "            <ErrorAlert\n",
        "            <ErrorAlert\n              failure={alert.failure}\n",
    )
    area_path.write_text(area, encoding="utf-8")
    alerts_path.write_text(alerts, encoding="utf-8")
    flow_error_path = (
        checkout
        / "src/frontend/src/pages/FlowPage/components/flowBuildingComponent/index.tsx"
    )
    flow_error = flow_error_path.read_text(encoding="utf-8")
    flow_error = (
        'import { FlowErrorPopup } from "@/components/laomedoErrors/ErrorPopup";\nimport { isRunnerConnectionError } from "@/components/laomedoRecovery/RunnerRecovery";\nimport NodeErrorNotice from "@/components/laomedoErrors/NodeErrorNotice";\nimport { isKnownNodeError } from "@/components/laomedoErrors/nodeErrors";\n'
        + flow_error
    )
    marker = "  const errorButtonsRef = useRef<HTMLDivElement>(null);"
    replacement = '  const graphNodes = useFlowStore((state) => state.nodes ?? []);\n  const affectedNode = graphNodes.length === 1 && graphNodes[0].data.type?.startsWith("Laomedo") ? graphNodes[0] : undefined;\n  const descriptiveError = buildInfo?.error?.find(message => isKnownNodeError(message, graphNodes.some(node => node.data.type?.startsWith("Laomedo")))) ?? buildInfo?.error?.[0];\n  const errorButtonsRef = useRef<HTMLDivElement>(null);'
    if flow_error.count(marker) != 1:
        raise SystemExit("pinned_flow_error_anchor_missing")
    flow_error = replace_once(flow_error, marker, replacement)
    flow_error = replace_once(
        flow_error,
        '                                  <Button size="sm" onClick={handleRetry}>',
        '                                  {!descriptiveError && <Button size="sm" onClick={handleRetry}>',
    )
    flow_error = replace_once(
        flow_error,
        '{t("flowBuild.retry")}\n                                  </Button>',
        '{t("flowBuild.retry")}\n                                  </Button>}',
    )
    flow_error = replace_once(
        flow_error,
        'className="max-h-48 overflow-y-auto"',
        'className="max-h-[60vh] overflow-y-auto"',
    )
    flow_error = replace_once(
        flow_error,
        "                        <Markdown\n",
        '                        {descriptiveError ? <NodeErrorNotice inline message={descriptiveError} context={{\n                          nodeId: affectedNode?.id, nodeType: affectedNode?.data.type, nodeLabel: affectedNode?.data.node?.display_name ?? "Flow",\n                          operation: affectedNode?.data.node?.template?.operation?.value,\n                          savedReferences: [affectedNode?.data.node?.template?.run_reference?.value, affectedNode?.data.node?.template?.run_reference_json?.value],\n                        }} /> : <Markdown\n',
    )
    flow_error = replace_once(
        flow_error,
        "                        </Markdown>",
        "                        </Markdown>}",
    )
    flow_error = replace_once(
        flow_error,
        'className="absolute right-0 font-mono text-xs"',
        'className={cn("absolute right-0 font-mono text-xs", descriptiveError && "hidden")}',
    )
    # Stop must disappear immediately on success, not survive as an exiting
    # animation over the successful duration.
    flow_error = replace_once(
        flow_error,
        '                      <AnimatePresence mode="sync">\n                        {!buildInfo?.success && (',
        '                      {!buildInfo?.success && <AnimatePresence mode="sync">\n                        {!buildInfo?.success && (',
    )
    flow_error = replace_once(
        flow_error,
        "                      </AnimatePresence>\n                    </div>",
        "                      </AnimatePresence>}\n                    </div>",
    )
    flow_error = replace_once(
        flow_error,
        '  return (\n    <AnimatePresence mode="wait">',
        '  if (!isBuilding && descriptiveError && !dismissed) {\n    return <FlowErrorPopup message={descriptiveError} laomedo={Boolean(affectedNode) || isKnownNodeError(descriptiveError, graphNodes.some(node => node.data.type?.startsWith("Laomedo")))} onDismiss={() => { setBuildInfo(null); setDismissed(false); }} context={{\n      nodeId: affectedNode?.id, nodeType: affectedNode?.data.type, nodeLabel: affectedNode?.data.node?.display_name,\n      operation: affectedNode?.data.node?.template?.operation?.value,\n      savedReferences: [affectedNode?.data.node?.template?.run_reference?.value, affectedNode?.data.node?.template?.run_reference_json?.value],\n    }} />;\n  }\n  return (\n    <AnimatePresence mode="wait">',
    )
    flow_error_path.write_text(flow_error, encoding="utf-8")
    outcome_patch = overlay / "runner-outcomes.patch"
    subprocess.run(
        [
            "git",
            "-C",
            str(checkout),
            "apply",
            "--ignore-space-change",
            "--check",
            str(outcome_patch),
        ],
        check=True,
    )
    subprocess.run(
        [
            "git",
            "-C",
            str(checkout),
            "apply",
            "--ignore-space-change",
            str(outcome_patch),
        ],
        check=True,
    )
    github_outcome_patch = overlay / "integration/github-build-outcome.patch"
    for mode in ("--check", None):
        command = ["git", "-C", str(checkout), "apply", "--ignore-space-change"]
        if mode:
            command.append(mode)
        subprocess.run(command + [str(github_outcome_patch)], check=True)
    from apply_langflow_local_profiles import apply_profiles

    apply_profiles(checkout, overlay)
    print("pinned_skill_viewer_overlay_applied")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("checkout", type=Path)
    apply(parser.parse_args().checkout)
