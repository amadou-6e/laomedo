/** Internal launch controls; no native process or model is started here. */
import {expect, it, vi} from "vitest";
import {nativeArguments, projectTrust, writeProviderCredential} from "./LaomedoLaunch";
import {writeFileSync, renameSync, lstatSync} from "node:fs";

vi.mock("node:fs", () => ({
    mkdirSync: vi.fn(), writeFileSync: vi.fn(), renameSync: vi.fn(), rmSync: vi.fn(),
    lstatSync: vi.fn(() => ({isDirectory: () => true, isSymbolicLink: () => false,
        mode: 0o700, uid: process.getuid?.()})),
}));

it("atomically replaces a private controller token and removes the launch environment copy", () => {
    const token = "fixture-access-token";
    const env = {LAOMEDO_CODEX_NATIVE_EVENTS: "1", LAOMEDO_CODEX_REFRESHABLE_AUTH: "1", ACCESS_TOKEN: token};
    nativeArguments(env, "/usr/local/bin/codex", "linux");
    expect(env).not.toHaveProperty("ACCESS_TOKEN");
    expect(writeFileSync).toHaveBeenLastCalledWith(expect.stringMatching(/^\/tmp\/laomedo-provider-auth\//), token,
        {encoding: "utf8", mode: 0o600, flag: "wx"});
    expect(renameSync).toHaveBeenCalledWith(expect.any(String), "/tmp/laomedo-provider-auth/access-token");
    expect(() => writeProviderCredential("secret\nnot-a-token")).toThrow("Invalid provider credential");
    vi.mocked(lstatSync).mockReturnValueOnce({isDirectory: () => false, isSymbolicLink: () => true} as any);
    expect(() => writeProviderCredential(token)).toThrow("Invalid provider credential directory");
});

it("never trusts model-writable project config in host-owned sessions", () => {
    expect(projectTrust(["/draft"], true)).toEqual({"/draft": {trust_level: "untrusted"}});
    expect(projectTrust(["/draft"], false)).toEqual({"/draft": {trust_level: "trusted"}});
});

it("preserves trusted native config flags as argv, never shell syntax", () => {
    const args=["-c","features.deferred_executor=true","--disable","memories"];
    expect(nativeArguments({LAOMEDO_CODEX_NATIVE_EVENTS:"1",LAOMEDO_CODEX_ARGS:JSON.stringify(args)},"/usr/local/bin/codex","linux")).toEqual(args);
    expect(nativeArguments({LAOMEDO_CODEX_ARGS:'["unexpected"]'})).toEqual([]);
});

it("fails closed for arbitrary subcommands, malformed data and unsupported launch", () => {
    for (const value of ['["exec","id"]','["-c"]','{}','[1,2]','["--config-file","/private"]','private-sensitive-invalid-json']) {
        expect(() => nativeArguments({LAOMEDO_CODEX_NATIVE_EVENTS:"1",LAOMEDO_CODEX_ARGS:value},"/usr/local/bin/codex","linux")).toThrow("Invalid Laomedo native launch policy");
    }
    expect(() => nativeArguments({LAOMEDO_CODEX_NATIVE_EVENTS:"1"})).toThrow("Unsupported Laomedo native launch environment");
});
