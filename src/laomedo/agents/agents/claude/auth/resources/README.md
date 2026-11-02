# Access-only login writer

`write_login.py` is a container-side, function-only helper. The host sends its
source as a nonsecret Python command and the expected byte length as an argument;
the access-only payload travels through the owned session's stdin. No credential
value belongs in arguments, environment, output, logs or the resource itself.

`write_login` reads exactly the declared bytes before creating a temporary file.
It refuses linked paths and an existing refresh-capable login, removes only its
own stale regular single-link `.login-` files, and atomically replaces the access
file with mode 0600. It does not refresh credentials or copy profile state.

This helper is not independently installed or invoked during import. Its guarded
entry point exists for the isolated copy container. Real mirror acceptance is
separate from internal file-protocol controls.
