/** Bounded host features absent from ACP v1; never a native RPC tunnel. */
import * as acp from "@agentclientprotocol/sdk";
import {z} from "zod";
import type {MessageConnection} from "vscode-jsonrpc/node";
import type {CodexAppServerClient} from "./CodexAppServerClient";
import {writeProviderCredential} from "./LaomedoLaunch";
import {createHash} from "node:crypto";
import {lstatSync, readFileSync, readdirSync} from "node:fs";
import {join} from "node:path";

const sessionPolicy = z.object({
    policy: z.enum(["normal", "split"]),
    model: z.string().min(1).max(200),
    effort: z.string().min(1).max(40),
    environmentId: z.string().min(1).max(200).optional(),
    externalTools: z.array(z.string().regex(/^external_[0-9a-f]{32}$/)).max(128).default([]),
    dynamicTools: z.array(z.object({
        type: z.literal("function"),
        name: z.literal("laomedo_output_precheck"),
        description: z.string().max(65536),
        inputSchema: z.record(z.string(), z.unknown()),
    }).strict()).max(1).default([]),
}).strict();

const promptPolicy = z.object({
    nativeCommand: z.object({
        name: z.enum(["status", "mcp", "skills", "review", "compact", "$skill-creator"]),
        arguments: z.string().max(4000),
        invocationId: z.string().uuid().optional(),
    }).strict().optional(),
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
export const credentialParams = z.object({accessToken: z.string().regex(/^[A-Za-z0-9._~+/=-]{16,32768}$/)}).strict();

export class LaomedoExtension {
    static readonly capabilities = {version: 1, rawEvents: true, hostPolicy: true, nativeCommands: 1, credentialRefresh: 1, bundledSkills: 1};
    private sessions = new Map<string, z.infer<typeof sessionPolicy>>();
    private rawQueue: Promise<void> = Promise.resolve();
    private rawFailed = false;
    private prompted = false;
    private prompting = false;
    private admittedSkill: {type: "skill"; name: string; path: string; manifestSha256: string} | undefined;
    private skillInputPrepared: {sessionId: string; invocationId: string; name: string; path: string; manifestSha256: string} | undefined;
    private executorId?: string;
    private completed = new Map<string, number>();
    private compactSession: string | undefined;
    private compactEvents: Array<{method: string; params: any}> = [];

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
                if (method === "turn/started" && this.skillInputPrepared) {
                    const turn = params as {threadId?: string; turn?: {id?: string}};
                    const prepared = this.skillInputPrepared;
                    if (turn.threadId === prepared.sessionId && typeof turn.turn?.id === "string") {
                        this.skillInputPrepared = undefined;
                        await host.notify("_laomedo/codexEvent", {
                            method: "laomedo/skillInput",
                            params: {threadId: prepared.sessionId, turnId: turn.turn.id,
                                invocationId: prepared.invocationId, name: prepared.name,
                                path: prepared.path, manifestSha256: prepared.manifestSha256,
                                origin: "laomedo_adapter", phase: "native_turn_accepted"},
                        });
                    }
                }
                if (this.compactSession && (params as {threadId?: string}).threadId === this.compactSession
                    && ["turn/started", "turn/completed", "item/started", "item/completed", "error"].includes(method)) {
                    const item = (params as any).item;
                    if (!method.startsWith("item/") || item?.type === "contextCompaction") {
                        if (this.compactEvents.length >= 32) throw new Error("Compaction evidence overflow");
                        this.compactEvents.push({method, params});
                    }
                }
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

    async refreshCredential(params: z.infer<typeof credentialParams>) {
        if (process.env["LAOMEDO_CODEX_REFRESHABLE_AUTH"] !== "1" || !this.executorId || this.prompting) {
            throw acp.RequestError.invalidParams("Managed provider credential unavailable");
        }
        writeProviderCredential(credentialParams.parse(params).accessToken);
        // Pinned native command-backed auth caches for 1 ms. Wait out that cache
        // before acknowledging, so the next request resolves the new bearer.
        await new Promise(resolve => setTimeout(resolve, 2));
        return {updated: true};
    }

    sessionParameters(request: acp.NewSessionRequest | acp.LoadSessionRequest) {
        const policy = sessionPolicy.parse(request._meta?.["laomedo"]);
        if (request.cwd !== "/draft" || request.mcpServers.length > 1) {
            throw acp.RequestError.invalidParams("Invalid Laomedo session scope");
        }
        if (Boolean(request.mcpServers.length) !== Boolean(policy.externalTools.length)
            || new Set(policy.externalTools).size !== policy.externalTools.length) {
            throw acp.RequestError.invalidParams("External MCP grant mismatch");
        }
        for (const server of request.mcpServers) {
            if (!("type" in server) || server.type !== "http" || server.name !== "external") {
                throw acp.RequestError.invalidParams("External MCP endpoint required");
            }
            const url = new URL(server.url);
            const header = server.headers[0];
            const parts = url.hostname.split(".").map(Number);
            const privateIp = parts.length === 4 && parts.every(part => Number.isInteger(part) && part >= 0 && part <= 255)
                && (parts[0] === 10 || (parts[0] === 192 && parts[1] === 168)
                    || (parts[0] === 172 && parts[1]! >= 16 && parts[1]! <= 31));
            if (url.protocol !== "http:" || (url.hostname !== "host.docker.internal" && !privateIp)
                || !url.port || url.username || url.password || url.search || url.hash
                || !/^\/[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}\/mcp$/.test(url.pathname)
                || server.headers.length !== 1 || !header || header.name !== "Authorization"
                || !/^Bearer [A-Za-z0-9_-]{43}$/.test(header.value)) {
                throw acp.RequestError.invalidParams("Invalid external MCP capability");
            }
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

    mcpToolNames(request: acp.NewSessionRequest | acp.LoadSessionRequest): string[] {
        // Exact host-admitted names are applied to native enabled_tools as well as the bridge.
        return sessionPolicy.parse(request._meta?.["laomedo"]).externalTools;
    }

    mcpToolOptions(names: string[]) {
        // Host admission already grants exactly these capability-bound tools.
        // Preserve global approval/sandbox policy and omit unselected names.
        const selected = sessionPolicy.shape.externalTools.parse(names);
        return {
            enabled_tools: selected,
            tools: Object.fromEntries(selected.map(name => [name, {approval_mode: "approve" as const}])),
        };
    }

    turnParameters(request: acp.PromptRequest) {
        const policy = this.sessions.get(request.sessionId);
        if (!policy) throw acp.RequestError.invalidParams("Unbound Laomedo session");
        const input = promptPolicy.parse(request._meta?.["laomedo"] ?? {});
        if (input.skills.some(skill => skill.path !== `/draft/.agents/skills/${skill.name}/SKILL.md`)) {
            throw acp.RequestError.invalidParams("Pinned skill path mismatch");
        }
        const systemSkill = Boolean(input.nativeCommand?.name.startsWith("$"));
        if (systemSkill && this.admittedSkill?.name !== input.nativeCommand!.name.slice(1)) throw acp.RequestError.invalidParams("Bundled skill was not admitted");
        if (systemSkill && !input.nativeCommand?.invocationId) throw acp.RequestError.invalidParams("Missing skill invocation identity");
        if (systemSkill) this.skillInputPrepared = {
            sessionId: request.sessionId, invocationId: input.nativeCommand!.invocationId!,
            name: this.admittedSkill!.name, path: this.admittedSkill!.path,
            manifestSha256: this.admittedSkill!.manifestSha256,
        };
        return {
            input: [...input.skills, ...(systemSkill ? [{type: "skill" as const, name: this.admittedSkill!.name, path: this.admittedSkill!.path}] : [])],
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

    commandPrompt(request: acp.PromptRequest): acp.ContentBlock[] {
        const input = promptPolicy.parse(request._meta?.["laomedo"] ?? {});
        const systemNames = ["imagegen", "openai-docs", "review-agent", "skill-creator", "skill-installer"];
        const allowed = input.nativeCommand?.name.startsWith("$") ? input.nativeCommand.name.slice(1) : undefined;
        for (const block of request.prompt) {
            if (block.type !== "text") continue;
            const mentioned = new Set(Array.from(block.text.matchAll(/\$([A-Za-z0-9_:-]+)/g), match => match[1]));
            for (const match of block.text.matchAll(/\[\$[A-Za-z0-9_:-]+\][\t\n\v\f\r ]*\(([^)]*)\)/g)) {
                const path = match[1]!.trim().replace(/^skill:\/\//, "").replace(/\\/g, "/");
                for (const name of systemNames) if (path === `/home/runner/.codex/skills/.system/${name}/SKILL.md`) mentioned.add(name);
            }
            if (systemNames.some(name => mentioned.has(name) && name !== allowed)) throw acp.RequestError.invalidParams("native_skill_approval_required");
        }
        if (!input.nativeCommand) return [];
        if (!this.sessions.has(request.sessionId)) throw acp.RequestError.invalidParams("Unbound command session");
        const command = input.nativeCommand;
        if (/[\x00-\x1f\x7f\u2028\u2029]/.test(command.arguments)
            || (!["review", "$skill-creator"].includes(command.name) && command.arguments.length !== 0)) {
            throw acp.RequestError.invalidParams("Invalid native command arguments");
        }
        const text = `${command.name.startsWith("$") ? "" : "/"}${command.name}${command.arguments ? ` ${command.arguments}` : ""}`;
        if (request.prompt.length !== 1 || request.prompt[0]?.type !== "text" || request.prompt[0].text !== text) {
            throw acp.RequestError.invalidParams("Native command text mismatch");
        }
        return command.name.startsWith("$") ? [] : request.prompt;
    }

    private async admitSystemSkill(name: string) {
        if (!["skill-creator"].includes(name)) throw acp.RequestError.invalidParams("Unsupported bundled skill");
        const source = await this.app.listSkills({cwds: ["/draft"], forceReload: true});
        const matches = source.data.flatMap(entry => entry.skills).filter(skill => skill.name === name);
        const path = `/home/runner/.codex/skills/.system/${name}/SKILL.md`;
        if (matches.length !== 1 || matches[0]!.scope !== "system" || !matches[0]!.enabled || matches[0]!.path !== path) {
            throw acp.RequestError.invalidParams("Bundled skill source changed");
        }
        const manifestText = readFileSync("/opt/acp/system-skills.json", "utf8");
        const manifest = JSON.parse(manifestText) as Record<string, Record<string, string>>;
        const expected = manifest[name];
        if (!expected || !expected["SKILL.md"]) throw acp.RequestError.invalidParams("Missing bundled skill manifest");
        const root = `/home/runner/.codex/skills/.system/${name}`;
        const found: Record<string, string> = {};
        const scan = (directory: string, relative = "") => {
            if (!lstatSync(directory).isDirectory() || lstatSync(directory).isSymbolicLink()) throw acp.RequestError.invalidParams("Invalid bundled skill directory");
            for (const entry of readdirSync(directory)) {
                const file = join(directory, entry);
                const key = relative ? `${relative}/${entry}` : entry;
                const stat = lstatSync(file);
                if (stat.isSymbolicLink()) throw acp.RequestError.invalidParams("Bundled skill symlink");
                if (stat.isDirectory()) scan(file, key);
                else if (stat.isFile()) found[key] = createHash("sha256").update(readFileSync(file)).digest("hex");
                else throw acp.RequestError.invalidParams("Invalid bundled skill file");
            }
        };
        if (lstatSync("/home/runner/.codex/skills/.system").isSymbolicLink()) throw acp.RequestError.invalidParams("Invalid system skill root");
        scan(root);
        if (Object.keys(found).length !== Object.keys(expected).length || Object.entries(expected).some(([key, hash]) => found[key] !== hash)) {
            throw acp.RequestError.invalidParams("Bundled skill content changed");
        }
        return {type: "skill" as const, name, path, manifestSha256: createHash("sha256").update(manifestText).digest("hex")};
    }

    private compactCompleted(): boolean {
        const events = this.compactEvents;
        const turns = events.filter(e => e.method === "turn/started");
        if (turns.length !== 1 || typeof turns[0]!.params.turn?.id !== "string") return false;
        const turn = turns[0]!.params.turn.id;
        const starts = events.filter(e => e.method === "item/started" && e.params.turnId === turn);
        const ends = events.filter(e => e.method === "item/completed" && e.params.turnId === turn);
        if (starts.length !== 1 || ends.length !== 1 || typeof starts[0]!.params.item.id !== "string") return false;
        const end = ends[0]!;
        return starts[0]!.params.item.id === end.params.item.id
            && events.indexOf(turns[0]!) < events.indexOf(starts[0]!)
            && events.indexOf(starts[0]!) < events.indexOf(end)
            && (end.params.item.status == null || end.params.item.status === "completed")
            && end.params.item.error == null
            && !events.some(e => e.method === "error" || (e.method === "turn/completed"
                && (e.params.turn.id !== turn || e.params.turn.status !== "completed")));
    }

    async prompt<T>(sessionId: string, run: () => Promise<T>, request?: acp.PromptRequest): Promise<T> {
        this.prompted = true;
        const admitted = request ? this.commandPrompt(request) : [];
        const policy = request ? promptPolicy.parse(request._meta?.["laomedo"] ?? {}) : undefined;
        this.admittedSkill = policy?.nativeCommand?.name.startsWith("$")
            ? await this.admitSystemSkill(policy.nativeCommand.name.slice(1)) : undefined;
        const control = admitted.length > 0 && ["status", "mcp", "skills"].includes(policy!.nativeCommand!.name);
        const compact = admitted.length > 0 && policy!.nativeCommand!.name === "compact";
        this.compactSession = compact ? sessionId : undefined;
        this.compactEvents = [];
        const before = this.completed.get(sessionId) ?? 0;
        this.prompting = true;
        try {
            return await run();
        } finally {
            // The response cannot overtake native terminal evidence on stdio.
            await this.rawQueue;
            this.prompting = false;
            this.admittedSkill = undefined;
            this.skillInputPrepared = undefined;
            const after = this.completed.get(sessionId) ?? 0;
            const compactCompleted = compact && this.compactCompleted();
            this.compactSession = undefined;
            if (this.rawFailed || (control ? after !== before : after === before && !compactCompleted)) {
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
