#!/usr/bin/env python3
"""Evidence-calibrated execution ledger and Codex hook gate."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sqlite3
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path

OUTCOMES = {"complete_verified", "complete_unverified", "incomplete", "unproven"}
RISK = {"low": 0, "medium": 1, "high": 2}
ALLOWLIST = re.compile(
    r"^\s*(?:hi|hello|hey|thanks|thank you|ok|okay|got it|sounds good|yes|no|"
    r"continue|proceed|go ahead)[\s.!?]*$",
    re.IGNORECASE,
)


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value)


def default_db() -> Path:
    return Path(__file__).resolve().parent.parent / "data" / "adaptive_execution.sqlite3"


def connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=30)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS turn_gate (
          turn_id TEXT PRIMARY KEY,
          session_id TEXT NOT NULL,
          cwd TEXT NOT NULL,
          prompt_hash TEXT NOT NULL,
          prompt_excerpt TEXT NOT NULL,
          required INTEGER NOT NULL,
          reason TEXT NOT NULL,
          created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS executions (
          turn_id TEXT PRIMARY KEY,
          session_id TEXT NOT NULL,
          cwd TEXT NOT NULL,
          project TEXT NOT NULL,
          summary TEXT NOT NULL,
          task_type TEXT NOT NULL,
          risk TEXT NOT NULL,
          systems_json TEXT NOT NULL,
          validation_json TEXT NOT NULL,
          route TEXT NOT NULL,
          comparison_json TEXT NOT NULL,
          awt_seconds INTEGER,
          cgp_seconds INTEGER,
          confidence TEXT NOT NULL,
          started_at TEXT NOT NULL,
          converged_at TEXT,
          ended_at TEXT,
          wall_seconds INTEGER,
          substantive_seconds INTEGER,
          closeout_seconds INTEGER,
          blocked_seconds INTEGER NOT NULL DEFAULT 0,
          status TEXT NOT NULL,
          outcome TEXT,
          proof TEXT,
          open_items TEXT,
          variance TEXT
        );
        """
    )
    return db


def items(value: str) -> list[str]:
    return sorted({x.strip().lower() for x in value.split(",") if x.strip()})


def classify(prompt: str) -> tuple[bool, str]:
    if not prompt.strip():
        return False, "empty prompt"
    if ALLOWLIST.fullmatch(prompt):
        return False, "explicit conversational allowlist"
    return True, "fail-closed substantive default"


def project_name(cwd: str) -> str:
    path = Path(cwd)
    return path.name.lower() or str(path).lower()


