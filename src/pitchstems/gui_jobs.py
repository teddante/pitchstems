from __future__ import annotations

import threading
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class WorkerJobState:
    next_token: int = 0
    active_token: int | None = None
    cancel_requested_token: int | None = None

    def start(self) -> int:
        self.next_token += 1
        self.active_token = self.next_token
        self.cancel_requested_token = None
        return self.next_token

    def cancel(self) -> bool:
        if self.active_token is None:
            return False
        self.cancel_requested_token = self.active_token
        return True

    def request_cancel(self, token: int) -> bool:
        if self.active_token != token:
            return False
        self.cancel_requested_token = token
        return True

    def is_cancel_requested(self, token: int) -> bool:
        return self.cancel_requested_token == token

    def finish(self, token: int) -> None:
        if self.active_token == token:
            self.active_token = None
        if self.cancel_requested_token == token:
            self.cancel_requested_token = None

    def invalidate(self) -> bool:
        had_active = self.active_token is not None
        self.next_token += 1
        self.active_token = None
        self.cancel_requested_token = None
        return had_active

    def is_active(self, token: int) -> bool:
        return self.active_token == token


@dataclass
class EditorLoadJobState:
    token: int = 0
    activity_tokens: set[int] = field(default_factory=set)
    worker: threading.Thread | None = None

    def next(self) -> int:
        self.token += 1
        return self.token


@dataclass
class MidiPreviewJobState:
    token: int = 0
    workers: dict[tuple[Path, str], tuple[int, threading.Thread]] = field(default_factory=dict)

    def next(self) -> int:
        self.token += 1
        self.workers.clear()
        return self.token
