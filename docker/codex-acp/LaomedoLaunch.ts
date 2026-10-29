/** Preserve host-owned native configuration arguments without a shell tunnel. */
export function nativeArguments(env: NodeJS.ProcessEnv, codexPath?: string, platform = process.platform): string[] {
    if (env["LAOMEDO_CODEX_NATIVE_EVENTS"] !== "1") return [];
    let args;
    try {
        args = JSON.parse(env["LAOMEDO_CODEX_ARGS"] ?? "[]");
    } catch {
        throw new Error("Invalid Laomedo native launch policy");
    }
    if (!codexPath || platform !== "linux") {
        throw new Error("Unsupported Laomedo native launch environment");
    }
    if (!Array.isArray(args) || args.length > 128 || args.length % 2 !== 0
        || args.some((value, index) => typeof value !== "string" || value.length > 8192
            || (index % 2 === 0 && !["-c", "--disable", "--enable"].includes(value)))) {
        throw new Error("Invalid Laomedo native launch policy");
    }
    return args;
}
