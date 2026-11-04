# GitHub contracts

`test_values.py` protects Issue and PR admission, strict-model redaction,
normalized field order, Unicode digest preimages and distinct public errors.
`test_intents.py` verifies the actual gateways' persisted modify and close
intents using independent payloads and hashes. Shared factories provide fresh
in-memory providers and owned temporary stores; these are internal regression
controls, not live GitHub acceptance.
