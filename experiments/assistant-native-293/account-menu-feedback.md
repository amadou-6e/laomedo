# Account menu and slash input feedback, 2026-11-20

## Owner-selected account defaults (feedback19-22)

The owner superseded mandatory explicit selection: new chats should default to
an available account. Source56479f074 defaults the first connected ready account
for the current profile/provider and preserves explicit choices and existing chat
bindings. The removed selection sentence is replaced by placeholder/trigger
Select an account or No account available. Without a binding, no stale model or
effort appears. Same-account reselection no longer clears models.

71assistant UI tests PASS, including profile-list fencing (a new test caught stale
model discovery before the account-owner guard was complete), ready-only defaults,
explicit override/list refresh and empty state. Build PASS1m17s; CI PASS at source
head. Specification5bbd464 updates contract and editable AC-293; validator1845
files/6projects/0errors. No Python changes; prior94backendtests remain historical
unchanged-backend evidence, not a new run.

Real shared integrated browser: new chat defaulted the actual saved Codex account,
loaded models, enabled Send for an unsent test draft, and opened the model/effort
popover. Switching to unconnected Claude showed No account available, disabled
Send and no stale effort. Returned to Codex; test draft cleared without sending.
No prompt/native command/graph executed. Actual full-view screenshots are private
ignored review artifacts, never archive attachments. Existing user conversation
and saved account preserved; stable preview port and tab reused.

Same Claude session reviewing implementation2957a6e3a..56479f074, specification
4f49b1e..5bbd464 and three actual images; this delta is fully unreviewed, reviewer
pending. Earlier approvals do not cover it; nothing merged.

Final same-session review of56479f074 / spec5bbd464: Implementation APPROVE with
71UItest/build/CI conditions fulfilled; Specification APPROVE. All three actual
desktop dark images inspected and matched. Visual INCOMPLETE for narrow/light/
focus states. Optional A1-A3, no blockers. No source changes after review; both
existing PRs updated, nothing merged. UI left on Codex with its default account
and discovered models; no test draft or extra model prompt remains.

## Completed reviewer correction

After quota restoration, the same Claude reviewer approved the UI corrections
and specification4f49b1e, but found S1: logout could await a failing database
before removing tool authority. Correction38253df86..2957a6e3a now fences known
raw/provider/canonical identities and removes contexts/tokens synchronously,
then persists revocation with cleanup in finally. Lookup/write failure and
event-gated timeout cancellation tests pass with actual signed-token refusal.
Eight concurrent first renewal admissions pass on file-backed SQLite.

Focused reviewer recheck: S1 verified-fixed, S2 settled for SQLite; Implementation
APPROVE at2957a6e3a, conditional on fullsuite and Black, both now met:94assistant
tests PASS214.055s, Black956 PASS, all required CI PASS. UI686tests and final
build remain unchanged frontend evidence. Specification APPROVE4f49b1e. Visual
INCOMPLETE; no new live logout/provider checks claimed. No source changes after
review, and no merge performed.

Remaining limits: an unseen renewal lost before persistence cannot recover the
earlier approval root; failed durable revoke can lose its memory-only fence at
restart. Per-item native cleanup may still stall or stop on an error; safe alias
pruning requires expiry accounting. These were disclosed, nonblocking review
items. The existing integrated preview was left running to preserve the working
user session; the later logout-only source correction was not loaded into it.

## Later renewal fix and explicit restart limitation

The earlier UI-only checks below are historical evidence, not the final backend
claim. At dbe659501 the real preview exposed a normal app-JWT renewal bug: pending
native approvals became unavailable after reload. The correction preserves the
verified browser lease with durable fingerprint aliases, including logout via
an unseen renewed token. No bearer is stored. All 91 assistant backend tests pass
(230.029s), including actual signed JWT verification, real ProviderConnections
renewal/reconstruction, SQLite expiry/owner/collision/revocation checks. Black956
and CI pass at that head.

Real integrated-browser check at dbe659501: a fresh /mcp proposal retains enabled
Approve/Reject after reload. Read-only owned database audit reports two verified
renewal aliases for the proposal root, pending state and authority not revoked.
The proposal was not approved or executed. Screenshot stays private/ignored.

