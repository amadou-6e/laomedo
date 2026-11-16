import { useEffect, useRef, useState } from "react";
import { ArrowLeft, ChevronRight, Plus, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import ErrorExplanation from "@/components/laomedoErrors/ErrorExplanation";
import { describeNodeFailure } from "@/components/laomedoErrors/nodeErrors";
import { beginLogin, cancelLogin, listConnections, readProgress, inspectDisconnect, disconnect, retryCleanup, ProviderFailure, type DisconnectInfo, type LoginProgress, type ProviderConnection } from "./api";
import "./providers.css";

type Screen = "list" | "type" | "method" | "pending" | "details" | "failure" | "duplicate" | "disconnect" | "removing" | "removed";
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

  return <section className="pc-screen" aria-labelledby="provider-heading">
    <div className="pc-card">
      <div className="pc-heading"><h1 id="provider-heading">{heading}</h1>
        {screen === "list" && <Button ignoreTitleCase disabled={busy} className="normal-case" onClick={() => { setSelected(undefined); setAttempt(undefined); sessionStorage.removeItem(pendingKey); window.history.replaceState(null, "", "/settings/providers"); setScreen("type"); }}><Plus size={16} aria-hidden="true" />Add provider</Button>}
      </div>
      {error && <div role="alert"><ErrorExplanation failure={describeNodeFailure(error, undefined)} /></div>}
      {screen === "list" && <>
        <p className="pc-muted">Settings / Providers</p>
        {rows === undefined ? <p role="status">{error ? "Could not load providers." : "Loading providers…"}</p> : rows.length === 0 ? <p className="pc-empty">No providers connected</p> : <div className="pc-list">{rows.map(row => <button type="button" key={row.connection_id} className="pc-row" onClick={() => { setSelected(row); setScreen("details"); }}><span className="pc-avatar" aria-hidden="true">Co</span><span className="pc-row-label"><strong>{row.label}</strong><span className="pc-muted">Codex · ChatGPT plan</span></span><span className="pc-status">{row.lifecycle === "connected" ? statuses[row.auth_state] : row.lifecycle === "cleanup_required" ? "Cleanup required" : "Disconnecting"}</span><ChevronRight size={16} aria-hidden="true" /></button>)}</div>}
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
        <p>{unconfirmed ? "Checking your saved connection…" : <>Complete sign-in with the provider.<br />We’ll update this page when it finishes.</>}</p>
        <div className="pc-notice" role="status">{unconfirmed || attempt?.status === "verifying" ? "Checking connection…" : "Waiting for sign-in…"}</div>
      </>}
      {screen === "details" && selected && <>
        <p>Codex · ChatGPT plan<br />{selected.label}</p>
        <p>{statuses[selected.auth_state]}{selected.auth_state === "ready" && " · Credential checked"}<br /><span className="pc-muted">Model usage not yet confirmed</span></p>
        <div className="pc-actions"><Button ignoreTitleCase variant="outline" className="normal-case" disabled={busy || selected.lifecycle !== "connected"} onClick={() => setScreen("method")}>Sign in again</Button><Button ignoreTitleCase variant="outline" className="normal-case" disabled={busy} onClick={() => selected.lifecycle === "connected" ? void prepareDisconnect() : setScreen("removing")}>{selected.lifecycle === "connected" ? "Disconnect" : "View cleanup"}</Button></div>
      </>}
      {screen === "disconnect" && selected && removal && <>
        <p>{selected.label}</p>
        <p>{removal.active_runs ? `${removal.active_runs} active ${removal.active_runs === 1 ? "run will" : "runs will"} stop. Their work and activity will be kept.` : "No active runs will be affected."}</p>
        <p className="pc-muted">This removes this connection from Laomedo. Your ChatGPT account and other connections stay unchanged.</p>
        <div className="pc-actions"><Button ignoreTitleCase variant="outline" className="normal-case" disabled={busy} onClick={() => setScreen("details")}>Cancel</Button><Button ignoreTitleCase className="normal-case" disabled={busy} onClick={() => void removeConnection()}>Disconnect</Button></div>
      </>}
      {screen === "removing" && <>
        <p role="status">{selected?.lifecycle === "cleanup_required" ? "We couldn’t finish removing this connection. New runs are blocked." : selected?.lifecycle === "connected" ? "Disconnect wasn’t confirmed. Refresh to check this connection." : "Stopping active work and removing this connection…"}</p>
        <p className="pc-muted">Your work and activity are kept.</p>
        {selected?.lifecycle === "cleanup_required" && <div className="pc-actions"><Button ignoreTitleCase className="normal-case" disabled={busy} onClick={() => void removeConnection(true)}>Retry cleanup</Button></div>}
      </>}
      {screen === "removed" && <>
        <p role="status">This connection has been removed from Laomedo.</p>
        <p className="pc-muted">Your ChatGPT account and other connections stay unchanged.</p>
        <div className="pc-actions"><Button ignoreTitleCase className="normal-case" onClick={() => { setSelected(undefined); setScreen("list"); }}>Back to providers</Button></div>
      </>}
      {screen === "failure" && <>
        {unconfirmed ? <ErrorExplanation failure={describeNodeFailure("provider_save_unconfirmed", undefined)} /> : <p>{attempt?.status === "expired" ? "Your sign-in expired. Try again." : <>We couldn’t finish signing you in.<br />Your saved connection hasn’t changed.</>}</p>}
        <div className="pc-actions"><Button ignoreTitleCase className="normal-case" disabled={busy || unconfirmed} onClick={() => { setAttempt(undefined); sessionStorage.removeItem(pendingKey); window.history.replaceState(null, "", "/settings/providers"); setScreen("method"); }}>Try again</Button></div>
      </>}
      {screen === "duplicate" && <>
        <p>This account is already connected.<br />Your existing connection hasn’t changed.</p>
        <div className="pc-actions"><Button ignoreTitleCase className="normal-case" onClick={() => setScreen("details")}>View connection</Button></div>
      </>}
    </div>
    <nav className="pc-navigation" aria-label="Connection navigation">
      {screen !== "list" && <button type="button" disabled={busy} aria-label="Back to connections" title="Back to connections" onClick={() => void back()}><ArrowLeft size={20} aria-hidden="true" /></button>}
      {!["type", "method", "disconnect", "removed"].includes(screen) && <button type="button" disabled={busy} aria-label="Refresh" title="Refresh connections" onClick={() => void refresh()}><RefreshCw size={20} aria-hidden="true" className={busy ? "animate-spin" : ""} /></button>}
    </nav>
  </section>;
}
