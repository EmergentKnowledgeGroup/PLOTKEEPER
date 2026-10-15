"""Synthetic dashboard for manual/browser QA; no watcher or Codex execution."""
import json
import sqlite3
from pathlib import Path
import sys
import tempfile

from plotkeeper.service import PlotkeeperService


def main():
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        service = PlotkeeperService(ledger_path=base / 'ledger.sqlite', sessions_root=base / 'sessions',
                                    codex_state_path=base / 'absent-state.sqlite',
                                    session_index_path=base / 'absent-index.jsonl')
        run = service.ledger.enroll('qa-synthetic-root', str(base), service.dashboard_url)
        (base / 'sessions' / 'qa-synthetic-root.jsonl').write_text(
            json.dumps({'type': 'session_meta', 'payload': {'id': 'qa-synthetic-root', 'cwd': str(base)}}) + '\n', encoding='utf-8')
        (base / 'absent-index.jsonl').write_text(
            json.dumps({'id': 'qa-synthetic-root', 'thread_name': 'Synthetic review recovery'}) + '\n', encoding='utf-8')
        with sqlite3.connect(base / 'absent-state.sqlite') as db:
            db.execute('CREATE TABLE threads (id TEXT PRIMARY KEY, title TEXT, cwd TEXT, rollout_path TEXT)')
            db.execute('INSERT INTO threads VALUES (?,?,?,?)',
                       ('qa-synthetic-root', 'Synthetic review recovery', str(base),
                        str(base / 'sessions' / 'qa-synthetic-root.jsonl')))
        service.ledger.replace_tasks(run.run_id, [
            {'task_id': 'T1', 'title': 'Verify the owned review control', 'status': 'working'},
            {'task_id': 'T2', 'title': 'Independent receipt verification', 'status': 'pending'}])
        service.ledger.mark_review_required(run.run_id)
        service.inject_review(run.run_id, runner=lambda *_a, **_k: 23)
        # Clicking Retry must use this fake runner, never a real Codex process.
        service._run_codex = lambda *_a, **_k: 23
        server = service.serve('127.0.0.1', 0)
        print(json.dumps({'port': server.server_port, 'run_id': run.run_id}), flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            server.server_close()
            service.close_db()


if __name__ == '__main__':
    main()