An additional ordinary send after the preview SERVER restart refused with the
existing Codex resume_after_runner_restart_forbidden safeguard, before another
model turn. This is not a successful send or a JWT failure. The current spec
explicitly preserves runner-restart fail-closed rules. We did not weaken it.
38253df86 adds the missing human-readable error/recovery and a real shared error
renderer test. Updated frontend build PASS1m19s; 686 tests across assistant and
shared error rendering PASS (17 suites; includes 69 assistant UI tests). New
linked conversation returned ACCOUNT-FINAL-SEND-293. The real database read
confirms completed, no error and exact marker response. The final built error
copy was visibly verified in the old chat, then the fresh working chat reopened
in the same integrated CoBrowse tab. No transparent continuation
after authenticated runner restart claimed. Earlier conversation remains intact.

Claude correction recheck is quota-blocked until18:50 Berlin. Initial UI review
covered cbb110473..9296cc4fa with REVISE; d4feb411f corrections await recheck.
The later auth fix and restart-error copy are fully unreviewed, reviewer pending.
Specifications 4f49b1e define the durable renewal/logout invariant; validator1845
files/6projects/0errors. Nothing merged.

Source cbb110473..9296cc4fa implements compact account rows, shared provider icons, a selected-row highlight, separate account-settings footer, aligned welcome cards, explicit blocked-send guidance and draft preservation. Review correction d4feb411f reserves AP-2 candidate command names across Codex, Claude and OpenCode and improves the account trigger's accessible description. Spec head f536052 records those definitions.

## Actual integrated-browser acceptance

Rendered build9296cc4fa on the normal saved-account preview. Selected unconnected Claude: visible named account guidance, disabled model picker/Send, editable draft. Switched to connected Codex, explicitly selected its real saved account, observed discovered models. Submitted a fresh ordinary message and received ACCOUNT-MENU-SEND-293. A deliberate /status extra refusal disabled Send; editing to /sta immediately removed that definite input error and re-enabled Send. /sta was submitted as an ordinary model message and received a response. Selected real /mcp from the observed slash menu and submitted it: a durable Run /mcp approval card appeared, with Approve/Reject. It was NOT approved or executed by this acceptance. No graph edited/run. Selected final native receipt: two model turns, zero executed native commands, completed and controller/Docker cleanup confirmed. User-owned history preserved.

A fresh browser read verified all five supported Codex command previews before session creation; only initial status is selectable, other previews are disabled until native advertisement. This is findability, not cold execution of all commands. The existing initial-status lifetime contract remains unchanged. Screenshots are private ignored local review artifacts, never publication attachments; account display identifiers are not archived here.

## Checks and limits

69 assistant UI tests pass at d4feb411f through the exp-only pinned preview Jest wrapper (Windows root matching and real remark-gfm ESM transforms; no new message-render mocks). Build9296cc4fa passed in1m16s; reviewed-correction build is running. Spec validator1845files6projects0errors. Existing backend820tests/4skips pass cbb110473; this feedback delta changes no Python or adapters. Required exact-head CI to be recorded after completion.

