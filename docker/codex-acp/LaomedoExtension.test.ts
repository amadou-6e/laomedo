/** Internal adapter controls. No provider, credentials or model turn is used. */
import {describe, it, expect, vi} from "vitest";
import type * as acp from "@agentclientprotocol/sdk";
import type {MessageConnection} from "vscode-jsonrpc/node";
import type {CodexAppServerClient} from "./CodexAppServerClient";
import {LaomedoExtension, probeParams, executorParams} from "./LaomedoExtension";

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
    it("advertises the versioned raw-event and host-policy contract", () => {
        expect(LaomedoExtension.capabilities).toEqual({version: 1, rawEvents: true, hostPolicy: true});
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
