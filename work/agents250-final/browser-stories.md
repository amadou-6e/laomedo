# Agent PR250 final browser acceptance

Source: refactor/205 a5378a99592d2a9feb43267e0645e29632c3acfe.
Environment: Windows, local Docker, pinned ACP images, real local runner APIs,
fresh private Langflow database, production-built frontend and headless Edge.
No provider doubles, response fixtures, child agents or live GitHub writes.

| Story | Observable acceptance |
| --- | --- |
| Discover and select a model | Explicit Refresh returns the runner's actual catalog; selected model/effort survive saved graph reload. Discovery creates no native model turn. |
| Run without an optional Skill | Browser Run on each actual provider creates one native execution, returns a useful answer grounded in the tracked README, and ends with terminal state and separately observed cleanup. |
| Inspect native Activity | Graph Activity shows the actual run/provider/native conversation, answer and observed usage; unknown or partial capture stays explicit. |
| Node controls | Advanced controls collapse independently, primary controls remain available, and graph reload preserves values. |
| Continue and inspect an existing session | Resume uses the retained native identity with a new attempt. Status does not create a model turn. No hidden reference is invented. |
| Cancel | An actual active run cancellation stops admission and reports separately whether exact resource termination is confirmed. An already-terminal run is not used as cancellation proof. |
| Backend offline and recovery | With the task-owned API stopped and Docker healthy, actual Run shows the descriptive shared popup; Start local runner restores API availability without rerunning the graph or submitting a model turn. |
| Error presentation | Failure has descriptive text, safe copyable details and actual recovery control; busy state is visible, cancel/dismiss does not imply execution cancellation, panel remains inside viewport. |
| Final owner inspection | Present actual saved graph links and evidence; keep PR250 unmerged until owner validates the final stories. |

Session/profile-browser management and interactive remote streams are not supplied
by this resource. No browser-profile restoration, authenticated remote browsing,
human takeover, stream FPS or GPU support is claimed.