Claude initial review cbb110473..9296cc4fa: Implementation REVISE U1 (known-command guard was Codex-only), Specification REVISE (define each provider's known names), Visual INCOMPLETE although actual full-window captures matched the requested appearance. Corrections/tests/source evidence await focused recheck. No merge performed. No live Claude/OpenCode execution or narrow/light-theme acceptance claimed.

## U2 parser evidence (zero model calls)

Normal assistant payload prepends ASSISTANT_INSTRUCTIONS and User message before text (runtime._job). Shared ACP transport sends one complete text block. ClaudeAgent._prompt additionally JSON-encodes the task for ordinary calls, then passes that unchanged to client.prompt. Claude ACP0.98.0 local command checks use leading/exact matches: firstText.startsWith('/'), parseMcpCommand trimStart startsWith('/mcp'), isUsageCommandText exact '/usage', promptToClaude MCP rewrite anchored at start/end. They do not turn an interior slash line into a native operation.

OpenCode service detectSlashCommand joins all text, trims it and returns immediately unless startsWith('/'); only a detected command reaches session.command, otherwise session.prompt. Inspected opencode-service.ts exactly matches public anomalyco/opencode v1.18.33 packages/opencode/src/acp/service.ts after newline normalization, SHA256238750d52e220080db7b7f4992432fbfc7fb7ec5a15a6175460f8f0832a2c8de. The local Claude package metadata identifies0.98.0, matching the Docker lock.

check-prefixed-slash.cjs extracts the actual inspected native parser function bodies with TypeScript and runs them without dependencies or provider access: six prefixed cases across OpenCode slash, Claude MCP and Claude usage parsers (18 assertions), plus three bare-command positive controls PASS. No model/native API calls. It does not prove the entire SDK/live provider flow and is not presented as that acceptance. Evidence source hashes are printed by the harness. Production tests do not import or fetch exp.

## 2026-11-21 feedback1-3

Production ceee6f691, specification7a62993. Owner reported missing default account and both settings links not opening. Prefer connected ready, then connected expired-token account for existing guarded discovery/refresh. Revoked/reauthorization-required/unavailable never default. Existing saved bindings/owner fences unchanged. Both links now navigate current-tab Settings > Providers.

75 UI tests pass19.512s; Vite reports successful build1m23s (PowerShell native stderr warning wrapper returned1, output contains completed asset build). Specs1845files6projects0errors. Required current production CI passes. Real shared integrated browser: new Codex chat automatically displays saved account/model; Manage accounts reaches rendered Providers page; return empty chat, switch unconnected OpenCode, Connect account reaches rendered Providers page in same tab. No prompts, native commands, credential copying or saved chat mutations. Current composer was empty before reload. Historical expiry of actual account was not directly inspected; expired fallback coverage is supporting unit evidence only. Private screenshots retained outside Git. Same reviewer session pending; no merge.

Focused corrections b3549a683/spec3a52ffc: held OpenCode go-key/unverified custody row is default-eligible without changing backend auth semantics; missing custody remains revoked. Settings links retain profile-scoped unsent drafts/provider and restore once. Existing editor beforeunload guard verified in source, not a new live unsaved-editor test. 78 UI tests PASS15.103s; Vite exit0 PASS1m17s; currentCI allpass. Actual OpenCode blocked state with unsent test draft -> Connect account -> Providers -> /assistant restored same draft/provider. Test text cleared and Codex reselected. No sends. Same reviewer F1/F2 verified-fixed at correctedhead, implementation APPROVE conditionalCI nowfulfilled; visual INCOMPLETE for narrow/light/focus/editorprompt/liveOpenCodekey. Spec source-inspection completion pending after reviewer disclosed summary-only spec reading. Optional stale-draft snapshot after canceled navigation and refreshhint remain disclosed, no merge.

## Feedback4/5, provider wiring status

Production9c7db7263/spec7bd9dcf: provider cards320px maximum, explanatory sentence width unchanged (stated narrower assumption after unanswered width preference). Composer editable while busy/active/pending; Send and exact retry admission remain fenced. Late native acknowledgements preserve newer drafts; creation transfers newer text to actual conversation; definite refusal retains submitted plus newer text. Supporting78UItests PASS13.351s including pending typing/no second Enter dispatch; final Vite exit0 PASS1m16s; CIallpass; spec0errors. Actual shared desktopdark screenshot shows narrower cards and unchanged sentence. No additional native/model turn submitted for this packet; real loading typing not separately live-tested. Current preview only Codex connected. Source wired Claude/OpenCode through saved-account provider controllers; executable builtin policy Claude compact, OpenCode init/review (compact explicitly unsupported, not implied by reserved candidate names). Same reviewer pending for thisdelta; prior source/spec approvals unchanged. Private screenshot outsideGit; no merge.

Feedback4/5 review at9c7db7263: Implementation APPROVEconditionalCIfulfilled, Spec REVISE Z-1 leftover read-only clause; VisualINCOMPLETE with desktopwidth rendermatchingstated320pxassumption. Spec2e5cb19 corrects editable wording and diagramgeometry. Tests-only5fc8f0dad adds deferredcreation/newdrafttransfer, deferrednativeack edited/unchangedtext, and definite-refusal/newdraftmerge regressions.82UItests PASS13.477s; actualimplementation/render unchangedfrom9c7. Initial newtest selector mistake Sendmessage correctedtoactualSend; no productionworkaround. FocusedZ1/Z2recheckpending. No additional native/modelprobe. No merge.

## Built-in command catalog and Claude controls (2026-11-21)

Owner clarified built-in slash commands only and confirmed narrower cards. Production discoverycc8f7105f includes all11 pinned Codex ACP entries and displays observed disabled commands with reasons rather than hiding them. Known Claude names reserve native dispatch before the first prompt. Guarded no-argument Claude usage/context/mcp addedeb749e8d5; native completion strengthened0c0b30c56 to root local-output receipt, successful root result with zero output tokens, ACPend_turn and actual output. Report output is neutral, not model prose/service-health certification. Provider-aware display/copy/export suppresses model Activity duplication and prior usage. Copy-button omission corrected96a2f6588 with actual clipboard click regression.

Supporting verification:98UItests PASS14.355s,76Claude tests PASS24.576s, wholeBlack956 exactcheckPASS; productionbuild0c0b30c56 PASS1m16s. Specs ee4e6c4 validator1845files6projects0errors(existinglargefilewarning). Earlier94assistantbackendtests PASS at eb749. These are fixture/component checks, not native integration acceptance. Backend restarted using same saved-profile preview and stable port; existing integrated CoBrowse tab reloaded. Real menu renders for Codex11entries/Claude4previews captured privately, no tokens or personal captures committed.

Review: discovery reviewedAPPROVE; Claude eb749 initialREVISE N1, spec3d58APPROVE. Focused0c0 review resolvedN2neutraloutput/N3requiredresult/N4scopedusage and mostN1, foundN1aCopydisabled due missingprovider. Correction96a2f6588 recheckpending. VisualINCOMPLETE, no all-command completion or merge-readiness claim. CurrentClaude OAuth requires owner code entry; OpenCodeGo key not provided. No ambient credentials copied. Plan/goals/repository selection/app-owned account/rename routing scope decisions remain with owner; not silently enabled or deferred by reviewer. Unrelated experiment probes preserved.

## 2026-11-22 saved-provider live validation

Production1ca39502e/spec5b176ef: owner keptplan/goal deferred, repositoryreviews unavailableinscratch, authorizedappaccount/renameroutes.128UI/provider testsPASS19.473s,77ClaudetestsPASS25.221s,Black956exactPASS,Viteexit0PASS1m19s,currentCIallPASS. SameClaude reviewerAPPROVE1ca39502e and spec5b176ef; VisualINCOMPLETE. P1pollbuttonssilentdropfixed withpollingflag whileinputremainsselectable; P2backgrounderrorretained; P3connectargsreserved. OwnerconfirmedClaudeinputselectionreport. No production change after review.

NormalUI connectedClaudeaccount and owner savedOpenCodeGo key. RealClaude freshreplypassed. Initialusage atoldcode returnednativeviewbutcompletionunknown because validator missed currentassistantlocal_command_run receipt; originalunknownpreserved and not automaticallyreplayed. ActualCLI2.1.310 localrun command/emptyargs/uuid+matchingzerooutputresult now validated; callback capturesmetadataonly. Freshnewconversation oncorrectedcode: /usage,/context,/mcp allcompleted withnativeoutputs, neutralOutputreceived andCopyenabled. MCP reports2serversconnected; no graph edits/runs. Private screenshots ignored outsideGit, no personal usage/accountdata published. No fixturetest counted as live.

OpenCodediscoveryinitiallyrefusedstale workerrecipe. Controllerfingerprintmatched. Workerwasunused, preservedoldimageunderbackuptag and rebuiltregisteredtag throughsharedDockerRuntime. Ownerpreviouslyapprovedowner-only builddirectoryrepair reapplied afterextra sandboxACE causedadmissionrefusal; verifiedbeforebuild. Rebuiltworker16a59d360d89, expectedrecipeaf899c466852. No runningcontainers/volumesdeleted. Automaticrebuildpolicytrackedseparately; no productionpolicybypass. OpenCodeliveacceptancecontinuing.

## Corrected Windows mount diagnosis and staging (2026-11-22)

### Follow-up: chat admission and terminal outcomes

Owner-reported first-step errors exposed two independent defects. The host
required a Codex/Claude single-container ownership receipt even after OpenCode
confirmed cleanup of all its owned resources. Production `1cfd103b3` consumes
OpenCode's actual terminal cleanup guarantee; unverified cleanup still fences.
The transparent native model radio now covers the visible row, preserving its
appearance and keyboard semantics. CoBrowse selected `opencode-go/gpt-6-luna`
normally. Real fresh and resumed paid Go prompts both returned the requested
markers and settled with no error banner. Twenty-four reconciliation tests and
129 then 130 UI tests passed. Same Claude reviewer approved `1cfd103b3` and
duplicate-error display `4247ec0a3`.

Native `/init` was actually approved and run in the isolated scratch target. It
returned a terminal explanation that no repository was present; one admitted
worker tool returned Git exit 128. It did not establish an AGENTS.md write and
is not successful acceptance. `e89618a5b` distinguishes this known failure from
unconfirmed execution without relaxing successful-command evidence. Rechecking
the immutable real export with `check_retained_native_outcome.py` and its admitted
manifest produces `opencode_native_command_failed`; this is retained-evidence
verification, not a fresh model run. Original history is unchanged. Spec
`08776b2d` explicitly preserves the error-free success requirement. Claude
approved both revisions. `/review` remains untested.

CI exposed a current fixture missing `_controller_staging` and an undocumented
internal cleanup error string. Fixture initialized and existing documented
cleanup category reused (`29a458a65`, Claude approved). Seventeen native and
finalization tests, six catalogue/config tests, 761 UI/provider/error tests and
Black's 956-file check passed. No unrelated Codex test modification staged.

New-conversation discovery still defaulted to global `opencode/*` free models
that the Go-authenticated ACP session did not advertise. Pinned CLI help verified
the supported `models [provider]` syntax without credentials/network/model calls.
Production `3820a571a` scopes discovery to `opencode-go`, the admitted credential
provider. Fourteen affected checks pass; final real default-selection acceptance
and focused reviewer recheck pending at this evidence checkpoint. No merge or
all-native-completion claim.

Earlier MAX_PATH diagnosis DISPROVED: public300-character original paths work through bothDockerCLIandSDK, and same-file8.3aliases didnotfixactualcatalog. Helpercheckpoint5a7ef2d3c removedbyd808b23ca; resultingtreeEXACTsameasreviewed1ca39502e (gitdiffempty), no obsoletehelper/testsretained. File-levelACL/strictowner-onlydummyprobesdidnotreproducecauseeither. Actualprivatecatalogparentdummyfile221charsreadable, freshcatalogUUID/controllerUUID/config284chars+viewfailEIO; compact252charcasealsofails. Actualconfighostexistsandnativeconfig/authsameowner; authreadable. RootDockerDesktopparent-treecreationissueunresolved, donotclaimexactcauseestablished. Publicdummycontrollerfilesinprivateprofilechild227charsreadable. Probeharnessopencode_bind_probe.py reproducesdirectorycaseswithoutreadingmountingcredentials; onlynewpublicfilesarecreated/removed.

Production1a4e75db7Windowsstagesonlydisposablecontrollerconfig/viewinprofilechild; authnotcopied, originalreadonlycredentialmountunchanged. RealOpenCodeGo modelcatalogNOWPASS, includingGo-backedmodels. UsermodelselectionneededbecauseCoBrowseclicksonsr-onlyradiosreturnelement_obscured; no inference/keyvalidationclaimyet. SameClaude reviewImplementationINCOMPLETE S1crashleftovers/S2readonly. Corrections9565ee98e: exactownedstagingchildrenpurgedonexistingconfirmed-disconnectboundary; nostartupsweepofliveprofile; copyfailureinsidecleanupscope; canonicalhelperonlyremovesverifiedownedchildandclearsreadonlybitoncontainedcopyafterreproducedWindowsPermissionError, neveronsourceorcredentials.85then86OpenCodetestsPASS17.184s;59connectionsPASS34.804s andtargetGo3PASS1.425s;Black956exactPASS. Newcleanupfocusedrecheckpending. PrivateClaudeimagesreviewedwithoutblockingvisibledefectbutVisualINCOMPLETE. No secrets/privateimagespublished; no merge/all-commandcompletionclaim.

Final acceptance on3820a571a: actualsharedpicker33modelsallopencode-go/, desktopdark screenshotverifiedsameappearance. Withoutchangingdefaultmodel freshCHAT-READY promptreturnedexactanswerandsettledwithoutbanner. RequiredCIallPASS. ExistingClaude reviewerAPPROVE29a458a65..3820a571a and spec08776b2. Finaldesktopimagecheckpending; broadernarrow/light/pollingunverified. No furtherproductionsourcechanges, noreplayofoldinit, /reviewuntested. Previewleftonworkingconversation55753.