def overlap(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 1.0
    return len(a & b) / len(a | b) if a | b else 0.0


def comparable(db: sqlite3.Connection, project: str, task_type: str, risk: str,
               systems: list[str], validation: list[str]) -> list[dict]:
    rows = db.execute(
        """SELECT * FROM executions
           WHERE status='closed' AND task_type=? AND substantive_seconds>0
           AND outcome IN ('complete_verified','complete_unverified','incomplete','unproven')""",
        (task_type,),
    ).fetchall()
    found = []
    for row in rows:
        if abs(RISK[risk] - RISK.get(row["risk"], 99)) > 1:
            continue
        sys_score = overlap(set(systems), set(json.loads(row["systems_json"])))
        val_score = overlap(set(validation), set(json.loads(row["validation_json"])))
        project_score = 1.0 if project == row["project"] else 0.0
        score = 0.4 * project_score + 0.35 * sys_score + 0.25 * val_score
        if score >= 0.60:
            found.append({"turn_id": row["turn_id"], "score": round(score, 3),
                          "substantive_seconds": row["substantive_seconds"],
                          "closeout_seconds": row["closeout_seconds"] or 0})
    return sorted(found, key=lambda x: (-x["score"], x["turn_id"]))


def cmd_begin(args: argparse.Namespace, db: sqlite3.Connection) -> int:
    systems, validation = items(args.systems), items(args.validation)
    project = project_name(args.cwd)
    matches = comparable(db, project, args.task_type, args.risk, systems, validation)
    if matches:
        best_score = matches[0]["score"]
        cohort = [m for m in matches if m["score"] == best_score]
        awt = int(statistics.median(m["substantive_seconds"] for m in cohort))
        cgp = int(statistics.median(m["closeout_seconds"] for m in cohort))
        if awt > 0 and 0 <= cgp < awt:
            route = "timebox"
            confidence = "provisional" if len(cohort) == 1 else "measured"
        else:
            route, confidence = "calibration", "comparable-clock-invalid"
            awt = cgp = None
    else:
        awt = cgp = None
        route, confidence = "calibration", "no-comparable-history"
    stamp = now()
    with db:
        db.execute(
            """INSERT INTO executions
               (turn_id,session_id,cwd,project,summary,task_type,risk,systems_json,
                validation_json,route,comparison_json,awt_seconds,cgp_seconds,
                confidence,started_at,status)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?, 'active')
               ON CONFLICT(turn_id) DO UPDATE SET
                 session_id=excluded.session_id,cwd=excluded.cwd,project=excluded.project,
                 summary=excluded.summary,task_type=excluded.task_type,risk=excluded.risk,
                 systems_json=excluded.systems_json,validation_json=excluded.validation_json,
                 route=excluded.route,comparison_json=excluded.comparison_json,
                 awt_seconds=excluded.awt_seconds,cgp_seconds=excluded.cgp_seconds,
                 confidence=excluded.confidence""",
            (args.turn_id, args.session_id, args.cwd, project, args.summary,
             args.task_type, args.risk, json.dumps(systems), json.dumps(validation),
             route, json.dumps(matches), awt, cgp, confidence, stamp),
        )
    print(json.dumps({"turn_id": args.turn_id, "route": route, "awt_seconds": awt,
                      "cgp_seconds": cgp, "confidence": confidence,
                      "comparables": matches}, indent=2))
    return 0


def cmd_converge(args: argparse.Namespace, db: sqlite3.Connection) -> int:
    row = db.execute("SELECT status FROM executions WHERE turn_id=?", (args.turn_id,)).fetchone()
    if not row or row["status"] != "active":
        raise SystemExit("No active execution receipt for this turn.")
    with db:
        db.execute("UPDATE executions SET converged_at=?, status='closeout' WHERE turn_id=?",
                   (now(), args.turn_id))
    print(json.dumps({"turn_id": args.turn_id, "status": "closeout"}))
    return 0


def cmd_close(args: argparse.Namespace, db: sqlite3.Connection) -> int:
    if args.outcome not in OUTCOMES:
        raise SystemExit("Invalid outcome.")
    row = db.execute("SELECT * FROM executions WHERE turn_id=?", (args.turn_id,)).fetchone()
    if not row or row["status"] not in {"active", "closeout"}:
        raise SystemExit("No open execution receipt for this turn.")
    if args.outcome == "complete_verified" and (not args.proof.strip() or args.open_items.strip()):
        raise SystemExit("complete_verified requires proof and no open required items.")
    if args.outcome != "complete_verified" and not args.open_items.strip():
        raise SystemExit("Non-verified outcomes require explicit open items.")
    ended = now()
    converged = row["converged_at"] or ended
    wall = max(0, int((parse_time(ended) - parse_time(row["started_at"])).total_seconds()))
    closeout = max(0, int((parse_time(ended) - parse_time(converged)).total_seconds()))
    substantive = max(0, wall - closeout - args.blocked_seconds)
    with db:
        db.execute(
            """UPDATE executions SET converged_at=?,ended_at=?,wall_seconds=?,
               substantive_seconds=?,closeout_seconds=?,blocked_seconds=?,status='closed',
               outcome=?,proof=?,open_items=?,variance=? WHERE turn_id=?""",
            (converged, ended, wall, substantive, closeout, args.blocked_seconds,
             args.outcome, args.proof.strip(), args.open_items.strip(),
             args.variance.strip(), args.turn_id),
        )
    print(json.dumps({"turn_id": args.turn_id, "status": "closed", "outcome": args.outcome,
                      "wall_seconds": wall, "substantive_seconds": substantive,
                      "closeout_seconds": closeout, "blocked_seconds": args.blocked_seconds}, indent=2))
    return 0


def hook_submit(payload: dict, db: sqlite3.Connection) -> int:
    required, reason = classify(payload.get("prompt", ""))
    prompt = payload.get("prompt", "")
    with db:
        db.execute(
            """INSERT OR REPLACE INTO turn_gate
               (turn_id,session_id,cwd,prompt_hash,prompt_excerpt,required,reason,created_at)
               VALUES (?,?,?,?,?,?,?,?)""",
            (payload["turn_id"], payload.get("session_id", ""), payload.get("cwd", ""),
             hashlib.sha256(prompt.encode("utf-8")).hexdigest(), prompt[:240],
             int(required), reason, now()),
        )
    if not required:
        return 0
    context = (
        "ADAPTIVE EXECUTION IS REQUIRED FOR THIS TURN. Before substantive work, use "
        "$adaptive-execution and run its begin command with this turn_id="
        f"{payload['turn_id']} and session_id={payload.get('session_id','')}. Apply $msw. "
        "Use calibration when no comparable record exists; use canonical $timebox only "
        "with returned evidence-derived timing. Close the receipt after proof. Do not create "
        "a persisted Codex goal unless the user explicitly requested one."
    )
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "UserPromptSubmit",
                                              "additionalContext": context}}))
    return 0


