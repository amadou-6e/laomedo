import catalog from "./node-error-catalog.json";

type Description = { title: string; description: string; recovery: string };
export type ErrorContext = {
  nodeId?: string;
  nodeType?: string;
  nodeLabel?: string;
  operation?: unknown;
  savedReferences?: unknown[];
};
export type NodeFailure = Description & { diagnostics: Record<string, string> };
const entries: Record<string, Description> = catalog;
const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const operations = new Set(["fresh", "start", "resume", "status", "cancel", "modify", "close"]);
const fallback: Description = {
  title: "The node could not confirm completion",
  description: "An unrecognized failure prevented a confirmed result. Its cause has not been established.",
  recovery: "Review the safe technical details. If a request may have reached the runner, check its existing run before starting another request.",
};

// Never copy exception bodies, stack traces, endpoints, tasks or arbitrary params.
function safeCode(value: unknown): string | undefined {
  if (typeof value !== "string") return;
  if (Object.prototype.hasOwnProperty.call(entries, value)) return value;
  if (/^[a-z][a-z0-9]*(?:_[a-z0-9]+){1,15}$/.test(value) && value.length <= 80 &&
      !/(?:secret|password|credential|bearer|token|api_key)/.test(value)) return value;
}

function codeFromMessage(raw: unknown): string | undefined {
  if (typeof raw !== "string" || raw.length > 65536) return;
  // Native Langflow wraps a component error; only inspect the final message,
  // not arbitrary substrings in a response, URL, JSON payload or traceback.
  const message = raw.replace(/^Error building Component[^\r\n]*:\s*\r?\n\s*/, "").trim();
  const failure = message.match(/^Laomedo run [0-9a-f-]{36} failed: ([a-z0-9_]+)$/i);
  if (failure) return safeCode(failure[1]);
  return safeCode(message.split(";", 1)[0].trim());
}

function structuredFailure(value: unknown, depth = 0): Record<string, unknown> | undefined {
  if (!value || typeof value !== "object" || depth > 5 || Array.isArray(value)) return;
  const item = value as Record<string, unknown>;
  if (typeof item.error_category === "string" && item.status !== "completed") return item;
  if (["failed", "unknown", "timeout", "interrupted"].includes(String(item.status)) &&
      typeof item.run_id === "string" && uuid.test(item.run_id)) return item;
  // Traverse only known result-envelope fields, never arbitrary payload keys.
  for (const key of ["run_reference", "data", "results", "message"]) {
    const found = structuredFailure(item[key], depth + 1);
    if (found) return found;
  }
}

function outputFailure(status: any): Record<string, unknown> | undefined {
  const outputs = status?.data?.outputs;
  if (!outputs || typeof outputs !== "object") return;
  for (const output of Object.values(outputs).slice(0, 32)) {
    const found = structuredFailure(output);
    if (found) return found;
  }
}

export function isKnownNodeError(raw: unknown, laomedoContext = false): boolean {
  const code = codeFromMessage(raw);
  return laomedoContext && Boolean(code) || typeof raw === "string" && /^Error building Component Laomedo[^\r\n]*:/i.test(raw);
}

export function hasLaomedoFailure(status: unknown): boolean {
  return Boolean(outputFailure(status));
}

function referenceState(values: unknown[] = []): string | undefined {
  let unreadable = false;
  for (let value of values.slice(0, 2)) {
    if (value == null || value === "") continue;
    if (typeof value === "string") {
      if (value.length > 65536) { unreadable = true; continue; }
      try { value = JSON.parse(value); } catch { unreadable = true; continue; }
    }
    if (value && typeof value === "object" && !Array.isArray(value)) {
      const object = value as Record<string, unknown>;
      const data = object.data && typeof object.data === "object" ? object.data as Record<string, unknown> : object;
      if (typeof data.run_id === "string" && uuid.test(data.run_id)) return "saved_reference_present";
      if (Object.keys(data).length) unreadable = true;
    }
  }
  return unreadable ? "saved_reference_unreadable" : undefined;
}

export function describeNodeFailure(raw: unknown, status: any, context: ErrorContext = {}): NodeFailure {
  const reference = outputFailure(status);
  const code = safeCode(reference?.error_category) ?? codeFromMessage(raw) ?? "unrecognized_error";
  const diagnostics: Record<string, string> = { code };
  if (typeof context.nodeId === "string" && /^[a-z][a-z0-9_-]{0,127}$/i.test(context.nodeId) &&
      !/^(sk_|gh[pousr]_)/i.test(context.nodeId)) diagnostics.node_id = context.nodeId;
  if (typeof context.operation === "string" && operations.has(context.operation)) diagnostics.operation = context.operation;
  if (typeof status?.run_id === "string" && uuid.test(status.run_id)) diagnostics.graph_execution_id = status.run_id;
  for (const key of ["run_id", "request_id", "thread_id", "invocation_id"]) {
    const value = reference?.[key];
    if (typeof value === "string" && uuid.test(value)) diagnostics[key] = value;
  }
  if (typeof reference?.trace_id === "string" && /^[0-9a-f]{32}$/i.test(reference.trace_id)) diagnostics.trace_id = reference.trace_id;
  if (typeof raw === "string" && raw.length <= 65536) {
    const run = raw.match(/(?:Laomedo run |run_id=)([0-9a-f-]{36})(?:\b|;)/i)?.[1];
    const request = raw.match(/check status for request_id before starting again: ([0-9a-f-]{36})$/i)?.[1];
    if (run && uuid.test(run)) diagnostics.run_id ??= run;
    if (request && uuid.test(request)) diagnostics.request_id ??= request;
  }
  let description = entries[code] ?? fallback;
  if (code === "prior_run_required") {
    const state = referenceState(context.savedReferences);
    if (state) {
      diagnostics.reference_state = state;
      description = state === "saved_reference_present" ? {
        title: "The saved run reference was not accepted",
        description: "This saved node contains a run reference, but the node reported no usable reference. The reason has not been established.",
        recovery: "Keep the original reference and share the technical details with the application maintainer. Check the existing run before starting a replacement.",
      } : entries.invalid_prior_run_json;
    }
  }
  return { ...description, diagnostics };
}

// Toasts are presentation only: original API events and machine codes are untouched.
export function describeLaomedoAlert(alert: { title: string; list?: string[] }, laomedoContext = false): { title: string; list?: string[]; diagnosticCode?: string; failure?: NodeFailure } {
  const raw = (alert.list ?? []).find(value => typeof value === "string" &&
    isKnownNodeError(value, laomedoContext));
  if (!raw) return alert;
  const failure = describeNodeFailure(raw, undefined);
  return { failure, title: failure.title, diagnosticCode: failure.diagnostics.code, list: [failure.description, "Open Error details or expand Technical details for recovery steps and diagnostics."] };
}
