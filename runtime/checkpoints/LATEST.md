# Plotkeeper Checkpoint

## CURRENT

Track: `PLOTKEEPER V0.1.12 LISTENER PID IDENTITY`

## PLOTKEEPER V0.1.12 LISTENER PID IDENTITY

- step: PR-open
- note: Live v0.1.11 install proved the legacy owner record names the venv wrapper while the TCP listener belongs to its direct child; v0.1.12 records the real socket owner and tightly migrates the legacy relationship.
- branch: hotfix/v0.1.12-listener-pid-identity
- head: 594b4dded6eb3fe9e6d63424a5097f97b3f7c55d (reviewed source candidate; checkpoint-only successor records it)
- next_cmd: `gh pr checks 6 --watch --interval 10`
- validations: legacy wrapper PID 26296 and listener child PID 18052 relationship proven read-only; command line, creation lineage, connector, port, and executable wrapper identity match; positive/direct-child and wrong-parent/wrong-command focused regression green; v0.1.12 contract hash `1457d84144c4e5c75249c8df62ef216c2c8f633258e09a2f49dd987abbddf895`; release pointer canonical hash `a5568b556dbdb77c94c800a8e2416c183fdae987ca158e6ac6340e49d0792fe1`; 99/99 tests; diff check green

## PLOTKEEPER V0.1.11 OWNER TIME PRECISION

- step: PR-open
- note: The reviewed v0.1.10 package installed but its owned restart exposed legacy whole-second records versus CIM fractional ticks; v0.1.11 preserves legacy precision while keeping new invariant records exact.
- branch: hotfix/v0.1.10-owner-time-precision
- head: 05ee7500f388edf39ebcebed97e9df8d16a1cf49 (reviewed source candidate; checkpoint-only successor records it)
- next_cmd: `gh pr checks 5 --watch --interval 10`
- validations: public main lease-restored to reviewed v0.1.10 `b73eaa69e7c481c2857b35d6c1975d138088d7c6`; precision fix preserved on dedicated branch; legacy fractional, exact invariant equality, and exact mismatch focused regression green; v0.1.11 contract hash `8af6dcd81a3944a5560cf6d9ac42775719abbdea0755d5503c4539bd7b091823`; release pointer canonical hash `bbed1b31909dcde147532167098c845c0b6121cff321ad60e9124737483edd38`; 98/98 tests; diff check green

## PLOTKEEPER V0.1.10 OWNER TIME IDENTITY

- step: PR-open
- note: The v0.1.9 package installed, but restart failed closed because the same Windows process creation instant was serialized in 24-hour form and returned in 12-hour form; v0.1.10 canonicalizes the instant without weakening ownership proof.
- branch: hotfix/v0.1.10-owner-time-identity
- head: af1c66d778592b30e3ee7228d8b2745aacdfc539 (reviewed source candidate; checkpoint-only successor records it)
- next_cmd: `gh pr checks 4 --watch --interval 10`
- validations: v0.1.9 release is immutable at `979f95577609fbdbccc47d5f854fd4eaf924a377`; v0.1.9 package files installed but owned v0.1.8 listener remains healthy; mismatch proven to be equivalent locale-formatted creation timestamps; v0.1.10 contract validates at `70ae32cba46f5fef9848d8a40cf2f173420a70a1303166f7e37029c5bb130aec`; release pointer canonical hash is `55547f92e4b6002d71e95487e515283b6c1702eeb1c9c230f3ba561a770e5d2c`; 98/98 tests; PowerShell parse and diff check green

## PLOTKEEPER V0.1.9 RELEASE HYGIENE

