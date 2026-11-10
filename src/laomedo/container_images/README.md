# Registered image resources

`models.py`: `ImageRegistration` validates trusted manifest values;
`ImageRecipe.from_registration()` snapshots only declared inputs, fingerprints
content and writes a private build context without rereading mutable source.
`registry.py`: `ImageRegistry.load()` selects packaged assets or the source
checkout independently of the working directory; `find()` returns a recipe.
`lock.py`: `ImageBuildLock` holds an OS-released cross-process lock per daemon and
image tag, with bounded wait and cancellation. `settings.py` supplies separate
build/verification budgets; `errors.py` exposes one safe acquisition failure code.
The package never creates Docker clients or starts builds. `laomedo/docker.py`
owns those operations and verifies an image before publishing its final tag.
