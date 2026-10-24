import { describeNodeFailure } from "@/components/laomedoErrors/nodeErrors";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { Button } from "@/components/ui/button";
import { api } from "@/controllers/API/api";
import { getBaseUrl } from "@/customization/utils/urls";

type Service = { state: string; can_start: boolean; reason?: string };

export function isRunnerConnectionError(message: unknown): boolean {
  if (typeof message !== "string" || message.length > 65536) return false;
  const error = message.replace(/^Error building Component[^\r\n]*:\s*\r?\n\s*/, "").trim();
  return /^runner_transport_failed(?:;|$)/.test(error) ||
    /^Laomedo run [0-9a-f-]{36} failed: runner_transport_failed$/i.test(error);
}

export type RecoveryState = { message: string; error: string; waiting: boolean; canStart: boolean; state?: string; reason?: string; restart: () => Promise<void> };

function LocalBackendRecovery({ children }: { children?: (state: RecoveryState) => ReactNode }) {
  const [service, setService] = useState<Service | null>(null);
  const [error, setError] = useState("");
  const [starting, setStarting] = useState(false);
  const pending = useRef(false);
  const generation = useRef(0);
  const endpoint = `${getBaseUrl()}laomedo/runner-service`;

  useEffect(() => {
    const controller = new AbortController();
    let loading = false;
    const load = async () => {
      if (loading || pending.current) return;
      loading = true;
      const version = generation.current;
      try {
        const { data } = await api.get<Service>(endpoint, { signal: controller.signal });
        if (!controller.signal.aborted && version === generation.current) {
          setService(data); setError("");
          if (data.state !== "starting") setStarting(false);
        }
      } catch {
        if (!controller.signal.aborted && version === generation.current) {
          setService(null);
          setError(describeNodeFailure("runner_service_configuration_unavailable", undefined).recovery);
        }
      } finally { loading = false; }
    };
    void load();
    const timer = setInterval(load, 2000);
    return () => { controller.abort(); clearInterval(timer); };
  }, [endpoint]);

  const restart = async () => {
    if (pending.current || !service?.can_start || service.state !== "offline") return;
    pending.current = true; generation.current += 1;
    setStarting(true); setError("");
    try {
      const { data } = await api.post<Service>(`${endpoint}/start`, null);
      setService(data); setError("");
      if (data.state !== "starting") setStarting(false);
    } catch {
      setStarting(false);
      setError(describeNodeFailure("runner_start_failed", undefined).recovery);
    } finally { pending.current = false; }
  };

  const waiting = starting || service?.state === "starting";
  const message = service?.state === "ready"
    ? "The local runner backend is online. Inspect the existing run before starting new work."
    : waiting ? "Restarting the local runner backend..."
    : service?.state === "offline" ? service.reason === "runner_start_failed"
      ? describeNodeFailure("runner_start_failed", undefined).description + " " + describeNodeFailure("runner_start_failed", undefined).recovery
      : "The local runner backend is offline. Restart it to restore the connection."
    : service?.state === "unmanaged" ? "Local backend recovery is not configured on this host. Ask the operator to configure it."
    : service ? describeNodeFailure("runner_identity_unverified", undefined).description + " " + describeNodeFailure("runner_identity_unverified", undefined).recovery
    : "Checking the local runner backend connection...";

  if (children) return children({ message, error, waiting, canStart: Boolean(service?.can_start), state: service?.state, reason: service?.reason, restart });
  return <section aria-label="Local backend recovery" className="space-y-3 text-foreground">
    <p role="status">{message}</p>
    {(service?.can_start || waiting) && <Button size="sm" onClick={restart} disabled={waiting}>
      {waiting ? "Restarting local backend..." : "Restart local backend"}
    </Button>}
    {error && <p role="alert">{error}</p>}
    <p className="text-xs text-muted-foreground">This restarts only the host-configured API. It does not rerun the graph. Inspect any existing run before starting new work.</p>
  </section>;
}

export default function RunnerRecovery({ message, children }: { message: unknown; children?: (state: RecoveryState) => ReactNode }) {
  return isRunnerConnectionError(message) ? <LocalBackendRecovery>{children}</LocalBackendRecovery> : null;
}
