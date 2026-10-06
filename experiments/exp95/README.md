# EXP-95 same-user negative control

Run `python -m experiments.exp95.probe` from the Laomedo checkout. It creates
one disposable grant ledger outside Git, launches a child process under the
same host user, and calls `LocalGrantAuthority.issue()` directly without the
CLI confirmation. It uses synthetic Work Graph data, zero model turns and no
credential. Its expected result is one minted grant and
`boundary_passed: false`. That is evidence of the existing weakness, not a
human-authorization pass. The temporary ledger is deleted when the probe exits.
