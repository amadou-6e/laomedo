/** Preserve host-owned native configuration arguments without a shell tunnel. */
import {mkdirSync, lstatSync, writeFileSync, renameSync, rmSync} from "node:fs";
import {randomUUID} from "node:crypto";

export function writeProviderCredential(token: string) {
    // This directory is in the credential-bearing controller, never its executor
    // or persistent Codex profile. Neither the pathname nor command is user input.
    const directory = "/tmp/laomedo-provider-auth";
    if (!/^[A-Za-z0-9._~+/=-]{16,32768}$/.test(token)) throw new Error("Invalid provider credential");
    mkdirSync(directory, {mode: 0o700, recursive: true});
    const stat = lstatSync(directory);
    if (!stat.isDirectory() || stat.isSymbolicLink() || (stat.mode & 0o077) !== 0
        || stat.uid !== process.getuid?.()) throw new Error("Invalid provider credential directory");
    const temporary = `${directory}/${randomUUID()}`;
    try {
        writeFileSync(temporary, token, {encoding: "utf8", mode: 0o600, flag: "wx"});
        renameSync(temporary, `${directory}/access-token`);
    } finally {
        rmSync(temporary, {force: true});
    }
}
export function projectTrust(roots: string[], hostOwned: boolean) {
    // Model-writable project configuration must never become a policy source.
    return Object.fromEntries(roots.map(root => [root, {trust_level: hostOwned ? "untrusted" : "trusted"}]));
}

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
    if (env["LAOMEDO_CODEX_REFRESHABLE_AUTH"] === "1") {
        writeProviderCredential(env["ACCESS_TOKEN"] ?? "");
        delete env["ACCESS_TOKEN"];
    }
    return args;
}
