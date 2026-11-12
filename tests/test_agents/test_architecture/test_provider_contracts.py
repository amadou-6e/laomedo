"""Enforce complete declared provider surfaces and compatible override shapes."""

import unittest

from support.interface_contracts import contract_violations
from support.interface_contracts import agent_access_violations
import ast
from support.paths import repository_root


class ProviderContractCheckerTests(unittest.TestCase):
    """Negative controls ensure the architecture guard catches real violations."""

    def check(self, interface, implementation):
        """Inspect independent source snippets without importing or executing them."""
        return contract_violations(
            {
                "example.base": interface,
                "example.provider": "from example.base import BaseRole\n"
                + implementation,
            },
            {"example.base.BaseRole"},
        )

    def test_agent_calls_reject_private_and_undeclared_members_through_aliases(self):
        source = "def consume(agent):\n alias = agent\n alias.start({})\n alias._run_dir('id')\n getattr(alias, 'native_prompt')()\n"
        errors = agent_access_violations(source, {"agent"}, {"start"})
        self.assertEqual(len(errors), 2)
        self.assertTrue(any("_run_dir" in item for item in errors))
        self.assertTrue(any("native_prompt" in item for item in errors))
        self.assertEqual(
            agent_access_violations(
                "def consume(agent):\n agent.read_activity('run','attempt')\n",
                {"agent"},
                {"read_activity"},
            ),
            [],
        )

    def test_declared_operations_and_private_helpers_pass(self):
        """Implementation helpers remain internal; an optional extra keyword is safe."""
        self.assertEqual(
            self.check(
                "class BaseRole:\n def execute(self, request, *, deadline=None): ...\n",
                "class Provider(BaseRole):\n"
                " def execute(self, request, *, deadline=None, trace=False): return self._run(request)\n"
                " def _run(self, request): return request\n",
            ),
            [],
        )

    def test_extra_public_operation_is_reported_with_location(self):
        """A nominal base must not conceal the provider's undeclared public API."""
        errors = self.check(
            "class BaseRole:\n def execute(self, request): ...\n",
            "class Provider(BaseRole):\n"
            " def execute(self, request): return request\n"
            " def bypass(self): return True\n",
        )
        self.assertEqual(len(errors), 1)
        self.assertIn("example/provider.py:4: Provider.bypass", errors[0])
        self.assertIn("not declared by example.base.BaseRole", errors[0])

    def test_transitive_mixin_leak_is_not_missed(self):
        """Inherited concrete additions are part of the exposed provider surface."""
        errors = self.check(
            "class BaseRole:\n def execute(self, request): ...\n",
            "class Extra:\n def bypass(self): ...\n"
            "class Provider(Extra, BaseRole):\n def execute(self, request): ...\n",
        )
        self.assertTrue(any("Provider.bypass" in error for error in errors))

    def test_explicit_derived_capability_is_checked_without_waiving_other_methods(self):
        """Only a declared interface extension admits a capability API."""
        sources = {
            "example.base": "class BaseRole:\n def execute(self, request): ...\n"
            "class BaseInterruptible(BaseRole):\n def request_cancel(self): ...\n",
            "example.provider": "from example.base import BaseInterruptible\n"
            "class Provider(BaseInterruptible):\n"
            " def execute(self, request): ...\n"
            " def request_cancel(self): ...\n",
        }
        contracts = {"example.base.BaseRole", "example.base.BaseInterruptible"}
        self.assertEqual(contract_violations(sources, contracts), [])
        self.assertTrue(contract_violations(sources, {"example.base.BaseRole"}))
        sources["example.provider"] += " def bypass(self): ...\n"
        self.assertTrue(
            any(
                "Provider.bypass" in item
                for item in contract_violations(sources, contracts)
            )
        )
        sources["example.provider"] = sources["example.provider"].replace(
            "request_cancel(self)", "request_cancel(self, required_extra)"
        )
        self.assertTrue(
            any(
                "Provider.request_cancel" in item and "contract call rejected" in item
                for item in contract_violations(sources, contracts)
            )
        )

    def test_sync_async_override_mismatch_fails(self):
        """An awaitable operation cannot become synchronous at a provider boundary."""
        errors = self.check(
            "class BaseRole:\n async def execute(self, request): ...\n",
            "class Provider(BaseRole):\n def execute(self, request): ...\n",
        )
        self.assertTrue(any("sync/async" in error for error in errors))

    def test_optional_contract_argument_cannot_become_required(self):
        """The minimal call admitted by the interface must remain valid."""
        errors = self.check(
            "class BaseRole:\n def execute(self, request, *, deadline=None): ...\n",
            "class Provider(BaseRole):\n def execute(self, request, *, deadline): ...\n",
        )
        self.assertTrue(any("contract call rejected" in error for error in errors))

    def test_contract_keyword_and_variadic_calls_cannot_be_narrowed(self):
        """Renamed keyword parameters and removed variadic support reject callers."""
        for contract, implementation in (
            ("request", "renamed"),
            ("request, **options", "request"),
            ("request, *items", "request"),
        ):
            with self.subTest(contract=contract):
                self.assertTrue(
                    self.check(
                        f"class BaseRole:\n def execute(self, {contract}): ...\n",
                        f"class Provider(BaseRole):\n def execute(self, {implementation}): ...\n",
                    )
                )

    def test_context_manager_protocol_must_also_be_declared(self):
        """Implicit with-protocol access is an external interface too."""
        errors = self.check(
            "class BaseRole:\n def execute(self, request): ...\n",
            "class Provider(BaseRole):\n"
            " def execute(self, request): ...\n"
            " def __enter__(self): return self\n",
        )
        self.assertTrue(any("Provider.__enter__" in error for error in errors))

    def test_missing_contract_and_empty_discovery_fail(self):
        """Deleted/moved sources cannot turn an empty architecture scan green."""
        self.assertTrue(contract_violations({}, {"example.base.BaseRole"}))
        self.assertTrue(
            contract_violations(
                {"example.base": "class BaseRole: pass\n"},
                {"example.base.BaseRole"},
            )
        )

    def test_aliased_imports_are_supported(self):
        """Declared ancestry is resolved through a module import alias."""
        sources = {
            "example.base": "class BaseRole:\n def execute(self, request): ...\n",
            "example.provider": "import example.base as contracts\n"
            "class Provider(contracts.BaseRole):\n def execute(self, request): ...\n",
        }
        self.assertEqual(contract_violations(sources, {"example.base.BaseRole"}), [])

    def test_c3_order_selects_the_actual_inherited_override(self):
        """A later incompatible mixin must not shadow the earlier valid override."""
        prefix = (
            "from example.base import BaseRole\n"
            "class Good:\n def execute(self, request): ...\n"
            "class Bad:\n def execute(self, renamed): ...\n"
        )
        for bases, fails in (("Good, Bad", False), ("Bad, Good", True)):
            with self.subTest(bases=bases):
                errors = contract_violations(
                    {
                        "example.base": "class BaseRole:\n def execute(self, request): ...\n",
                        "example.provider": prefix
                        + f"class Provider({bases}, BaseRole): pass\n",
                    },
                    {"example.base.BaseRole"},
                )
                self.assertEqual(bool(errors), fails)

    def test_static_and_property_binding_cannot_change(self):
        """Matching names and arguments do not excuse changed descriptor semantics."""
        for decorator in ("staticmethod", "property"):
            with self.subTest(decorator=decorator):
                argument = "request" if decorator == "staticmethod" else "self"
                errors = self.check(
                    f"class BaseRole:\n @{decorator}\n def execute({argument}): ...\n",
                    "class Provider(BaseRole):\n def execute(self, request): ...\n",
                )
                self.assertTrue(any("binding differs" in error for error in errors))


