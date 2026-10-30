# Private local state — proposed, not implemented

This module will own generic directory admission and permission mechanisms used
by the local Claude login mirror. Feature-specific paths and credentials remain
with their callers. It does not manage Docker, OAuth, lease policy or profiles.

Before source implementation, the R3 plan pins the exact legacy SIWC mechanism
and its exception translation. That wrapper must preserve existing behavior;
the stricter Claude path must not silently tighten SIWC's contract.

| Name / location | Responsibility and vocabulary |
| --- | --- |
| `utils.py` | Function-only lexical ancestor checks and directory restriction. Reject links/reparse points and checkout paths for the strict caller; change only its owned leaf permissions. |
| `models.py` | Canonical permission command policy/result values when those inputs travel together; no credential values. |
| `errors.py` | Class-only typed policy failures with safe fixed reasons; no raw subprocess output, SID, path or secret in public errors. |

Use `validate_*` for admission, `restrict_*` for permission effects and `verify_*`
for descriptor checks. An abstract `Base` or generic Store is not needed.
The strict Windows path will verify current-user ownership and protected DACLs
using Win32 security descriptors. It will refuse unsupported broad or ambiguous
permissions rather than infer privacy from a successful `icacls` exit alone.
POSIX admission requires the current owner and mode 0700. No hostile filesystem
race-free guarantee is claimed.

This is a README-first design checkpoint. No permission code, credential access
or runtime validation is included yet.
