# EXP-78 amendment 02: retain the native listing event safely

Before the final rerun, add a sanitized projection of the actual native
`skills/list` request and response to the committed observation. Preserve
the method, `forceReload` flag, requested cwd class, response count, exact
fixture name, and fixture path class. Omit unrelated skill names and absolute
private paths. The raw app-server event stream remains in the disposable
profile and is deleted after the probe; no credential or model request is
sent. This makes the decisive native event inspectable without publishing
personal or machine-specific path data.
