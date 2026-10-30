# Host mediation boundary

`RunGrantAuthority`, `MediationStore` and the service own authorization, replay,
expiry, effect accounting and GitHub credential custody. New metadata values live
in `models.py`: `MediationServiceRecord` describes the local discovery file;
`AuthorizedLeaseScope` groups the admitted repository/branch, operations,
connection generation and explicit PR targets. `to_record()` preserves optional
fields and the private Python set/int-keyed-map callback contract where applicable.
Neither value object authorizes itself or performs a provider request.

ACP supplies the Agent session protocol. It does not repair the native-command
networking boundary. The experimental file-mailbox relay remains unpromoted;
production repair is separately tracked in issue #215. Retain disabled native
command networking and host-owned effect authority when designing that follow-up.
