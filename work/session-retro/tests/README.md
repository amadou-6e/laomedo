# Evidence reader controls

`test_reader` owns native span integrity, active appends, source mutations, long lines and partial tails. `test_index` owns atomic restart, correlation, retrieval/redaction and refusal to use unrelated output locations. Tests create internal synthetic sessions in temporary directories; these are controls, not real-session findings or acceptance. `support/utils.py` constructs native records without importing another TestCase. Run `python -m unittest discover -s tests -v` with the experiment root on PYTHONPATH. No network, login, model request or unrelated file is used.

`support/` is support-only and contains no TestCase or discoverable tests, so its
name intentionally lacks the test_ prefix.
