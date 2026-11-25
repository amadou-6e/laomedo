# Account-scoped pull request reads

`PrivatePullRequestSelection` identifies a connected account and a repository; `PrivatePullRequestRead` also identifies a pull request. `PrivatePullRequestResult` carries the read result and the authorization that must be checked before release.

`PrivatePullRequestAccess.discover()` lists pull requests after verifying the current profile, account and repository consent. `read()` obtains one pull request under the same checks. Both revalidate the authorization before returning. These methods do not authorize writes or graph execution.
