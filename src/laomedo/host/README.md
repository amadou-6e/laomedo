# Host services

Host owns credentials, leases, mediation, publication and runner services.
`http.py` supplies the neutral outbound `NoRedirect` policy used by GitHub,
Skills and Langflow clients. It rejects redirect forwarding through urllib's
HTTPError path; callers own authentication and feature-specific errors.
Credential-specific refusal handlers keep their distinct error contracts.
