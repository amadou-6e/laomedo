# GitHub source-control policy adapter

`GitHubGitTransport` binds repository, connection generation, branch/ref rules,
verified objects and uncertain remote outcomes to GitHub operations. Generic
execution, environment isolation and shared Git verbs belong to `laomedo/git`.
The D4 target moves `GitHubMediatedTransport` to `github/transport/mediated.py`,
beside the Git and REST owners it composes. This README-first checkpoint has not
moved code yet. That dispatcher does not create another execution or credential
path; `GitHubGitTransport` keeps its current callable/method contracts here.

`classify_workflow_diff` inspects admitted outgoing objects before a push;
`__call__` implements the existing operation boundary; `_fetch` acquires only
selected refs. These framework/callable names remain stable. Repo/ref decisions,
byte limits, force-with-lease policy and provider credential selection stay here.
Credentials are supplied only to the command that needs them. A push timeout is
an unknown remote outcome, never permission to retry automatically.

The internal test seam accepts a `GitCommandRunner` object. Production constructors
omit it and use the one shared runner. The retired subprocess/environment helper
interfaces require explicit migration; no parallel legacy execution is retained.
