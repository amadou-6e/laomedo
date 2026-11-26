import { useEffect, useRef, useState } from "react";
import { CircleAlert, ExternalLink, RefreshCw } from "lucide-react";
import { describeNodeFailure } from "@/components/laomedoErrors/nodeErrors";
import { Button } from "@/components/ui/button";
import {
  ProviderFailure,
  readSubscriptionLimits,
  type ProviderConnection,
  type SubscriptionObservation,
  type SubscriptionWindow,
} from "./api";

function windowLabel(window: SubscriptionWindow) {
  if (window.kind === "monthly") return "Monthly window";
  const minutes = window.window_minutes;
  if (minutes === null)
    return window.kind === "primary" ? "Primary window" : "Secondary window";
  if (minutes % 1440 === 0) return `${minutes / 1440}-day window`;
  if (minutes % 60 === 0) return `${minutes / 60}-hour window`;
  return `${minutes}-minute window`;
}

function AllowanceWindow({
  window,
  bucket,
}: {
  window: SubscriptionWindow;
  bucket: string;
}) {
  const remaining =
    window.used_percent === null
      ? null
      : Math.max(0, 100 - window.used_percent);
  const label = windowLabel(window);
  const reset =
    window.resets_at === null ? null : new Date(window.resets_at * 1000);
  return (
    <div className="pc-quota-window">
      <div className="pc-quota-window-heading">
        <span>{label}</span>
        <strong>
          {remaining === null
            ? "Allowance unknown"
            : `${new Intl.NumberFormat(undefined, { maximumFractionDigits: 1 }).format(remaining)}% remaining`}
        </strong>
      </div>
      {remaining !== null && (
        <div
          className="pc-quota-track"
          role="meter"
          aria-label={`${bucket}: ${label} allowance remaining`}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={remaining}
        >
          <div className="pc-quota-fill" style={{ width: `${remaining}%` }} />
        </div>
      )}
      <p
        className="pc-quota-time"
        title={reset?.toLocaleString(undefined, { timeZoneName: "short" })}
      >
        {reset
          ? `Resets ${reset.toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" })}`
          : "Reset time unknown"}
      </p>
    </div>
  );
}

