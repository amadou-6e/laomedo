import { useEffect, useState } from "react";
import IconComponent from "@/components/common/genericIconComponent";
import { RefreshCw } from "lucide-react";
import "./providers.css";
import { Button } from "@/components/ui/button";
import { listConnections, readGraphPreferences, saveGraphPreferences, type ProviderConnection } from "./api";

const harnesses = [{ id: "codex", label: "Codex" }, { id: "claude", label: "Claude Code" }, { id: "opencode", label: "OpenCode" }];

export default function SubscriptionAgents({ flowId }: { flowId?: string }) {
  const [harness, setHarness] = useState("codex");
  const [accounts, setAccounts] = useState<ProviderConnection[]>([]);
  const [preferred, setPreferred] = useState("");
  const [saved, setSaved] = useState("");
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState("");
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    let cancelled = false;
    setBusy(true); setError(""); setAccounts([]); setPreferred(""); setSaved("");
    if (!flowId) { setBusy(false); return; }
    Promise.all([listConnections(), readGraphPreferences(flowId)]).then(([rows, preferences]) => {
      if (cancelled) return;
      setAccounts(rows); setPreferred(preferences.codex ?? ""); setSaved(preferences.codex ?? "");
    }).catch(() => { if (!cancelled) setError("Could not load this graph's accounts. Refresh to try again."); })
      .finally(() => { if (!cancelled) setBusy(false); });
    return () => { cancelled = true; };
  }, [flowId, revision]);
  async function save() {
    if (!flowId || busy) return;
    setBusy(true); setError("");
    try { const result = await saveGraphPreferences(flowId, preferred || null); setSaved(result.codex ?? ""); }
    catch { setError("Could not save this graph's preferred account. Your saved preference has not been confirmed; refresh before retrying."); }
    finally { setBusy(false); }
  }
  return <section className="flex h-full min-w-0 flex-1 flex-col overflow-hidden bg-background text-foreground" aria-label="Subscription agents">
    <header className="shrink-0 border-b px-4 pt-4">
      <div className="flex items-center justify-between gap-3"><h1 className="text-base font-semibold">Subscription agents</h1><Button variant="ghost" size="icon" aria-label="Refresh accounts" title="Refresh accounts" disabled={busy} onClick={() => setRevision(value => value + 1)}><RefreshCw size={16} aria-hidden="true" /></Button></div>
      <div role="tablist" aria-label="Agent harness" className="mt-3 flex gap-4">{harnesses.map(item => <button type="button" role="tab" id={`harness-${item.id}`} aria-controls="harness-panel" aria-selected={harness === item.id} key={item.id} onClick={() => setHarness(item.id)} className={`border-b-2 px-2 py-3 text-sm ${harness === item.id ? "border-primary font-semibold" : "border-transparent text-muted-foreground"}`}>{item.label}</button>)}</div>
    </header>
    <div id="harness-panel" role="tabpanel" aria-labelledby={`harness-${harness}`} className="pc-settings-panel">
      {harness !== "codex" || (!busy && !error && accounts.length === 0) ? <section className="pc-settings-section pc-subscription-empty" aria-labelledby="missing-subscription-heading">
        <div className="pc-empty-art" aria-hidden="true">
          {[0, 1, 2].map(row => <div key={row} className="pc-ghost-account">
            <span className="pc-ghost-mark">{harness === "claude" ? <IconComponent name="Claude" className="h-6 w-6" /> : <span className="pc-ghost-terminal">{">_"}</span>}</span>
            <span className="pc-ghost-copy"><span className="pc-ghost-brand">{harnesses.find(item => item.id === harness)?.label}</span><span className="pc-ghost-line" /></span>
            <span className="pc-ghost-status" />
          </div>)}
        </div>
        <h2 id="missing-subscription-heading">{harness === "codex" ? "No Codex account connected" : `No ${harnesses.find(item => item.id === harness)?.label} connections`}</h2>
        <p className="pc-card-description">{harness === "codex" ? "Connect your account to choose it as this graph's default." : "Account sign-in for this harness is not available yet."}</p>
        {harness === "codex" && <a className="pc-manage-account" href="/settings/providers">Connect Codex</a>}
      </section> : <>
        <section className="pc-settings-section" aria-label="Graph account preference">
          <div className="pc-section-heading"><h2>Account preference</h2><a className="pc-manage-account" href="/settings/providers">Manage accounts</a></div>
          <p className="pc-card-description">Choose the default for this graph. Nodes can override it in Advanced controls.</p>
          {error && <p role="alert" className="pc-account-notice">{error}</p>}
          <div className="pc-account-field"><select aria-label="Preferred Codex account for this graph" disabled={busy || !!error || !flowId} value={preferred} onChange={event => setPreferred(event.target.value)} className="pc-account-select">
            <option value="">Choose an account on each node</option>
            {preferred && !accounts.some(row => row.connection_id === preferred) && <option value={preferred} disabled>Saved account unavailable</option>}
            {accounts.map(row => <option key={row.connection_id} value={row.connection_id} disabled={row.lifecycle !== "connected" || row.auth_state !== "ready"}>{row.label}</option>)}
          </select></div>
          {preferred && accounts.some(row => row.connection_id === preferred && (row.lifecycle !== "connected" || row.auth_state !== "ready")) && <p className="pc-account-notice" role="status">This account needs attention. Open Manage accounts to reconnect it.</p>}
          {preferred !== saved && <div className="pc-save-row"><Button ignoreTitleCase disabled={busy || !!error || !flowId} onClick={() => void save()}>Save preference</Button></div>}
        </section>
        <section className="pc-settings-section" aria-labelledby="subscription-limits-heading">
          <div className="pc-section-heading"><h2 id="subscription-limits-heading">Subscription limits</h2></div>
          <p className="pc-card-description">Remaining allowance and reset times for each connected account.</p>
          {busy && <p role="status" className="pc-account-notice">Loading accounts...</p>}
          <ul className="pc-subscription-list" aria-label="Account subscription limits">{accounts.map(row => <li key={row.connection_id}>
            <div className="pc-subscription-row"><span className="pc-subscription-account">{row.label}</span><span className="pc-availability">Not available yet</span></div>
            <p>Subscription limit reporting is not connected yet.</p>
          </li>)}</ul>
        </section>
      </>}
    </div>
  </section>;
}
