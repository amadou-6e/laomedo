# GitHub REST delivery

`GitHubRestTransport` delivers admitted operations to its configured repository.
`__call__` selects the narrow supported operation. Reads normalize Issue/PR data;
writes preserve confirmed, rejected and uncertain outcomes. Credential suppliers
are host-owned and evaluated for the current connection generation. An Issue/PR
identifier is never authorization. Redirect refusal comes from `laomedo.host.http`.

No transport method silently retries an uncertain write. Pagination, payload and
deadline limits bound reads; response admission remains in the domain contracts.