class ProviderInterfaceContractTests(unittest.TestCase):
    """Current production providers must expose their declared role contract only."""

    def test_provider_public_surfaces_match_declared_role_interfaces(self):
        """Fail on live undeclared APIs without a baseline or provider exceptions."""
        root = repository_root() / "src"
        sources = {}
        for path in root.joinpath("laomedo").rglob("*.py"):
            parts = path.relative_to(root).with_suffix("").parts
            module = ".".join(parts[:-1] if parts[-1] == "__init__" else parts)
            sources[module] = path.read_text(encoding="utf-8-sig")
        contracts = {
            "laomedo.agents.agents.base.base." + name
            for name in (
                "BaseCommandExecutor",
                "BaseInterruptibleCommandExecutor",
                "BaseSplitCommandExecutor",
                "BaseCredentialProvider",
                "BaseModelCatalog",
            )
        }
        contracts.add("laomedo.agents.agents.base.agent.BaseAgent")
        violations = contract_violations(sources, contracts)
        self.assertEqual(
            violations,
            [],
            "Provider interface violations:\n"
            + "\n".join("src/" + violation for violation in violations),
        )

    def test_application_consumers_use_declared_agent_members(self):
        root = repository_root() / "src/laomedo"
        base = ast.parse((root / "agents/agents/base/agent.py").read_text())
        agent = next(
            n
            for n in base.body
            if isinstance(n, ast.ClassDef) and n.name == "BaseAgent"
        )
        members = {
            n.name
            for n in agent.body
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
            and not n.name.startswith("_")
        }
        for node in ast.walk(agent):
            if (
                isinstance(node, ast.Attribute)
                and isinstance(node.ctx, ast.Store)
                and isinstance(node.value, ast.Name)
                and node.value.id == "self"
                and not node.attr.startswith("_")
            ):
                members.add(node.attr)
        consumers = {
            "host/runner/http/handler.py": {"self.server.runner"},
            "integrations/langflow/join/controller.py": {"runner", "self.runner"},
        }
        for path, roots in consumers.items():
            with self.subTest(path=path):
                self.assertEqual(
                    agent_access_violations((root / path).read_text(), roots, members),
                    [],
                )

    def test_application_imports_do_not_reach_provider_implementations(self):
        root = repository_root() / "src/laomedo"
        for path in root.rglob("*.py"):
            relative = path.relative_to(root).as_posix()
            if (
                relative.startswith("agents/agents/")
                or relative == "agents/registry.py"
            ):
                continue  # Provider internals and the explicit composition root.
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8-sig"))):
                names = (
                    [i.name for i in node.names]
                    if isinstance(node, ast.Import)
                    else [node.module or ""] if isinstance(node, ast.ImportFrom) else []
                )
                for name in names:
                    if name.startswith(
                        tuple(
                            "laomedo.agents.agents." + provider + "."
                            for provider in ("codex", "claude", "opencode")
                        )
                    ):
                        # Startup may select fixed provider configuration, never behavior.
                        self.assertTrue(
                            name.endswith(".settings"), (relative, node.lineno, name)
                        )

    def test_shared_roles_do_not_reintroduce_provider_private_runtime_abstractions(
        self,
    ):
        """Native lifecycles remain provider-owned instead of an unused nominal role."""
        import ast

        retired = {"BaseAgentRuntime", "RuntimeLaunch", "RuntimeObservation"}
        root = repository_root() / "src" / "laomedo"
        violations = []
        for path in root.rglob("*.py"):
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8-sig"))):
                if isinstance(node, ast.ClassDef) and node.name in retired:
                    violations.append(str(path.relative_to(root)) + ":" + node.name)
                elif isinstance(node, ast.ImportFrom):
                    violations.extend(
                        str(path.relative_to(root)) + ":" + name.name
                        for name in node.names
                        if name.name in retired
                    )
        self.assertEqual(violations, [])
