/** Internal adapter controls. No provider, credentials or model turn is used. */
import {describe, it, expect, vi} from "vitest";
import type * as acp from "@agentclientprotocol/sdk";
import type {MessageConnection} from "vscode-jsonrpc/node";
import type {CodexAppServerClient} from "./CodexAppServerClient";
import {LaomedoExtension, probeParams, executorParams} from "./LaomedoExtension";
import {writeProviderCredential} from "./LaomedoLaunch";

vi.mock("./LaomedoLaunch", () => ({writeProviderCredential: vi.fn()}));

function setup() {
    let observe: (event: any) => void = () => {};
    const native = {onRequest: vi.fn(), sendRequest: vi.fn().mockResolvedValue({})};
    const host = {notify: vi.fn().mockResolvedValue(undefined), request: vi.fn().mockResolvedValue({success: true})};
    const terminate = vi.fn();
    const extension = new LaomedoExtension({onClientTransportEvent: (fn: any) => {observe = fn;}} as unknown as CodexAppServerClient,
        native as unknown as MessageConnection, host as unknown as acp.AgentContext, terminate);
    const request = {cwd: "/draft", mcpServers: [], _meta: {laomedo: {policy: "normal", model: "observed-model", effort: "low"}}} as acp.NewSessionRequest;
    return {extension, native, host, terminate, request, observe: (method: string, params: any) => observe({eventType:"notification", method, params})};
}

