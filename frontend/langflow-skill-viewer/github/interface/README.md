# GitHub inspection boundary

`describeGitHubInspectionFailure` admits only declared API code slots, retains safe machine diagnostics through the shared presenter, and supplies a read-only domain fallback. `GitHubInspectionError` renders the shared explanation and subtle diagnostic copy icon. It does not fetch, authorize or retry. Issue/PR viewers own their selected identity, request cancellation and explicit Refresh control.

`githubBuildFailure` projects failed or uncertain GitHub operation output into an
unsuccessful node build. `githubRunFailure` summarizes only the current run's
executed nodes, so a terminal stream event cannot replace a failed operation with
a success banner. The integration covers streamed, background and legacy build
events; it preserves output data and never dispatches or retries an operation.
