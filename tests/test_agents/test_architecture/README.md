# Agent dependency boundaries

Existing provider-neutral lifecycle and public-boundary regressions. Source scans assert actual files exist so retired paths cannot produce a false pass. Run with normal Agent concern discovery.

## Provider interface enforcement

`test_provider_contracts.py` checks the five provider role interfaces and the
explicit interruptible-worker and split-executor capability contracts in
`agents/agents/base/base/interim.py`. Implementations may expose only methods/properties
declared by their role, including inherited public methods and context-manager
protocols. Helpers must remain internal. Override checks reject narrowed call
shapes, changed method binding and sync/async mismatches. Constructors remain
host-composition concerns with provider-specific arguments.

The dependency-free `provider-interface-contracts` CI job runs the guard and its
negative controls. Normal Agent and installed-wheel discovery also includes it.
There is no baseline, provider allowlist, expected violation count or soft-fail.
An explicitly selected derived capability contributes its declared interface to
implementations of that capability. The checker still rejects undeclared mixin
methods and incompatible capability overrides; a provider class is not an
interface exemption.
The existing provider surface leaks make the check fail until the implementation
is repaired. Do not expand a base with unrelated operations just to clear CI;
resolve the responsibility or declare a justified capability contract explicitly.

This is a structural surface check, stronger than checking a few known calls but
not a general call-site/type checker. It does not prove absence of outside calls
to private helpers, arbitrary `getattr`, monkey-patching, dynamically attached
attributes or type/behavior incompatibilities. Those require typed consumer
boundaries and additional checks. The future software-engineering pattern
registry and reusable call-site helpers are tracked in
[my-skills#38](https://github.com/amadou-6e/my-skills/issues/38); skill implementation
is deferred. This guard imports no provider and performs no model/native work.

Target interfaces are organized in base/base concern modules and values in base/models concern modules. Declaration-package checks reject flat-file twins, facade re-exports and caller imports through the empty initializers. The live provider guard remains selected on interim contracts until behavioral migration.
