# Internal compatibility regression

pre-src-native-flow.json is the tracked native Codex example as it existed at
Laomedo commit6069ac9, before the src migration. Its embedded component source
is intentionally unchanged. It contains the public example's static task, IDs
and skill pins, not a copied user workspace or credential record.

The fixture is for internal import/serialization regression tests only. Loading
or executing its imports does not dispatch an agent and is not real integration
acceptance. Actual model/graph verification is recorded separately.
