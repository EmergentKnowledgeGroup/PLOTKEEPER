"""Create a private-data-free Plotkeeper run for evaluation and screenshots."""

from __future__ import annotations

import argparse
import json
import shutil
import threading
import webbrowser
from pathlib import Path

from plotkeeper.service import PlotkeeperService


def build_demo(runtime: Path, port: int) -> tuple[PlotkeeperService, str]:
    if runtime.exists():
        shutil.rmtree(runtime)
    sessions = runtime / "sessions"
    sessions.mkdir(parents=True)
    service = PlotkeeperService(
        ledger_path=runtime / "plotkeeper.sqlite3",
        sessions_root=sessions,
        dashboard_url=f"http://127.0.0.1:{port}",
    )
    project_root = Path(__file__).resolve().parents[1]
    run = service.ledger.enroll("demo-root-session", str(project_root), service.dashboard_url)
    service.ledger.attach_child(run.run_id, "demo-research-agent")
    service.ledger.attach_child(run.run_id, "demo-qa-agent")
    service.ledger.replace_tasks(
        run.run_id,
        [
            {"task_id": "T001", "title": "Bind the production goal", "status": "completed", "owner": "root", "workstream": "Planning", "source": "examples/demo.py"},
            {"task_id": "T002", "title": "Package the dashboard assets", "status": "completed", "owner": "implementation", "workstream": "Repository", "source": "examples/demo.py"},
            {"task_id": "T003", "title": "Verify the fresh install", "status": "working", "owner": "qa", "workstream": "Verification", "source": "examples/demo.py"},
            {"task_id": "T004", "title": "Run independent closeout review", "status": "pending", "owner": "root", "workstream": "Verification", "source": "examples/demo.py"},
        ],
    )
    contract = {
        "id": "DEMO-PLOTKEEPER-001",
        "status": "ACTIVE",
        "user_goal": "Ship a portable, documented Plotkeeper repository.",
        "contract_hash": "demo-not-a-production-receipt",
        "baseline": {"sha": "208ece4"},
        "invariants": [
            "Codex session JSONL remains read-only.",
            "Only an independent PASS receipt may close the run.",
        ],
    }
    contract_path = runtime / "demo-contract.json"
    contract_path.write_text(json.dumps(contract, indent=2), encoding="utf-8")
    service.ledger.set_goal_contract(run.run_id, str(contract_path), contract)
    service.ledger.add_report(run.run_id, "claim", "Portable package layout implemented.", session_id="demo-research-agent", evidence=["pyproject.toml", "plotkeeper/web/index.html"])
    service.ledger.add_report(run.run_id, "report", "Backend and static dashboard tests passed.", session_id="demo-qa-agent", evidence=["python -m unittest discover -s tests -v"])
    return service, run.run_id


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime", type=Path, default=Path("examples/.demo-runtime"))
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=47832)
    parser.add_argument("--serve", action="store_true", help="Keep the populated dashboard running.")
    parser.add_argument("--open", action="store_true", help="Open the dashboard in the default browser.")
    args = parser.parse_args()
    service, run_id = build_demo(args.runtime.resolve(), args.port)
    url = f"http://{args.host}:{args.port}/"
    print(json.dumps({"ok": True, "run_id": run_id, "dashboard": url, "runtime": str(args.runtime.resolve())}, indent=2))
    if not args.serve:
        service.close_db()
        return 0
    server = service.serve(args.host, args.port)
    watcher = threading.Thread(target=service.watch_forever, daemon=True)
    watcher.start()
    if args.open:
        webbrowser.open(url)
    print(f"Demo dashboard listening on {url}. Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        service.close_db()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
