# Examples

The demo creates a populated Plotkeeper ledger without reading private Codex
sessions. From the repository root:

```powershell
py -3 -m pip install -e .
py -3 examples/demo.py --serve --open
```

The demo dashboard uses <http://127.0.0.1:47832/> so it can run beside the
default service on port `47831`. Generated data is written to
`examples/.demo-runtime/` and is ignored by Git.

`specswarm-checklist.md` is a minimal plan that can be passed to `sync-plan`.
`goal-contract.example.json` documents the small subset Plotkeeper displays;
production contracts must still be created and validated by the authoritative
goal-contract workflow.
