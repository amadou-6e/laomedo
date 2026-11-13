# Activity "starting" state and OpenCode experiment preparation

**Bottom line:** I found no blockers in the production change or the experiment helper. The production code and docs are APPROVE. The experiment helper is APPROVE for experiment-only use. The visual verdict covers only the earlier "Waiting for turn" wording: the new lowercase "starting" has not been checked on screen.

## Production: base ae56d802 → head 6c3f9c83

I read all of `activity-starting.diff` and `conversationRows` in `utils.ts:113-128`.

**How the state is decided**
- `conversationRows` sets `lane=null` whenever a thread has no observed turns. Its own `unknown` status applies only when there are no turns at all.
- The renderer now shows `waiting` only when three things hold at once:
  - the lane is null;
  - the row is the main (root) thread;
  - `run.status === "running"`.
- Every other case is unchanged:
  - an observed lane keeps its status (`running`, `incomplete` or `completed`);
  - a sub-thread with no data stays `unknown`;
  - a finished run with zero turns still shows `unknown` with the error style, which is pre-existing behaviour.
- `waiting` is an internal value that never reaches the API. On screen it reads "starting" with the same neutral `secondaryStatic` style as "running", so it can't be mistaken for a failure.
- The row's accessible label also says "starting" in this state; otherwise it keeps the run status.
- Before the native thread exists, a loaded detail for a running run shows "starting" instead of "No captured turns". Finished runs still show "No captured turns".

**Test and README**
- The test steps through starting → running → failed with real polling. It checks that "unknown" and "starting" are absent in the right states and that a genuine failure is still labelled "failed".
- The README matches the behaviour.

**Optional, not a defect:** the internal value is still named `waiting` while the screen says "starting". Renaming it would make the code easier to follow.

## Experiment preparation (exp 654ea727 → 870b8512, experiment-only)

I read all of `opencode-preparation.diff`.

**What the helper reads**
- It opens the host Console database read-only, through an SQLite `mode=ro` URI.
- It selects only `access_token`, `token_expiry`, `url` and `active_org_id`, never a refresh token.

**What it checks before using the token**
- The token is not a placeholder: redacted values, `***`, the canary prefix and `{…}` are all refused.
- The token has more than 60 seconds left before it expires.
- The account URL is HTTPS on host `opencode.ai`, with no user, password, query or fragment, and a `/console` path.

**How it sends the token**
- The token is sent only to `<validated url>/api/config`.
- Redirects are refused through the current `laomedo.host.http.NoRedirect`.

**What it accepts back**
- The configuration must have the expected organisation header, Go endpoint and npm SDK.
- Only allow-listed SDKs and `opencode.ai/inference/go/` endpoints are kept, and model names are pattern-checked.
- `supported_config` first drops unsupported routes, and `console_provider` validates again afterwards.

**What it writes and exposes**
- Writes are limited to a profile directory that `prepare_private_directory` restricts with ACLs. The files are the access key, its validity record with a SHA-256 fingerprint rather than the token, and the routing.
- Nothing is printed. Error codes carry no secret values.
- `validation_server.py` prepares the profile only on a fresh launch (`not previous`). It passes the profile explicitly to `OpenCodeAgentRuntime` and sets only the runner-token path variable.
- Production does not import this helper, and none of the retired production modules are restored.

**Uncertainties (low; none is a blocker):**
- **E-1:** the helper sends `User-Agent: opencode/1.18.33`, presenting itself as the native client. That is acceptable for this bounded experiment, but should not be copied into production.
- **E-2:** the profile is kept until the end of the session, so the access key sits on disk until then. Make sure it is actually deleted when the session ends; I did not verify cleanup.
- **E-3:** in `provider_key` mode the written key comes from the remote configuration and has no recorded expiry. This experiment does not cover that branch, and the live run used Console-token mode as you described.
- **E-4:** the error codes raised here (`opencode_console_origin_not_allowed` and others) were removed from the production catalogue earlier. That is correct, since these are experiment-only failures that never reach a node.

## Images inspected

1. **`opencode-waiting-redacted.png`**, during the real live wait:
   - the row reads "Laomedo OpenCode Agent · 0 turns" with a small grey neutral badge reading "Waiting for turn", which is the old wording;
   - there is no red unknown badge, and the footer appears below;
   - the side-navigation icons were still loading.
2. **`opencode-complete-redacted.png`**, the same run after completion:
   - OpenTelemetry shows "0 of 0 records", followed by Conversation with "2 of 2";
   - there is a "You 02:56:00 PM" row and an "OpenCode 02:56:00 PM · 1.5s" reply, both masked;
   - the footer appears below, and the spacing is consistent.

**Visual gaps that remain:**
- Neither image shows the new "starting" text, the badge's width with that word, or the "starting" fallback text before the native thread exists.
- No fresh integrated screenshot exists, because the shared tab is currently hidden.
- The masks prevent any review of message content.
- The images are standalone renders, not the owner's browser.

## Verdicts

- **Production code and docs (ae56d802 → 6c3f9c83):** APPROVE. The new build was still running when you sent this; the earlier build passed.
- **Experiment code (654ea727 → 870b8512):** APPROVE for experiment-only use, with E-1 to E-3 noted. This is not a production login or provisioning feature.
- **Visual:** APPROVE only for the neutral styling of the waiting state and the completed layout, using the old wording. The exact "starting" copy has not been visually accepted; that needs a fresh screenshot from the revealed tab.
- **Relied on your statements:** the 36 tests, CI, and the live OpenCode fresh/resume run and its identities.
- **Not covered:** cancellation and recovery, and the accuracy of the zero cost reported by the native catalogue.
- **Separate:** footer licensing L-01, which is still unselected.
- **Not authorized:** merge or issue closure.