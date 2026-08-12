# Plotkeeper Checkpoint

## CURRENT

Track: `PLOTKEEPER ACTIVE RUN SURFACE WORK`

## PLOTKEEPER ACTIVE RUN SURFACE WORK

- step: post-green-tests
- note: Successor contract `PROD-20260811-plotkeeper-active-run-surface-phase-sequencing-fix` is implemented and verified; all obligation classes now honor lifecycle phases without predeployment live-proof circularity.
- branch: main
- head: 4bfa592788cec1fd0d76c0e9378882568664f9cb
- next_cmd: `git diff --check`
- validations: successor contract VALID at 3064525e6de091b477e452605f7c067f5c98ac8c18ff95a0c8e2c6ae070ef76e; predecessor 82d41e46d2b6de525421ece81916e98ae6e9b283f5d4da939ad6bf26ee7964a7 preserved; 59 tests green including phase-aware server/bundled validators and invalid-phase rejection; Node syntax, cache hygiene, and diff check green; copied-live inventory remains four non-subagent active runs

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
