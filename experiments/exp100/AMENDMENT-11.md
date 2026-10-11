# Prospective S10 B object-acquisition control

Before B's identity is claimed. Reviewer approved the progression fix at
36e35e8 but refused B execution: A and the earlier B setup already had the
base object, so literal fetch exercised listing, not host object acquisition.
A's observation remains unchanged; add this limit to its results.

After cloning the workspace, advance only the local provider's develop ref
to a commit absent from the agent clone. Confirm its absence with cat-file
before launching the fixture. Keep the trusted run baseline unchanged for
push verification; the newer base is only the selected read target.
Require fetchedBase to equal this provider-base commit, not the old baseline,
and exactly one provider Git fetch with target
refs/heads/develop:refs/heads/laomedo-read. Missing acquisition or a wrong hash
fails assessment. Mutation controls must reject a dropped fetch entry.

All other S10 B identities, command/permission scope, synthetic renewal,
source pin, unknown preservation, bounds and cleanup remain unchanged.
Commit the corrected executable and obtain one focused recheck before B.
