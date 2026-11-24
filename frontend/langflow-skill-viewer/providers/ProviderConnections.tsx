import { useEffect, useRef, useState } from "react";
import { ArrowLeft, Plus, RefreshCw } from "lucide-react";
import IconComponent from "@/components/common/genericIconComponent";
import { Button } from "@/components/ui/button";
import LangflowLogo from "@/assets/LangflowLogo.svg?react";
import ErrorExplanation from "@/components/laomedoErrors/ErrorExplanation";
import { describeNodeFailure } from "@/components/laomedoErrors/nodeErrors";
import { readCodexAttempt, confirmCodexReplacement, readClaudeAttempt, submitClaudeCode, saveGoConnection, beginLogin, cancelLogin, listConnections, readProgress, inspectDisconnect, disconnect, retryCleanup, ProviderFailure, type DisconnectInfo, type LoginProgress, type ProviderConnection } from "./api";
import openAiLogo from "./assets/openai-logo.svg";
import openCodeLogoDark from "./assets/opencode-logo-dark.svg";
import openCodeLogoLight from "./assets/opencode-logo-light.svg";
import "./connections.css";
import "./providers.css";

type Screen = "list" | "returning" | "complete" | "type" | "method" | "pending" | "details" | "failure" | "duplicate" | "disconnect" | "removing" | "removed";
const codexLogo = <img src={openAiLogo} className="pc-codex-logo" alt="" />;
const pendingKey = "laomedo.provider-attempt";
const reconnectKey = "laomedo.provider-reconnecting";
const statuses = { ready: "Connected", expired: "Sign in again", reauthorization_required: "Sign in again", revoked: "Sign in again", unavailable: "Unavailable" };