function AccountLimits({
  flowId,
  account,
}: {
  flowId: string;
  account: ProviderConnection;
}) {
  const [observation, setObservation] =
    useState<SubscriptionObservation | null>(null);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState("");
  const [now, setNow] = useState(Date.now());
  const request = useRef(0);
  const active = useRef<AbortController | null>(null);
  const supported = account.provider === "codex" || account.provider === "claude" ||
    (account.provider === "opencode" && account.method === "opencode_go_key");
  const eligible =
    account.lifecycle === "connected" &&
    (account.auth_state === "ready" ||
      (account.method === "opencode_go_key" && account.auth_state === "unavailable"));

  async function load(refresh: boolean) {
    active.current?.abort();
    const controller = new AbortController();
    active.current = controller;
    const sequence = ++request.current;
    setBusy(true);
    setFailure("");
    try {
      const result = await readSubscriptionLimits(
        flowId,
        account.connection_id,
        account.generation,
        { refresh, signal: controller.signal },
      );
      if (sequence === request.current && !controller.signal.aborted) {
        setObservation(result);
        setNow(Date.now());
      }
    } catch (error) {
      if (sequence !== request.current || controller.signal.aborted) return;
      const fenced =
        error instanceof ProviderFailure &&
        [
          "provider_session_required",
          "provider_connection_unavailable",
          "provider_connection_changed",
          "provider_connection_disconnecting",
        ].includes(error.code);
      if (fenced) {
        setObservation(null);
        setFailure("Account unavailable. Open Manage accounts to reconnect.");
      } else {
        setFailure("Could not refresh. Try again.");
        setObservation((value) =>
          value?.snapshot
            ? { ...value, state: "stale", reason: "refresh_failed" }
            : null,
        );
      }
    } finally {
      if (sequence === request.current && !controller.signal.aborted) {
        active.current = null;
        setBusy(false);
      }
    }
  }

  useEffect(() => {
    if (!supported || !eligible) return;
    void load(true);
    const timer = setInterval(() => {
      if (!active.current) void load(true);
    }, 10000);
    return () => {
      clearInterval(timer);
      ++request.current;
      active.current?.abort();
    };
  }, [flowId, account.connection_id, account.generation, supported, eligible]);
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 15000);
    return () => clearInterval(timer);
  }, []);

  const quotaCode = {
    authentication_failed: "opencode_go_usage_authentication_failed",
    not_entitled: "opencode_go_usage_not_entitled",
    rate_limited: "opencode_go_usage_rate_limited",
  }[observation?.reason ?? ""];
  const quotaFailure = quotaCode ? describeNodeFailure(quotaCode, undefined) : null;
  const stale =
    observation?.state === "stale" ||
    (observation?.snapshot &&
      observation.stale_after !== null &&
      now / 1000 >= observation.stale_after);
  const status = !supported
    ? "Not available"
    : !eligible
      ? "Account unavailable"
      : busy
        ? "Checking..."
        : stale
          ? "Out of date"
          : observation?.state === "unavailable" || failure
            ? (observation?.reason === "not_entitled" ? "Go access required" : "Could not check")
            : !observation?.snapshot
              ? ""
              : "";
  return (
    <li className="pc-quota-account">
      <div className="pc-subscription-row">
        <span className="pc-subscription-account">{account.label}</span>
        <div className="pc-quota-actions">
          <span className="pc-availability" role="status">
            {status}
          </span>
          {supported && (
            <Button
              variant="ghost"
              size="icon"
              aria-label={`Refresh limits for ${account.label}`}
              title={`Refresh limits for ${account.label}`}
              disabled={busy || !eligible}
              onClick={() => void load(true)}
            >
              <RefreshCw
                size={16}
                className={busy ? "animate-spin" : undefined}
                aria-hidden="true"
              />
            </Button>
          )}
        </div>
      </div>
      {!supported ? (
        <p>This provider does not report subscription limits here.</p>
      ) : !eligible ? (
        <p>Open Manage accounts to reconnect.</p>
      ) : observation?.reason === "unsupported" ? (
        <p>Sign in again in Manage accounts to use this connection for subscription limits.</p>
      ) : (
        <>
          {observation?.snapshot && (
            <div
              className={
                stale ? "pc-quota-buckets pc-quota-stale" : "pc-quota-buckets"
              }
            >
              {observation.snapshot.buckets.length === 0 && (
                <p>No limits reported.</p>
              )}
              {observation.snapshot.buckets.map((bucket) => (
                <section
                  key={bucket.limit_id}
                  className="pc-quota-bucket"
                  aria-label={bucket.label || bucket.limit_id}
                >
                  <h3>
                    {bucket.label || bucket.limit_id}
                  </h3>
                  {bucket.windows.length === 0 ? (
                    <p>No limits reported.</p>
                  ) : (
                    bucket.windows.map((window) => (
                      <AllowanceWindow
                        key={window.kind}
                        window={window}
                        bucket={bucket.label || bucket.limit_id}
                      />
                    ))
                  )}
                  {bucket.credits && (
                    <p>
                      {bucket.credits.unlimited === true
                        ? "Unlimited credits"
                        : bucket.credits.has_credits === false
                          ? "No credits"
                          : bucket.credits.balance !== null
                            ? `Credit balance: ${bucket.credits.balance}`
                            : "Credit balance unknown"}
                    </p>
                  )}
                </section>
              ))}
            </div>
          )}
          {observation?.observed_at !== null &&
            observation?.observed_at !== undefined && (
              <p
                className="pc-quota-time"
                title={new Date(observation.observed_at * 1000).toLocaleString(
                  undefined,
                  { timeZoneName: "short" },
                )}
              >
                {stale ? "Last checked" : "Checked"}{" "}
                {new Date(observation.observed_at * 1000).toLocaleTimeString(
                  undefined,
                  { hour: "2-digit", minute: "2-digit" },
                )}
              </p>
            )}
          {(failure ||
            observation?.reason === "refresh_failed" ||
            observation?.reason === "busy" ||
            observation?.reason === "authentication_failed" ||
            observation?.reason === "not_entitled" ||
            observation?.reason === "rate_limited") && (
            <div className="pc-quota-notice" role="alert">
              <CircleAlert size={20} className="pc-quota-notice-icon" aria-hidden="true" />
              <div className="pc-quota-notice-content">
                <h3>{quotaFailure?.title || "Limits temporarily unavailable"}</h3>
                <p>{observation?.reason === "not_entitled" ? "Check the Go subscription for this key in OpenCode Console." : failure ||
                (observation?.reason === "busy"
                  ? "Account is busy. Try again when its run finishes."
                  : quotaFailure
                    ? `${quotaFailure.description} ${quotaFailure.recovery}`
                    : "Could not refresh. Try again.")}
                </p>
                {observation?.reason === "not_entitled" && (
                  <a href="https://opencode.ai/console" target="_blank" rel="noopener noreferrer" className="pc-manage-account">
                    OpenCode Console
                    <ExternalLink size={14} aria-hidden="true" />
                  </a>
                )}
              </div>
            </div>
          )}
        </>
      )}
    </li>
  );
}

export default function SubscriptionLimits({
  flowId,
  accounts,
}: {
  flowId: string;
  accounts: ProviderConnection[];
}) {
  return (
    <ul
      className="pc-subscription-list"
      aria-label="Account subscription limits"
    >
      {accounts.map((account) => (
        <AccountLimits
          key={`${flowId}:${account.connection_id}:${account.generation}`}
          flowId={flowId}
          account={account}
        />
      ))}
    </ul>
  );
}
