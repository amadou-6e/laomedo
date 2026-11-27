"""Install the direct-chat UI on the pinned Langflow source after the base overlay."""

from pathlib import Path
import shutil


def apply_assistant(checkout: Path, source: Path):
    """Require exact route/header/logout anchors and preserve existing editor state paths."""
    frontend = checkout / "src/frontend/src"
    destination = frontend / "components/laomedoAssistant"
    if destination.exists():
        raise SystemExit("assistant_overlay_requires_fresh_checkout")
    routes = frontend / "routes.tsx"
    text = routes.read_text(encoding="utf-8")
    before = '<Route path="" element={<CustomDashboardWrapperPage />}>'
    if text.count(before) != 2:
        # The second wrapper belongs to the editor route; never replace it.
        raise SystemExit("assistant_route_anchor_missing")
    text = (
        'import AssistantPage from "@/components/laomedoAssistant/AssistantPage";\n'
        + text.replace(
            before,
            before
            + '\n                <Route path="assistant" element={<AssistantPage />} />',
            1,
        )
    )
    header = frontend / "components/core/appHeaderComponent/index.tsx"
    content = header.read_text(encoding="utf-8")
    anchor = "{false && <ModelProviderCount />}"
    if content.count(anchor) != 1:
        raise SystemExit("assistant_header_anchor_missing")
    content = (
        'import AssistantEntry from "@/components/laomedoAssistant/AssistantEntry";\n'
        + content.replace(anchor, "<AssistantEntry />\n        " + anchor)
    )
    logout = frontend / "controllers/API/queries/auth/use-post-logout.ts"
    signout = logout.read_text(encoding="utf-8")
    anchor = "  async function logoutUser(): Promise<unknown> {"
    if signout.count(anchor) != 1:
        raise SystemExit("assistant_logout_anchor_missing")
    signout = (
        'import { lockAssistant } from "@/components/laomedoAssistant/api";\n'
        + signout.replace(anchor, anchor + "\n    await lockAssistant();")
    )
    editor = frontend / "pages/FlowPage/index.tsx"
    editor_content = editor.read_text(encoding="utf-8")
    editor_anchor = (
        "                    </main>\n                  </FlowSearchProvider>"
    )
    if editor_content.count(editor_anchor) != 1:
        raise SystemExit("assistant_editor_anchor_missing")
    editor_content = (
        'import AssistantSidebar from "@/components/laomedoAssistant/sidebar/AssistantSidebar";\n'
        + editor_content.replace(
            editor_anchor,
            "                    </main>\n                    <AssistantSidebar />\n                  </FlowSearchProvider>",
        )
    )
    rail = (
        frontend
        / "pages/FlowPage/components/flowSidebarComponent/components/sidebarSegmentedNav.tsx"
    )
    rail_content = rail.read_text(encoding="utf-8")
    rail_anchor = "        ))}\n      </SidebarMenu>"
    if rail_content.count(rail_anchor) != 1:
        raise SystemExit("assistant_rail_anchor_missing")
    rail_content = (
        'import AssistantSidebarToggle from "@/components/laomedoAssistant/sidebar/AssistantSidebarToggle";\n'
        + rail_content.replace(
            rail_anchor,
            "        ))}\n        <AssistantSidebarToggle hiddenFromTabOrder={hiddenFromTabOrder} />\n      </SidebarMenu>",
        )
    )
    parameter = frontend / "components/core/parameterRenderComponent/index.tsx"
    parameter_content = parameter.read_text(encoding="utf-8")
    parameter_anchor = "    const baseInputProps: InputProps = {"
    if parameter_content.count(parameter_anchor) != 1:
        raise SystemExit("assistant_registered_mcp_parameter_anchor_missing")
    parameter_content = (
        'import RegisteredMcpReference from "@/components/laomedoAssistant/graphs/RegisteredMcpReference";\n'
        'import { isRegisteredMcpNode } from "@/components/laomedoAssistant/graphs/registeredMcp";\n'
        + parameter_content.replace(
            parameter_anchor,
            '    if (name === "mcp_server" && isRegisteredMcpNode(useFlowStore.getState().nodes.find(entry => entry.id === nodeId)?.data)) {\n'
            "      return <RegisteredMcpReference value={templateValue} labelledBy={ariaLabelledBy} />;\n"
            "    }\n" + parameter_anchor,
        )
    )
    generic = frontend / "CustomNodes/GenericNode/index.tsx"
    generic_content = generic.read_text(encoding="utf-8")
    generic_anchor = "    (data.node?.outputs ?? []).forEach((output) => {"
    if generic_content.count(generic_anchor) != 1:
        raise SystemExit("assistant_registered_mcp_output_anchor_missing")
    generic_content = (
        'import { isRegisteredMcpNode } from "@/components/laomedoAssistant/graphs/registeredMcp";\n'
        + generic_content.replace(
            generic_anchor,
            generic_anchor
            + '\n      if (isRegisteredMcpNode(data) && output.name !== "component_as_tool") return;',
        )
    )
    mount = frontend / "CustomNodes/hooks/use-fetch-data-on-mount.ts"
    mount_content = mount.read_text(encoding="utf-8")
    mount_anchor = "  useEffect(() => {\n    async function fetchData() {"
    if mount_content.count(mount_anchor) != 1:
        raise SystemExit("assistant_registered_mcp_mount_anchor_missing")
    mount_content = (
        'import useFlowStore from "@/stores/flowStore";\n'
        'import { isRegisteredMcpNode } from "@/components/laomedoAssistant/graphs/registeredMcp";\n'
        + mount_content.replace(
            mount_anchor,
            "  useEffect(() => {\n"
            "    if (isRegisteredMcpNode(useFlowStore.getState().nodes.find(entry => entry.id === nodeId)?.data)) return;\n"
            "    async function fetchData() {",
        )
    )
    store = frontend / "stores/flowStore.ts"
    store_content = store.read_text(encoding="utf-8")
    store_anchor = "      const freshOut = freshDef.outputs?.[i];"
    if store_content.count(store_anchor) != 1:
        raise SystemExit("assistant_registered_mcp_translation_anchor_missing")
    store_content = (
        'import { isRegisteredMcpNode } from "@/components/laomedoAssistant/graphs/registeredMcp";\n'
        + store_content.replace(
            store_anchor,
            "      const freshOut = isRegisteredMcpNode(node.data)\n"
            "        ? freshDef.outputs?.find((candidate) => candidate.name === output.name)\n"
            "        : freshDef.outputs?.[i];",
        )
    )
    shutil.copytree(
        source / "assistant", destination, ignore=shutil.ignore_patterns("README.md")
    )
    routes.write_text(text, encoding="utf-8")
    header.write_text(content, encoding="utf-8")
    logout.write_text(signout, encoding="utf-8")
    editor.write_text(editor_content, encoding="utf-8")
    rail.write_text(rail_content, encoding="utf-8")
    parameter.write_text(parameter_content, encoding="utf-8")
    generic.write_text(generic_content, encoding="utf-8")
    mount.write_text(mount_content, encoding="utf-8")
    store.write_text(store_content, encoding="utf-8")
