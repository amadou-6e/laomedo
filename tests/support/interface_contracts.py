"""Check explicit provider surfaces without importing optional runtimes.

This is a structural guard, not a Python type checker. It rejects public methods
outside the selected role contract, including inherited additions, and verifies
call-shape/async compatibility. It cannot resolve arbitrary dynamic call sites,
private access through aliases, runtime attributes or semantic substitutability.
"""

import ast
import inspect


def _resolve(expression, module, imports):
    """Resolve a declared class/base reference using local and imported names."""
    if isinstance(expression, ast.Name):
        return imports.get(expression.id, module + "." + expression.id)
    if isinstance(expression, ast.Attribute):
        prefix = _resolve(expression.value, module, imports)
        return prefix + "." + expression.attr if prefix else None
    return None


def _index(sources):
    """Index top-level owned classes and resolve their direct base references."""
    result = {}
    for module, source in sources.items():
        tree = ast.parse(source)
        imports = {}
        for node in tree.body:
            if isinstance(node, ast.ImportFrom) and not node.level:
                for alias in node.names:
                    imports[alias.asname or alias.name] = (
                        (node.module or "") + "." + alias.name
                    )
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    imports[alias.asname or alias.name.split(".")[0]] = (
                        alias.name if alias.asname else alias.name.split(".")[0]
                    )
        for node in tree.body:
            if isinstance(node, ast.ClassDef):
                result[module + "." + node.name] = (
                    module,
                    node,
                    [_resolve(base, module, imports) for base in node.bases],
                )
    return result


def _ancestors(name, classes, active=()):
    """Resolve owned ancestry and reject cycles rather than skipping the scan."""
    if name in active:
        raise ValueError("Cyclic contract inheritance: " + name)
    if name not in classes:
        return set()
    result = set()
    for parent in classes[name][2]:
        if parent:
            result.add(parent)
            result.update(_ancestors(parent, classes, (*active, name)))
    return result


def _members(name, classes):
    """Collect inherited methods using Python's declared C3 method order."""
    if name not in classes:
        return {}
    # Traverse source declarations only; no project code is executed.
    order = _mro(name, classes)
    result = {}
    for owner in reversed(order):
        for node in classes[owner][1].body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                result[node.name] = (owner, node)
    return result


def _mro(name, classes):
    """Compute C3 order for owned bases, failing on inconsistent inheritance."""
    bases = [parent for parent in classes[name][2] if parent in classes]
    sequences = [_mro(parent, classes)[:] for parent in bases] + [bases[:]]
    result = [name]
    while any(sequences):
        sequences = [sequence for sequence in sequences if sequence]
        candidate = next(
            (
                sequence[0]
                for sequence in sequences
                if not any(sequence[0] in other[1:] for other in sequences)
            ),
            None,
        )
        if candidate is None:
            raise ValueError("Inconsistent contract inheritance: " + name)
        result.append(candidate)
        for sequence in sequences:
            if sequence[0] == candidate:
                sequence.pop(0)
    return result


def _signature(method):
    """Translate an AST method signature without evaluating annotations/defaults."""
    arguments = method.args
    positional = [*arguments.posonlyargs, *arguments.args]
    optional_start = len(positional) - len(arguments.defaults)
    parameters = []
    static = any(
        isinstance(decorator, ast.Name) and decorator.id == "staticmethod"
        for decorator in method.decorator_list
    )
    for index, argument in enumerate(positional):
        if index == 0 and not static:
            continue
        parameters.append(
            inspect.Parameter(
                argument.arg,
                (
                    inspect.Parameter.POSITIONAL_ONLY
                    if index < len(arguments.posonlyargs)
                    else inspect.Parameter.POSITIONAL_OR_KEYWORD
                ),
                default=None if index >= optional_start else inspect.Parameter.empty,
            )
        )
    if arguments.vararg:
        parameters.append(
            inspect.Parameter(arguments.vararg.arg, inspect.Parameter.VAR_POSITIONAL)
        )
    for argument, default in zip(arguments.kwonlyargs, arguments.kw_defaults):
        parameters.append(
            inspect.Parameter(
                argument.arg,
                inspect.Parameter.KEYWORD_ONLY,
                default=None if default is not None else inspect.Parameter.empty,
            )
        )
    if arguments.kwarg:
        parameters.append(
            inspect.Parameter(arguments.kwarg.arg, inspect.Parameter.VAR_KEYWORD)
        )
    return inspect.Signature(parameters)


def _signature_errors(contract, implementation):
    """Reject narrowed call shapes, changed binding and sync/async mismatches."""
    errors = []
    if isinstance(contract, ast.AsyncFunctionDef) != isinstance(
        implementation, ast.AsyncFunctionDef
    ):
        errors.append("sync/async differs from contract")
    for decorator_name in ("property", "classmethod", "staticmethod"):
        decorated = lambda method: any(
            isinstance(decorator, ast.Name) and decorator.id == decorator_name
            for decorator in method.decorator_list
        )
        if decorated(contract) != decorated(implementation):
            errors.append(decorator_name + " binding differs from contract")
    expected, actual = _signature(contract), _signature(implementation)
    for kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD):
        if any(p.kind == kind for p in expected.parameters.values()) and not any(
            p.kind == kind for p in actual.parameters.values()
        ):
            errors.append("contract variadic parameters are narrowed")
    for minimal, keyword in ((True, False), (False, False), (False, True)):
        args, kwargs = [], {}
        for parameter in expected.parameters.values():
            if minimal and parameter.default is not inspect.Parameter.empty:
                continue
            if parameter.kind == inspect.Parameter.POSITIONAL_ONLY or (
                parameter.kind == inspect.Parameter.POSITIONAL_OR_KEYWORD
                and not keyword
            ):
                args.append(None)
            elif parameter.kind in (
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
                inspect.Parameter.KEYWORD_ONLY,
            ):
                kwargs[parameter.name] = None
        try:
            actual.bind(*args, **kwargs)
        except TypeError as error:
            errors.append("contract call rejected: " + str(error))
    return sorted(set(errors))


def contract_violations(sources, contracts):
    """Return actionable diagnostics for selected role interfaces and providers.

    Sources map absolute module names to source text. Contracts are fully qualified
    class names. Missing contracts and empty provider discovery fail explicitly.
    Only source is inspected; no credentials, native processes or models are used.
    """
    classes = _index(sources)
    diagnostics = []
    for contract_name in sorted(contracts):
        if contract_name not in classes:
            diagnostics.append("Missing contract: " + contract_name)
            continue
        expected = _members(contract_name, classes)
        providers = [
            name for name in classes if contract_name in _ancestors(name, classes)
        ]
        if not providers:
            diagnostics.append("No implementations found for " + contract_name)
        for provider in sorted(providers):
            for name, (owner, method) in _members(provider, classes).items():
                if name == "__init__" or (
                    name.startswith("_") and not name.endswith("__")
                ):
                    continue
                location = (
                    owner.rsplit(".", 1)[0].replace(".", "/")
                    + ".py:"
                    + str(method.lineno)
                    + ": "
                    + provider.rsplit(".", 1)[1]
                    + "."
                    + name
                )
                if name not in expected:
                    diagnostics.append(
                        location + " is not declared by " + contract_name
                    )
                elif owner != expected[name][0]:
                    for error in _signature_errors(expected[name][1], method):
                        diagnostics.append(location + ": " + error)
    return sorted(set(diagnostics))
