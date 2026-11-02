# Codex nested sandbox seccomp profile

The legacy Docker runner uses this default-deny profile so its non-root Codex
process can construct Bubblewrap's nested filesystem/network sandbox on Docker
versions whose default profile denies user namespace creation. No extra container
capabilities or privileged mode are granted; no-new-privileges remains enabled.
The deferred split controller retains its existing Docker default policy.

Upstream: Moby profiles, Apache-2.0, commit
`4b8214fc4971e06172938a1f1554ccff6647ee80`, `seccomp/default.json`:
https://github.com/moby/profiles/blob/4b8214fc4971e06172938a1f1554ccff6647ee80/seccomp/default.json

The original engine-version-specific URL was unavailable. This is an explicitly
pinned upstream baseline, not a claim to reproduce Docker 29.8.2's exact built-in
profile. All upstream rules, including capability gates and errno fallback,
remain unchanged. Three rules are appended:

- Allow clone only when CLONE_NEWUSER is present. Other namespace flags may
  accompany it, including mount, PID, network, IPC, UTS and cgroup. The original
  ordinary-process clone rule is preserved. s390/s390x are unsupported by this
  extension because their clone argument ordering differs; startup fails closed.
- Allow unshare only for the exact CLONE_NEWUSER flag value.
- Allow mount, umount2 and pivot_root, which Bubblewrap needs after entering its
  user namespace. Kernel capability checks still apply. The non-root controller
  has no CAP_SYS_ADMIN in its original namespace; granting these syscalls does
  not grant that capability.

clone3 retains the upstream ENOSYS fallback. setns, bpf, ptrace and other
capability-gated operations are not added by this extension. Nested user
namespaces expose additional kernel attack surface, including user-namespace
and network-namespace facilities such as netfilter/nf_tables that the default
profile blocks. A kernel exploit could affect Docker Desktop's WSL VM. This is
an explicit policy change, not an unchanged Docker default. Namespace flags and mount operations
must not be expanded without review and real positive/negative sandbox checks.

The runner verifies the packaged profile checksum before launch and launches its
verified immutable image ID. Missing or changed policy fails closed. The JSON,
provenance and upstream license must be included in installed packages.
The package directory is trusted host code: anyone able to modify it can also
change the runner. The checksum detects changes but does not eliminate the small
interval before Docker reads that file; protect installed package write access.
