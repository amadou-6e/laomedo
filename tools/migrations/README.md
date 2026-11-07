# Explicit source migration

These checkout-owned tools migrate files selected by the caller. Application
imports do not use these maps, and no import hook or compatibility facade is
installed.

| File | Responsibility |
| --- | --- |
| `module-paths.json` | Retired module names to final defining modules |
| `symbol-paths.json` | Published symbols to their final defining modules |
| `cli-paths.json` | Supported launcher-module replacements |
| `manual-symbols.json` | Retired procedural APIs whose arguments, authorization or outcomes require manual review |
| `retained-shared-callers.json` | Exact source bytes and dependencies admitted by explicit internal historical-probe controls |

`migrate_module_paths.py` previews by default. `--apply` writes a selected file
atomically with an exclusive backup; `--check` reports whether migration is
needed. Review all changes, dynamic references and call signatures manually.
The tool does not execute a graph or certify a historical execution.
Colon-style launcher attributes from retired modules require manual migration;
rewriting only their module would leave an unverified attribute or constructor.
Retired handler factories likewise require explicit service bindings rather than
an automatic substitution of a server class. OpenCode worker image pins retain
their provider-owned settings even when their current values match Codex.

GitHubGitTransport, VerifiedGitStage and stage_verified_git use a GitCommandRunner
through `runner=`. Their old subprocess-shaped `run=` callbacks and removed
procedural Git environment/argv helpers require manual migration. The tool
refuses recognized direct or aliased uses rather than guessing arguments.
`VerifiedGitStage.git(*args)` is unsupported; its admitted object store is
available through `stage.repository` operations.

Codex `servers` modules define transport classes; they are not CLI launchers.
Their import migration belongs to the module map, not `cli-paths.json`.
The separate legacy contract-flow migrator accepts formatting differences only
when the complete Python AST (including docstrings) and comment tokens still
match its known source. Changed code, added comments and invalid Python are refused.

Historical observations retain their original identity and bytes. Inventoried
probe sources retain their post-format source bytes. Selected internal controls
load hash-checked copies with top-level from-import changes. The S11 copy also
rebinds its explicitly inventoried `_helpers` dependency-loading statements;
all code outside those declared statements has identical ASTs. Arbitrary module
aliases, dynamic API access and call-signature rewrites are unsupported.
Removed process helpers become explicit refusals;
unsupported native/main entrypoints must not run against the current package.
Scoped internal controls can supply a credential-free test environment, with
cleanup. This proves those controls only, never native or live integration.
