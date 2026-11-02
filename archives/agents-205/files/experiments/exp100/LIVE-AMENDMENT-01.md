# S12 Amendment 01: fixed read-after-create visibility pause

Prospective: committed before any live attempt. Keep LIVE-PROTOCOL.md unchanged.
Prior EXP-15 proves read-after-write listings can lag. After the one confirmed
issue-create response, wait exactly five seconds before the positive view/list/
GraphQL readbacks. This is not a POST retry or an inferred confirmation.
No repeat lookup loop: missing visibility still records incomplete evidence
and consumes the identity. The one-POST/80-read/600-second budgets remain fixed.
