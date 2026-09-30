// Structural import check. Build AGENTVIZ src/lib/parseSession.ts with esbuild
// and pass the bundle plus a private synthetic rollout; never print raw text.
import { readFileSync } from "node:fs";
import { pathToFileURL } from "node:url";

const [bundlePath, rolloutPath] = process.argv.slice(2);
if (!bundlePath || !rolloutPath) {
  process.stderr.write("usage: node probe_agentviz_import.mjs <parser-bundle.mjs> <private-rollout.jsonl>\n");
  process.exit(2);
}
const { detectFormat, parseSession } = await import(pathToFileURL(bundlePath).href);
const raw = readFileSync(rolloutPath, "utf8");
const format = detectFormat(raw);
const parsed = parseSession(raw);
if (!parsed || format !== "codex") {
  process.stderr.write("private rollout did not parse as Codex\n");
  process.exit(1);
}
const toolCalls = parsed.events.filter(event => event.track === "tool_call");
const summary = {
  parser_format: parsed.metadata.format,
  native_session_id: parsed.metadata.sessionId,
  normalized_event_count: parsed.events.length,
  normalized_turn_count: parsed.turns.length,
  tool_call_count: toolCalls.length,
  tool_call_id_count: toolCalls.filter(event => typeof event.toolCallId === "string" && event.toolCallId.length > 0).length,
  attached_tool_output_count: toolCalls.filter(event => typeof event.toolOutput === "string" && event.toolOutput.length > 0).length,
  original_payload_id_count: parsed.events.filter(event => typeof event.raw?.payload?.id === "string").length,
  native_turn_ids: [...new Set(parsed.events.map(event => event.codexTurnId).filter(Boolean))],
  parse_issues: parsed.metadata.parseIssues,
};
process.stdout.write(JSON.stringify(summary) + "\n");
