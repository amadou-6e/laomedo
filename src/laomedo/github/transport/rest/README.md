# GitHub REST delivery

`GitHubRestTransport` delivers admitted operations to its configured repository.
`__call__` selects the narrow supported operation. Reads normalize Issue/PR data;
writes preserve confirmed, rejected and uncertain outcomes. Credential suppliers
are host-owned and evaluated for the current connection generation. An Issue/PR
identifier is never authorization. Redirect refusal comes from `laomedo.http`.

The default HTTPS opener uses `truststore.SSLContext` to verify certificates and
hostnames through the operating system's trust store. This supports a managed
Windows certificate chain without disabling verification or replacing SSL
process-wide. An explicitly injected opener remains caller-owned.

No transport method silently retries an uncertain write. Pagination, payload and
deadline limits bound reads; response admission remains in the domain contracts.