- step: post-green-tests
- note: The reviewed v0.1.9 product patch is unchanged; an append-only enforcement successor now exposes the full cumulative authorized path set to the verifier and trusted guard's single-contract model.
- branch: hotfix/v0.1.9-release-hygiene
- head: c58944aee61ed7963203478c0002da8b9e1f7e25 (reviewed enforcement candidate; checkpoint-only successor records it)
- next_cmd: `gh pr checks 3 --watch --interval 10`
- validations: restored parent contract `PROD-20260814-plotkeeper-v019-release-hygiene` validates at `4edee01b3ee3cd19b25ab4bcb87801482c36fefd88765f45965de725587f6771`; review remediation validates at `1621339dedb4313817067a3782d2263ca2b6b39cc2b7972ef3e6ffadcd255350`; enforcement successor validates at `a3a04bcfa1f280e9d1ff3be9fd5170292193e8316c11a5315b88263019b20e46`; release pointer canonical hash is `3784acf02ca8e64497685a3bc5586ba9f3ad909f9988cc9192a0b2692b5ba0e2`; 97/97 tests; generated owner record is ignored while present; diff check green; protected v0.1.8 baseline remains immutable

## PLOTKEEPER V0.1.8 INSTALLER HOTFIX

- step: PR-open
- note: v0.1.7 package publication succeeded but its default no-Port installer path dropped an empty argv value and failed before connector/service readiness; PR 2 carries the sentinel fix and is being promoted as immutable v0.1.8.
- branch: hotfix/v0.1.7-installer
- head: a37597eec7edf2de23b9d250c12002c248474480 (reviewed source candidate; this checkpoint-only successor records it)
- next_cmd: `py -3 -B -m unittest discover -s tests -v && gh pr checks 2 --watch --interval 10`
- validations: active hotfix contract validates at `8b2bc02ee5f18bbf30390e259789fcf88597195c323891cd8acc7d7dde3555f2`; executable isolated no-Port install regression passes and persists a valid loopback connector; prior full suite 96/96; Node and PowerShell parse green; git diff check green; PR 2 updated with v0.1.8 release surfaces; public v0.1.7 remains immutable

## PLOTKEEPER V0.1.7 LISTENER OWNERSHIP

- step: post-green-tests
- note: Lifecycle ownership now requires the persisted PID record's connector path/port, repository root, executable path, creation time, and command-line hash; real foreign subprocesses with spoofed plotkeeper.cli argv and dashboard HTML survive both start and install rejection paths.
- branch: release/v0.1.7-plotkeeper-surface
- head: 972429e0413ea790c1b4cd576cece924b6dd4de7
- next_cmd: `Independent production-goal review of the exact diff; no install/live-service mutation is authorized`
- validations: active contract validates at d0a5e050f7e998ce635276c1bbb780d9e76611fd0777ac00cdb0a85c7a42b24e; focused ownership/docs tests 9 passed; full suite 85 passed; PowerShell parser passed for install.ps1/start.ps1; ownership scripts contain no -match/HTML inference; controlled fixture command line and spoof HTML were observed; git diff --check passed; controlled foreign PID remained unchanged; no install, live-service mutation, commit, or push

## PLOTKEEPER V0.1.7 PR RELEASE

- step: post-green-tests
- note: PR 1 remains open and unmerged; CodeRabbit findings are corrected, CI is green, and final v0.1.7 version, changelog, release, rollback, and verifier surfaces are updated for final review.
- branch: release/v0.1.7-plotkeeper-surface
- head: a0a0406 + final release surfaces
- next_cmd: `git diff --check && py -3 -B -m unittest discover -s tests -v`
- validations: sanitized release contract validates at `9ed96e422737d84ce29d0d573656d6c07326748c2c9d26635a40ef40a8687f1b`; 82 tests before final docs; Ruff E702; Node syntax; diff check; two CodeRabbit passes reconciled

## PLOTKEEPER PLAN RECONSTRUCTION

- step: post-green-tests
- note: Fallback runs now offer one explicit, idempotent reconstruction request that resumes the exact enrolled Codex root at run.cwd, requires evidence-backed recovery of the original SpecSwarm artifacts, syncs the exact run, reads rows back, and reports corrections without filename guessing.
- branch: main
- head: a6db3162fd90cde039c112cab11ce023a2c78845
- next_cmd: `py -3 -B -m unittest discover -s tests -v`
- validations: successor contract `PROD-20260813-plotkeeper-plan-reconstruction` validates at `080d26e7688c9b7032fae93113bfad24f57b6bfc89638d9286fccea519b380dc`; exact resume session/cwd/prompt/idempotence/synced-task guards pass; 76/76 tests, Node syntax, and diff check green

