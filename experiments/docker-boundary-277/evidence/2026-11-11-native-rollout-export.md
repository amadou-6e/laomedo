# Native Codex rollout export on recorded Docker binding - 2026-11-11

Implementation:0fdacaa78; generic recovery mechanisms unchanged from9bcb0149c.

One real user-authorized Codex prompt using the existing access-only session adapter, model gpt-5.6-sol/low. The completed native run exported its actual retained rollout through the production shared Docker jobs on its recorded endpoint/profile/image. The 37034-byte JSONL had matching session identity; all three export jobs cleaned up their exact receipts. Temporary Codex profile and private state were removed. No raw native content, account metadata, credential or private profile is retained here. This is actual native export acceptance, not synthetic JSONL fixture acceptance. It does not establish host-loss during export or other provider restart behavior.

```json
{"stage": "native_fresh", "status": "completed", "error": null, "answer_ok": true, "model": "gpt-5.6-sol", "effort": "low"}
{"stage": "native_rollout_export", "bytes": 37034, "thread_identity_matches": true, "recorded_profile_used": true, "recorded_endpoint_present": true, "pending_export_receipts": 0}
{"stage": "temporary_profile_cleanup", "removed": true}
{"stage": "private_state_cleanup", "removed": true}
```

New harnesses and these conclusions are fully unreviewed - reviewer pending. No whole-PR approval.
