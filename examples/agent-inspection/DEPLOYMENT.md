# Agent inspection activation

Owner preapproved this implementation. After Claude review and passing checks:
- Upgrade only the dedicated example controller on 8784/8785 to reviewed source. Verify its one existing run is terminal, with no pending graph work and no owned container; preserve all campaign state, issue operations, binding, receipts, ledger 1/3 and independent lease service.
- Keep standing runners 8779/8780, skill source8782 and issue read8783 unchanged. The only configured inspector connection is http://host.docker.internal:8784.
- Replace viewer7864 frontend with the separate inspection build and read-only source mount work-issue-graph.local. Reuse its existing backend transport secret. No raw state/provider profile mount or credential change.
- Preserve saved flows, database/user, auto-login, catalog, current skill and customized writer-node code. Compare before/after; rollback viewer if any mismatch. Keep old viewer container available.
- Validate existing recorded run7433da21-1389-428a-b43b-75834fa57d99 through Inspect agent; final JSON is rejected, execution completed. No Run click, model turn or GitHub write.

Scripts: upgrade-agent-inspection-controller.ps1 runs first, then activate-agent-inspection.py. Existing custom-component mount, source-service and issue-service variables are preserved exactly; no catalog installation occurs. Final source and asset manifest are checked before viewer activation.
