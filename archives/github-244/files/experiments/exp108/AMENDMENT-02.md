# EXP-108 amendment 02: browser code-to-state binding

Frozen after the first result and before changing the probe. The original
protocol requires a browser callback code to be bound to its challenge state.
The v1 fake provider treated the code as one-use but did not check its state.
Add a control with two valid pending states for the same account and repo:
the code issued for one must not complete the other. The fake endpoint must
reject that exchange. Keep the v1 result and report the amended run as v2.

This is a validity correction to the synthetic setup, not evidence about
GitHub's real authorization endpoint.
