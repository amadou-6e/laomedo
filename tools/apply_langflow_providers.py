"""Install provider Settings in the maintained pinned frontend overlay."""

from pathlib import Path
import shutil


def provider_policy_edits(checkout: Path):
    """Prepare exact pinned source edits for export/import and account labels."""
    frontend = checkout / "src/frontend/src"
    core = checkout / "src/backend/base/langflow/api/utils/core.py"
    core_text = core.read_text(encoding="utf-8")
    export_anchor = (
        "    flow = copy.deepcopy(flow)\n\n    # Strip volatile top-level metadata"
    )
    if core_text.count(export_anchor) != 1:
        raise SystemExit("provider_export_anchor_missing")
    core_text = core_text.replace(
        export_anchor,
        "    from laomedo.integrations.langflow.provider_connections.exports import strip_local_bindings\n\n    flow = strip_local_bindings(flow)\n\n    # Strip volatile top-level metadata",
    )
    uploads = checkout / "src/backend/base/langflow/api/v1/flows.py"
    upload_text = uploads.read_text(encoding="utf-8")
    upload_anchor = (
        "    # Normalise code fields: if exported with code-as-lines format, rejoin to"
    )
    if upload_text.count(upload_anchor) != 1:
        raise SystemExit("provider_import_anchor_missing")
    upload_text = upload_text.replace(
        upload_anchor,
        "    from laomedo.integrations.langflow.provider_connections.exports import strip_local_bindings\n\n    data = strip_local_bindings(data)\n\n"
        + upload_anchor,
    )
    download = frontend / "customization/utils/custom-reactFlowUtils.ts"
    download_text = download.read_text(encoding="utf-8")
    download_anchor = "encodeURIComponent(sortedJsonString)"
    if download_text.count(download_anchor) != 1:
        raise SystemExit("provider_client_export_anchor_missing")
    download_text = (
        'import { stripLocalBindings } from "@/components/laomedoProviders/exports";\n'
        + download_text.replace(
            download_anchor,
            "encodeURIComponent(JSON.stringify(stripLocalBindings(JSON.parse(sortedJsonString)), null, 2))",
        )
    )
    edits = {core: core_text, uploads: upload_text, download: download_text}
    dropdown = frontend / "components/core/dropdownComponent"
    trigger = dropdown / "components/DropdownTrigger.tsx"
    trigger_text = trigger.read_text(encoding="utf-8")
    trigger_anchor = 'selectedMetadata?.laomedo_native_model === true && typeof selectedMetadata.display_name === "string"'
    if trigger_text.count(trigger_anchor) != 1:
        raise SystemExit("provider_label_trigger_anchor_missing")
    edits[trigger] = trigger_text.replace(
        trigger_anchor,
        '(selectedMetadata?.laomedo_native_model === true || selectedMetadata?.laomedo_connection === true) && typeof selectedMetadata.display_name === "string"',
    )
    options = dropdown / "components/DropdownOptionsList.tsx"
    options_text = options.read_text(encoding="utf-8")
    options_anchor = '{filteredMetadata?.[index]?.laomedo_native_model === true && typeof filteredMetadata[index]?.display_name === "string" ? ('
    if options_text.count(options_anchor) != 1:
        raise SystemExit("provider_label_options_anchor_missing")
    edits[options] = options_text.replace(
        options_anchor,
        '{filteredMetadata?.[index]?.laomedo_connection === true ? (<div className="truncate text-[13px]">{filteredMetadata[index].display_name}</div>) : filteredMetadata?.[index]?.laomedo_native_model === true && typeof filteredMetadata[index]?.display_name === "string" ? (',
    )
    footer_anchor = "filteredMetadata[index]?.laomedo_native_model !== true && ("
    if edits[options].count(footer_anchor) != 1:
        raise SystemExit("provider_label_metadata_anchor_missing")
    edits[options] = edits[options].replace(
        footer_anchor,
        "filteredMetadata[index]?.laomedo_native_model !== true && filteredMetadata[index]?.laomedo_connection !== true && (",
    )
    search = dropdown / "hooks/useDropdownOptions.ts"
    search_text = search.read_text(encoding="utf-8")
    search_anchor = "item?.laomedo_native_model === true"
    if search_text.count(search_anchor) != 2:
        raise SystemExit("provider_label_search_anchor_missing")
    edits[search] = search_text.replace(
        search_anchor,
        "(item?.laomedo_native_model === true || item?.laomedo_connection === true)",
    )
    return edits


def apply_providers(checkout: Path, source: Path):
    """Check every upstream anchor before copying assets or changing entrypoints."""
    frontend = checkout / "src/frontend/src"
    target = frontend / "components/laomedoProviders"
    if target.exists():
        raise SystemExit("provider_overlay_requires_fresh_checkout")
    edits = provider_policy_edits(checkout)
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
    flow_page = frontend / "pages/FlowPage/index.tsx"
    flow_text = flow_page.read_text(encoding="utf-8")
    trace_start = flow_text.index("  if (showTraces) {")
    trace_end = flow_text.index("  if (showMemories) {", trace_start)
    flow_text = (
        flow_text[:trace_start]
        + "  if (showTraces) {\n    return <GraphTraces flowId={flowId} />;\n  }\n\n"
        + flow_text[trace_end:]
    )
    flow_text = (
        'import GraphTraces from "@/modals/graphAgents/GraphTraces";\n' + flow_text
    )
    edits[flow_page] = flow_text
    agents_index = frontend / "modals/graphAgents/index.tsx"
    if not agents_index.exists():
        raise SystemExit("provider_graph_agents_anchor_missing")
    shutil.copytree(source / "providers", target)
    agents_index.write_text(
        'export { default } from "@/components/laomedoProviders/SubscriptionAgents";\n',
        encoding="utf-8",
    )
    routes.write_text(text, encoding="utf-8")
    settings.write_text(settings_text, encoding="utf-8")
    for path, contents in edits.items():
        path.write_text(contents, encoding="utf-8")
