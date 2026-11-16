"""Install provider Settings in the maintained pinned frontend overlay."""

from pathlib import Path
import shutil


def apply_providers(checkout: Path, source: Path):
    """Check every upstream anchor before copying assets or changing entrypoints."""
    frontend = checkout / "src/frontend/src"
    target = frontend / "components/laomedoProviders"
    if target.exists():
        raise SystemExit("provider_overlay_requires_fresh_checkout")
    routes = frontend / "routes.tsx"
    text = routes.read_text(encoding="utf-8")
    anchor = 'import SettingsPage from "./pages/SettingsPage";'
    route_anchor = '<Route path="mcp-servers" element={<MCPServersPage />} />'
    if text.count(anchor) != 1 or text.count(route_anchor) != 1:
        raise SystemExit("provider_settings_route_anchor_missing")
    text = text.replace(
        anchor,
        anchor
        + '\nimport ProviderConnections from "@/components/laomedoProviders/ProviderConnections";',
    )
    text = text.replace(
        route_anchor,
        '<Route path="providers" element={<ProviderConnections />} />\n' + route_anchor,
    )
    settings = frontend / "pages/SettingsPage/index.tsx"
    settings_text = settings.read_text(encoding="utf-8")
    settings_anchor = "\n  sidebarNavItems.push("
    if settings_text.count(settings_anchor) != 1:
        raise SystemExit("provider_settings_menu_anchor_missing")
    settings_text = settings_text.replace(
        settings_anchor,
        '\n  sidebarNavItems.push({ title: "Providers", href: "/settings/providers", icon: <ForwardedIconComponent name="Terminal" className="w-4" /> });\n'
        + settings_anchor,
    )
    shutil.copytree(source / "providers", target)
    routes.write_text(text, encoding="utf-8")
    settings.write_text(settings_text, encoding="utf-8")
