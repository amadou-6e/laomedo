import { useCallback, useEffect, useState } from "react";
import { ExternalLink } from "lucide-react";
import useFlowStore from "@/stores/flowStore";
import { connectionCapability, connectionRequest } from "@/components/laomedoGitHubConnections/api";
import type { ConnectionIndex } from "@/components/laomedoGitHubConnections/types";
import { filterPRChoices } from "@/CustomNodes/GenericNode/components/RenderInputParameters/PRNodeControls";
import { subscribePrivateInvalidation } from "@/modals/skillFilesModal/private/api";

async function privateRequest(action: "discover" | "read", body: Record<string, unknown>, signal?: AbortSignal) {
  const session = await fetch("/api/v1/laomedo/private-session", { credentials: "same-origin", cache: "no-store", signal }).then(response => response.json());
  if (!session?.ready || typeof session.csrf_token !== "string") throw Error("Account session unavailable");
  const response = await fetch(`/api/v1/laomedo/private-pull-requests/${action}`, { method: "POST", credentials: "same-origin", cache: "no-store", signal,
    headers: { "Content-Type": "application/json", "X-Laomedo-CSRF": session.csrf_token }, body: JSON.stringify(body) });
  if (!response.ok) throw Error("Account or repository access unavailable");
  return response.json();
}

export async function readPrivatePR(connectionId: string, repositoryId: number, prNumber: number, signal?: AbortSignal) {
  return privateRequest("read", { connection_id: connectionId, repository_id: repositoryId, pr_number: prNumber }, signal);
}

/** Bind account selection to current profile consent; private reads do not grant writes. */
export default function PRAccountControls({ data }: { data: any }) {
  const [enabled, setEnabled] = useState(false);
  const [index, setIndex] = useState<ConnectionIndex>();
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [prs, setPrs] = useState<any[]>([]);
  const [search, setSearch] = useState("");
  const setNode = useFlowStore(state => state.setNode);
  const account = String(data.node?.template?.github_connection?.value || "");
  const repository = String(data.node?.template?.repository_url?.value || "");
  const update = useCallback((fields: Record<string, unknown>, prs?: any[]) => setNode(data.id, (old: any) => {
    const template = { ...old.data.node.template };
    for (const [name, value] of Object.entries(fields)) template[name] = { ...template[name], value };
    if (prs) template.pr_choice = { ...template.pr_choice, options: prs.map(pr => pr.choice), options_metadata: prs.map(pr => ({ id: pr.choice, state: pr.state, labels: pr.labels, laomedo_pr_search: true })) };
    return { ...old, data: { ...old.data, node: { ...old.data.node, template } } };
  }), [data.id, setNode]);
  useEffect(() => { let active = true; connectionCapability().then(value => { if (active) setEnabled(value); }); return () => { active = false; }; }, []);
  useEffect(() => subscribePrivateInvalidation(() => { setIndex(undefined); if (account) { setPrs([]); update({ pr_choice: "" }, []); setError("Account access changed. Refresh the account selection."); } }), [account, update]);
  useEffect(() => {
    setPrs([]);
    if (!enabled || !account || !repository) return;
    let active = true; const controller = new AbortController(); setBusy(true); setError("");
    (async () => {
      try {
        const result = await connectionRequest();
        const selected = result.index.connections.find(entry => entry.connection.id === account && entry.connection.state === "ready");
        const name = repository.match(/^https:\/\/github\.com\/([A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+?)\/?$/)?.[1]?.replace(/\.git$/i, "");
        const repo = selected?.connection.repositories.find(entry => entry.full_name.toLowerCase() === name?.toLowerCase());
        if (!repo) throw Error("Repository not available to this account");
        const response = await privateRequest("discover", { connection_id: account, repository_id: repo.id }, controller.signal);
        if (!Array.isArray(response.prs)) throw Error("Invalid PR response");
        if (active) {
          setIndex(result.index);
          const choice = String(data.node?.template?.pr_choice?.value || "");
          const number = choice.match(/^#([1-9][0-9]*)(?: |$)/)?.[1];
          const selected = response.prs.find((pr: any) => number && pr.choice.startsWith(`#${number} `));
          setPrs(response.prs);
          update({ pr_choice: selected ? `#${number}` : "" }, []);
        }
      } catch { if (active) { setPrs([]); update({ pr_choice: "" }, []); setError("Unable to read pull requests for this account and repository."); } }
      finally { if (active) setBusy(false); }
    })();
    return () => { active = false; controller.abort(); };
  }, [enabled, account, repository, update]);
  if (!data.node?.template?.github_connection || (!enabled && !account)) return null;
  return <section className="nodrag nopan grid gap-2 px-5 py-3 text-sm" aria-label="PR account">
    <div className="flex items-center gap-2"><label htmlFor={`pr-account-${data.id}`}>Account</label><a href="/settings/github" target="_blank" rel="noreferrer" aria-label="Manage GitHub accounts"><ExternalLink className="h-3.5 w-3.5" /></a></div>
    <select id={`pr-account-${data.id}`} value={account} disabled={!enabled || busy} className="rounded border bg-background p-2" onFocus={() => { if (!index) void connectionRequest().then(value => setIndex(value.index)).catch(() => setError("Unable to load accounts.")); }}
      onChange={event => { setError(""); setPrs([]); setSearch(""); update({ github_connection: event.target.value, repository_url: "", pr_choice: "", labels: [], discovery_status: "" }, []); }}>
      <option value="">Anonymous</option>
      {account && !index?.connections.some(entry => entry.connection.id === account) && <option value={account}>Selected account</option>}
      {index?.connections.filter(entry => entry.connection.state === "ready").map(({ connection }) => <option key={connection.id} value={connection.id}>{connection.principal.login} ({connection.mode})</option>)}
    </select>
    {account && repository && <div className="grid gap-1">
      <label htmlFor={`pr-search-${data.id}`}>Pull request</label>
      <input id={`pr-search-${data.id}`} value={search} onChange={event => setSearch(event.target.value)} placeholder="Search PRs, state:open, label:bug" className="rounded border bg-background p-2" />
      <select aria-label="Pull request" value={String(data.node?.template?.pr_choice?.value || "")} onChange={event => update({ pr_choice: event.target.value })} className="rounded border bg-background p-2">
        <option value="">Select a pull request</option>
        {filterPRChoices(search, prs.map(pr => pr.choice), prs.map(pr => ({ id: pr.choice, state: pr.state, labels: pr.labels, laomedo_pr_search: true }))).map(choice => <option key={choice} value={choice.match(/^#[1-9][0-9]*/)?.[0]}>{choice}</option>)}
      </select>
    </div>}
    {busy && <p role="status">Loading pull requests…</p>}
    {error && <p role="alert">{error}</p>}
  </section>;
}
