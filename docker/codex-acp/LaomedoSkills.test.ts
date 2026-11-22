/** Manifest/provenance admission tests; no CLI, profile or model is used. */
import {beforeEach, expect, it, vi} from "vitest";
import {createHash} from "node:crypto";
import {lstatSync, readFileSync, readdirSync} from "node:fs";
import type * as acp from "@agentclientprotocol/sdk";
import type {MessageConnection} from "vscode-jsonrpc/node";
import type {CodexAppServerClient} from "./CodexAppServerClient";
import {LaomedoExtension} from "./LaomedoExtension";

vi.mock("node:fs", () => ({lstatSync: vi.fn(), readFileSync: vi.fn(), readdirSync: vi.fn()}));

beforeEach(() => {
    vi.mocked(readFileSync).mockReset();
    vi.mocked(lstatSync).mockReset();
    vi.mocked(readdirSync).mockReset();
});

function setup() {
    const body = "Bundled instructions";
    const hash = createHash("sha256").update(body).digest("hex");
    vi.mocked(readFileSync).mockImplementation((path: any) => (String(path).endsWith("system-skills.json")
        ? JSON.stringify({"skill-creator": {"SKILL.md": hash}}) : Buffer.from(body)) as any);
    vi.mocked(readdirSync).mockReturnValue(["SKILL.md"] as any);
    vi.mocked(lstatSync).mockImplementation((path: any) => ({isSymbolicLink: () => false,
        isDirectory: () => !String(path).endsWith("SKILL.md"), isFile: () => String(path).endsWith("SKILL.md")}) as any);
    let observe: (event: any) => void = () => {};
    const skill = {name: "skill-creator", scope: "system", enabled: true, path: "/home/runner/.codex/skills/.system/skill-creator/SKILL.md"};
    const app = {listSkills: vi.fn().mockResolvedValue({data: [{cwd: "/draft", skills: [skill], errors: []}]}), onClientTransportEvent: (fn: any) => {observe = fn;}};
    const host = {notify: vi.fn().mockResolvedValue(undefined)};
    const extension = new LaomedoExtension(app as unknown as CodexAppServerClient, {onRequest: vi.fn()} as unknown as MessageConnection, host as unknown as acp.AgentContext, vi.fn());
    extension.bind({cwd: "/draft", mcpServers: [], _meta: {laomedo: {policy: "normal", model: "m", effort: "low"}}} as acp.NewSessionRequest, "thread");
    const request = {sessionId: "thread", prompt: [{type: "text", text: "$skill-creator Explain"}], _meta: {laomedo: {nativeCommand: {name: "$skill-creator", arguments: "Explain"}}}} as acp.PromptRequest;
    return {extension, app, request, skill, complete: () => observe({eventType: "notification", method: "turn/completed", params: {threadId: "thread", turn: {id: "t", status: "completed"}}})};
}

it("injects the verified native system skill only into its explicitly admitted turn", async () => {
    const {extension, request, complete} = setup();
    expect(() => extension.turnParameters(request)).toThrow();
    await extension.prompt("thread", async () => {
        expect(extension.turnParameters(request).input).toEqual([{type: "skill", name: "skill-creator", path: "/home/runner/.codex/skills/.system/skill-creator/SKILL.md"}]);
        expect(extension.turnParameters({...request, _meta: {laomedo: {}}}).input).toEqual([]);
        complete();
    }, request);
    expect(() => extension.turnParameters(request)).toThrow();
});

it("refuses a changed bundled body before running the native turn", async () => {
    const {extension, request} = setup();
    const original = vi.mocked(readFileSync).getMockImplementation()!;
    vi.mocked(readFileSync).mockImplementation(((path: any, ...args: any[]) => String(path).endsWith("SKILL.md") ? Buffer.from("Changed") : (original as any)(path, ...args)) as any);
    const run = vi.fn();
    await expect(extension.prompt("thread", run, request)).rejects.toMatchObject({data: "Bundled skill content changed"});
    expect(run).not.toHaveBeenCalled();
});

it.each(["user", "duplicate"])("refuses %s provenance before reading or dispatching a skill", async reason => {
    const {extension, app, request, skill} = setup();
    app.listSkills.mockResolvedValue({data: [{cwd: "/draft", skills: reason === "user" ? [{...skill, scope: "user"}] : [skill, skill], errors: []}]});
    const run = vi.fn();
    await expect(extension.prompt("thread", run, request)).rejects.toMatchObject({data: "Bundled skill source changed"});
    expect(readFileSync).not.toHaveBeenCalled();
    expect(run).not.toHaveBeenCalled();
});
