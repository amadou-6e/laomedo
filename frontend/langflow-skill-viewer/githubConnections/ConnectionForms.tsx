import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

export default function ConnectionForms({
  mode,
  busy,
  submit,
  close,
}: {
  mode: "setup" | "token";
  busy: boolean;
  submit: (value: Record<string, unknown>) => void;
  close: () => void;
}) {
  return (
    <form
      className="grid max-w-xl gap-4"
      onSubmit={(event) => {
        event.preventDefault();
        const form = event.currentTarget;
        const values = Object.fromEntries(new FormData(form).entries());
        // Clear credential DOM synchronously, before any awaited admission/network work.
        form.reset();
        submit(values);
      }}
    >
      <h2 className="text-lg font-semibold">
        {mode === "setup" ? "GitHub App setup" : "Use a token"}
      </h2>
      {mode === "setup" ? (
        <>
          <p>
            First, register a GitHub App with Contents read-only access and expiring
            user tokens. Use the callback URL below. Then enter its credentials here.
          </p>
          <a
            className="text-primary underline underline-offset-4"
            href="https://github.com/settings/apps/new"
            target="_blank"
            rel="noreferrer"
          >
            1. Register an App on GitHub
          </a>
          <label>
            2. Client ID
            <Input
              name="client_id"
              required
              autoComplete="off"
              maxLength={128}
              disabled={busy}
            />
          </label>
          <label>
            3. App slug
            <Input
              name="slug"
              required
              autoComplete="off"
              maxLength={100}
              disabled={busy}
            />
          </label>
          <label>
            4. Client secret
            <Input
              name="secret"
              type="password"
              required
              autoComplete="new-password"
              maxLength={4096}
              disabled={busy}
            />
          </label>
        </>
      ) : (
        <>
          <p>
            Enter a fine-grained personal access token deliberately. Laomedo
            uses source reads only; the token may have additional permissions on
            GitHub.
          </p>
          <label>
            Fine-grained token
            <Input
              name="token"
              type="password"
              required
              autoComplete="new-password"
              maxLength={4096}
              disabled={busy}
            />
          </label>
        </>
      )}
      <div className="flex gap-2">
        <Button type="submit" disabled={busy}>
          {mode === "setup" ? "Save app credentials" : "Verify token"}
        </Button>
        <Button
          type="button"
          variant="outline"
          disabled={busy}
          onClick={(event) => {
            event.currentTarget.form?.reset();
            close();
          }}
        >
          Cancel
        </Button>
      </div>
    </form>
  );
}