export default function ProviderConnections() {
  const [screen, setScreen] = useState<Screen>(() => {
    const query = new URLSearchParams(window.location.search);
    return query.has("attempt") || sessionStorage.getItem(pendingKey) ? "returning" : ["failed", "unconfirmed"].includes(query.get("login") ?? "") ? "failure" : "list";
  });
  const reconnecting = useRef(sessionStorage.getItem(reconnectKey) === "true");
  const [rows, setRows] = useState<ProviderConnection[]>();
  const [selected, setSelected] = useState<ProviderConnection>();
  const [provider, setProvider] = useState("codex");
  const [nativeUrl, setNativeUrl] = useState<string | null>(null);
  const [nativeCode, setNativeCode] = useState("");
  const [deviceCode, setDeviceCode] = useState<string | null>(null);
  const [replacement, setReplacement] = useState<{ email: string; plan_type: string } | null>(null);
  const [claudeOpened, setClaudeOpened] = useState(false);
  const [goKey, setGoKey] = useState("");
  const [goLabel, setGoLabel] = useState("");
  const [goSaveUnconfirmed, setGoSaveUnconfirmed] = useState(false);
  const [attempt, setAttempt] = useState<LoginProgress>();
  const [busy, setBusy] = useState(false);
  const [removal, setRemoval] = useState<DisconnectInfo>();
  const [error, setError] = useState("");
  const surface = useRef<HTMLElement | null>(null);
  const epoch = useRef(0);
  const inFlight = useRef<number | null>(null);
  const claudeTab = useRef<Window | null>(null);

  useEffect(() => {
    if (!nativeUrl || !claudeTab.current) return;
    const tab = claudeTab.current;
    claudeTab.current = null;
    if (!tab.closed) { tab.location.replace(nativeUrl); setClaudeOpened(true); }
  }, [nativeUrl]);

  useEffect(() => () => { claudeTab.current?.close(); }, []);
  useEffect(() => {
    if (attempt && !["connecting", "verifying"].includes(attempt.status)) {
      claudeTab.current?.close(); claudeTab.current = null;
    }
  }, [attempt?.status]);

  useEffect(() => {
    // A new screen starts at the top; read-only polling leaves scroll untouched.
    let parent = surface.current?.parentElement;
    while (parent) {
      if (/auto|scroll/.test(window.getComputedStyle(parent).overflowY)) parent.scrollTop = 0;
      parent = parent.parentElement;
    }
    if (document.scrollingElement) document.scrollingElement.scrollTop = 0;
  }, [screen]);

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
        if (progress.provider === "claude" && ["connecting", "verifying"].includes(progress.status)) {
          const native = await readClaudeAttempt(id);
          if (revision !== epoch.current) return;
          progress = native.progress; setNativeUrl(native.authorization_url); setProvider("claude");
        }
        if (progress.provider === "codex" && ["connecting", "verifying", "awaiting_confirmation"].includes(progress.status)) {
          const native = await readCodexAttempt(id);
          if (revision !== epoch.current) return;
          progress = native.progress; setNativeUrl(native.authorization_url); setDeviceCode(native.user_code); setReplacement(native.replacement_account); setProvider("codex");
        }
        setAttempt(progress);
        if (["connecting", "verifying", "awaiting_confirmation"].includes(progress.status)) setScreen("pending");
        else {
          sessionStorage.removeItem(pendingKey);
          if (progress.code !== "provider_save_unconfirmed") {
            window.history.replaceState(null, "", "/settings/providers");
            setAttempt({ ...progress, attempt_id: "" });
          }
          if (progress.status === "connected" || progress.status === "duplicate") {
            if (progress.code === "provider_cleanup_unconfirmed") setError(progress.code);
            setSelected(next.find(row => row.connection_id === progress.connection_id));
            sessionStorage.removeItem(reconnectKey);
            setScreen(progress.code === "provider_cleanup_unconfirmed" ? "details" : "complete");
          } else if (progress.status === "cancelled") { setAttempt(undefined); sessionStorage.removeItem(reconnectKey); setScreen("list"); }
          else setScreen("failure");
        }
      } else if (attempt?.code === "provider_save_unconfirmed") {
        if (goSaveUnconfirmed) { setGoSaveUnconfirmed(false); setAttempt(undefined); setScreen("list"); }
        else setScreen("failure");
      }
    } catch (failure) {
      if (revision === epoch.current) {
        setError(failure instanceof ProviderFailure ? failure.code : "provider_connections_unavailable");
        if (screen === "returning") {
          setAttempt({ attempt_id: new URLSearchParams(window.location.search).get("attempt") || sessionStorage.getItem(pendingKey) || "", status: "failed", connection_id: null, code: "provider_save_unconfirmed" });
          setScreen("failure");
        } else if (attempt?.code === "provider_save_unconfirmed") setScreen("failure");
      }
    } finally {
      if (inFlight.current === revision) inFlight.current = null;
      if (revision === epoch.current) setBusy(false);
    }
  }

  useEffect(() => {
    if (screen !== "complete") return;
    const timer = window.setTimeout(() => { setSelected(undefined); setAttempt(undefined); setScreen("list"); }, 2800);
    return () => window.clearTimeout(timer);
  }, [screen]);

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
          try {
            const currentRemoval = await inspectDisconnect(selected.connection_id);
            if (revision !== epoch.current) return;
            setRemoval(currentRemoval);
            setError("provider_confirmation_changed"); setScreen("disconnect");
          } catch (reloadFailure) {
            if (revision !== epoch.current) return;
            setRemoval(undefined); setScreen("details");
            setError(reloadFailure instanceof ProviderFailure ? reloadFailure.code : "provider_connections_unavailable");
          }
        } else { setError("provider_cleanup_unconfirmed"); setScreen("removing"); }
      }
    } finally { if (inFlight.current === revision) inFlight.current = null; if (revision === epoch.current) setBusy(false); }
  }

  async function saveGo() {
    if (inFlight.current) return;
    const revision = ++epoch.current;
    inFlight.current = revision; setBusy(true); setError("");
    setGoSaveUnconfirmed(false);
    const submitted = goKey; setGoKey("");
    try {
      const result = await saveGoConnection(submitted, goLabel);
      if (revision !== epoch.current) return;
      setSelected(result.connection); setGoLabel("");
      setRows(current => [...(current ?? []).filter(row => row.connection_id !== result.connection.connection_id), result.connection]);
      setScreen(result.duplicate ? "duplicate" : "details");
    } catch (failure) {
      if (revision === epoch.current) {
        const code = failure instanceof ProviderFailure && failure.code !== "provider_connections_unavailable" ? failure.code : "provider_save_unconfirmed";
        if (code === "provider_save_unconfirmed") {
          setGoSaveUnconfirmed(true); setAttempt({ attempt_id: "", status: "failed", connection_id: null, code }); setScreen("failure");
        } else setError(code);
      }
    }
    finally { if (inFlight.current === revision) inFlight.current = null; if (revision === epoch.current) setBusy(false); }
  }

  async function confirmReplacement() {
    if (!attempt?.attempt_id || inFlight.current) return;
    const revision = ++epoch.current;
    inFlight.current = revision; setBusy(true); setError("");
    try { const progress = await confirmCodexReplacement(attempt.attempt_id); if (revision === epoch.current) setAttempt(progress); }
    catch { if (revision === epoch.current) setError("provider_connections_unavailable"); }
    finally { if (inFlight.current === revision) { inFlight.current = null; setBusy(false); } }
  }

  async function finishClaude() {
    if (!attempt?.attempt_id || inFlight.current) return;
    const revision = ++epoch.current; inFlight.current = revision; setBusy(true); setError("");
    const code = nativeCode; setNativeCode("");
    try { const progress = await submitClaudeCode(attempt.attempt_id, code); if (revision === epoch.current) setAttempt(progress); }
    catch { if (revision === epoch.current) { setError("provider_save_unconfirmed"); setAttempt(current => current ? { ...current, code: "provider_save_unconfirmed" } : current); } }
    finally { if (inFlight.current === revision) inFlight.current = null; if (revision === epoch.current) setBusy(false); }
  }

  async function signIn() {
    if (inFlight.current) return;
    if (activeProvider === "claude") {
      claudeTab.current = window.open("about:blank", "_blank");
      if (claudeTab.current) claudeTab.current.opener = null;
    }
    setGoSaveUnconfirmed(false);
    setClaudeOpened(false); setNativeCode(""); setNativeUrl(null); setDeviceCode(null); setReplacement(null);
    reconnecting.current = Boolean(selected);
    sessionStorage.setItem(reconnectKey, String(reconnecting.current));
    const revision = ++epoch.current;
    inFlight.current = revision; setBusy(true); setError("");
    try {
      const result = await beginLogin(selected?.connection_id, activeProvider === "claude" ? "claude" : "codex");
      if (revision !== epoch.current) return;
      setAttempt(result.progress);
      sessionStorage.setItem(pendingKey, result.progress.attempt_id);
      setScreen("pending");
      // One explicit click starts native sign-in in this tab. No mount, polling
      // or Refresh operation opens a provider page.
      if (activeProvider === "claude") setNativeUrl(result.authorization_url);
      else { setNativeUrl(result.authorization_url); setDeviceCode(result.user_code ?? null); }
    } catch (failure) {
      claudeTab.current?.close(); claudeTab.current = null;
      if (revision === epoch.current) {
        if (failure instanceof ProviderFailure && failure.code === "provider_connection_busy") { setError(failure.code); setScreen("details"); }
        else if (failure instanceof ProviderFailure && ["provider_session_required", "provider_connection_limit", "provider_login_in_progress"].includes(failure.code)) { setError(failure.code); }
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
    claudeTab.current?.close(); claudeTab.current = null;
    window.history.replaceState(null, "", "/settings/providers");
    setGoSaveUnconfirmed(false);
    setError(""); setAttempt(undefined); setGoKey(""); setGoLabel(""); setNativeCode(""); setNativeUrl(null); setClaudeOpened(false); sessionStorage.removeItem(reconnectKey);
    setScreen(screen === "disconnect" ? "details" : screen === "method" ? (selected ? "details" : "type") : "list");
  }

  const activeProvider = selected?.provider ?? provider;
  const providerName = activeProvider === "opencode" ? "OpenCode Go" : activeProvider === "claude" ? "Claude Code" : "Codex";
  const logo = (type: string) => type === "opencode" ? <><img src={openCodeLogoLight} className="pc-account-logo pc-opencode-light" alt="" /><img src={openCodeLogoDark} className="pc-account-logo pc-opencode-dark" alt="" /></> : type === "claude" ? <IconComponent name="Claude" className="h-6 w-6" /> : codexLogo;
  const unconfirmed = attempt?.code === "provider_save_unconfirmed";
  const mismatch = attempt?.code === "provider_account_mismatch";
  const heading = screen === "disconnect" ? `Disconnect ${providerName}?` : screen === "removed" ? "Disconnected" : screen === "removing" ? (selected?.lifecycle === "cleanup_required" ? "Cleanup required" : selected?.lifecycle === "connected" ? "Check connection" : "Disconnecting") : screen === "list" ? "Providers" : screen === "type" ? "Add provider" : screen === "method" ? `Connect ${providerName}` : screen === "pending" ? (attempt?.status === "awaiting_confirmation" ? "Use this ChatGPT account?" : unconfirmed ? "Check connection" : "Finish signing in") : screen === "failure" ? (mismatch ? "Different account selected" : unconfirmed ? "Check connection" : attempt?.status === "expired" ? "Sign-in expired" : "Sign-in failed") : screen === "duplicate" ? "Already connected" : selected?.label ?? "Provider connection";

  const status = (row: ProviderConnection) => row.lifecycle === "connected" ? row.method === "opencode_go_key" ? row.auth_state === "revoked" ? "Key unavailable" : "Key saved" : statuses[row.auth_state] : row.lifecycle === "cleanup_required" ? "Cleanup required" : "Disconnecting";
  const emphasizedStatus = (row: ProviderConnection) => row.lifecycle === "connected" && (row.auth_state === "ready" || row.method === "opencode_go_key" && row.auth_state !== "revoked");
  const ready = selected?.lifecycle === "connected" && selected.auth_state === "ready";
  const needsSignIn = selected?.lifecycle === "connected" && ["expired", "reauthorization_required", "revoked"].includes(selected.auth_state);

  return <section ref={surface} className="github-connections" aria-labelledby="provider-heading">
    {screen === "list" && <header className="gc-heading">
      <div><h1 id="provider-heading">Providers</h1><p className="gc-muted">Manage the provider accounts Laomedo can use.</p></div>
      <Button ignoreTitleCase disabled={busy} onClick={() => { setSelected(undefined); setAttempt(undefined); sessionStorage.removeItem(pendingKey); window.history.replaceState(null, "", "/settings/providers"); setScreen("type"); }}><Plus size={16} aria-hidden="true" />Add provider</Button>
    </header>}
    <div className={screen === "list" ? "pc-list-screen" : screen === "details" ? "gc-screen gc-detail" : "gc-screen"}>
      {error && <div role="alert"><ErrorExplanation failure={describeNodeFailure(error, undefined)} /></div>}
      <section className={["returning", "complete", "failure"].includes(screen) ? "pc-handoff-surface" : screen === "list" ? "gc-panel gc-accounts" : screen === "details" ? "gc-panel gc-detail-card" : "gc-panel gc-focus"}>
        {!["list", "details", "returning", "complete", "failure"].includes(screen) && <h2 id="provider-heading">{heading}</h2>}
        {screen === "failure" && <LangflowLogo className="pc-handoff-logo pc-handoff-settled" aria-hidden="true" />}
        {screen === "failure" && <h2 id="provider-heading">{heading}</h2>}
        {["returning", "complete"].includes(screen) && <div className="pc-sign-in-result" role="status" aria-live="polite">
          <LangflowLogo className={`pc-handoff-logo ${screen === "complete" ? "pc-handoff-settled" : ""}`} aria-hidden="true" />
          <h2 id="provider-heading">{screen === "returning" ? "Finishing sign-in\u2026" : attempt?.status === "duplicate" ? "Already connected" : "Connection saved!"}</h2>
          {screen === "complete" && <p className="gc-muted">{attempt?.status === "duplicate" ? "You signed in to an account that is already connected. Your existing connection is unchanged." : reconnecting.current ? "You signed in to the same account again." : "Your account is ready to use."}</p>}
        </div>}
        {screen === "list" && <>
          {rows === undefined ? <p role="status">{error ? "Could not load providers." : "Loading providersâ€¦"}</p> : rows.length === 0 ? <div className="gc-empty"><h2>No providers connected</h2><p className="gc-muted">Add a provider account to use it in your flows.</p></div> : <>
            <h2 className="gc-eyebrow">Accounts</h2>
            {rows.map(row => <div className="gc-account-row" key={row.connection_id}>
              <span className="gc-avatar" aria-hidden="true">{logo(row.provider)}</span>
              <div className="gc-account-copy"><h3>{row.label}</h3><p className="gc-muted">{row.provider === "opencode" ? "OpenCode Go | Subscription key" : row.provider === "claude" ? "Claude Code | Claude subscription" : "Codex | ChatGPT plan"}</p></div>
              <span className={`gc-status ${emphasizedStatus(row) ? "gc-ready" : "gc-attention"}`}>{status(row)}</span>
              <Button ignoreTitleCase variant="outline" aria-label={`View connection for ${row.label}`} onClick={() => { setSelected(row); setScreen("details"); }}>View connection</Button>
            </div>)}
          </>}
        </>}
        {screen === "type" && <>
          <p className="gc-muted">Choose the provider you want to connect.</p>
          <div className="pc-types" role="group" aria-label="Provider type">{["codex", "claude", "opencode"].map(type => <button type="button" aria-pressed={provider === type} className="pc-choice" key={type} onClick={() => setProvider(type)}><span className="pc-choice-logo" aria-hidden="true">{logo(type)}</span>{type === "opencode" ? "OpenCode" : type[0].toUpperCase() + type.slice(1)}</button>)}</div>
          <Button ignoreTitleCase disabled={busy} onClick={() => provider === "opencode" ? setScreen("method") : void signIn()}>Continue</Button>
        </>}
        {screen === "method" && <>
          {activeProvider === "opencode" ? <>
            <p className="gc-muted">Use a key from your OpenCode Go subscription.</p>
            <a className="gc-link" href="https://opencode.ai/console" target="_blank" rel="noopener noreferrer">Open OpenCode Console</a>
            <input className="pc-account-select" aria-label="Connection name" placeholder="Connection name" maxLength={100} value={goLabel} onChange={event => setGoLabel(event.target.value)} autoComplete="off" disabled={busy} />
            <input className="pc-account-select" type="password" aria-label="OpenCode Go key" placeholder="OpenCode Go key" value={goKey} onChange={event => setGoKey(event.target.value)} autoComplete="off" disabled={busy} />
            <p className="gc-muted">Saving stores the key locally. It does not verify your account or send a model request.</p>
            <Button ignoreTitleCase disabled={busy || !goKey || !goLabel.trim()} onClick={() => void saveGo()}>Save connection</Button>
          </> : <><p className="gc-muted">{activeProvider === "claude" ? "Sign in with the official Claude Code client to use your Claude subscription." : "Sign in with ChatGPT to use your eligible ChatGPT plan."}</p>
          <Button ignoreTitleCase disabled={busy} onClick={() => void signIn()}>Continue to sign in</Button></>}
        </>}
        {screen === "pending" && <>
          {attempt?.provider === "codex" && attempt.status === "awaiting_confirmation" && replacement ? <>
            <p className="gc-muted">Replace the saved Codex login with this verified account. Your graph selections will stay the same.</p>
            <div className="gc-identity"><span className="gc-avatar" aria-hidden="true">{codexLogo}</span><div><strong>{replacement.email}</strong><p className="gc-muted">ChatGPT {replacement.plan_type}</p></div></div>
            <Button ignoreTitleCase disabled={busy} onClick={() => void confirmReplacement()}>Replace connection</Button>
          </> : attempt?.provider === "codex" && attempt.status === "connecting" ? <>
            {deviceCode && nativeUrl ? <>
              <p className="gc-muted">Enter this code on the ChatGPT sign-in page. Return here when you finish.</p>
              <div className="pc-device-code" aria-label="ChatGPT sign-in code">{deviceCode}</div>
              <Button ignoreTitleCase asChild><a href={nativeUrl} target="_blank" rel="noopener noreferrer">Continue to ChatGPT</a></Button>
              <p className="gc-muted" role="status">Waiting for you to finish signing in...</p>
            </> : <p className="gc-muted" role="status">Preparing ChatGPT sign-in...</p>}
          </> : attempt?.provider === "claude" && attempt.status === "connecting" ? <>
            {nativeUrl ? <>
              <p className="gc-muted">{claudeOpened ? "Paste the code from Claude to finish signing in." : "Continue to Claude to sign in, then paste the code it gives you below."}</p>
              {!claudeOpened && <Button ignoreTitleCase asChild><a href={nativeUrl} target="_blank" rel="noopener noreferrer" onClick={() => setClaudeOpened(true)}>Continue to Claude</a></Button>}
              {claudeOpened && <><input className="pc-account-select" type="password" aria-label="Claude sign-in code" placeholder="Claude sign-in code" autoComplete="off" value={nativeCode} onChange={event => setNativeCode(event.target.value)} disabled={busy} />
              <Button ignoreTitleCase disabled={busy || !nativeCode} onClick={() => void finishClaude()}>Finish sign-in</Button></>}
            </> : <p className="gc-muted" role="status">Preparing Claude sign-in{"\u2026"}</p>}
          </> : <>
            {!unconfirmed && attempt?.status !== "verifying" && <p className="gc-muted">Complete sign-in with the provider. This page will update when it finishes.</p>}
            <p className="gc-notice" role="status">{unconfirmed ? "Checking your saved connection\u2026" : attempt?.status === "verifying" ? "Checking connection\u2026" : "Waiting for sign-in\u2026"}</p>
          </>}
        </>}
        {screen === "details" && selected && <>
          <div className="gc-identity"><span className="gc-avatar" aria-hidden="true">{logo(selected.provider)}</span><h2 id="provider-heading">{selected.label}</h2><span className={`gc-status ${emphasizedStatus(selected) ? "gc-ready" : "gc-attention"}`}>{status(selected)}</span></div>
          <p className="gc-muted">{selected.method === "opencode_go_key" ? "Your Go key is saved locally. Account identity and access have not been verified; the selected model checks access when you run it." : ready ? "Laomedo uses this account when you select it in a graph." : needsSignIn ? "Sign in again to restore access for this account." : "We cannot check this connection right now. Refresh to check again."}</p>
          <div className="gc-footer"><p className="gc-muted">Removing this connection stops Laomedo access.</p><div className="pc-connection-actions">{selected.lifecycle === "connected" && <Button ignoreTitleCase variant={needsSignIn && selected.method !== "opencode_go_key" ? "default" : "outline"} disabled={busy} onClick={() => selected.provider === "opencode" ? setScreen("method") : void signIn()}>{selected.provider === "opencode" ? "Add another Go key" : "Sign in again"}</Button>}<Button ignoreTitleCase variant="outline" disabled={busy} onClick={() => selected.lifecycle === "connected" ? void prepareDisconnect() : setScreen("removing")}>{selected.lifecycle === "connected" ? "Disconnect" : "View cleanup"}</Button></div></div>
        </>}
        {screen === "disconnect" && selected && removal && <>
          <p>{selected.label}</p>
          <p className="gc-muted">{removal.active_runs ? `${removal.active_runs} active ${removal.active_runs === 1 ? "run will" : "runs will"} stop. Their work and activity will be kept.` : "No active runs will be affected."}</p>
          <p className="gc-muted">This removes this connection from Laomedo. Your provider account and other connections stay unchanged.</p>
          <div className="gc-footer"><Button ignoreTitleCase variant="outline" disabled={busy} onClick={() => setScreen("details")}>Cancel</Button><Button ignoreTitleCase disabled={busy} onClick={() => void removeConnection()}>Disconnect</Button></div>
        </>}
        {screen === "removing" && <>
          <p role="status">{selected?.lifecycle === "cleanup_required" ? "We couldnâ€™t finish removing this connection. New runs are blocked." : selected?.lifecycle === "connected" ? "Disconnect wasnâ€™t confirmed. Refresh to check this connection." : "Stopping active work and removing this connectionâ€¦"}</p>
          <p className="gc-muted">Your work and activity are kept.</p>
          {selected?.lifecycle === "cleanup_required" && <Button ignoreTitleCase disabled={busy} onClick={() => void removeConnection(true)}>Retry cleanup</Button>}
        </>}
        {screen === "removed" && <>
          <p role="status">This connection has been removed from Laomedo.</p>
          <p className="gc-muted">Your provider account and other connections stay unchanged.</p>
          <Button ignoreTitleCase onClick={() => { setSelected(undefined); setScreen("list"); }}>Back to providers</Button>
        </>}
        {screen === "failure" && <>
          {mismatch ? <p className="gc-muted">{describeNodeFailure("provider_account_mismatch", undefined).description}</p> : unconfirmed ? <ErrorExplanation failure={describeNodeFailure("provider_save_unconfirmed", undefined)} /> : <p className="gc-muted">{attempt?.status === "expired" ? "Your sign-in expired. Try again." : <>We couldnâ€™t finish signing you in.<br />Your saved connection hasnâ€™t changed.</>}</p>}
          {mismatch ? <Button ignoreTitleCase disabled={busy} onClick={() => { setProvider(selected?.provider ?? attempt?.provider ?? provider); setSelected(undefined); setAttempt(undefined); sessionStorage.removeItem(pendingKey); sessionStorage.removeItem(reconnectKey); reconnecting.current = false; window.history.replaceState(null, "", "/settings/providers"); setScreen("method"); }}>Add as new connection</Button> : <Button ignoreTitleCase disabled={busy || unconfirmed} onClick={() => { setAttempt(undefined); sessionStorage.removeItem(pendingKey); window.history.replaceState(null, "", "/settings/providers"); setScreen("method"); }}>Try again</Button>}
        </>}
        {screen === "duplicate" && <>
          <p className="gc-muted">{selected?.provider === "opencode" ? "This key is already saved." : "This account is already connected."}<br />Your existing connection hasnâ€™t changed.</p>
          <Button ignoreTitleCase onClick={() => setScreen("details")}>View connection</Button>
        </>}
      </section>
      {screen !== "complete" && <nav className="gc-navigation" aria-label="Connection navigation">
        {screen !== "list" && <button type="button" className="gc-link gc-icon" disabled={busy} aria-label="Back to connections" title="Back to connections" onClick={() => void back()}><ArrowLeft size={20} aria-hidden="true" /></button>}
        {!["type", "method", "disconnect", "removed"].includes(screen) && <button type="button" className="gc-link gc-icon" disabled={busy} aria-label="Refresh" title="Refresh connections" onClick={() => void refresh()}><RefreshCw size={20} aria-hidden="true" /></button>}
      </nav>}
    </div>
  </section>;
}
