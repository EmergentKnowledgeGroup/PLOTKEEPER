from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from .connector import connector_path, ensure_connector
from .service import PlotkeeperService


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="plotkeeper")
    parser.add_argument("--ledger", default=os.environ.get("PLOTKEEPER_LEDGER", "runtime/plotkeeper.sqlite3"))
    parser.add_argument("--connector", default=os.environ.get("PLOTKEEPER_CONNECTOR"))
    parser.add_argument("--sessions", default=os.environ.get("PLOTKEEPER_SESSIONS", str(Path.home() / ".codex" / "sessions")))
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("status")
    sub.add_parser("connector")
    current = sub.add_parser("current")
    current.add_argument("--cwd", default=None)
    current.add_argument("--run-id", default=None)
    current.add_argument("--session-id", default=None)
    report = sub.add_parser("report")
    report.add_argument("--run-id", required=True)
    report.add_argument("--kind", required=True)
    report.add_argument("--text", required=True)
    report.add_argument("--evidence", action="append", default=[])
    sync = sub.add_parser("sync-plan")
    sync.add_argument("--run-id", required=True)
    sync.add_argument("--file", action="append", required=True)
    sync.add_argument("--contract")
    serve = sub.add_parser("serve")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=None)
    poll = sub.add_parser("poll")
    poll.add_argument("--once", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    connector_file = Path(args.connector).resolve() if args.connector else connector_path(Path(args.ledger).resolve().parent.parent)
    connector = ensure_connector(connector_file, args.port if args.command == "serve" else None)
    service = PlotkeeperService(ledger_path=args.ledger, sessions_root=args.sessions,
                                dashboard_url=str(connector["url"]), profile_root=connector_file.parent.parent)
    if args.command == "connector":
        print(json.dumps(connector, sort_keys=True))
    elif args.command == "status":
        service.poll_once()
        print(json.dumps([r.to_dict() for r in service.ledger.list_runs()], sort_keys=True))
    elif args.command == "current":
        service.poll_once()
        result = service.current(args.cwd, run_id=args.run_id, session_id=args.session_id)
        print(json.dumps(result, sort_keys=True))
        if not result.get("ok"):
            service.close_db()
            return 2
    elif args.command == "report":
        print(json.dumps(service.report(args.run_id, args.kind, args.text, evidence=args.evidence), sort_keys=True))
    elif args.command == "sync-plan":
        print(json.dumps(service.sync_plan(args.run_id, args.file, args.contract), sort_keys=True))
    elif args.command == "poll":
        print(json.dumps({"events": service.poll_once()}, sort_keys=True))
    elif args.command == "serve":
        server = service.serve(args.host, int(connector["port"]))
        watcher = __import__("threading").Thread(target=service.watch_forever, daemon=True)
        watcher.start()
        print(f"Plotkeeper listening on {connector['url']}", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
