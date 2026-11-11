# Explicit OpenCode native Activity acceptance - 2026-11-11

Implementation: 68415e3dd, no production changes during these runs. Explicit experiment transport_factory supplies OpenCodeAgentRuntime with a uniquely owned temporary private profile. Default production OpenCode host composition remains gated; preflight correctly reported unknown readiness / transport_configuration_only, not authenticated readiness. Native discovery returned49 connected models; selected opencode-go/claude-haiku-5-5, effort default.

User authorized choosing an isolated profile. The existing read-only active Console account bootstrap supplied access-only credentials into an ACL-restricted directory outside Git. No refresh token, credential, account identifier, native transcript or profile is retained here. Its expiry/fingerprint checks remain enabled. The all-model native bootstrap refused opencode_model_sdk_not_allowed for one Google SDK model. The explicit trusted fetch composition selected31 of32 Go routes supported by the existing allowlist before native routing validation. That successful subset does not establish automatic all-model bootstrap or default production composition acceptance.

## Fresh/resume success; late cancellation observation fails

```json
[
  {
    "stage": "routing_selection",
    "available_models": 32,
    "supported_models": 31
  },
  {
    "stage": "readiness",
    "provider": "opencode",
    "ready": null,
    "reason": "opencode_transport_not_verified",
    "scope": "transport_configuration_only"
  },
  {
    "stage": "discovery",
    "model_count": 49,
    "selected_model": "opencode-go/claude-haiku-5-5",
    "effort": "default"
  },
  {
    "stage": "fresh",
    "provider": "opencode",
    "status": "completed",
    "error": null,
    "capture_reason": null,
    "closed": true,
    "complete": true,
    "stream_state": "complete",
    "record_count": 5,
    "item_count": 3,
    "stable_replay": true,
    "thread_preserved": true,
    "cancel_confirmed": false,
    "answer_ok": true
  },
  {
    "stage": "resume",
    "provider": "opencode",
    "status": "completed",
    "error": null,
    "capture_reason": null,
    "closed": true,
    "complete": true,
    "stream_state": "complete",
    "record_count": 3,
    "item_count": 2,
    "stable_replay": true,
    "thread_preserved": true,
    "cancel_confirmed": false,
    "answer_ok": true
  },
  {
    "stage": "cancel",
    "provider": "opencode",
    "status": "completed",
    "error": null,
    "capture_reason": null,
    "closed": true,
    "complete": true,
    "stream_state": "complete",
    "record_count": 5,
    "item_count": 3,
    "stable_replay": true,
    "thread_preserved": true,
    "cancel_confirmed": false,
    "active_tool_observed": true,
    "requested": true
  }
]
```

Fresh/resume passed expected answer, complete native Activity, HTTP capture/store/display, stable repeated/paged reads and native thread preservation. The common tool-call trigger arrived during finalization: cancellation requested=true but status remained completed and cancel_confirmed=false. The harness failed its cancellation assertion. This observation is retained; it does not prove active native execution ignored cancellation. The temporary profile was automatically deleted while unwinding; no inference was repeated solely to test deletion.

## Active owned-worker cancellation passes

The corrected trigger requires the backend prompt flag still bound and an exact owned worker receipt whose named container independently reports State.Running=true. No production behavior changed. A fresh run was needed to establish the isolated profile's session; the previously successful separate resume was not repeated. Cancellation ran against that resumed session after a running credential-free worker was observed.

```json
[
  {
    "stage": "routing_selection",
    "available_models": 32,
    "supported_models": 31
  },
  {
    "stage": "readiness",
    "provider": "opencode",
    "ready": null,
    "reason": "opencode_transport_not_verified",
    "scope": "transport_configuration_only"
  },
  {
    "stage": "discovery",
    "model_count": 49,
    "selected_model": "opencode-go/claude-haiku-5-5",
    "effort": "default"
  },
  {
    "stage": "fresh",
    "provider": "opencode",
    "status": "completed",
    "error": null,
    "capture_reason": null,
    "closed": true,
    "complete": true,
    "stream_state": "complete",
    "record_count": 5,
    "item_count": 3,
    "stable_replay": true,
    "thread_preserved": true,
    "cancel_confirmed": false,
    "answer_ok": true
  },
  {
    "stage": "cancel",
    "provider": "opencode",
    "status": "cancelled",
    "error": null,
    "capture_reason": null,
    "closed": true,
    "complete": true,
    "stream_state": "complete",
    "record_count": 4,
    "item_count": 2,
    "stable_replay": true,
    "thread_preserved": true,
    "cancel_confirmed": true,
    "active_tool_observed": true,
    "requested": true
  },
  {
    "stage": "temporary_profile_cleanup",
    "removed": true
  }
]
```

The latter process completed successfully and deleted its temporary profile. Cancellation status/confirmation, complete Activity closure/capture, common display and replay all passed. The output field active_tool_observed=true in this run refers to the stronger independently observed running worker trigger; it is not merely a projected historical tool-call. Host-loss, daemon-wide cleanup and unsupported-model routes remain unverified. Claude independently approved the harness delta c11976467..271f9058c and supported these acceptance conclusions as disclosed. Optional harness notes do not invalidate the logged results; this later status correction changes no executable code. No whole-PR approval is claimed.
