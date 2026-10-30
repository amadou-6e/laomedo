# Private local state

This module owns generic directory admission and permission mechanisms used
by the local Claude login mirror. Feature-specific paths and credentials remain
with their callers. It does not manage Docker, OAuth, lease policy or profiles.

Before source implementation, the R3 plan pins the exact legacy SIWC mechanism
and its exception translation. That wrapper must preserve existing behavior;
the stricter Claude path must not silently tighten SIWC's contract.

| Name / location | Responsibility and vocabulary |
| --- | --- |
| `utils.py` | Function-only lexical ancestor checks and directory restriction. Reject links/reparse points and checkout paths for the strict caller; change only its owned leaf permissions. |
| `models.py`: `DirectoryPermissionPolicy`, `DirectoryPermissionResult` | Canonical command policy and private SID observation; no credential values. `timeout_seconds` clamps command admission to the original deadline. |
| `windows.py`: `WindowsDirectorySecurity` | `system_directory` resolves the native command directory. `verify` checks the current owner and protected owner-only inheritable DACL without changing it. |
| `errors.py` | Class-only typed policy failures with safe fixed reasons; no raw subprocess output, SID, path or secret in public errors. |

Use `validate_*` for admission, `restrict_*` for permission effects and `verify_*`
for descriptor checks. An abstract `Base` or generic Store is not needed.
The strict Windows path will verify current-user ownership and protected DACLs
using Win32 security descriptors. It will refuse unsupported broad or ambiguous
permissions rather than infer privacy from a successful `icacls` exit alone.
POSIX admission requires the current owner and mode 0700. No hostile filesystem
race-free guarantee is claimed.

The SIWC wrapper preserves its legacy arguments, timeouts and exception
translation; it does not opt into stricter path admission. Strict callers use
`prepare_private_directory`, which restricts a newly created leaf but verifies an
existing leaf without rewriting its permissions. Internal tests cover that
separation. Real credential copying and provider validation remain pending.
