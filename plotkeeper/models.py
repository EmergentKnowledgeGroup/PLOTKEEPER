from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any
from pathlib import Path
from typing import Mapping


class RunState(StrEnum):
    OPEN = "OPEN"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    REVIEW_PENDING = "REVIEW_PENDING"
    REVIEWED = "REVIEWED"
    CLOSED = "CLOSED"


@dataclass(frozen=True)
class SessionObservation:
    session_id: str
    path: str
    cwd: str | None = None
    # Stable task/message identity shared by Codex session/worktree variants.
    # Falls back to ``session_id`` when the source carries no canonical id.
    canonical_root_id: str | None = None
    parent_session_id: str | None = None
    is_root: bool = False
    invoked_specswarm: bool = False
    root_complete: bool = False
    root_idle: bool = False
    goal_complete_requested: bool = False
    review_results: list[dict[str, Any]] = field(default_factory=list)
    attach_run_ids: list[str] = field(default_factory=list)
    claims: list[dict[str, Any]] = field(default_factory=list)
    reports: list[dict[str, Any]] = field(default_factory=list)
    evidence_links: list[str] = field(default_factory=list)
    last_timestamp: str | None = None
    # Locally available Codex identity. These are appended for positional
    # compatibility with existing SessionObservation consumers.
    task_id: str | None = None
    task_label: str | None = None


@dataclass(frozen=True)
class Run:
    run_id: str
    root_session_id: str
    state: RunState
    cwd: str | None
    dashboard_url: str
    created_at: str
    updated_at: str
    review_injected_at: str | None = None
    review_receipt: dict[str, Any] | None = None
    closed_at: str | None = None
    children: tuple[str, ...] = ()

    def to_dict(self, identity: Mapping[str, Any] | None = None) -> dict[str, Any]:
        out = asdict(self)
        out["state"] = self.state.value
        out["children"] = list(self.children)
        out["status"] = self.state.value
        identity = identity or {}
        project_name = identity.get("project_name") or (Path(self.cwd).name if self.cwd else "Plotkeeper run")
        task_label = identity.get("task_label") or identity.get("title") or self.root_session_id
        task_id = identity.get("task_id") or identity.get("thread_id") or self.root_session_id
        out["project_name"] = str(project_name)
        out["task_label"] = str(task_label)
        out["task_id"] = str(task_id)
        out["thread_id"] = str(task_id)
        out["session_id"] = str(task_id)
        if identity.get("agent_path"):
            out["agent_path"] = str(identity["agent_path"])
        return out
