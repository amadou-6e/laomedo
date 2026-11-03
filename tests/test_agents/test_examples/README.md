# Maintained graph construction

These checks build actual component metadata through the consolidated Agent example.
They protect provider selection, optional Skill pins, serialized ports and explicit
refusal when a provider lacks provenance handoff support. They never execute a
provider. A structural check is not a working-example or browser acceptance result.

Run `python -m unittest discover -s tests/test_agents/test_examples -t tests -v`
in the declared Langflow environment. The suite skips only if `lfx` is absent.
