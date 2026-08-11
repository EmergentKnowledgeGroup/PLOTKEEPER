from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any
from pathlib import Path


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

    def to_dict(self) -> dict[str, Any]:
        out = asdict(self)
        out["state"] = self.state.value
        out["children"] = list(self.children)
        out["status"] = self.state.value
        out["project_name"] = Path(self.cwd).name if self.cwd else "Plotkeeper run"
        return out
