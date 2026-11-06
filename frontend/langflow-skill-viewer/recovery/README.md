# Local runner recovery

`RunnerRecovery` owns checking/start/cancel transitions for the local runner. `RecoveryPopup` presents those states; `PopupFrame` owns the viewport-bound notification stack and focus lifecycle. These controls do not rerun a graph or send a model request. The installer deploys this package to components/laomedoRecovery.
