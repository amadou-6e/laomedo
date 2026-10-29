/** Bounded host features absent from ACP v1; never a native RPC tunnel. */
import * as acp from "@agentclientprotocol/sdk";
import {z} from "zod";
import type {MessageConnection} from "vscode-jsonrpc/node";
import type {CodexAppServerClient} from "./CodexAppServerClient";

const sessionPolicy = z.object({
    policy: z.enum(["normal", "split"]),
    model: z.string().min(1).max(200),
    effort: z.string().min(1).max(40),
    environmentId: z.string().min(1).max(200).optional(),
    dynamicTools: z.array(z.object({
        type: z.literal("function"),
        name: z.literal("laomedo_output_precheck"),
        description: z.string().max(65536),
        inputSchema: z.record(z.string(), z.unknown()),
    }).strict()).max(1).default([]),
}).strict();

const promptPolicy = z.object({
    skills: z.array(z.object({
        type: z.literal("skill"),
        name: z.string().regex(/^[A-Za-z0-9_-]+$/),
        path: z.string().regex(/^\/draft\/\.agents\/skills\/[A-Za-z0-9_-]+\/SKILL\.md$/),
    }).strict()).max(64).default([]),
}).strict();

export const emptyParams = z.object({}).strict();
export const modelParams = z.object({cursor: z.string().nullable().optional()}).strict();
export const probeParams = z.object({
    check: z.enum(["workspace_write", "canonical_write", "store_write", "auth_read", "git_binary", "network"]),
}).strict();
export const executorParams = z.object({
    environmentId: z.string().min(1).max(200),
    execServerUrl: z.literal("ws://127.0.0.1:39871"),
    authBearerToken: z.string().min(32).max(512),
    connectTimeoutMs: z.literal(15000),
}).strict();
export const statusParams = executorParams.pick({environmentId: true});

export class LaomedoExtension {
    static readonly capabilities = {version: 1, rawEvents: true, hostPolicy: true};
    private sessions = new Map<string, z.infer<typeof sessionPolicy>>();
    private rawQueue: Promise<void> = Promise.resolve();
    private rawFailed = false;
    private prompted = false;
    private executorId?: string;
    private completed = new Map<string, number>();

    constructor(
        private app: CodexAppServerClient,
        private native: MessageConnection,
        private host: Pick<acp.AgentContext, "notify" | "request">,
        private terminate: () => void,
    ) {
        app.onClientTransportEvent((event) => {
            if (event.eventType !== "notification") return;
            const {method, params} = event;
            if (!(method === "thread/started" || method === "thread/tokenUsage/updated"
                || method === "turn/started" || method === "turn/completed"
                || method === "error"
                || method.startsWith("item/") || method.startsWith("turn/plan/")
                || method.startsWith("turn/diff/"))) return;
            this.rawQueue = this.rawQueue.then(async () => {
                await host.notify("_laomedo/codexEvent", {method, params});
                if (method === "turn/completed") {
                    const threadId = (params as {threadId: string}).threadId;
                    this.completed.set(threadId, (this.completed.get(threadId) ?? 0) + 1);
                }
            }).catch(() => {
                this.rawFailed = true;
                terminate();
            });
        });
        native.onRequest("item/tool/call", async (params: any) => {
            const policy = this.sessions.get(params.threadId);
            if (params.tool !== "laomedo_output_precheck" || params.namespace != null
                || !policy?.dynamicTools.length) {
                throw acp.RequestError.methodNotFound("item/tool/call");
            }
            // Host is pure contract validation. No filesystem/terminal delegation.
            return host.request("_laomedo/outputPrecheck", params);
        });
    }

    sessionParameters(request: acp.NewSessionRequest | acp.LoadSessionRequest) {
        const policy = sessionPolicy.parse(request._meta?.["laomedo"]);
        if (request.cwd !== "/draft" || request.mcpServers.length) {
            throw acp.RequestError.invalidParams("Invalid Laomedo session scope");
        }
        if ((policy.policy === "split") !== Boolean(policy.environmentId)
            || (policy.environmentId && policy.environmentId !== this.executorId)) {
            throw acp.RequestError.invalidParams("Executor selection mismatch");
        }
        return {
            model: policy.model,
            approvalPolicy: "never" as const,
            ...(policy.dynamicTools.length ? {dynamicTools: policy.dynamicTools} : {}),
            ...(policy.environmentId ? {environments: [{environmentId: policy.environmentId, cwd: "/draft"}]} : {}),
        };
    }

