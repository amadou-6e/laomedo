# Maintained graph construction

These checks build actual component metadata through the consolidated Agent example.
They protect provider selection, optional Skill pins, serialized ports and explicit
refusal when a provider lacks provenance handoff support. They never execute a
provider. A structural check is not a working-example or browser acceptance result.

Run `python -m unittest discover -s tests/test_agents/test_examples -t tests -v`
in the declared Langflow environment. The suite skips only if `lfx` is absent.

`data/` contains saved graph wire-format inputs, not runnable example exports or
new execution evidence. `test_serialization.py` preserves embedded-component,
optional-Skill, connection-handle and answer/run output assertions from those
inputs. `handoffs.py` constructs internal handoff/controller graphs for the existing
optional Langflow runtime controls: `build()` returns the explicit chain;
`build_controller()` returns the bounded controller graph. Neither executes a
provider. Current developers use `examples/agents/build_flow.py`; historical
provider campaigns are preserved on `exp` at `f6112286` with exact-byte manifests.

Copied wire fixtures have canonical imports and synchronized source/cache hashes.
They are editable internal controls; immutable originals and their exact hashes
remain on `exp`. Current component-template checks validate the copied source
and cache hashes; no public saved-graph migration command remains.

`data/controller.json` is a saved-wire migration input, not a current controller
template. The current builder uses `components/laomedo/bounded_controller.py`.
