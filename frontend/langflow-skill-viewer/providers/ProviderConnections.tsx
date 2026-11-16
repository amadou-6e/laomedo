import { useEffect, useRef, useState } from "react";
import { ArrowLeft, ChevronRight, Plus, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import ErrorExplanation from "@/components/laomedoErrors/ErrorExplanation";
import { describeNodeFailure } from "@/components/laomedoErrors/nodeErrors";
import { beginLogin, cancelLogin, listConnections, readProgress, type LoginProgress, type ProviderConnection } from "./api";
import "./providers.css";

type Screen = "list" | "type" | "method" | "pending" | "details" | "failure" | "duplicate";
const pendingKey = "laomedo.provider-attempt";
const statuses = { ready: "Connected", expired: "Sign in again", reauthorization_required: "Sign in again", revoked: "Sign in again", unavailable: "Unavailable" };

export default function ProviderConnections() {
  const [screen, setScreen] = useState<Screen>("list");
  const [rows, setRows] = useState<ProviderConnection[]>();
  const [selected, setSelected] = useState<ProviderConnection>();
  const [provider, setProvider] = useState("codex");
  const [attempt, setAttempt] = useState<LoginProgress>();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const epoch = useRef(0);
  const inFlight = useRef<number | null>(null);

  async function refresh() {
    if (inFlight.current) return;
    const revision = ++epoch.current;
    inFlight.current = revision;
    setBusy(true); setError("");
    try {
      const next = await listConnections();
      if (revision !== epoch.current) return;
      setRows(next);
      setSelected(current => next.find(row => row.connection_id === current?.connection_id));
      const id = attempt?.attempt_id ?? new URLSearchParams(window.location.search).get("attempt") ?? sessionStorage.getItem(pendingKey);
      if (id) {
        const progress = await readProgress(id);
        if (revision !== epoch.current) return;
        setAttempt(progress);
        if (["connecting", "verifying"].includes(progress.status)) setScreen("pending");
        else {
          sessionStorage.removeItem(pendingKey);
          if (progress.status === "connected" || progress.status === "duplicate") {
            setSelected(next.find(row => row.connection_id === progress.connection_id));
            setScreen(progress.status === "duplicate" ? "duplicate" : "details");
          } else if (progress.status !== "cancelled") setScreen("failure");
        }
      }
    } catch {
      if (revision === epoch.current) setError("provider_connections_unavailable");
    } finally {
      if (inFlight.current === revision) inFlight.current = null;
      if (revision === epoch.current) setBusy(false);
    }
  }

  useEffect(() => {
    if (new URLSearchParams(window.location.search).get("login") === "failed") setScreen("failure");
    void refresh();
    return () => { ++epoch.current; inFlight.current = null; };
  }, []);

  useEffect(() => {
    if (screen !== "pending") return;
    const timer = window.setInterval(() => { void refresh(); }, 1500);
    return () => window.clearInterval(timer);
  }, [screen, attempt?.attempt_id]);

  async function signIn() {
    if (inFlight.current) return;
    const revision = ++epoch.current;
    inFlight.current = revision; setBusy(true); setError("");
    try {
      const result = await beginLogin(selected?.connection_id);
      if (revision !== epoch.current) return;
      setAttempt(result.progress);
      sessionStorage.setItem(pendingKey, result.progress.attempt_id);
      setScreen("pending");
      // One explicit click starts native sign-in in this tab. No mount, polling
      // or Refresh operation opens a provider page.
      window.location.assign(result.authorization_url);
    } catch {
      if (revision === epoch.current) { setError("provider_sign_in_failed"); setScreen("failure"); }
    } finally { if (inFlight.current === revision) inFlight.current = null; if (revision === epoch.current) setBusy(false); }
  }

  async function back() {
    if (inFlight.current) return;
    if (screen === "pending" && attempt) {
      const revision = ++epoch.current;
      inFlight.current = revision; setBusy(true); setError("");
      try {
        const result = await cancelLogin(attempt.attempt_id);
        if (["connecting", "verifying"].includes(result.status)) throw new Error();
        setAttempt(undefined); sessionStorage.removeItem(pendingKey);
      } catch { setError("provider_cancel_unconfirmed"); return; }
      finally { if (inFlight.current === revision) inFlight.current = null; if (revision === epoch.current) setBusy(false); }
    }
    ++epoch.current;
    window.history.replaceState(null, "", "/settings/providers");
    setError(""); setAttempt(undefined);
    setScreen(screen === "method" ? (selected ? "details" : "type") : "list");
  }

  const heading = screen === "list" ? "Providers" : screen === "type" ? "Add provider" : screen === "method" ? "Connect Codex" : screen === "pending" ? "Finish signing in" : screen === "failure" ? (attempt?.status === "expired" ? "Sign-in expired" : "Sign-in failed") : screen === "duplicate" ? "Already connected" : selected?.label ?? "Provider connection";

  return <section className="pc-screen" aria-labelledby="provider-heading">
    <div className="pc-card">
      <div className="pc-heading"><h1 id="provider-heading">{heading}</h1>
        {screen === "list" && <Button ignoreTitleCase disabled={busy} className="normal-case" onClick={() => { setSelected(undefined); setAttempt(undefined); sessionStorage.removeItem(pendingKey); window.history.replaceState(null, "", "/settings/providers"); setScreen("type"); }}><Plus size={16} aria-hidden="true" />Add provider</Button>}
      </div>
      {error && <div role="alert"><ErrorExplanation failure={describeNodeFailure(error, undefined)} /></div>}
      {screen === "list" && <>
        <p className="pc-muted">Settings / Providers</p>
        {rows === undefined ? <p role="status">{error ? "Could not load providers." : "Loading providers…"}</p> : rows.length === 0 ? <p className="pc-empty">No providers connected</p> : <div className="pc-list">{rows.map(row => <button type="button" key={row.connection_id} className="pc-row" onClick={() => { setSelected(row); setScreen("details"); }}><span className="pc-avatar" aria-hidden="true">Co</span><span className="pc-row-label"><strong>{row.label}</strong><span className="pc-muted">Codex · ChatGPT plan</span></span><span className="pc-status">{statuses[row.auth_state]}</span><ChevronRight size={16} aria-hidden="true" /></button>)}</div>}
      </>}
      {screen === "type" && <>
        <p>Choose the provider you want to connect.</p>
        <div className="pc-types" role="group" aria-label="Provider type">{["codex", "claude", "opencode"].map(type => <button type="button" aria-pressed={provider === type} className="pc-choice" disabled={type !== "codex"} key={type} onClick={() => setProvider(type)}>{type === "opencode" ? "OpenCode" : type[0].toUpperCase() + type.slice(1)}{type !== "codex" && <small>Not available yet</small>}</button>)}</div>
        <div className="pc-actions"><Button ignoreTitleCase className="normal-case" onClick={() => setScreen("method")}>Continue</Button></div>
      </>}
      {screen === "method" && <>
        <p>Choose how to connect.</p>
        <div className="pc-choice" aria-current="true"><strong>Sign in with ChatGPT</strong><p className="pc-muted">Use your eligible ChatGPT plan.</p></div>
        <div className="pc-actions"><Button ignoreTitleCase className="normal-case" disabled={busy} onClick={() => void signIn()}>Continue to sign in</Button></div>
      </>}
      {screen === "pending" && <>
        <p>Complete sign-in with the provider.<br />We’ll update this page when it finishes.</p>
        <div className="pc-notice" role="status">{attempt?.status === "verifying" ? "Checking connection…" : "Waiting for sign-in…"}</div>
      </>}
      {screen === "details" && selected && <>
        <p>Codex · ChatGPT plan<br />{selected.label}</p>
        <p>{statuses[selected.auth_state]}{selected.auth_state === "ready" && " · Credential checked"}<br /><span className="pc-muted">Model usage not yet confirmed</span></p>
        <div className="pc-actions"><Button ignoreTitleCase variant="outline" className="normal-case" disabled={busy} onClick={() => setScreen("method")}>Sign in again</Button><Button ignoreTitleCase variant="outline" className="normal-case" disabled title="Waiting for active-run cleanup integration">Disconnect</Button></div>
      </>}
      {screen === "failure" && <>
        <p>{attempt?.status === "expired" ? "Your sign-in expired. Try again." : "We couldn’t finish signing you in."}<br />Your saved connection hasn’t changed.</p>
        <div className="pc-actions"><Button ignoreTitleCase className="normal-case" disabled={busy} onClick={() => { setAttempt(undefined); sessionStorage.removeItem(pendingKey); window.history.replaceState(null, "", "/settings/providers"); setScreen("method"); }}>Try again</Button></div>
      </>}
      {screen === "duplicate" && <>
        <p>This account is already connected.<br />Your existing connection hasn’t changed.</p>
        <div className="pc-actions"><Button ignoreTitleCase className="normal-case" onClick={() => setScreen("details")}>View connection</Button></div>
      </>}
    </div>
    <nav className="pc-navigation" aria-label="Connection navigation">
      {screen !== "list" && <button type="button" disabled={busy} aria-label="Back to connections" title="Back to connections" onClick={() => void back()}><ArrowLeft size={20} aria-hidden="true" /></button>}
      {screen !== "type" && screen !== "method" && <button type="button" disabled={busy} aria-label="Refresh" title="Refresh connections" onClick={() => void refresh()}><RefreshCw size={20} aria-hidden="true" className={busy ? "animate-spin" : ""} /></button>}
    </nav>
  </section>;
}