describe("Laomedo ACP policy", () => {
    it("updates only host-managed split credentials while no native prompt is active", async () => {
        const {extension, observe, host} = setup();
        const params = {accessToken: "fixture-renewed-access-token"};
        await expect(extension.refreshCredential(params)).rejects.toThrow();
        process.env["LAOMEDO_CODEX_REFRESHABLE_AUTH"] = "1";
        try {
            await extension.registerExecutor({environmentId:"e",execServerUrl:"ws://127.0.0.1:39871",authBearerToken:"x".repeat(32),connectTimeoutMs:15000});
            await expect(extension.refreshCredential(params)).resolves.toEqual({updated:true});
            expect(writeProviderCredential).toHaveBeenCalledWith(params.accessToken);
            await extension.prompt("root", async () => {
                await expect(extension.refreshCredential(params)).rejects.toThrow();
                observe("turn/completed", {threadId:"root",turn:{id:"t",status:"completed"}});
            });
            expect(host.notify).not.toHaveBeenCalledWith(expect.anything(), expect.objectContaining(params));
        } finally { delete process.env["LAOMEDO_CODEX_REFRESHABLE_AUTH"]; }
    });
    it("admits only explicit bound built-ins and preserves ordinary slash prompt handling", async () => {
        const {extension, request, terminate} = setup();
        extension.bind(request, "native-session");
        const ordinary = {sessionId:"native-session",prompt:[{type:"text",text:"/status"}]} as acp.PromptRequest;
        expect(extension.commandPrompt(ordinary)).toEqual([]);
        const command = {...ordinary,_meta:{laomedo:{nativeCommand:{name:"status",arguments:""}}}};
        expect(extension.commandPrompt(command)).toEqual(ordinary.prompt);
        await expect(extension.prompt("native-session", async () => ({stopReason:"end_turn"}), command)).resolves.toEqual({stopReason:"end_turn"});
        expect(terminate).not.toHaveBeenCalled();
        expect(() => extension.commandPrompt({...command,prompt:[{type:"text",text:"/logout"}]})).toThrow();
        expect(() => extension.commandPrompt({...command,_meta:{laomedo:{nativeCommand:{name:"logout",arguments:""}}}})).toThrow();
        expect(() => extension.commandPrompt({...command,_meta:{laomedo:{nativeCommand:{name:"review",arguments:"one\ntwo"}}}})).toThrow();
    });
    it("accepts matched compaction evidence only for an explicit compact command", async () => {
        for (const explicit of [false, true]) {
            const {extension, request, observe, terminate} = setup();
            extension.bind(request, "root");
            const command = {sessionId:"root",prompt:[{type:"text",text:"/compact"}],_meta:{laomedo:{nativeCommand:{name:"compact",arguments:""}}}} as acp.PromptRequest;
            const pending = extension.prompt("root", async () => {
                observe("turn/started", {threadId:"root",turn:{id:"t"}});
                observe("item/started", {threadId:"root",turnId:"t",item:{type:"contextCompaction",id:"i"}});
                observe("item/completed", {threadId:"root",turnId:"t",item:{type:"contextCompaction",id:"i"}});
                return {stopReason:"end_turn"};
            }, explicit ? command : undefined);
            if (explicit) { await expect(pending).resolves.toEqual({stopReason:"end_turn"}); expect(terminate).not.toHaveBeenCalled(); }
            else { await expect(pending).rejects.toThrow(); expect(terminate).toHaveBeenCalled(); }
        }
    });
    it("refuses compaction items with a mismatched identity", async () => {
        const {extension, request, observe} = setup(); extension.bind(request,"root");
        const command = {sessionId:"root",prompt:[{type:"text",text:"/compact"}],_meta:{laomedo:{nativeCommand:{name:"compact",arguments:""}}}} as acp.PromptRequest;
        await expect(extension.prompt("root",async () => {
            observe("turn/started",{threadId:"root",turn:{id:"t"}});
            observe("item/started",{threadId:"root",turnId:"t",item:{type:"contextCompaction",id:"i"}});
            observe("item/completed",{threadId:"root",turnId:"t",item:{type:"contextCompaction",id:"other"}});
        },command)).rejects.toThrow();
    });
    it("admits only scoped external HTTP MCP endpoints with exact tool grants", () => {
        const {extension, request} = setup();
        const external = {
            type: "http" as const, name: "external",
            url: "http://host.docker.internal:12345/11111111-1111-4111-8111-111111111111/mcp",
            headers: [{name: "Authorization", value: "Bearer " + "x".repeat(43)}],
        };
        const externalTools = ["external_" + "a".repeat(32)];
        const configured = {...request, mcpServers: [external],
            _meta: {laomedo: {...request._meta!["laomedo"] as object, externalTools}}};
        expect(extension.sessionParameters(configured).approvalPolicy).toBe("never");
        expect(extension.mcpToolNames(configured)).toEqual(externalTools);
        expect(extension.mcpToolOptions(externalTools)).toEqual({enabled_tools: externalTools, tools: {[externalTools[0]!]: {approval_mode: "approve"}}});
        expect(extension.mcpToolOptions([])).toEqual({enabled_tools: [], tools: {}});
        expect(() => extension.mcpToolOptions(["unselected-shell"])).toThrow();
        expect(() => extension.sessionParameters({...configured,
            mcpServers: [{...external, url: "https://upstream.example/mcp"}]})).toThrow();
        expect(() => extension.sessionParameters({...configured,
            mcpServers: [{...external, name: "laomedo"}]})).toThrow();
        expect(() => extension.sessionParameters({...configured, mcpServers: []})).toThrow();
        expect(() => extension.sessionParameters({...request, mcpServers: [external]})).toThrow();
    });
    it("advertises the versioned raw-event and host-policy contract", () => {
        expect(LaomedoExtension.capabilities).toEqual({version: 1, rawEvents: true, hostPolicy: true, nativeCommands: 1, credentialRefresh: 1, bundledSkills: 1});
    });
    it("inherits the normal permission profile without agent-mode overrides", () => {
        const {extension, request} = setup();
        const params = extension.sessionParameters(request);
        extension.bind(request, "native-session");
        expect(params.approvalPolicy).toBe("never");
        const turn = extension.turnParameters({sessionId:"native-session", prompt:[]});
        expect(turn).toEqual({input:[]});
        extension.assertSelection("native-session", "observed-model", "low");
        expect(() => extension.assertSelection("native-session", "other", "low")).toThrow();
    });

    it("rejects missing/unknown policy, unregistered split selection and arbitrary commands", () => {
        const {extension, request} = setup();
        expect(() => extension.sessionParameters({...request, _meta:{}})).toThrow();
        expect(() => extension.sessionParameters({...request, _meta:{laomedo:{policy:"agent-full-access"}}})).toThrow();
        expect(() => extension.sessionParameters({...request, _meta:{laomedo:{policy:"split",model:"m",effort:"low",environmentId:"unregistered"}}})).toThrow();
        expect(() => probeParams.parse({check:"auth_read", command:["cat", "/anything"]})).toThrow();
        expect(() => executorParams.parse({environmentId:"e",execServerUrl:"ws://remote:39871",authBearerToken:"x".repeat(32),connectTimeoutMs:15000})).toThrow();
    });

    it("preserves native completion before returning and excludes unrelated child completion", async () => {
        const {extension, host, observe, terminate} = setup();
        let release: () => void = () => {};
        host.notify.mockImplementationOnce(() => new Promise<void>(resolve => {release = resolve;}));
        let returned = false;
        const pending = extension.prompt("root", async () => {
            observe("turn/completed", {threadId:"root", turn:{id:"turn",status:"completed"}});
            return "result";
        }).then(value => {returned = true; return value;});
        await Promise.resolve(); await Promise.resolve();
        expect(returned).toBe(false);
        release();
        expect(await pending).toBe("result");
        expect(terminate).not.toHaveBeenCalled();
        await expect(extension.prompt("root", async () => {
            observe("turn/completed", {threadId:"child",turn:{id:"child-turn",status:"completed"}});
        })).rejects.toThrow();
        expect(terminate).toHaveBeenCalled();
    });

    it("never forwards account/auth/config or executor capability records", async () => {
        const {extension, host, observe} = setup();
        for (const method of ["account/updated", "config/updated", "environment/status"]) {
            observe(method, {private:"never forward"});
        }
        await expect(extension.prompt("root", async () => {})).rejects.toThrow();
        expect(host.notify).not.toHaveBeenCalled();
    });

    it("closes registration and preflight once a prompt starts", async () => {
        const {extension} = setup();
        await expect(extension.prompt("root", async () => {})).rejects.toThrow();
        await expect(extension.preflight({check:"workspace_write"})).rejects.toThrow();
        await expect(extension.registerExecutor({environmentId:"e",execServerUrl:"ws://127.0.0.1:39871",authBearerToken:"x".repeat(32),connectTimeoutMs:15000})).rejects.toThrow();
    });
});


describe("zero-turn account quota boundary", () => {
    it("sends only the named empty request and refuses discovery after session binding", async () => {
        const {extension, native, request} = setup();
        await extension.rateLimits();
        expect(native.sendRequest).toHaveBeenCalledExactlyOnceWith("account/rateLimits/read", {});
        extension.bind(request, "native-session");
        await expect(extension.rateLimits()).rejects.toThrow();
        expect(native.sendRequest).toHaveBeenCalledTimes(1);
    });
});