def hook_stop(payload: dict, db: sqlite3.Connection) -> int:
    turn_id = payload.get("turn_id", "")
    gate = db.execute("SELECT * FROM turn_gate WHERE turn_id=?", (turn_id,)).fetchone()
    if not gate or not gate["required"]:
        print("{}")
        return 0
    row = db.execute("SELECT * FROM executions WHERE turn_id=?", (turn_id,)).fetchone()
    if not row:
        reason = (
            "ADAPTIVE EXECUTION GATE: This governed turn has no execution receipt. Loop back now: "
            "invoke $adaptive-execution, run begin for the current turn_id, apply the returned "
            "calibration/timebox route and $msw contract, then close the receipt with honest proof. "
            "Do not ask the user to repair this omission."
        )
        print(json.dumps({"decision": "block", "reason": reason}))
        return 0
    if row["status"] != "closed":
        reason = (
            f"ADAPTIVE EXECUTION GATE: Receipt {turn_id} is {row['status']}, not closed. "
            "Resume required work or run converge and close with an honest outcome, proof, and "
            "open items. Do not report completion or ask the user to bypass the gate."
        )
        print(json.dumps({"decision": "block", "reason": reason}))
        return 0
    print("{}")
    return 0


def cmd_hook(args: argparse.Namespace, db: sqlite3.Connection) -> int:
    payload = json.load(sys.stdin)
    event = payload.get("hook_event_name")
    if event == "UserPromptSubmit":
        return hook_submit(payload, db)
    if event == "Stop":
        return hook_stop(payload, db)
    print("{}")
    return 0


def cmd_status(args: argparse.Namespace, db: sqlite3.Connection) -> int:
    row = db.execute("SELECT * FROM executions WHERE turn_id=?", (args.turn_id,)).fetchone()
    print(json.dumps(dict(row) if row else {"turn_id": args.turn_id, "status": "missing"}, indent=2))
    return 0


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser()
    p.add_argument("--db", type=Path, default=default_db())
    sub = p.add_subparsers(dest="command", required=True)
    begin = sub.add_parser("begin")
    for flag in ("turn-id", "session-id", "cwd", "summary", "task-type"):
        begin.add_argument(f"--{flag}", required=True)
    begin.add_argument("--risk", choices=RISK, required=True)
    begin.add_argument("--systems", default="")
    begin.add_argument("--validation", default="")
    converge = sub.add_parser("converge")
    converge.add_argument("--turn-id", required=True)
    close = sub.add_parser("close")
    close.add_argument("--turn-id", required=True)
    close.add_argument("--outcome", choices=sorted(OUTCOMES), required=True)
    close.add_argument("--proof", default="")
    close.add_argument("--open-items", default="")
    close.add_argument("--variance", default="")
    close.add_argument("--blocked-seconds", type=int, default=0)
    status = sub.add_parser("status")
    status.add_argument("--turn-id", required=True)
    sub.add_parser("hook")
    return p


def main() -> int:
    args = parser().parse_args()
    if getattr(args, "blocked_seconds", 0) < 0:
        raise SystemExit("blocked-seconds cannot be negative.")
    db = connect(args.db)
    return {"begin": cmd_begin, "converge": cmd_converge, "close": cmd_close,
            "status": cmd_status, "hook": cmd_hook}[args.command](args, db)


if __name__ == "__main__":
    raise SystemExit(main())
