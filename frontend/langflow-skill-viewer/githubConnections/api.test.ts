import { authorizationUrl } from "./api";

it.each([
  "https://github.com.evil.example/login/oauth/authorize",
  "https://user:password@github.com/login/oauth/authorize",
  "https://github.com/login/oauth/authorize#untrusted",
  "http://github.com/login/oauth/authorize",
  "https://github.com/settings/apps/new",
  "javascript:alert(1)",
])(
  "refuses an authorization destination outside the fixed endpoint: %s",
  (value) => {
    expect(authorizationUrl(value)).toBeUndefined();
  },
);

it("admits the existing GitHub attempt URL without changing its query", () => {
  const url =
    "https://github.com/login/oauth/authorize?state=attempt&client_id=app";
  expect(authorizationUrl(url)).toBe(url);
});
