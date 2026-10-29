/** Internal launch controls; no native process or model is started here. */
import {expect, it} from "vitest";
import {nativeArguments} from "./LaomedoLaunch";

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
