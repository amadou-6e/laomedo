// Run from the pinned Langflow frontend checkout. Exercise the real GFM parser.
const path = require("node:path");
const rootDir = process.cwd();
const upstream = require(path.join(rootDir, "jest.config.js"));
const allowGfm = pattern => pattern.replace("remark-(?:parse|rehype)", "(?:remark-(?:parse|rehype|gfm)|markdown-table|escape-string-regexp)");
module.exports = {
  ...upstream,
  rootDir,
  transform: Object.fromEntries(Object.entries(upstream.transform).map(([pattern, value]) => [allowGfm(pattern), value])),
  transformIgnorePatterns: upstream.transformIgnorePatterns.map(allowGfm),
};
