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

## Installed artifact consistency

`DockerBuildPy.run` in the repository `setup.py` clears only the generated
`laomedo` package under its selected build output before copying current source.
It rejects source/output overlap and output paths outside the build root. This
prevents retired modules in an old build cache from shadowing current modules.
Registered Docker inputs are then copied from their canonical `docker/` owners;
installed-artifact checks compare the exact registered set and bytes. They do not
accept an arbitrary extra resource tree. Runner-SDK tests remain in the runner
job; core-only wheels still exercise dependency-free image recipe/lock controls.
