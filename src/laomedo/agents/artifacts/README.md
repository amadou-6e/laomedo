# Agent artifacts

Retain and transfer explicitly selected output files between Agent runs. Current
behavior is in `utils.py`; `ArtifactStore` and `ArtifactReference` remain target
objects until extraction replaces those functions. GitHub publication policy is
not an artifact-storage responsibility.

`selections` validates the retained selection list; `relative_path` validates a
manifest path; `import_selected` validates references,
ownership, paths and size before copying. Read the actual utility signatures rather
than treating these vocabulary terms as new implemented methods. Errors remain
`ArtifactError` with unchanged codes and boundary behavior. Retaining files is not
proof that the originating run or a remote publication completed.
# Selected file values

`ArtifactReference` in `models.py` groups the six already admitted manifest
fields. Typed preparation and handoff values retain those objects until the
existing JSON boundary. Selection, protected-path checks, byte verification and
filesystem effects remain in the owning artifact functions; a model is not an
authorization grant. Dynamic path-to-hash inventories remain keyed maps.
