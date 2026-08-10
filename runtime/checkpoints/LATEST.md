# Plotkeeper Checkpoint

## CURRENT

Track: `PLOTKEEPER PUBLIC RELEASE WORK`

## PLOTKEEPER PUBLIC RELEASE WORK

- step: post-green-tests
- note: Slopware plugin integration, Plotkeeper adaptive Codex hooks, attribution, and Apache-2.0 licensing implemented; candidate is ready for exact-SHA independent review before publication.
- branch: main
- head: b36c6f3d0ffed1f5e919e49668e79cf8fe2adb7a
- next_cmd: `git diff --check && py -3 -m unittest discover -s tests -v`
- validations: 21 unit/static/repository/integration tests green; installer hook merge is idempotent and preserves unrelated configuration; all three canonical Slopware packages asserted; full Apache-2.0 text and separate CC BY 4.0 notice present; git diff check green

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
