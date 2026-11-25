import { useCallback, useEffect, useRef, useState } from "react";
import useFlowStore from "@/stores/flowStore";
import { ExternalLink, Info, RefreshCw } from "lucide-react";
import useHandleOnNewValue from "@/CustomNodes/hooks/use-handle-new-value";
import { api } from "@/controllers/API/api";
import { getURL } from "@/controllers/API/helpers/constants";
import { connectionCapability, connectionRequest, ConnectionFailure } from "@/components/laomedoGitHubConnections/api";
import type { ConnectionIndex } from "@/components/laomedoGitHubConnections/types";
import NodeErrorNotice from "@/components/laomedoErrors/NodeErrorNotice";
import { privateSkillRequest, subscribePrivateInvalidation } from "./api";
import type { PrivateDiscovery, PrivateOrigin } from "./models";

/** Select a previously saved source or a repository available to the chosen connection. */
export function SkillSourceSuggestions({ data }: { data: any }) {
  const [open, setOpen] = useState(false);
  const [sources, setSources] = useState<string[]>([]);
  const [error, setError] = useState(false);
  const [loading, setLoading] = useState(false);
  const connectionId = String(data.node?.template?.github_connection?.value || "");
  const { handleOnNewValue } = useHandleOnNewValue({ node: data.node, nodeId: data.id, name: "source" });

  useEffect(() => {
    if (!open) return;
    let active = true;
    const abort = new AbortController();
    setSources([]); setError(false); setLoading(true);
    const load = async () => {
      try {
        const [response, connections] = await Promise.all([
          api.get(`${getURL("FLOWS")}/?get_all=true`, { signal: abort.signal }),
          connectionId ? connectionRequest() : Promise.resolve(undefined),
        ]);
        if (!active) return;
        const flows = Array.isArray(response.data) ? response.data : response.data?.items || [];
        const saved: string[] = [];
        for (const flow of flows) for (const node of flow.data?.nodes || []) {
          const value = node.data?.node?.template;
          const type = node.data?.node?.name || node.data?.node?.type || node.data?.type;
          if (type === "LaomedoSkill" && String(value?.github_connection?.value || "") === connectionId && typeof value?.source?.value === "string" && value.source.value.trim()) saved.push(value.source.value);
        }
        const selected = connections?.index.connections.find(({ connection }) => connection.id === connectionId && connection.state === "ready");
        const repositories = selected?.connection.repositories.map((repository) => `https://github.com/${repository.full_name}`) || [];
        setSources([...new Set([...repositories, ...saved])]);
      } catch { if (active) setError(true); }
      finally { if (active) setLoading(false); }
    };
    void load();
    return () => { active = false; abort.abort(); };
  }, [open, connectionId]);

  return <div className="nodrag nopan px-5 pb-2 text-xs">
    <button type="button" className="text-muted-foreground underline" aria-expanded={open} onClick={() => setOpen(!open)}>Choose a saved source or repository</button>
    {open && <div className="mt-1 max-h-40 overflow-auto rounded border bg-background" role="group" aria-label="Saved sources and repositories">
      {sources.map((source) => <button key={source} type="button" className="block w-full truncate px-2 py-1 text-left hover:bg-muted" title={source} onClick={() => { handleOnNewValue({ value: source }); setOpen(false); }}>{source}</button>)}
      {!sources.length && <p className="px-2 py-1 text-muted-foreground">{loading ? "Loading sources…" : error ? "Sources could not be loaded." : "No saved sources or repositories."}</p>}
    </div>}
  </div>;
}

