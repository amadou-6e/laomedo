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
    anchor = "    if (autoLogin) {"
    if signout.count(anchor) != 1:
        raise SystemExit("assistant_logout_anchor_missing")
    signout = (
        'import { lockAssistant } from "@/components/laomedoAssistant/api";\n'
        + signout.replace(anchor, "    await lockAssistant();\n" + anchor)
    )
    shutil.copytree(
        source / "assistant", destination, ignore=shutil.ignore_patterns("README.md")
    )
    routes.write_text(text, encoding="utf-8")
    header.write_text(content, encoding="utf-8")
    logout.write_text(signout, encoding="utf-8")
