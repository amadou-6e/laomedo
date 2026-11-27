# Shared error catalogue controls

`test_catalogue.py` checks stable public error-code coverage, descriptive fallback,
redaction and the defining Agent/runner/Skill error producers. It follows actual
module ownership through the migration maps and fails when a producer is missing.
It does not establish rendered error-card or real recovery acceptance.

Run `python -m unittest discover -s tests/test_shared/test_errors -t tests -v`.
The shared repository-root helper resolves checked-in catalogue/producer files
independently of test nesting and the installed package's location.
