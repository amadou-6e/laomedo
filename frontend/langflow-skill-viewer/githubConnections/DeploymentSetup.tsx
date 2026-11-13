import { useState } from "react";
import { Button } from "@/components/ui/button";
import { connectionRequest } from "./api";

/** One-time deployment registration; ordinary account sign-in never enters here. */
export default function DeploymentSetup() {
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState(
    new URLSearchParams(window.location.search).get("registration") ===
      "unconfirmed",
  );
  async function register() {
    setBusy(true);
    setFailed(false);
    try {
      const result = await connectionRequest("provision");
      const value = result.outcome as { action?: unknown; manifest?: unknown };
      if (typeof value?.action !== "string" || !value.manifest)
        throw new Error();
      const url = new URL(value.action);
      if (
        url.origin !== "https://github.com" ||
        url.pathname !== "/settings/apps/new" ||
        url.username ||
        url.password ||
        url.hash
      )
        throw new Error();
      const form = document.createElement("form");
      form.method = "post";
      form.action = url.href;
      const manifest = document.createElement("input");
      manifest.type = "hidden";
      manifest.name = "manifest";
      manifest.value = JSON.stringify(value.manifest);
      form.append(manifest);
      document.body.append(form);
      form.submit();
      form.remove();
    } catch {
      setFailed(true);
      setBusy(false);
    }
  }
  return (
    <main className="mx-auto max-w-lg p-8 space-y-6">
      <h1 className="text-xl font-semibold">Set up this installation</h1>
      <p>
        Register a private GitHub App for this local Laomedo installation.
        GitHub will ask you to confirm creation and choose which repositories it
        can read.
      </p>
      <p>
        Laomedo fills in the configuration and stores the credentials securely.
        No credentials need to be copied.
      </p>
      {failed && (
        <p role="alert">
          Setup could not be confirmed. Check your GitHub Apps before starting
          again; an App may already have been created.
        </p>
      )}
      <Button disabled={busy} onClick={() => void register()}>
        {busy ? "Opening GitHub…" : "Continue on GitHub"}
      </Button>
      <a className="block underline" href="/settings/github">
        Back to connections
      </a>
    </main>
  );
}