## PLOTKEEPER CANONICAL TITLE TASK POPOUT

- step: post-green-tests
- note: Phase-start authority was sealed before mutation; Codex session-index titles now override prompt previews, empty active runs expose one truthful thread-level fallback task, headers clamp to two lines, and pop-out uses an isolated Chromium app profile.
- branch: main
- head: 31ab330a1f6f2ef959f782330a292a713acd99a9
- next_cmd: `git diff --check && py -3 -B -m unittest discover -s tests -v`
- validations: contract `PROD-20260813-plotkeeper-canonical-title-task-popout` validates at `022e73876c51b5b52e803a75a0b8ee2a7244c102cbe53d5430c46d769f6f09bc`; exact MoonMarket fixture resolves `Review core spec`; fallback/synced-task precedence tests pass; isolated launcher arguments prove app mode, dedicated profile, and exact URL; 75/75 tests plus Node/Python/diff checks green

## PLOTKEEPER POPOUT PRIVATE CONNECTOR

- step: post-green-tests
- note: Exact run-bound external-browser pop-out and one persisted OS-assigned private loopback connector are implemented across service, installer, startup, CLI, Codex config, SpecSwarm, UI, tests, and docs; installed lifecycle and independent review remain.
- branch: main
- head: 58f3dee2bdca8109be78e26bf245275787ddf453
- next_cmd: `.\scripts\install.ps1`
- validations: final active contract `PROD-20260813-plotkeeper-popout-private-connector-final` validates at `a157f786d6291f287f4cc70f033536b2e1fc1dc83690dd145a412047001b2d2e`; 73/73 tests green; focused origin/path/browser-opener attacks green; Node/Python/PowerShell syntax and git diff check green; generated connector is exactly ignored

## PLOTKEEPER RESPONSIVE RUN PICKER

- step: post-green-browser-qa
- note: Native viewport-unbounded run select replaced by an accessible project-grouped listbox; long labels are compact and bounded, and Run Detail remains a full-width row below Workstreams at every supported width.
- branch: main
- head: 73c89e7d402a0c498207e07299685ac729ecfde7
- next_cmd: `py -3 -B -m unittest discover -s tests -v`
- validations: active contract `PROD-20260813-plotkeeper-responsive-run-picker` validates at `59593e7645aa3e2b7883b572d87cf63d868f6a3e3b6d7dac7da0fc10adf8205b`; focused static tests and Node syntax green; real browser geometry at 375/768/1024/1440 shows menu inside viewport, document scrollWidth equals clientWidth, and inspector top equals board bottom; keyboard open/Escape and project grouping green; zero browser warnings/errors

## PLOTKEEPER V0.1.6 COMBINED RELEASE

- step: post-green-tests
- note: Combined v0.1.6 changelog, front-facing summary, workflow contract pointer, and rollback documentation are corrected; the full exact suite and static checks are green, and the combined candidate review is next.
- branch: main
- head: bf2b50a33c5436b323af8f06f14de7d9f5116acf
- next_cmd: `py -3 -B -m unittest discover -s tests -v`
- validations: adaptive calibration receipt active; sealed combined release contract validates at `b8d7377f5374de1a44dec11ec1d59c10efb1421dfa36638be94e20d26414d8a2`; public baseline is v0.1.5 at `3dc3488cbfaa55df13e6abebf4b1ca395c319916`; 70/70 tests green; Node syntax, contract validation, and git diff check green; GitHub CLI authenticated

## PLOTKEEPER INJECTED RESUME CWD FIX

- step: post-green-tests
- note: Review and check-in resumes now share a fail-closed run-aware subprocess boundary that launches from the enrolled repository; cross-repository and invalid-cwd regressions are green. Independent review and release remain.
- branch: main
- head: 796e4ab6e0daccf9e38219b9bb93980193daa1e4
- next_cmd: `py -3 -B -m unittest discover -s tests -v`
- validations: active contract `PROD-20260812-plotkeeper-injected-resume-cwd` validates at `a8a0c98496ebed4b97cf4c76415f7f9e25d683bfb6ea2f3e12a9fb7b296aa5bd`; MoonMarket run record confirms `Z:\MoonMarket`; focused 3 tests and full 70-test suite green; source scan finds no injected-resume subprocess bypass