    bind(request: acp.NewSessionRequest | acp.LoadSessionRequest, sessionId: string) {
        this.sessions.set(sessionId, sessionPolicy.parse(request._meta?.["laomedo"]));
    }

    turnParameters(request: acp.PromptRequest) {
        const policy = this.sessions.get(request.sessionId);
        if (!policy) throw acp.RequestError.invalidParams("Unbound Laomedo session");
        const input = promptPolicy.parse(request._meta?.["laomedo"] ?? {});
        if (input.skills.some(skill => skill.path !== `/draft/.agents/skills/${skill.name}/SKILL.md`)) {
            throw acp.RequestError.invalidParams("Pinned skill path mismatch");
        }
        return {
            input: input.skills,
            ...(policy.policy === "split" ? {
                sandboxPolicy: {type: "externalSandbox" as const, networkAccess: "restricted" as const},
                environments: [{environmentId: policy.environmentId, cwd: "/draft", runtimeWorkspaceRoots: ["/draft"]}],
            } : {}),
        };
    }

    assertSelection(sessionId: string, model: string, effort: string | null) {
        const policy = this.sessions.get(sessionId);
        if (!policy || policy.model !== model || policy.effort !== effort) {
            throw acp.RequestError.invalidParams(undefined, "Host model/effort selection mismatch");
        }
    }

    async prompt<T>(sessionId: string, run: () => Promise<T>): Promise<T> {
        this.prompted = true;
        const before = this.completed.get(sessionId) ?? 0;
        try {
            return await run();
        } finally {
            // The response cannot overtake native terminal evidence on stdio.
            await this.rawQueue;
            if (this.rawFailed || (this.completed.get(sessionId) ?? 0) === before) {
                this.terminate();
                throw acp.RequestError.internalError("Native completion evidence unavailable");
            }
        }
    }

    async models(params: z.infer<typeof modelParams>) {
        return this.app.listModels({cursor: params.cursor ?? null});
    }

    async skills() {
        if (this.prompted) throw acp.RequestError.invalidParams("Discovery already closed");
        return this.app.listSkills({cwds: ["/draft"], forceReload: true});
    }

    async preflight(params: z.infer<typeof probeParams>) {
        if (this.sessions.size || this.prompted) throw acp.RequestError.invalidParams("Preflight already closed");
        const commands = {
            workspace_write: ["sh", "-c", "printf CANARY > /draft/canary.txt"],
            canonical_write: ["sh", "-c", "printf FORBIDDEN > /canonical/sentinel.txt"],
            store_write: ["sh", "-c", "printf FORBIDDEN > /store/sentinel.txt"],
            auth_read: ["sh", "-c", "cat /home/runner/.codex/auth.json >/dev/null"],
            git_binary: ["git", "--version"],
            network: ["python3", "-c", "import socket; s=socket.socket(); s.settimeout(3); s.connect(('1.1.1.1',443)); print('NETWORK_CONNECTED')"],
        };
        return this.native.sendRequest("command/exec", {
            command: commands[params.check], cwd: "/draft", timeoutMs: 15000,
        });
    }

    async registerExecutor(params: z.infer<typeof executorParams>) {
        if (this.prompted || this.executorId || this.sessions.size) {
            throw acp.RequestError.invalidParams("Executor registration already closed");
        }
        const result = await this.native.sendRequest("environment/add", params);
        this.executorId = params.environmentId;
        return result;
    }

    async executorStatus(params: z.infer<typeof statusParams>) {
        if (this.prompted || params.environmentId !== this.executorId) {
            throw acp.RequestError.invalidParams("Executor selection mismatch");
        }
        return this.native.sendRequest("environment/status", params);
    }
}
