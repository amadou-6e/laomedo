import { useEffect, useRef, useState } from "react";
import useFlowStore from "@/stores/flowStore";
import { connectionCapability, connectionRequest, ConnectionFailure } from "@/components/laomedoGitHubConnections/api";
import type { ConnectionIndex } from "@/components/laomedoGitHubConnections/types";
import ErrorExplanation from "@/components/laomedoErrors/ErrorExplanation";
import { describeNodeFailure } from "@/components/laomedoErrors/nodeErrors";
import { privateSkillRequest, subscribePrivateInvalidation } from "./api";
import type { PrivateDiscovery, PrivateOrigin } from "./models";

export default function PrivateSkillControls({ data }: { data: any }) {
  const template = data.node?.template || {};
  const connectionId = String(template.github_connection?.value || "");
  const source = String(template.source?.value || "");
  const skill = String(template.skill_id?.value || "");
  const revision = String(template.revision_id?.value || "");
  const [enabled, setEnabled] = useState(false);
  const [index, setIndex] = useState<ConnectionIndex>();
  const [choices, setChoices] = useState<PrivateDiscovery["skills"]>([]);
  const [origins, setOrigins] = useState<PrivateOrigin[]>([]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const epoch = useRef(0);
  const setNode = useFlowStore((state) => state.setNode);
  const update = (fields: Record<string, unknown>) => setNode(data.id, (old: any) => {
    const next = { ...old.data.node.template };
    for (const [name, value] of Object.entries(fields)) next[name] = { ...next[name], value };
    return { ...old, data: { ...old.data, node: { ...old.data.node, template: next } } };
  });
  useEffect(() => {
    let active = true;
    connectionCapability().then((value) => { if (active) setEnabled(value); });
    return () => { active = false; ++epoch.current; };
  }, []);
  useEffect(() => subscribePrivateInvalidation(() => {
    ++epoch.current; setIndex(undefined); setChoices([]); setOrigins([]); setBusy(false);
    if (connectionId) setError("github_connection_changed");
  }), [connectionId]);
  useEffect(() => { ++epoch.current; setChoices([]); setOrigins([]); setBusy(false); setError(""); }, [connectionId, source]);
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
        setChoices(found.skills); setOrigins([]);
      } else {
        const found = await privateSkillRequest<{ revisions: PrivateOrigin[] }>("revisions", selected, { choice: skill });
        if (epoch.current !== current) return;
        setOrigins(found.revisions);
      }
      update({ private_repository_id: String(repository.id) });
    } catch (failure) {
      if (epoch.current !== current) return;
      setChoices([]); setOrigins([]); setIndex(undefined);
      setError(failure instanceof ConnectionFailure ? failure.code : "github_connection_unavailable");
    } finally { if (epoch.current === current) setBusy(false); }
  };
  if (!enabled && !connectionId) return null;
  const revisions = origins.map((origin) => `${origin.label} @ ${origin.commit}`);
  return <section className="nodrag nopan grid gap-2 px-5 py-3 text-sm" aria-label="Private Skill source">
    <label htmlFor={`connection-${data.id}`}>Connection</label>
    <select id={`connection-${data.id}`} className="rounded border bg-background p-2" value={connectionId} disabled={busy || !enabled}
      onFocus={() => { if (!index && !busy) void load("connections"); }}
      onChange={(event) => { ++epoch.current; update({ github_connection: event.target.value, private_repository_id: "", skill_id: "", revision_id: "", resolved_skill_id: "", resolved_revision_id: "", resolved_selection: "" }); }}>
      <option value="">Anonymous</option>
      {connectionId && !index?.connections.some((entry) => entry.connection.id === connectionId) && <option value={connectionId}>Selected connection</option>}
      {index?.connections.filter((entry) => entry.connection.state === "ready").map(({ connection }) => <option key={connection.id} value={connection.id}>{connection.principal.login} ({connection.mode})</option>)}
    </select>
    {connectionId && <>
      <p className="text-xs text-muted-foreground">Private files are read only. Agent execution is unavailable.</p>
      <button type="button" className="rounded border px-2 py-1" disabled={busy || !enabled} onClick={() => void load("skills")}>Refresh Skills</button>
      <label htmlFor={`private-skill-${data.id}`}>Skill</label>
      <input id={`private-skill-${data.id}`} className="rounded border bg-background p-2" list={`private-skills-${data.id}`} defaultValue={skill} key={`${connectionId}:${source}:${skill}`}
        placeholder="Search discovered Skills" disabled={busy || !choices.length} onChange={(event) => {
          if (choices.some((choice) => choice.choice === event.target.value)) { ++epoch.current; setOrigins([]); update({ skill_id: event.target.value, revision_id: "", resolved_skill_id: "", resolved_revision_id: "", resolved_selection: "" }); }
        }} />
      <datalist id={`private-skills-${data.id}`}>{choices.map((choice) => <option key={choice.choice} value={choice.choice} />)}</datalist>
      <button type="button" className="rounded border px-2 py-1" disabled={busy || !skill || !enabled} onClick={() => void load("revisions")}>Refresh revisions</button>
      <label htmlFor={`private-revision-${data.id}`}>Revision</label>
      <input id={`private-revision-${data.id}`} className="rounded border bg-background p-2" list={`private-revisions-${data.id}`} defaultValue={revision} key={`${connectionId}:${source}:${skill}:${revision}`}
        placeholder="Search discovered revisions" disabled={busy || !origins.length} onChange={(event) => {
          const origin = origins.find((_entry, i) => revisions[i] === event.target.value);
          if (origin) update({ revision_id: event.target.value, resolved_skill_id: origin.skill_id, resolved_revision_id: origin.revision_id,
            resolved_selection: JSON.stringify([source, skill, event.target.value, connectionId]) });
        }} />
      <datalist id={`private-revisions-${data.id}`}>{revisions.map((label) => <option key={label} value={label} />)}</datalist>
    </>}
    {busy && <p role="status">Checking access…</p>}
    {error && <ErrorExplanation failure={describeNodeFailure(error, undefined)} />}
    <a className="text-primary underline" href="/settings/github" target="_blank" rel="noreferrer">Manage GitHub connections</a>
  </section>;
}