## PLOTKEEPER STARSHAPE ATOMIC GATE INDEPENDENT REVIEW

- step: phase-start-independent-review
- note: Fresh reviewer-only VALIDATED-phase audit of committed candidate 909f23f against sealed repair contract c18e225b8bfb9d00cc5ef28eadb8f44347c682dc0a3ec77d7d8b2692f2ffa791; no implementation, Git mutation, live service mutation, or real run mutation is authorized.
- branch: main
- head: 909f23f44ef2ee391d54b30c9a3920e8267b90bb
- next_cmd: `py -3 -B -m unittest discover -s tests -v`
- validations: one clean main worktree at phase start; protected baseline 3dc3488cbfaa55df13e6abebf4b1ca395c319916; exact candidate 909f23f44ef2ee391d54b30c9a3920e8267b90bb; adversarial fixtures must use disposable ledgers only; Starshape inspection is read-only

## STARSHAPE SUCCESSOR LF CLOSEOUT REVIEW

- step: post-green-tests-amendment
- note: Independent review correctly failed candidate 909f23f for a direct Ledger.finalize_review bypass. The validator is now mandatory inside that ledger boundary, alternate validator injection is removed, receipt mutation is rejected, and the expanded Plotkeeper suite is green; fresh review of the amended commit is next.
- branch: main
- head: 3dc3488cbfaa55df13e6abebf4b1ca395c319916
- next_cmd: `Commit the direct-ledger bypass amendment, run a fresh independent production-goal-review against PROD-20260812-plotkeeper-starshape-closeout-revalidation, and only after PASS restart the local service.`
- validations: adaptive execution turn 019ff764-ebac-72a3-a6c7-1e4b56a9b051 opened on calibration route; Plotkeeper repository has one main worktree and a clean tracked/untracked status at phase start; Starshape candidate head is 22958b32cd84d21ddcfdc0e30590e5d85436a5ce with unrelated dirty state preserved and no extra worktrees; fresh adverse receipt edd89d902175dd62c572d080be202297a320b243716338ae36be6c684c2e7e86 is validator-green FAIL with one shared missing closeout control; Plotkeeper repair contract c18e225b8bfb9d00cc5ef28eadb8f44347c682dc0a3ec77d7d8b2692f2ffa791 validates ACTIVE; Starshape restored pre-close proof is 150 pytest passed, successor LF E2E PASS, frontend lint PASS, frontend production build PASS; candidate 909f23f independent receipt is validator-green FAIL with sealed hash 152e1f0b5ba387a2e0f79d763ed7a206da12ba0b3d2f1f1d3f2848732cbefa1f and file SHA256 0c57ff1245d0c315f8eac6887f70cf93b8536ada811f940531a819c057bf8fc2; amended gate full unittest suite is 68 passed and direct dictionary closure plus validator injection are rejected

## PLOTKEEPER LINKED SUCCESSOR RELEASE

- step: post-green-tests
- note: v0.1.4 linked successors are public and operationally green; final attestation exposed and v0.1.5 repairs nested bundle discovery plus truthful artifact-stable target progression. Independent v0.1.5 review and release remain.
- branch: main
- head: 705ec0554728a25c0056db80f128c2ed53e35bd7
- next_cmd: `py -3 -B -m unittest discover -s tests -v`
- validations: active repair contract `PROD-20260812-plotkeeper-attestation-gate-repair` validates at `bb36cb22a43d2fd02f4560b9e35fb02cca6e21c503cd60ca624c32b59ca16f43`; 64 tests green; nested valid bundle and target progression adversarial cases green; v0.1.4 public SHA/tag/release/Actions and linked-successor behavior green; prior Starshape track preserved unchanged

## STARSHAPE RUN 670A CLOSEOUT REVIEW

