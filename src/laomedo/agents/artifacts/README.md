# Agent artifacts

This package retains and transfers explicitly selected output files between Agent
runs. `utils.py` owns selection, validation and file transfer. `ArtifactReference`
in `models.py` is the canonical selected-file value. GitHub publication policy
belongs to its authorized publisher.

`selections` validates the retained selection list; `relative_path` validates a
manifest path; `import_selected` validates references,
ownership, paths and size before copying. These are standalone functions.
`ArtifactError` exposes stable refusal codes. Retaining files is not
proof that the originating run or a remote publication completed.
## Selected file values

`ArtifactReference` in `models.py` groups the six already admitted manifest
fields. Typed preparation and handoff values retain those objects until the
existing JSON boundary. Selection, protected-path checks, byte verification and
filesystem effects remain in the owning artifact functions; a model is not an
authorization grant. Dynamic path-to-hash inventories remain keyed maps.
