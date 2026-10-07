"""Verify unselected native patch routing under the active runner config.

The fake model and token are synthetic; both containers and the profile volume
are removed by the shared probe after exact-file checks.
"""

from probe_patch_hook import main


if __name__ == "__main__":
    main(with_hook=False)