- step: post-green-independent-production-review
- note: Independent production-goal review PASS for exact Starshape candidate e1fea74b63c13d464c651bc5585f10ca3d3cf6d6 under PROD-20260811-starshape-professional-v2-execution. The reviewer inspected all 64 tasks, 266 reports, 266 timeline entries, 34 sessions, 33 children, and 1,912 evidence-locator occurrences; current-phase open items are zero. T040, T041, and T053-T058 remain eight explicit future external/release/Stage B/C gates and are not authorized or silently completed.
- branch: main
- head: 705ec0554728a25c0056db80f128c2ed53e35bd7
- next_cmd: `py -3 C:\Users\UltariumV3\.codex\skills\production-goal-review\scripts\validate_review_receipt.py runtime\goal-contracts\PROD-20260811-starshape-professional-v2-execution.json runtime\goal-reviews\plotkeeper-closeout-sol\review-receipt.json --repo-root . --receipt-dir runtime\goal-reviews\plotkeeper-closeout-sol`
- validations: independent PASS at 98 percent confidence; receipt 13052d8c21d877117c36a3ee060b0d98967bd0c3c4477921a16c7d37878c6e67 validates for phase VALIDATED; contract hash 08c719f84e47d208661d095f892afaaf613d18d19413a6a78e1202ceac8ca484 and candidate SHA exact; 111 pytest tests, frontend lint/build, local E2E, isolated PostgreSQL browser lifecycle checks, methodology mobile view, and all ten PDF pages green; current-phase open items 0; future authority gates 8

## PLOTKEEPER ACTIVE RUN SURFACE WORK

- step: post-green-tests
- note: Successor contract `PROD-20260811-plotkeeper-active-run-installer-restart-fix` is implemented and verified; upgrades now replace owned listeners and reject foreign listeners before reporting live readiness.
- branch: main
- head: e8589d558dee4e41c4f3af50aa2f48818f2af624
- next_cmd: `git diff --check`
- validations: successor contract VALID at 99cd45ea027cf78771822861765fe66b4d2871e3b74f19120aefb1f141702ed9; protected public predecessor e8589d558dee4e41c4f3af50aa2f48818f2af624; 59 tests green; version 0.1.3 synchronized; installer restart/foreign-listener/temp-root assertions, Node syntax, cache hygiene, and diff check green; live manually restarted API returns four non-subagent active runs

## PLOTKEEPER ACTIVE RUN SURFACE IMPLEMENTATION

- step: post-green-tests
- note: Exact run/session resolution, read-only Codex identity/liveness catalog, active-only grouped picker, run-bound dashboard URL, and SpecSwarm bridge are implemented; delegated implementation remains uncommitted for parent integration.
- branch: main
- head: ecc8a01f58732ac04de4995cfc10b7840b87377c
- next_cmd: `py -3 -m unittest discover -s tests -v`
- validations: focused active-run/backend/web tests green (24 total); full suite 51 green (final run after UI state reset); Node app.js syntax green; git diff --check green

## PLOTKEEPER PANEL RELIABILITY WORK

- step: post-green-tests
- note: Panel reliability package integrated and final release amendment binds verifier/rollback to the protected predecessor; exact-candidate rereview and release remain.
- branch: main
- head: 5c33658
- next_cmd: `git diff --check && py -3 -m unittest discover -s tests -v`
- validations: full suite 48 green; PowerShell parser green; alternate-port start.ps1 served valid dashboard HTML and health then stopped cleanly; git diff check green; live port 47831 restart deferred until exact-candidate review

## PLOTKEEPER COMPLETE BUNDLE WORK

- step: post-green-tests
- note: SpecSwarm and its complete skill-code dependency closure are vendored and installed locally; the first independent review found a stale rollback SHA, now corrected under a narrow final amendment; exact-candidate rereview and publication remain.
- branch: main
- head: eb5ac3f49c8641b952aabf133c53bff6c1344bd6
- next_cmd: `git diff --check && py -3 -m unittest discover -s tests -v`
- validations: 43 tests green; final contract validates at e6d2d0965c8ca6c0ff848285846f785d75b2a86e57f99294e7019d8ddd71c6c5; isolated bundled-only install and portable Plotkeeper bridge green; no bundled bytecode/cache; upstream Slopware package manifests exact; rollback target corrected to protected public baseline a0d2340; git diff check green

