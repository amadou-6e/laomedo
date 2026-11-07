# Workflow file policy

This module owns the GitHub-specific interpretation of changed workflow paths.
`touches_workflows(paths)` is a predicate over already-inspected native path bytes.
It performs no Git execution, API request or authorization. Transport and verified
publication share it so the same file changes receive the same classification.

There is no behavioral object to introduce for this one pure predicate. Its naming
system uses a descriptive domain verb rather than an empty policy class.
