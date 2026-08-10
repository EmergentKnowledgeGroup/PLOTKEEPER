# Contributing

Keep changes narrow and preserve the read-only input boundary and review gate.

1. Create a local branch from the intended protected baseline.
2. Install the editable package as documented in `INSTALLATION.md`.
3. Add focused tests for behavior changes.
4. Run:

   ```powershell
   .\.venv\Scripts\python -m unittest discover -s tests -v
   .\.venv\Scripts\python -m compileall -q plotkeeper examples
   ```

5. Exercise `examples/demo.py --serve` and inspect the dashboard at desktop and
   mobile widths for web changes.
6. Keep generated ledgers, private session data, virtual environments, and
   screenshots containing private material out of commits.

Do not weaken a test or closure condition merely to make a proposed change pass.
