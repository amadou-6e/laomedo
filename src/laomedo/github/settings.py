"""Central GitHub settings access; defining submodules retain ownership.

The exported classes are not instantiated here. Environment and credential
access remain at the point of use; constants are original objects, not copies.
"""

from laomedo.github.interface.issues.settings import Settings as IssueServiceSettings
from laomedo.github.interface.pull_requests.settings import (
    Settings as PullRequestServiceSettings,
)
from laomedo.github.issues.settings import ERROR_CODES as ISSUE_ERROR_CODES
from laomedo.github.issues.settings import (
    PRE_DISPATCH_ERRORS as ISSUE_PRE_DISPATCH_ERRORS,
)
from laomedo.github.pull_requests.settings import ERROR_CODES as PR_ERROR_CODES
from laomedo.github.pull_requests.settings import (
    PRE_DISPATCH_ERRORS as PR_PRE_DISPATCH_ERRORS,
)

from laomedo.github.transport.settings import ISSUE_GRAPHQL_QUERY

__all__ = [
    "ISSUE_GRAPHQL_QUERY",
    "IssueServiceSettings",
    "PullRequestServiceSettings",
    "ISSUE_ERROR_CODES",
    "ISSUE_PRE_DISPATCH_ERRORS",
    "PR_ERROR_CODES",
    "PR_PRE_DISPATCH_ERRORS",
]
