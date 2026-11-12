"""One-time current-source import relocation during the develop integration."""
import ast
import json
import subprocess
from pathlib import Path


def owner(name, root):
    parts = name.split('.')
    for end in range(len(parts), 0, -1):
        path = root.joinpath('src', *parts[:end])
        if path.with_suffix('.py').is_file() or (path / '__init__.py').is_file():
            return '.'.join(parts[:end]), parts[end:]
    return None, []


def resolve(name, root, modules, symbols, *, module=False):
    applied = set()
    for _ in range(30):
        exact = (modules if module else {**modules, **symbols}).get(name)
        if exact and exact != name and name not in applied:
            applied.add(name)
            name = exact
            continue
        current, tail = owner(name, root)
        if current is not None and (not tail if module else len(tail) <= 1):
            return name
        parts = name.split('.')
        for end in range(len(parts) - 1, 0, -1):
            prefix = '.'.join(parts[:end])
            target = modules.get(prefix)
            if target and target != prefix and prefix not in applied:
                applied.add(prefix)
                name = target + '.' + '.'.join(parts[end:])
                break
        else:
            return name
    raise RuntimeError('relocation_chain_unresolved')


def source_imports(source, root, modules, symbols):
    tree = ast.parse(source)
    raw = source.encode('utf-8')
    offsets = [0]
    for line in raw.splitlines(keepends=True):
        offsets.append(offsets[-1] + len(line))
    edits, bindings, imported, added = [], {}, {}, set()
    used = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and not node.level:
            for item in node.names:
                imported[item.asname or item.name] = resolve(node.module + '.' + item.name, root, modules, symbols)

    def replace(node, text):
        edits.append((offsets[node.lineno-1] + node.col_offset, offsets[node.end_lineno-1] + node.end_col_offset, text.encode('utf-8')))

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            retained = []
            for item in node.names:
                if item.name.startswith('laomedo.') and item.asname and node in tree.body:
                    bindings[item.asname] = resolve(item.name, root, modules, symbols, module=True)
                else:
                    retained.append(item.name + (' as ' + item.asname if item.asname else ''))
            if len(retained) != len(node.names):
                replace(node, 'import ' + ', '.join(retained) if retained else '')
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level and node.module.startswith('laomedo.'):
            replacements = []
            for item in node.names:
                if item.name == '*':
                    raise RuntimeError('manual_star_import_required')
                target = resolve(node.module + '.' + item.name, root, modules, symbols)
                definition, tail = owner(target, root)
                if not definition or not tail:
                    replacements.append('from ' + node.module + ' import ' + item.name + (' as ' + item.asname if item.asname else ''))
                    continue
                if len(tail) != 1:
                    raise RuntimeError('manual_nested_import_required:' + target)
                local = item.asname or item.name
                replacements.append('from ' + definition + ' import ' + tail[0] + (' as ' + local if local != tail[0] else ''))
            indent = ' ' * node.col_offset
            text = ('\n' + indent).join(replacements)
            if text != ast.get_source_segment(source, node):
                replace(node, text)

    for node in ast.walk(tree):
        if not isinstance(node, ast.Attribute) or not isinstance(node.value, ast.Name) or node.value.id not in bindings:
            continue
        target = resolve(bindings[node.value.id] + '.' + node.attr, root, modules, symbols)
        definition, tail = owner(target, root)
        if not definition or not tail:
            raise RuntimeError('manual_module_value_required:' + target)
        symbol = tail[0]
        if imported.get(symbol) == definition + '.' + symbol:
            local = symbol
        elif symbol not in used:
            local = symbol
        else:
            qualifier = ''.join(part.title() for part in definition.split('.')[-2:])
            local = qualifier + symbol.lstrip('_').title()
        imported[local] = definition + '.' + symbol
        added.add('from ' + definition + ' import ' + symbol + (' as ' + local if local != symbol else ''))
        replace(node, local + ('.' + '.'.join(tail[1:]) if len(tail) > 1 else ''))

    escaped = [node.id for node in ast.walk(tree) if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load) and node.id in bindings and not any(isinstance(parent, ast.Attribute) and parent.value is node for parent in ast.walk(tree))]
    if escaped:
        raise RuntimeError('manual_escaped_module_alias_required:' + ','.join(sorted(set(escaped))))
    for start, end, text in sorted(edits, reverse=True):
        raw = raw[:start] + text + raw[end:]
    updated = raw.decode('utf-8')
    if added:
        parsed = ast.parse(updated)
        insert = 0
        for node in parsed.body:
            if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str) or isinstance(node, ast.ImportFrom) and node.module == '__future__':
                insert = node.end_lineno
            else:
                break
        lines = updated.splitlines(keepends=True)
        lines[insert:insert] = ['\n' + '\n'.join(sorted(added)) + '\n']
        updated = ''.join(lines)
    ast.parse(updated)
    return updated


def main():
    import sys
    root = Path(sys.argv[1]).resolve()
    if root.name != 'provider-205-integration' or root.parent.name != 'worktrees':
        raise RuntimeError('unexpected_integration_root')
    maps = {}
    for filename in ['module-paths.json', 'symbol-paths.json']:
        theirs = json.loads(subprocess.check_output(['git','-C',str(root),'show','6077e79a:tools/migrations/'+filename]))
        ours = json.loads(subprocess.check_output(['git','-C',str(root),'show','8fe9e364:tools/migrations/'+filename]))
        maps[filename] = {**theirs, **ours}
    modules, symbols = maps['module-paths.json'], maps['symbol-paths.json']
    modules.update({
        'laomedo.http.redirect': 'laomedo.host.http',
        'laomedo.git.credentials.helper': 'laomedo.git.credential_helper',
        'laomedo.git.credentials': 'laomedo.git.credential_helper',
        'laomedo.github.workflows.utils': 'laomedo.github.workflows',
        'laomedo.host.credentials.token.connection': 'laomedo.host.credentials.token',
        **{'laomedo.skills.registry.' + name: 'laomedo.skills.registry.utils.' + target for name,target in [('files','files'),('hashing','hashing'),('paths','paths'),('policy','policy'),('patch','diff')]},
    })
    symbols['laomedo.skills.operations.utils.proposal'] = 'laomedo.skills.operations.utils.proposal.proposal'
    changed, refused = [], []
    for prefix in ['src','components','tests']:
        for path in (root/prefix).rglob('*.py'):
            source = path.read_text(encoding='utf-8-sig')
            if '<<<<<<<' in source:
                continue
            try:
                updated = source_imports(source, root, modules, symbols)
            except (RuntimeError, SyntaxError) as error:
                refused.append({'path':str(path.relative_to(root)),'reason':str(error)})
                continue
            if updated != source:
                path.write_text(updated,encoding='utf-8')
                changed.append(str(path.relative_to(root)))
    for filename, values in maps.items():
        resolved = {key:resolve(value,root,modules,symbols,module=filename=='module-paths.json') for key,value in values.items()}
        (root/'tools/migrations'/filename).write_text(json.dumps(resolved,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'changed':changed,'refused':refused},indent=2))


if __name__ == '__main__':
    main()
