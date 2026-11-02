# Skill operation controls

`test_service.py` protects the real registry/service boundary: atomic multi-file
edits, conflicts, authorization, immutable history, comparisons and HTTP admission.
`test_graph.py` protects scheduling and error propagation with internal stubs;
it does not establish real-agent or browser acceptance.

`test_models.py` protects the existing operation payload's round trip, strict
file validation and editor provenance codes. `SkillProposalModelTests` names
that concern; its `test_*` methods assert these contracts directly against the
canonical production models without repeating their implementation.

`SkillOperationCase` in `models.py` names one isolated test scenario. Its fields
retain the source root, initial revision, store, service, policy and operation.
`prepare(revision=None, commit="")` delegates reservation to that case's service,
defaulting only to its own initial immutable revision. Production exceptions pass
through. `make_operation_case(root)` creates fresh source/registry/history files
under the caller-owned temporary root and returns the grouped case. Cleanup is
owned by each test's temporary directory. Policies and proposal dictionaries stay
raw so invalid payload controls exercise the production boundary unchanged.
Pydantic copies their outer dictionaries during construction; changing a case's
policy does not implicitly replace the service's policy. Tests explicitly assign
the service policy when exercising a policy change.
