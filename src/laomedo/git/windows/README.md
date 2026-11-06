# Windows Git process containment

This leaf owns Windows Job Object lifetime for budgeted Git reads only. The
`GitCommandRunner` is the single native launcher. No second
launcher, provider controller or general process framework is introduced.

The implementation creates an unnamed, non-inheritable job with
kill-on-close and no breakaway flags; launches through the shared Popen path with
`CREATE_SUSPENDED`; assigns that exact process handle before resuming its sole
primary thread. A failed assignment/resume never continues uncontained.
Nested-job admission is required on the current Windows platform; an incompatible
outer job must fail closed, without a breakaway or taskkill fallback.

| Owner / name | Method vocabulary and responsibility |
| --- | --- |
| `tree.py`: `WindowsProcessTree` | `attach(process)` binds the exact suspended process; `resume(pid)` resumes only its primary thread after assignment; `active_processes()` queries job accounting; `terminate(deadline)` requests job-wide termination and waits for zero active processes within the cleanup budget; `close()` releases the owned handle. |
| `models.py`: native ABI structures | Describe only Win32 memory layouts for job limits/accounting and thread enumeration. These are ctypes structures required by the native API, not application DTOs or replacements for canonical Pydantic Git request models. |
| `settings.py`: fixed ABI values | Name the documented Windows flags/information classes once; no external settings or configurable breakaway policy is introduced. |

An exited root and taskkill's numeric exit code are insufficient descendant
proof. A successful result also requires an empty job; surviving children must
be terminated and accounted for before returning. Uncertain cleanup retains its
fail-closed category. Interrupts remain interrupts with an explicit
cleanup observation, rather than being converted into ordinary Git errors.

Use stdlib ctypes at this narrow boundary. pywin32 is currently an optional
runner dependency, whereas source/Git reads are core functionality; making that
extra mandatory is unnecessary. The ABI controls cover actual Windows nested-job admission
and successful roots that leave a child. POSIX and WORKSPACE/HOST_TRANSPORT
profiles use their own launch/cleanup paths. Actual Windows process controls cover these paths; they are internal
mechanism evidence, not live HTTPS source, graph/browser or owner acceptance.

The design follows Microsoft's documented [Job Objects](https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects),
[nested jobs](https://learn.microsoft.com/en-us/windows/win32/procthread/nested-jobs),
[suspended process creation](https://learn.microsoft.com/en-us/windows/win32/procthread/process-creation-flags),
[thread enumeration](https://learn.microsoft.com/en-us/windows/win32/api/tlhelp32/nf-tlhelp32-createtoolhelp32snapshot),
[ResumeThread](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-resumethread)
and [job accounting](https://learn.microsoft.com/en-us/windows/win32/api/winnt/ns-winnt-jobobject_basic_accounting_information)
contracts. These references describe the mechanism, not Laomedo acceptance.
