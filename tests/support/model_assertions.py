"""Shared assertions for ordinary model renderings; use test-only secrets."""


def assert_secrets_excluded(testcase, model, secrets):
    """Check repr, str, ordinary dump and JSON without computing expected payloads."""
    for rendered in (
        repr(model),
        str(model),
        str(model.model_dump()),
        model.model_dump_json(),
    ):
        for secret in secrets:
            testcase.assertNotIn(secret, rendered)
