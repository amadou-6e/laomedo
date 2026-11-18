# Assistant sidebar acceptance

Production implementation: Laomedo issue296 / PR299, base fc0cfa3ad, tested head
4ea6234eb. Specification: specs PR434, head75f21c7. Independent Claude review
remains pending because the existing reviewer session reports quota until
12:20 Berlin on2026-11-18. These checks do not authorize merging.

`check.mjs` uses the existing isolated application and its normal browser login.
It opens an actual saved graph, opens the shared chat history, types an unsent
draft, closes/reopens, resizes by keys and pointer, verifies narrow overlay hit
testing and opener focus, and checks the canvas and URL survive. All checks
passed on4ea6234eb. No inference, approvals or graph mutations are submitted.
Screenshots and private live app metadata remain ignored outside this archive.
An earlier attempt ran during a frontend rebuild and timed out; rerunning after
the completed build passed. Fixture unit tests are separate from these checks.
