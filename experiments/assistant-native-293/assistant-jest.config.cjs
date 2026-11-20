// Preview-only Jest wrapper for the pinned upstream checkout's Windows paths
// and its remark-gfm ESM import. Production tests do not load this exp harness.
const path = require('path');
const frontend = 'C:/CodeWorkspace/laomedo/.tools/assistant-282-upstream/src/frontend';
const config = require(path.join(frontend, 'jest.config.js'));
module.exports = {
  ...config,
  rootDir: frontend,
  testMatch: ['**/*.test.ts', '**/*.test.tsx'],
  transformIgnorePatterns: config.transformIgnorePatterns.map(pattern =>
    pattern.replace('remark-(?:parse|rehype)', 'remark-(?:gfm|parse|rehype)').replace('(?!(.*', '(?!(escape-string-regexp|markdown-table|.*')),
  transform: {
    ...config.transform,
    'node_modules[/\\\\](?:remark-gfm|escape-string-regexp|markdown-table)[/\\\\].+\\.js$': path.join(frontend, 'transform-import-meta.js'),
  },
};
