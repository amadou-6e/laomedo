# Current import ownership and retained evidence

`test_imports.py` scans maintained Python sources and inventoried component graph
code for imports of retired owners. `utils.load_owner_maps()` loads the internal
ownership maps; it does not load or exercise a retired migration CLI.

`test_shared.py` checks that mapped Skill, workspace, publication, Git and HTTP
targets resolve to current definitions. It also verifies byte integrity and
fail-before-process behavior for the explicitly inventoried retained Shared
campaign dependency. That dependency remains a separate migration scope; it is
not a pattern for new production work or proof of current runtime isolation.

Run `python -m unittest discover -s tests/test_shared/test_migration -t tests -v`.
These checks neither fetch `exp` nor execute providers. Historical migration
tools, tests and source provenance are archived on `exp`; normal verification
does not recreate those retired implementations.
