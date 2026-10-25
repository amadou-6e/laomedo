import { describeNodeFailure } from "@/components/laomedoErrors/nodeErrors";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { Button } from "@/components/ui/button";
import { api } from "@/controllers/API/api";
import { getBaseUrl } from "@/customization/utils/urls";

type Service = { state: string; can_start: boolean; reason?: string; startup_id?: string; startup_cancelled?: boolean };
export const DOCKER_INSTALL_URL = "https://docs.docker.com/get-started/get-docker/";
export const PREREQUISITE_CODES = ["runner_docker_not_installed", "runner_docker_unavailable", "runner_docker_check_unconfirmed", "runner_local_offline"];

// Bound the full client chain, including authentication/error interceptors.
async function recoveryRequest<T>(request: Promise<T>): Promise<T> {
  let timer: ReturnType<typeof setTimeout> | undefined;
  try {
    return await Promise.race([request, new Promise<never>((_, reject) => {
      timer = setTimeout(() => reject(new Error("Recovery request unconfirmed")), 10000);
    })]);
  } finally { clearTimeout(timer); }
}

export function isRunnerConnectionError(message: unknown): boolean {
  if (typeof message !== "string" || message.length > 65536) return false;
  const error = message.replace(/^Error building Component[^\r\n]*:\s*\r?\n\s*/, "").trim();
  return /^runner_transport_failed(?:;|$)/.test(error) ||
    /^Laomedo run [0-9a-f-]{36} failed: runner_transport_failed$/i.test(error);
}

export type RecoveryState = { message: string; guidance: string; title?: string; installDocker: boolean; error: string; waiting: boolean; canStart: boolean; state?: string; reason?: string; cancel: () => Promise<boolean>; cancelling: boolean; restart: () => Promise<void> };

function LocalBackendRecovery({ children }: { children?: (state: RecoveryState) => ReactNode }) {
  const [service, setService] = useState<Service | null>(null);
  const [error, setError] = useState("");
  const [starting, setStarting] = useState(false);
  const pending = useRef(false);
  const [cancelling, setCancelling] = useState(false);
  const startRequest = useRef<Promise<{ data: Service }> | null>(null);
  const completedStart = useRef<Service | null>(null);
  const generation = useRef(0);
  const endpoint = `${getBaseUrl()}laomedo/runner-service`;

  useEffect(() => {
    const controller = new AbortController();
    let loading = false;
    const load = async () => {
      if (loading || pending.current || cancelling) return;
      loading = true;
      const version = generation.current;
      try {
        const { data } = await recoveryRequest(api.get<Service>(endpoint, { signal: controller.signal, timeout: 10000 }));
        if (!controller.signal.aborted && version === generation.current) {
          setService(data); setError("");
          if (data.state !== "starting") setStarting(false);
        }
      } catch {
        if (!controller.signal.aborted && version === generation.current) {
          setService(null);
          setStarting(false);
          setError(describeNodeFailure("runner_service_configuration_unavailable", undefined).description);
        }
      } finally { loading = false; }
    };
    void load();
    const timer = setInterval(load, 2000);
    return () => { controller.abort(); clearInterval(timer); };
  }, [endpoint, cancelling]);

  const restart = async () => {
    if (pending.current || !service?.can_start || service.state !== "offline") return;
    pending.current = true; generation.current += 1;
    setStarting(true); setError(""); completedStart.current = null;
    try {
      startRequest.current = recoveryRequest(api.post<Service>(`${endpoint}/start`, null, {timeout: 10000}));
      const { data } = await startRequest.current;
      completedStart.current = data;
      setService(data); setError("");
      if (data.state !== "starting") setStarting(false);
    } catch {
      setStarting(false); setService(null);
      setError("The local runner startup could not be confirmed.");
    } finally { pending.current = false; startRequest.current = null; }
  };

  const cancel = async () => {
    if (cancelling) return false;
    if (!starting && !["starting", "cancelling"].includes(service?.state ?? "")) return true;
    setCancelling(true); generation.current += 1; setError("");
    try {
      const target = startRequest.current ? (await startRequest.current).data
        : service?.startup_id ? service : completedStart.current ?? service;
      if (!target?.startup_id) {
        setStarting(false);
        setError(describeNodeFailure("runner_start_cancel_unconfirmed", undefined).description);
        return false;
      }
      let { data } = await recoveryRequest(api.post<Service>(`${endpoint}/cancel-start`, null, {params: {startup_id: target.startup_id}, timeout: 10000}));
      const deadline = Date.now() + 120000;
      while (data.state === "cancelling" && Date.now() < deadline) {
        await new Promise(resolve => setTimeout(resolve, 500));
        data = (await recoveryRequest(api.get<Service>(endpoint, {timeout: 10000}))).data;
      }
      setService(data); setStarting(false);
      if (data.reason === "runner_start_cancelled" || data.startup_cancelled === true) return true;
      setError(data.state === "ready" ? "The backend is already online; startup can no longer be cancelled." : describeNodeFailure("runner_start_cancel_unconfirmed", undefined).description);
      return false;
    } catch {
      setStarting(false); setError(describeNodeFailure("runner_start_cancel_unconfirmed", undefined).description); return false;
    } finally { setCancelling(false); }
  };

  const waiting = !error && (starting || service?.state === "starting" || service?.state === "cancelling");
  const prerequisite = PREREQUISITE_CODES.includes(service?.reason ?? "")
    ? describeNodeFailure(service!.reason!, undefined) : undefined;
  const message = service?.state === "ready"
    ? "The local runner is online. Check the existing run before starting new work."
    : prerequisite ? prerequisite.description
    : service?.state === "cancelling" ? "Cancelling runner startup..."
    : waiting ? "Starting the local runner..."
    : service?.state === "offline" ? service.reason === "runner_start_failed"
      ? describeNodeFailure("runner_start_failed", undefined).description
      : "Docker is ready, but the local runner is not running."
    : service?.state === "starting" ? "Backend startup is unconfirmed."
    : service?.state === "unmanaged" ? "Local backend recovery is not configured on this machine."
    : service ? describeNodeFailure("runner_identity_unverified", undefined).description + " " + describeNodeFailure("runner_identity_unverified", undefined).recovery
    : error ? "The local backend connection could not be confirmed."
    : "Checking the local runner backend connection...";

  const guidance = prerequisite ? prerequisite.recovery : service?.state === "ready" ? ""
    : "Starting the runner does not rerun the graph. Check any existing run before starting new work.";
  const installDocker = service?.reason === "runner_docker_not_installed";
  if (children) return children({ message, guidance, title: prerequisite?.title, installDocker, error, waiting, cancel, cancelling, canStart: Boolean(service?.can_start), state: service?.state, reason: service?.reason, restart });
  return <section aria-label="Local backend recovery" className="space-y-3 text-foreground">
    <p role="status">{message}</p>
    {(service?.can_start || waiting) && <Button size="sm" onClick={restart} disabled={waiting}>
      {waiting ? "Starting local runner..." : "Start local runner"}
    </Button>}
    {installDocker && <a href={DOCKER_INSTALL_URL} target="_blank" rel="noopener noreferrer">Install Docker</a>}
    {error && <p role="alert">{error}</p>}
    {!waiting && guidance && <p className="text-xs text-muted-foreground">{guidance}</p>}
  </section>;
}

export default function RunnerRecovery({ message, children }: { message: unknown; children?: (state: RecoveryState) => ReactNode }) {
  return isRunnerConnectionError(message) ? <LocalBackendRecovery>{children}</LocalBackendRecovery> : null;
}
