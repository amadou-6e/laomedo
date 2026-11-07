# Issue context controls

`test_reader.py` owns bounded read aggregation, issue identity, timeline
completeness, target selection and read failures. Its deterministic HTTP values
live in the owning `utils.py` and do not establish live GitHub acceptance.

`ContextCliTests` in `test_cli.py` executes the actual module entrypoint and checks
forwarded repository/issue/target arguments, successful JSON, safe error JSON and
exit codes. The reader is replaced only inside these internal CLI controls;
neither a network request nor an Agent run occurs.
