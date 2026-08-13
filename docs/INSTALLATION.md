# Installation and configuration

## Supported path: current-user installation

From the repository root in PowerShell:

```powershell
.\scripts\install.ps1
```

The script:

1. creates `.venv` with the selected Python interpreter;
2. installs the current checkout into that environment;
3. chooses and persists an available high private port on `127.0.0.1`, then starts Plotkeeper there;
4. adds a `Plotkeeper` value under the current user's Windows `Run` key.

No administrator elevation is required. The default ledger remains in
`runtime/plotkeeper.sqlite3` inside the checkout. Uninstalling startup
registration does not delete it.

Choose another interpreter or port when needed:

```powershell
.\scripts\install.ps1 -Python 'C:\Path\To\python.exe' -Port 48731
```

## Development installation

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python -m pip install -e .
.\.venv\Scripts\python -m unittest discover -s tests -v
.\scripts\start.ps1
```

The package also installs a `plotkeeper` console command inside `.venv`:

```powershell
.\.venv\Scripts\plotkeeper.exe --help
```

## Configuration

| Setting | Default | Override |
| --- | --- | --- |
| Session directory | `%USERPROFILE%\.codex\sessions` | `PLOTKEEPER_SESSIONS` or `--sessions` |
| Ledger | `runtime\plotkeeper.sqlite3` | `PLOTKEEPER_LEDGER` or `--ledger` |
| Host | `127.0.0.1` | `serve --host` |
| Port | Persisted OS-assigned dynamic/private port | `serve --port` or installer `-Port` |

Global options precede the subcommand:

```powershell
.\.venv\Scripts\plotkeeper.exe `
  --sessions 'D:\Codex\sessions' `
  --ledger 'D:\PlotkeeperData\ledger.sqlite3' `
  serve --port 61234
```

Do not bind Plotkeeper to a non-loopback interface unless the surrounding
network and host controls are understood. The service currently has no login
layer because its intended boundary is the local machine.

## Remove startup registration

```powershell
.\scripts\uninstall.ps1
```

This preserves `.venv` and the runtime ledger. Delete those manually only after
confirming their data is no longer needed.
