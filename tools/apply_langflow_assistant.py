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
    anchor = "    if (autoLogin && !(await profileMode().catch(() => true))) {"
    if signout.count(anchor) != 1:
        raise SystemExit("assistant_logout_anchor_missing")
    signout = (
        'import { lockAssistant } from "@/components/laomedoAssistant/api";\n'
        + signout.replace(anchor, "    await lockAssistant();\n" + anchor)
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
    shutil.copytree(
        source / "assistant", destination, ignore=shutil.ignore_patterns("README.md")
    )
    routes.write_text(text, encoding="utf-8")
    header.write_text(content, encoding="utf-8")
    logout.write_text(signout, encoding="utf-8")
    editor.write_text(editor_content, encoding="utf-8")
    rail.write_text(rail_content, encoding="utf-8")
