import { useCallback, useEffect, useState } from "react";
import { ChevronDown, ExternalLink } from "lucide-react";
import useFlowStore from "@/stores/flowStore";
import { connectionCapability, connectionRequest } from "@/components/laomedoGitHubConnections/api";
import type { ConnectionIndex } from "@/components/laomedoGitHubConnections/types";
import { filterPRChoices } from "@/CustomNodes/GenericNode/components/RenderInputParameters/PRNodeControls";
import { subscribePrivateInvalidation } from "@/modals/skillFilesModal/private/api";

async function privateRequest(action: "discover" | "read", body: Record<string, unknown>, signal?: AbortSignal) {
  const session = await fetch("/api/v1/laomedo/private-session", { headers: {}, credentials: "same-origin", cache: "no-store", signal }).then(response => response.json());
  if (!session?.ready || typeof session.csrf_token !== "string") throw Error("Account session unavailable");
  const response = await fetch(`/api/v1/laomedo/private-pull-requests/${action}`, { method: "POST", credentials: "same-origin", cache: "no-store", signal,
    headers: { "Content-Type": "application/json", "X-Laomedo-CSRF": session.csrf_token }, body: JSON.stringify(body) });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    if (body.code === "github_repository_access_unconfirmed") throw Error("GitHub could not confirm repository access. Check the app pull request read permission.");
    if (body.code === "private_session_required") throw Error("Sign in again to use this account.");
    throw Error("Account or repository access unavailable");
  }
  return response.json();
}

export async function readPrivatePR(connectionId: string, repositoryId: number, prNumber: number, signal?: AbortSignal) {
  return privateRequest("read", { connection_id: connectionId, repository_id: repositoryId, pr_number: prNumber }, signal);
}

/** Bind account selection to current profile consent; private reads do not grant writes. */
export default function PRAccountControls({ data, mode }: { data: any; mode: "account" | "selector" }) {
  const [enabled, setEnabled] = useState(false);
  const [index, setIndex] = useState<ConnectionIndex>();
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [prs, setPrs] = useState<any[]>([]);
  const [search, setSearch] = useState("");
  const [expanded, setExpanded] = useState(false);
  const [accountOpen, setAccountOpen] = useState(false);
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
  useEffect(() => {
    if (mode !== "account" || !enabled || !account) return;
    let active = true;
    connectionRequest().then(result => { if (active) setIndex(result.index); }).catch(() => { if (active) setError("Unable to load accounts."); });
    return () => { active = false; };
  }, [mode, enabled, account]);
  useEffect(() => subscribePrivateInvalidation(() => { setIndex(undefined); if (account) { setPrs([]); update({ pr_choice: "" }, []); setError("Account access changed. Refresh the account selection."); } }), [account, update]);
  useEffect(() => {
    setPrs([]);
    if (mode !== "selector" || !enabled || !account || !repository) return;
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
      } catch (failure) { if (active) { setPrs([]); update({ pr_choice: "" }, []); const message = failure instanceof Error ? failure.message : ""; const safe = ["Repository not available to this account", "Account session unavailable", "Account or repository access unavailable", "GitHub could not confirm repository access. Check the app pull request read permission.", "Sign in again to use this account."]; setError(safe.includes(message) ? message : "Unable to read pull requests for this account and repository."); } }
      finally { if (active) setBusy(false); }
    })();
    return () => { active = false; controller.abort(); };
  }, [enabled, account, repository, update, mode]);
  if (!data.node?.template?.github_connection || (!enabled && !account)) return null;
  return <section className="nodrag nopan grid gap-2 px-5 py-3 text-sm" aria-label="PR account">
    {mode === "account" && <><div className="flex items-center gap-2"><label htmlFor={`pr-account-${data.id}`}>Account</label><a href="/settings/github" target="_blank" rel="noreferrer" aria-label="Manage GitHub accounts"><ExternalLink className="h-3.5 w-3.5" /></a></div>
    <div className="relative">
      <button id={`pr-account-${data.id}`} type="button" aria-haspopup="listbox" aria-expanded={accountOpen} disabled={!enabled} className="w-full rounded border bg-background p-2 text-left" onClick={() => { setAccountOpen(!accountOpen); if (!index) void connectionRequest().then(value => setIndex(value.index)).catch(() => setError("Unable to load accounts.")); }}>
        {account ? (index?.connections.find(entry => entry.connection.id === account)?.connection.principal.login || "Selected account") : "Host default"} <ChevronDown className="inline h-3.5 w-3.5" />
      </button>
      {accountOpen && <div role="listbox" aria-label="GitHub accounts" className="absolute z-50 w-full rounded border bg-background shadow-lg">
        {[{ id: "", label: "Host default" }, ...(index?.connections.filter(entry => entry.connection.state === "ready").map(({ connection }) => ({ id: connection.id, label: `${connection.principal.login} (${connection.mode})` })) || [])].map(choice => <button type="button" role="option" aria-selected={account === choice.id} key={choice.id} className="block w-full px-2 py-1 text-left hover:bg-muted" onClick={() => { setAccountOpen(false); setError(""); setPrs([]); setSearch(""); update({ github_connection: choice.id, repository_url: "", pr_choice: "", labels: [], discovery_status: "" }, []); }}>{choice.label}</button>)}
      </div>}
    </div></>}
    {mode === "selector" && account && repository && <div className="relative grid gap-1">
      <label htmlFor={`pr-search-${data.id}`}>Pull request</label>
      <input id={`pr-search-${data.id}`} role="combobox" aria-expanded={expanded} aria-controls={`pr-results-${data.id}`} value={expanded ? search : (prs.find(pr => pr.choice.startsWith(`${data.node?.template?.pr_choice?.value} `))?.choice || "")} onFocus={() => { setSearch(""); setExpanded(true); }} onChange={event => setSearch(event.target.value)} onKeyDown={event => { if (event.key === "Escape") setExpanded(false); }} placeholder="Search PRs, state:open, label:bug" className="rounded border bg-background p-2" />
      {expanded && <div id={`pr-results-${data.id}`} role="listbox" className="absolute top-full z-50 max-h-48 w-full overflow-auto rounded border bg-background shadow-lg">
        {filterPRChoices(search, prs.map(pr => pr.choice), prs.map(pr => ({ id: pr.choice, state: pr.state, labels: pr.labels, laomedo_pr_search: true }))).map(choice => <button type="button" role="option" aria-selected={data.node?.template?.pr_choice?.value === choice.match(/^#[1-9][0-9]*/)?.[0]} key={choice} className="block w-full px-2 py-1 text-left hover:bg-muted" onClick={() => { update({ pr_choice: choice.match(/^#[1-9][0-9]*/)?.[0] || "" }); setExpanded(false); }}>{choice}</button>)}
      </div>}
    </div>}
    {mode === "selector" && busy && <p role="status">Loading pull requests…</p>}
    {error && <p role="alert">{error}</p>}
  </section>;
}
