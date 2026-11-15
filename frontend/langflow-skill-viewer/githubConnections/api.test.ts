import { authorizationUrl, installationUrl } from "./api";

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

it("constructs a fixed installation URL with the pending identifier and refuses foreign paths", () => {
  const id = "04c5b5b0-3859-4bf3-999c-08a189be7f06";
  expect(installationUrl("laomedo-local", id)).toBe(
    `https://github.com/apps/laomedo-local/installations/new?state=${id}`,
  );
  expect(installationUrl("../settings/apps", id)).toBeUndefined();
  expect(installationUrl("user@evil.example", id)).toBeUndefined();
  expect(installationUrl("laomedo-local", "arbitrary-state")).toBeUndefined();
});
