import { useEffect, useRef, useState } from "react";
import { ArrowLeft, Plus, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import ErrorExplanation from "@/components/laomedoErrors/ErrorExplanation";
import { describeNodeFailure } from "@/components/laomedoErrors/nodeErrors";
import { beginLogin, cancelLogin, listConnections, readProgress, inspectDisconnect, disconnect, retryCleanup, ProviderFailure, type DisconnectInfo, type LoginProgress, type ProviderConnection } from "./api";
import "./connections.css";
import "./providers.css";

type Screen = "list" | "type" | "method" | "pending" | "details" | "failure" | "duplicate" | "disconnect" | "removing" | "removed";
const codexLogo = <svg aria-hidden="true" focusable="false" width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M20 12C20 7.58172 16.4183 4 12 4C7.58172 4 4 7.58172 4 12C4 16.4183 7.58172 20 12 20C16.4183 20 20 16.4183 20 12ZM16 13.5C16.5523 13.5 17 13.9477 17 14.5C17 15.0523 16.5523 15.5 16 15.5H13C12.4477 15.5 12 15.0523 12 14.5C12 13.9477 12.4477 13.5 13 13.5H16ZM7.98535 8.64258C8.42937 8.37617 8.99745 8.49427 9.30078 8.90039L9.35742 8.98535L10.8574 11.4854L10.9199 11.6074C11.0269 11.858 11.0269 12.142 10.9199 12.3926L10.8574 12.5146L9.35742 15.0146C9.07324 15.4881 8.45888 15.6415 7.98535 15.3574C7.51188 15.0732 7.35846 14.4589 7.64258 13.9854L8.83301 12L7.64258 10.0146L7.59473 9.92383C7.37931 9.46516 7.54152 8.90898 7.98535 8.64258ZM22 12C22 17.5228 17.5228 22 12 22C6.47715 22 2 17.5228 2 12C2 6.47715 6.47715 2 12 2C17.5228 2 22 6.47715 22 12Z" fill="currentColor"/></svg>;
const pendingKey = "laomedo.provider-attempt";
const statuses = { ready: "Connected", expired: "Sign in again", reauthorization_required: "Sign in again", revoked: "Sign in again", unavailable: "Unavailable" };

export default function ProviderConnections() {
  const [screen, setScreen] = useState<Screen>("list");
  const [rows, setRows] = useState<ProviderConnection[]>();
  const [selected, setSelected] = useState<ProviderConnection>();
  const [provider, setProvider] = useState("codex");
  const [attempt, setAttempt] = useState<LoginProgress>();
  const [busy, setBusy] = useState(false);
  const [removal, setRemoval] = useState<DisconnectInfo>();
  const [error, setError] = useState("");
  const epoch = useRef(0);
  const inFlight = useRef<number | null>(null);

  async function refresh() {
    if (inFlight.current) return;
    const revision = ++epoch.current;
    inFlight.current = revision;
    setBusy(true); setError("");
    if (attempt?.code === "provider_save_unconfirmed") setScreen("pending");
    try {
      const next = await listConnections();
      if (revision !== epoch.current) return;
      setRows(next);
      setSelected(current => next.find(row => row.connection_id === current?.connection_id));
      if (screen === "removing" && selected && !next.some(row => row.connection_id === selected.connection_id)) setScreen("removed");
      const id = attempt?.attempt_id || new URLSearchParams(window.location.search).get("attempt") || sessionStorage.getItem(pendingKey);
      if (id) {
        let progress: LoginProgress;
        try { progress = await readProgress(id); }
        catch (failure) {
          if (!(failure instanceof ProviderFailure) || failure.code !== "provider_login_expired") throw failure;
          progress = { attempt_id: id, status: "expired", connection_id: null, code: null };
        }
        if (revision !== epoch.current) return;
        setAttempt(progress);
        if (["connecting", "verifying"].includes(progress.status)) setScreen("pending");
        else {
          sessionStorage.removeItem(pendingKey);
          if (progress.code !== "provider_save_unconfirmed") {
            window.history.replaceState(null, "", "/settings/providers");
            setAttempt({ ...progress, attempt_id: "" });
          }
          if (progress.status === "connected" || progress.status === "duplicate") {
            setSelected(next.find(row => row.connection_id === progress.connection_id));
            setScreen(progress.status === "duplicate" ? "duplicate" : "details");
          } else if (progress.status !== "cancelled") setScreen("failure");
        }
      } else if (attempt?.code === "provider_save_unconfirmed") setScreen("failure");
    } catch {
      if (revision === epoch.current) { setError("provider_connections_unavailable"); if (attempt?.code === "provider_save_unconfirmed") setScreen("failure"); }
    } finally {
      if (inFlight.current === revision) inFlight.current = null;
      if (revision === epoch.current) setBusy(false);
    }
  }

  useEffect(() => {
    if (new URLSearchParams(window.location.search).get("login") === "failed") setScreen("failure");
    if (new URLSearchParams(window.location.search).get("login") === "unconfirmed") {
      setAttempt({ attempt_id: "", status: "failed", connection_id: null, code: "provider_save_unconfirmed" });
      setScreen("failure");
    }
    void refresh();
    return () => { ++epoch.current; inFlight.current = null; };
  }, []);

  useEffect(() => {
    if (screen !== "pending") return;
    const timer = window.setInterval(() => { void refresh(); }, 1500);
    return () => window.clearInterval(timer);
  }, [screen, attempt?.attempt_id]);

  useEffect(() => {
    if (screen !== "removing" || selected?.lifecycle !== "disconnecting") return;
    const timer = window.setInterval(() => { void refresh(); }, 1500);
    return () => window.clearInterval(timer);
  }, [screen, selected?.connection_id, selected?.lifecycle]);

  async function prepareDisconnect() {
    if (!selected || inFlight.current) return;
    const revision = ++epoch.current;
    inFlight.current = revision; setBusy(true); setError("");
    try {
      const info = await inspectDisconnect(selected.connection_id);
      if (revision !== epoch.current) return;
      setRemoval(info); setAttempt(undefined); sessionStorage.removeItem(pendingKey);
      window.history.replaceState(null, "", "/settings/providers");
      setScreen("disconnect");
    } catch { if (revision === epoch.current) setError("provider_connections_unavailable"); }
    finally { if (inFlight.current === revision) inFlight.current = null; if (revision === epoch.current) setBusy(false); }
  }

  async function removeConnection(retry = false) {
    if (!selected || !removal && !retry || inFlight.current) return;
    const revision = ++epoch.current;
    inFlight.current = revision; setBusy(true); setError("");
    try {
      const result = retry ? await retryCleanup(selected.connection_id) : await disconnect(removal!);
      if (revision !== epoch.current) return;
      setAttempt(undefined); sessionStorage.removeItem(pendingKey);
      setScreen(result.status === "removed" ? "removed" : "removing");
      if (result.status === "removed") setRows(current => current?.filter(row => row.connection_id !== result.connection_id));
      else setSelected(current => current ? { ...current, lifecycle: result.status as "disconnecting" | "cleanup_required" } : current);
    } catch (failure) {
      if (revision === epoch.current) {
        if (failure instanceof ProviderFailure && failure.code === "provider_confirmation_changed") {
          const currentRemoval = await inspectDisconnect(selected.connection_id);
          if (revision !== epoch.current) return;
          setRemoval(currentRemoval);
          setError("provider_confirmation_changed"); setScreen("disconnect");
        } else { setError("provider_cleanup_unconfirmed"); setScreen("removing"); }
      }
    } finally { if (inFlight.current === revision) inFlight.current = null; if (revision === epoch.current) setBusy(false); }
  }

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
    } catch (failure) {
      if (revision === epoch.current) {
        if (failure instanceof ProviderFailure && failure.code === "provider_connection_busy") { setError(failure.code); setScreen("details"); }
        else { setError("provider_sign_in_failed"); setScreen("failure"); }
      }
    } finally { if (inFlight.current === revision) inFlight.current = null; if (revision === epoch.current) setBusy(false); }
  }

  async function back() {
    if (inFlight.current) return;
    if (screen === "pending" && attempt?.attempt_id) {
      const revision = ++epoch.current;
      inFlight.current = revision; setBusy(true); setError("");
      try {
        const result = await cancelLogin(attempt.attempt_id);
        if (revision !== epoch.current) return;
        if (["connecting", "verifying"].includes(result.status)) throw new Error();
        setAttempt(undefined); sessionStorage.removeItem(pendingKey);
      } catch { if (revision === epoch.current) setError("provider_cancel_unconfirmed"); return; }
      finally { if (inFlight.current === revision) inFlight.current = null; if (revision === epoch.current) setBusy(false); }
    }
    ++epoch.current;
    window.history.replaceState(null, "", "/settings/providers");
    setError(""); setAttempt(undefined);
    setScreen(screen === "disconnect" ? "details" : screen === "method" ? (selected ? "details" : "type") : "list");
  }

  const unconfirmed = attempt?.code === "provider_save_unconfirmed";
  const heading = screen === "disconnect" ? "Disconnect Codex?" : screen === "removed" ? "Disconnected" : screen === "removing" ? (selected?.lifecycle === "cleanup_required" ? "Cleanup required" : selected?.lifecycle === "connected" ? "Check connection" : "Disconnecting") : screen === "list" ? "Providers" : screen === "type" ? "Add provider" : screen === "method" ? "Connect Codex" : screen === "pending" ? (unconfirmed ? "Check connection" : "Finish signing in") : screen === "failure" ? (unconfirmed ? "Check connection" : attempt?.status === "expired" ? "Sign-in expired" : "Sign-in failed") : screen === "duplicate" ? "Already connected" : selected?.label ?? "Provider connection";

  const status = (row: ProviderConnection) => row.lifecycle === "connected" ? statuses[row.auth_state] : row.lifecycle === "cleanup_required" ? "Cleanup required" : "Disconnecting";
  const ready = selected?.lifecycle === "connected" && selected.auth_state === "ready";

  return <section className="github-connections" aria-labelledby="provider-heading">
    {screen === "list" && <header className="gc-heading">
      <div><h1 id="provider-heading">Providers</h1><p className="gc-muted">Manage the provider accounts Laomedo can use.</p></div>
      <Button ignoreTitleCase disabled={busy} onClick={() => { setSelected(undefined); setAttempt(undefined); sessionStorage.removeItem(pendingKey); window.history.replaceState(null, "", "/settings/providers"); setScreen("type"); }}><Plus size={16} aria-hidden="true" />Add provider</Button>
    </header>}
    <div className={screen === "list" ? "pc-list-screen" : screen === "details" ? "gc-screen gc-detail" : "gc-screen"}>
      {error && <div role="alert"><ErrorExplanation failure={describeNodeFailure(error, undefined)} /></div>}
      <section className={screen === "list" ? "gc-panel gc-accounts" : screen === "details" ? "gc-panel gc-detail-card" : "gc-panel gc-focus"}>
        {screen !== "list" && screen !== "details" && <h2 id="provider-heading">{heading}</h2>}
        {screen === "list" && <>
          {rows === undefined ? <p role="status">{error ? "Could not load providers." : "Loading providers…"}</p> : rows.length === 0 ? <div className="gc-empty"><h2>No providers connected</h2><p className="gc-muted">Add a provider account to use it in your flows.</p></div> : <>
            <h2 className="gc-eyebrow">Connected accounts</h2>
            {rows.map(row => <div className="gc-account-row" key={row.connection_id}>
              <span className="gc-avatar" aria-hidden="true">{codexLogo}</span>
              <div className="gc-account-copy"><h3>{row.label}</h3><p className="gc-muted">Codex · ChatGPT plan</p></div>
              <span className={`gc-status ${row.lifecycle === "connected" && row.auth_state === "ready" ? "gc-ready" : "gc-attention"}`}>{status(row)}</span>
              <Button ignoreTitleCase variant="outline" aria-label={`View connection for ${row.label}`} onClick={() => { setSelected(row); setScreen("details"); }}>View connection</Button>
            </div>)}
          </>}
        </>}
        {screen === "type" && <>
          <p className="gc-muted">Choose the provider you want to connect.</p>
          <div className="pc-types" role="group" aria-label="Provider type">{["codex", "claude", "opencode"].map(type => <button type="button" aria-pressed={provider === type} className="pc-choice" disabled={type !== "codex"} key={type} onClick={() => setProvider(type)}>{type === "opencode" ? "OpenCode" : type[0].toUpperCase() + type.slice(1)}{type !== "codex" && <small>Not available yet</small>}</button>)}</div>
          <Button ignoreTitleCase onClick={() => setScreen("method")}>Continue</Button>
        </>}
        {screen === "method" && <>
          <p className="gc-muted">Sign in with ChatGPT to use your eligible ChatGPT plan.</p>
          <Button ignoreTitleCase disabled={busy} onClick={() => void signIn()}>Continue to sign in</Button>
        </>}
        {screen === "pending" && <>
          <p className="gc-muted">{unconfirmed ? "Checking your saved connection…" : <>Complete sign-in with the provider.<br />We’ll update this page when it finishes.</>}</p>
          <p className="gc-notice" role="status">{unconfirmed || attempt?.status === "verifying" ? "Checking connection…" : "Waiting for sign-in…"}</p>
        </>}
        {screen === "details" && selected && <>
          <div className="gc-identity"><span className="gc-avatar" aria-hidden="true">{codexLogo}</span><h2 id="provider-heading">{selected.label}</h2><span className={`gc-status ${ready ? "gc-ready" : "gc-attention"}`}>{status(selected)}</span></div>
          <p className="gc-muted">{ready ? "Access is maintained automatically when supported." : "Sign in again to restore access for this account."}</p>
          <div className="gc-footer"><p className="gc-muted">Removing this connection stops Laomedo access.</p><div className="pc-connection-actions">{selected.lifecycle === "connected" && <Button ignoreTitleCase disabled={busy} onClick={() => setScreen("method")}>Sign in to Codex again</Button>}<Button ignoreTitleCase variant="outline" disabled={busy} onClick={() => selected.lifecycle === "connected" ? void prepareDisconnect() : setScreen("removing")}>{selected.lifecycle === "connected" ? "Disconnect" : "View cleanup"}</Button></div></div>
        </>}
        {screen === "disconnect" && selected && removal && <>
          <p>{selected.label}</p>
          <p className="gc-muted">{removal.active_runs ? `${removal.active_runs} active ${removal.active_runs === 1 ? "run will" : "runs will"} stop. Their work and activity will be kept.` : "No active runs will be affected."}</p>
          <p className="gc-muted">This removes this connection from Laomedo. Your ChatGPT account and other connections stay unchanged.</p>
          <div className="gc-footer"><Button ignoreTitleCase variant="outline" disabled={busy} onClick={() => setScreen("details")}>Cancel</Button><Button ignoreTitleCase disabled={busy} onClick={() => void removeConnection()}>Disconnect</Button></div>
        </>}
        {screen === "removing" && <>
          <p role="status">{selected?.lifecycle === "cleanup_required" ? "We couldn’t finish removing this connection. New runs are blocked." : selected?.lifecycle === "connected" ? "Disconnect wasn’t confirmed. Refresh to check this connection." : "Stopping active work and removing this connection…"}</p>
          <p className="gc-muted">Your work and activity are kept.</p>
          {selected?.lifecycle === "cleanup_required" && <Button ignoreTitleCase disabled={busy} onClick={() => void removeConnection(true)}>Retry cleanup</Button>}
        </>}
        {screen === "removed" && <>
          <p role="status">This connection has been removed from Laomedo.</p>
          <p className="gc-muted">Your ChatGPT account and other connections stay unchanged.</p>
          <Button ignoreTitleCase onClick={() => { setSelected(undefined); setScreen("list"); }}>Back to providers</Button>
        </>}
        {screen === "failure" && <>
          {unconfirmed ? <ErrorExplanation failure={describeNodeFailure("provider_save_unconfirmed", undefined)} /> : <p className="gc-muted">{attempt?.status === "expired" ? "Your sign-in expired. Try again." : <>We couldn’t finish signing you in.<br />Your saved connection hasn’t changed.</>}</p>}
          <Button ignoreTitleCase disabled={busy || unconfirmed} onClick={() => { setAttempt(undefined); sessionStorage.removeItem(pendingKey); window.history.replaceState(null, "", "/settings/providers"); setScreen("method"); }}>Try again</Button>
        </>}
        {screen === "duplicate" && <>
          <p className="gc-muted">This account is already connected.<br />Your existing connection hasn’t changed.</p>
          <Button ignoreTitleCase onClick={() => setScreen("details")}>View connection</Button>
        </>}
      </section>
      <nav className="gc-navigation" aria-label="Connection navigation">
        {screen !== "list" && <button type="button" className="gc-link gc-icon" disabled={busy} aria-label="Back to connections" title="Back to connections" onClick={() => void back()}><ArrowLeft size={20} aria-hidden="true" /></button>}
        {!["type", "method", "disconnect", "removed"].includes(screen) && <button type="button" className="gc-link gc-icon" disabled={busy} aria-label="Refresh" title="Refresh connections" onClick={() => void refresh()}><RefreshCw size={20} aria-hidden="true" /></button>}
      </nav>
    </div>
  </section>;
}
