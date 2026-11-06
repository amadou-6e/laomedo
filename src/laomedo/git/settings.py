"""Fixed bounds and private protocol names for host Git operations."""

GIT_COMMAND_TIMEOUT_SECONDS = 30
GIT_TREE_CLEANUP_SECONDS = 5
MEDIATED_TOKEN_ENV = "LAOMEDO_MEDIATED_GIT_TOKEN"

# Fixed protocol admission, never caller or environment configuration.
ISOLATED_READ_OPTIONS = {
    "--version": frozenset(),
    "clone": frozenset({"--bare", "--depth=1", "--no-single-branch"}),
    "fetch": frozenset({"--prune", "--depth=1", "--tags"}),
    "for-each-ref": frozenset({"--format=%(refname)"}),
    "rev-parse": frozenset({"--verify"}),
    "ls-tree": frozenset({"-rz", "--full-tree"}),
    "cat-file": frozenset({"-s"}),
}
