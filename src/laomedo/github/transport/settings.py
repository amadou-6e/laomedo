"""Fixed REST query and repository admission pattern; no environment reads."""

import re

_REPOSITORY = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+\Z")
ISSUE_GRAPHQL_QUERY = "query($owner:String!,$name:String!){repository(owner:$owner,name:$name){issues(first:30,states:OPEN){nodes{number title body}}}}"
