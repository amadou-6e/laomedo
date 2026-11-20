// Zero-model parser evidence from the locally inspected pinned adapter sources.
// This exercises extracted native parser bodies, not an integration or login.
const fs = require('fs');
const vm = require('vm');
const crypto = require('crypto');
const ts = require('C:/CodeWorkspace/laomedo/.tools/assistant-282-upstream/src/frontend/node_modules/typescript');
const root = 'C:/CodeWorkspace/laomedo/.tools/native-provider-sources/';
function parser(file, name) {
  const text = fs.readFileSync(root + file, 'utf8');
  const source = ts.createSourceFile(file, text, ts.ScriptTarget.Latest, true);
  const node = source.statements.find(item => ts.isFunctionDeclaration(item) && item.name?.text === name);
  if (!node) throw Error('Parser missing');
  const printed = ts.createPrinter().printNode(ts.EmitHint.Unspecified, node, source).replace(/^export\s+/, '');
  const compiled = ts.transpileModule(printed, {compilerOptions: {target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS}}).outputText;
  const context = vm.createContext({exports: {}});
  vm.runInContext(compiled, context);
  return {call: context[name] ?? context.exports[name], sha256: crypto.createHash('sha256').update(text).digest('hex')};
}
const openCode = parser('opencode-service.ts', 'detectSlashCommand');
const claudeMcp = parser('mcp-command.js', 'parseMcpCommand');
const claudeUsage = parser('usage-markdown.js', 'isUsageCommandText');
const prefix = 'Laomedo assistant instructions.\nUser message:\n';
for (const text of ['/sta', '/init', '/compact', '/model example', '/mcp', '/usage']) {
  if (openCode.call([{type: 'text', text: prefix + text}]) !== undefined) throw Error('Prefixed OpenCode text interpreted natively');
  if (claudeMcp.call(prefix + text) !== null) throw Error('Prefixed Claude MCP text interpreted natively');
  if (claudeUsage.call(prefix + text) !== false) throw Error('Prefixed Claude usage text interpreted natively');
}
if (openCode.call([{type: 'text', text: '/init'}]).name !== 'init') throw Error('Native parser control failed');
if (claudeMcp.call('/mcp').action !== 'status' || claudeUsage.call('/usage') !== true) throw Error('Native parser controls failed');
console.log(JSON.stringify({prefixed_cases: 6, parser_assertions: 18, bare_command_controls: 3, model_calls: 0, native_api_calls: 0, source_sha256: {opencode: openCode.sha256, claude_mcp: claudeMcp.sha256, claude_usage: claudeUsage.sha256}}));
