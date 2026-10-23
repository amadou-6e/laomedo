import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { api } from "@/controllers/API/api";
import { getBaseUrl } from "@/customization/utils/urls";

type Service = { state: string; can_start: boolean; remaining_turns?: number; reason?: string };

export function isRunnerConnectionError(message: unknown): boolean {
  if (typeof message !== "string" || message.length > 65536) return false;
  const error = message.replace(/^Error building Component[^\r\n]*:\s*\r?\n\s*/, "").trim();
  return /^runner_transport_failed(?:;|$)/.test(error) ||
    /^Laomedo run [0-9a-f-]{36} failed: runner_transport_failed$/i.test(error);
}

function LocalBackendRecovery() {
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
        if (!controller.signal.aborted && version === generation.current)
          setError("The local backend availability could not be checked. Check its host configuration.");
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
      setError("The local backend could not be restarted. Check the host startup log before trying again.");
    } finally { pending.current = false; }
  };

  const waiting = starting || service?.state === "starting";
  const message = service?.state === "ready"
    ? service.remaining_turns === 0
      ? "The local runner backend is online. Its approved turn limit is reached; status and recorded results remain available."
      : "The configured local runner backend is online. Inspect the existing run before retrying; the original connection failure may have another cause."
    : waiting ? "Restarting the local runner backend..."
    : service?.state === "offline" ? "The local runner backend is offline. Restart it to restore the connection."
    : service?.state === "unmanaged" ? "Local backend recovery is not configured on this host. Ask the operator to configure it."
    : service ? "The local runner backend identity could not be verified. Check the host configuration."
    : "Checking the local runner backend connection...";

  return <section aria-label="Local backend recovery" className="space-y-3 text-foreground">
    <h3 className="font-semibold">The local runner connection failed</h3>
    <p role="status">{message}</p>
    {(service?.can_start || waiting) && <Button size="sm" onClick={restart} disabled={waiting}>
      {waiting ? "Restarting local backend..." : "Restart local backend"}
    </Button>}
    {error && <p role="alert">{error}</p>}
    <p className="text-xs text-muted-foreground">This restarts only the host-configured API. It does not rerun the graph or change its approved turn limit. Inspect any existing run before starting new work.</p>
    <details><summary className="cursor-pointer text-xs">Technical details</summary><code>runner_transport_failed</code></details>
  </section>;
}

export default function RunnerRecovery({ message }: { message: unknown }) {
  return isRunnerConnectionError(message) ? <LocalBackendRecovery /> : null;
}
