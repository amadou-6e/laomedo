# Skill interface errors

These controls protect catalogue coverage for literal failures emitted by the
Skill component and its shared Agent feedback validator. ErrorCatalogueTests reads
the actual producers and requires a title, explanation and recovery for every
emitted literal code. New producer codes therefore cannot silently rely on the
generic fallback. Dynamic and external failures still require separate fallback
and redaction checks; this literal-producer guard does not claim that coverage.

The shared frontend presenter retains technical codes separately from descriptive
text. Real graph/browser checks establish presentation; these internal controls
do not replace them.

SkillOwnershipTests protects defining-symbol imports, the direction of domain
dependencies and the absence of retired implementation facades. Its methods scan
the actual owning modules rather than store copies of their implementation bodies.

`test_http.py` exercises authenticated source/operation listeners with internal
collaborators: instance-local tokens and services, no-store responses, safe domain
failure projection and client error categories. `SkillHTTPCase` in `models.py`
groups each server/client route contract; `utils.http_cases()` builds the two
explicit cases. `RunningHTTPServer` owns each temporary socket and thread.
These wire controls do not establish real Skill, browser or authentication acceptance.
