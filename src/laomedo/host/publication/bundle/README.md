# Bundle verification records

`ContainerStageRecord` and `BundleVerificationRecord` in `models.py` construct
the initial new journal values. `to_record()` preserves every explicit unknown,
null and false value. These frozen write values are not stricter readers for
historical journals and do not replace the existing later diagnostic updates.

The stage functions still own Docker effects, exported bytes, exact cleanup and
the final status downgrade when cleanup is unconfirmed. In particular, a return
inside `try` still receives the existing `finally` dictionary updates; serialization
must not be moved ahead of that cleanup. No timeout or authorization changes here.
