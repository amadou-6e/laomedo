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
