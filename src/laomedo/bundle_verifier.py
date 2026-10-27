"""Compatibility entrypoint for saved graphs and installed services."""

if __name__ == "__main__":
    import runpy
    runpy.run_module('laomedo.host.publication.bundle_verifier', run_name="__main__", alter_sys=True)
else:
    from laomedo._compat import alias_module
    alias_module(__name__, 'laomedo.host.publication.bundle_verifier')
