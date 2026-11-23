"""Feature settings and fixed protocol values; mutable state has one owner."""

from __future__ import annotations

CLEANUP_SECONDS = 20.0


IMAGE = "laomedo-claude-controller:2.1.310-acp0.98.0-skills1"


PROFILE = "laomedo-claude-profile"


CLI_VERSION = "2.1.310"

# Pinned bundled prompt skills. None admits the native instruction-only route;
# it grants no additional tool, filesystem, network or external-effect permission.
BUNDLED_SKILL_REQUIREMENTS = {
    "claude-api": None,
    "deep-research": "native_skill_requires_external_services",
    "design": "native_skill_requires_external_services",
    "design-sync": "native_skill_requires_external_services",
    "dataviz": "native_skill_requires_external_services",
    "update-config": "native_skill_requires_provider_configuration",
    "verify": "native_skill_requires_repository",
    "debug": "native_skill_requires_provider_configuration",
    "code-review": "native_skill_requires_subagents",
    "simplify": "native_skill_requires_subagents",
    "batch": "native_skill_requires_subagents",
    "fewer-permission-prompts": "native_skill_requires_provider_configuration",
    "doctor": "native_skill_requires_provider_configuration",
    "loop": "native_skill_requires_scheduling",
    "workflow-authoring": "native_skill_requires_external_services",
    "run": "native_skill_requires_external_services",
    "run-skill-generator": "native_skill_requires_provider_configuration",
    "plugin-authoring": "native_skill_requires_provider_configuration",
}


EXECUTION_GUARD = """import os,sys,time
remaining=min(float(sys.argv[2]),float(sys.argv[1])-time.time())
if remaining <= 0: raise SystemExit(124)
os.execvp('timeout',['timeout','--signal=TERM','--kill-after=5s',str(remaining),*sys.argv[3:]])
"""


SYSTEM = (
    "Work in /draft using the provided tools and pinned native skills. "
    "Read and edit files through the workspace command tool. Native controller "
    "file and shell tools are disabled. Only draft files may be changed. Commands execute in a separate "
    "credential-free container without network access. External GitHub effects "
    "require the scoped mediation tool or a validated downstream operation. "
    "Do not claim external changes without a successful receipt. When an output "
    "contract is provided, return exactly one JSON object without fences."
)


EFFORTS = ("default", "low", "medium", "high", "xhigh", "max")


MODEL_CATALOG_TTL_SECONDS = 300


NATIVE_AUTH_CLEANUP_SECONDS = 20