/** Populate the existing searchable Skill/Revision fields; Connection stays Advanced. */
export default function PrivateSkillControls({ data }: { data: any }) {
  const template = data.node?.template || {};
  const connectionId = String(template.github_connection?.value || "");
  const source = String(template.source?.value || "");
  const skill = String(template.skill_id?.value || "");
  const revision = String(template.revision_id?.value || "");
  const [enabled, setEnabled] = useState(false);
  const [index, setIndex] = useState<ConnectionIndex>();
  const [origins, setOrigins] = useState<PrivateOrigin[]>([]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const epoch = useRef(0);
  const setNode = useFlowStore((state) => state.setNode);
  const update = useCallback((fields: Record<string, unknown>, options: Record<string, string[]> = {}) => setNode(data.id, (old: any) => {
    const next = { ...old.data.node.template };
    for (const [name, value] of Object.entries(fields)) next[name] = { ...next[name], value };
    for (const [name, values] of Object.entries(options)) next[name] = { ...next[name], options: values, combobox: false };
    return { ...old, data: { ...old.data, node: { ...old.data.node, template: next } } };
  }), [data.id, setNode]);
  useEffect(() => {
    let active = true;
    connectionCapability().then((value) => { if (active) setEnabled(value); });
    return () => { active = false; ++epoch.current; };
  }, []);
  useEffect(() => subscribePrivateInvalidation(() => {
    ++epoch.current; setIndex(undefined); setOrigins([]); setBusy(false);
    if (connectionId) { update({}, { skill_id: [], revision_id: [] }); setError("github_connection_changed"); }
  }), [connectionId, update]);
  const load = async (kind: "connections" | "skills" | "revisions") => {
    const current = ++epoch.current;
    setBusy(true); setError("");
    try {
      const result = await connectionRequest();
      if (epoch.current !== current) return;
      setIndex(result.index);
      if (kind === "connections") return;
      const parsed = source.match(/^https:\/\/github\.com\/([A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+?)(?:\.git)?\/?$/);
      const connection = result.index.connections.find((entry) => entry.connection.id === connectionId && entry.connection.state === "ready");
      const repository = connection?.connection.repositories.find((entry) => entry.full_name.toLowerCase() === parsed?.[1]?.toLowerCase());
      if (!repository) throw new ConnectionFailure("github_repository_access_unconfirmed");
      const selected = { connectionId, repositoryId: repository.id };
      if (kind === "skills") {
        const found = await privateSkillRequest<PrivateDiscovery>("discover", selected);
        if (epoch.current !== current) return;
        setOrigins([]);
        update({ private_repository_id: String(repository.id) }, { skill_id: found.skills.map((item) => item.choice) });
        if (skill && found.skills.some((item) => item.choice === skill)) {
          const retained = await privateSkillRequest<{ revisions: PrivateOrigin[] }>("revisions", selected, { choice: skill });
          if (epoch.current !== current) return;
          setOrigins(retained.revisions);
          update({}, { revision_id: retained.revisions.map((origin) => `${origin.label} @ ${origin.commit}`) });
        }
      } else {
        const found = await privateSkillRequest<{ revisions: PrivateOrigin[] }>("revisions", selected, { choice: skill });
        if (epoch.current !== current) return;
        setOrigins(found.revisions);
        update({ private_repository_id: String(repository.id) }, { revision_id: found.revisions.map((origin) => `${origin.label} @ ${origin.commit}`) });
      }
    } catch (failure) {
      if (epoch.current !== current) return;
      setOrigins([]); setIndex(undefined);
      if (connectionId) update({}, { skill_id: [], revision_id: [] });
      setError(failure instanceof ConnectionFailure ? failure.code : "github_connection_unavailable");
    } finally { if (epoch.current === current) setBusy(false); }
  };
  const latestLoad = useRef(load); latestLoad.current = load;
  const previous = useRef({ identity: "", skill: "" });
  useEffect(() => {
    const identity = `${enabled}:${connectionId}:${source}`;
    const sourceChanged = previous.current.identity !== identity;
    previous.current = { identity, skill };
    ++epoch.current; setOrigins([]); setBusy(false); setError("");
    if (enabled && connectionId && source && (sourceChanged || skill))
      void latestLoad.current(sourceChanged ? "skills" : "revisions");
  }, [enabled, connectionId, source, skill]);
  useEffect(() => {
    const origin = origins.find((item) => `${item.label} @ ${item.commit}` === revision);
    if (origin) update({ resolved_skill_id: origin.skill_id, resolved_revision_id: origin.revision_id,
      resolved_selection: JSON.stringify([source, skill, revision, connectionId]) });
  }, [origins, revision, source, skill, connectionId, update]);
  if (!enabled && !connectionId) return null;
  return <section className="nodrag nopan grid gap-2 px-5 py-3 text-sm" aria-label="Private Skill source">
    <div className="flex items-center gap-2">
      <label htmlFor={`connection-${data.id}`}>Connection</label>
      <button type="button" aria-label="Private files are read only. Agent execution is unavailable." title="Private files are read only. Agent execution is unavailable."><Info className="h-3.5 w-3.5 text-muted-foreground" aria-hidden="true" /></button>
      <button type="button" aria-label="Refresh private source" title="Refresh private source" disabled={busy || !enabled || !connectionId || !source} onClick={() => void load("skills")}><RefreshCw className="h-3.5 w-3.5" aria-hidden="true" /></button>
      <a aria-label="Manage GitHub connections" title="Manage GitHub connections" href="/settings/github" target="_blank" rel="noreferrer"><ExternalLink className="h-3.5 w-3.5" aria-hidden="true" /></a>
    </div>
    <select id={`connection-${data.id}`} className="rounded border bg-background p-2" value={connectionId} disabled={busy || !enabled}
      onFocus={() => { if (!index && !busy) void load("connections"); }}
      onChange={(event) => { ++epoch.current; update({ github_connection: event.target.value, discovery_status: "", private_repository_id: "", skill_id: "", revision_id: "", resolved_skill_id: "", resolved_revision_id: "", resolved_selection: "" }, { skill_id: [], revision_id: [] }); }}>
      <option value="">Anonymous</option>
      {connectionId && !index?.connections.some((entry) => entry.connection.id === connectionId) && <option value={connectionId}>Selected connection</option>}
      {index?.connections.filter((entry) => entry.connection.state === "ready").map(({ connection }) => <option key={connection.id} value={connection.id}>{connection.principal.login} ({connection.mode})</option>)}
    </select>
    {busy && <p role="status">Checking access…</p>}
    {error && <div role="alert" className="text-destructive"><NodeErrorNotice message={error}
      label="Access to this repository could not be confirmed."
      context={{ nodeId: data.id, nodeType: "LaomedoSkill", operation: "Private source" }} /></div>}
  </section>;
}
