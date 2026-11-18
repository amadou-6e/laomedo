// Run from the pinned Langflow frontend checkout. Exercise the real GFM parser.
const path = require("node:path");
const rootDir = process.cwd();
const upstream = require(path.join(rootDir, "jest.config.js"));
const allowGfm = (pattern) => {
  const anchor = "remark-(?:parse|rehype)";
  // Only the pinned upstream Markdown allowlist needs extending; leave other transforms intact.
  if (!pattern.includes(anchor)) return pattern;
  return pattern.replace(
    anchor,
    "(?:remark-(?:parse|rehype|gfm)|markdown-table|escape-string-regexp)",
  );
};
if (
  !upstream.transformIgnorePatterns.some((pattern) =>
    pattern.includes("remark-(?:parse|rehype)"),
  )
) {
  throw new Error(
    "Pinned upstream Markdown ESM allowlist changed; update the activity test config.",
  );
}
module.exports = {
  ...upstream,
  rootDir,
  transform: Object.fromEntries(
    Object.entries(upstream.transform).map(([pattern, value]) => [
      allowGfm(pattern),
      value,
    ]),
  ),
  transformIgnorePatterns: upstream.transformIgnorePatterns.map(allowGfm),
};