## PLOTKEEPER PUBLIC RELEASE WORK

- step: authenticated-release-proof-post-green
- note: After independent FAIL, added HMAC-authenticated phase receipts, exact candidate evidence resolution, active workflow/run binding, and adversarial wrong-key/nonexistent-evidence controls; candidate commit and staged independent review are next.
- branch: main
- head: e495b00791d7ad6394773e4920368ab008372969
- next_cmd: `py -3 -m unittest discover -s tests -v`
- validations: 33 tests green; compileall green; git diff check green; authenticated contract validates at 91115d18a0bb6dbbc996da9d1ee21fec83753f18c81cd0f0de2f4197110c8b0a; Plotkeeper run ad06db522b8c4d81a6705c14c5a1dbb6 bound to active contract; ignored review key generated without disclosure; public origin remains empty

## PLOTKEEPER FIRST CLASS REPO WORK

- step: post-green-tests
- note: Portable package layout, isolated installer path, seeded demo, repository documentation, CI, and live desktop/mobile screenshots implemented and verified; independent production-goal review remains.
- branch: main
- head: 208ece46587eeaa13eef6928e8e49ca0836bb0ea
- next_cmd: `git diff --check && py -3 -m unittest discover -s tests -v`
- validations: 18 unit/static/repository tests green; compileall green; PowerShell script syntax green; fresh isolated wheel install and console entry point green; installed-package demo API green; desktop 1440x1000 and mobile 390x844 live screenshots captured with zero console errors; contract validator green; git diff check green

## PLOTKEEPER GLOBAL WORK

- step: post-green-tests
- note: Production goal contract ingestion/display and mandatory production-goal-review closeout injection implemented and deployed; first real Specswarm end-to-end remains unproven.
- branch: main
- head: f7d5fb3
- next_cmd: `Invoke-RestMethod http://127.0.0.1:47831/health`
- validations: 14 unit/static tests green; sealed production contract validates; compileall and JS syntax green; live service and desktop/mobile empty-state browser QA green; independent review PARTIAL only because no real enrolled contract-bearing run exists yet

## PLOTKEEPER RELEASE CONTRACT SELECTION FIX

- step: post-green-tests
- note: Tracked `RELEASE_CONTRACT.json` now deterministically binds guard and server verifier to the v0.1.7 PR release contract; mtime/reordering and RL-NONE successor attacks are covered. No commit, push, install, or live-service mutation.
- branch: release/v0.1.7-plotkeeper-surface
- head: 9d0400f3c36c6615598222c5780b04488aeb86ad
- next_cmd: `py -3 -B -m unittest discover -s tests -v`
- validations: active successor contract validates at `f5859da6ca2145ccfbd805ee8ca44acf6a2d5775ef2e1c626d5f84c58320cc78`; focused guard/verifier/docs suite 30 passed; full unittest suite 90 passed; py_compile and git diff --check passed; no commit, push, install, restart, deployment, or live-service mutation

## PLOTKEEPER POINTER HASH PARITY FIX

- step: post-green-tests
- note: Release pointer now stores a canonical JSON contract hash stable across LF and CRLF; guard and verifier parity regressions pass. No commit, push, install, or live mutation.
- branch: release/v0.1.7-plotkeeper-surface
- head: 16c438044d36a9f1214e75dd8be9ecf33e0b047f
- next_cmd: `py -3 -B -m unittest discover -s tests -v`
- validations: active successor contract validates at `d74c64eab95ba61a98a58b34176e89fc12b1c0d2c41b8f6879bbaf3f6d1f6741`; canonical pointer hash `8c82f3735b58ecd18c8bfb1f5260972eca4dbd8c3a3d60af27622e5de0be0ca3`; focused guard/verifier parity suite 27 passed; full unittest suite 92 passed; py_compile and git diff --check passed; no commit, push, install, restart, deployment, or live-service mutation
