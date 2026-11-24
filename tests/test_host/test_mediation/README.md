# Host mediation lifecycle

`test_lifecycle.py` composes the installed authority, lease service, mediation
store and loopback HTTP listener. Approval precedes binding and acceptance;
completion revokes the exact grant and blocks its bearer before transport.
Repeated revocation remains durable and cannot resurrect a grant.

Transport and Docker inspection use internal controls. No GitHub credential,
Docker daemon or model is used; these are not deployment or campaign acceptance.
Each case owns its temporary databases/listeners and joins its HTTP thread.

Run `python -m unittest discover -s tests/test_host/test_mediation -t tests -v`.
