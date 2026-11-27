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

function setup(name = "skill-creator") {
    const body = "Bundled instructions";
    const hash = createHash("sha256").update(body).digest("hex");
    vi.mocked(readFileSync).mockImplementation((path: any) => (String(path).endsWith("system-skills.json")
        ? JSON.stringify({[name]: {"SKILL.md": hash}}) : Buffer.from(body)) as any);
    vi.mocked(readdirSync).mockReturnValue(["SKILL.md"] as any);
    vi.mocked(lstatSync).mockImplementation((path: any) => ({isSymbolicLink: () => false,
        isDirectory: () => !String(path).endsWith("SKILL.md"), isFile: () => String(path).endsWith("SKILL.md")}) as any);
    let observe: (event: any) => void = () => {};
    const skill = {name, scope: "system", enabled: true, path: `/home/runner/.codex/skills/.system/${name}/SKILL.md`};
    const app = {listSkills: vi.fn().mockResolvedValue({data: [{cwd: "/draft", skills: [skill], errors: []}]}), onClientTransportEvent: (fn: any) => {observe = fn;}};
    const host = {notify: vi.fn().mockResolvedValue(undefined)};
    const extension = new LaomedoExtension(app as unknown as CodexAppServerClient, {onRequest: vi.fn()} as unknown as MessageConnection, host as unknown as acp.AgentContext, vi.fn());
    extension.bind({cwd: "/draft", mcpServers: [], _meta: {laomedo: {policy: "normal", model: "m", effort: "low"}}} as acp.NewSessionRequest, "thread");
    const request = {sessionId: "thread", prompt: [{type: "text", text: `$${name} Explain`}], _meta: {laomedo: {nativeCommand: {name: `$${name}`, arguments: "Explain", invocationId: "00000000-0000-4000-8000-000000000001"}}}} as acp.PromptRequest;
    return {extension, app, host, request, skill,
        start: () => observe({eventType: "notification", method: "turn/started", params: {threadId: "thread", turn: {id: "t"}}}),
        complete: () => observe({eventType: "notification", method: "turn/completed", params: {threadId: "thread", turn: {id: "t", status: "completed"}}})};
}

it.each(["skill-creator"])("injects verified %s only into its explicitly admitted turn", async name => {
    const {extension, host, request, start, complete} = setup(name);
    expect(() => extension.turnParameters(request)).toThrow();
    await extension.prompt("thread", async () => {
        expect(extension.turnParameters(request).input).toEqual([{type: "skill", name, path: `/home/runner/.codex/skills/.system/${name}/SKILL.md`}]);
        expect(extension.turnParameters({...request, _meta: {laomedo: {}}}).input).toEqual([]);
        start(); complete();
    }, request);
    expect(host.notify).toHaveBeenCalledWith("_laomedo/codexEvent", expect.objectContaining({method: "laomedo/skillInput", params: expect.objectContaining({threadId: "thread", turnId: "t", invocationId: "00000000-0000-4000-8000-000000000001", origin: "laomedo_adapter"})}));
    expect(() => extension.turnParameters(request)).toThrow();
});

it("refuses a bundled skill whose native search requirement is unavailable", async () => {
    const {extension, request} = setup("openai-docs");
    const run = vi.fn();
    await expect(extension.prompt("thread", run, request)).rejects.toThrow();
    expect(run).not.toHaveBeenCalled();
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

it("refuses native text and linked skill mentions outside an explicitly admitted skill", () => {
    const {extension, request} = setup();
    for (const text of ["Explain $skill-creator", "Use $imagegen", "[$other](skill:///home/runner/.codex/skills/.system/skill-installer/SKILL.md)"]) {
        expect(() => extension.commandPrompt({...request, prompt: [{type: "text", text}], _meta: {laomedo: {}}})).toThrow();
    }
    expect(extension.commandPrompt({...request, prompt: [{type: "text", text: "$20 a month"}], _meta: {laomedo: {}}})).toEqual([]);
    expect(() => extension.commandPrompt({...request, prompt: [{type: "text", text: "$skill-creator Use $imagegen"}], _meta: {laomedo: {nativeCommand: {name: "$skill-creator", arguments: "Use $imagegen"}}}})).toThrow();
});
