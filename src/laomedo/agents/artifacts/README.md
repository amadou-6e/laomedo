# Agent artifacts

Retain and transfer explicitly selected output files between Agent runs. Current
behavior is in `utils.py`; `ArtifactStore` and `ArtifactReference` remain target
objects until extraction replaces those functions. GitHub publication policy is
not an artifact-storage responsibility.

`select` identifies retained outputs; import/materialization validates references,
ownership, paths and size before copying. Read the actual utility signatures rather
than treating these vocabulary terms as new implemented methods. Errors remain
`ArtifactError` with unchanged codes and boundary behavior. Retaining files is not
proof that the originating run or a remote publication completed.
