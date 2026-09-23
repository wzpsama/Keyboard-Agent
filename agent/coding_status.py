"""Validate and consume the small, local coding-agent status protocol."""

from __future__ import annotations

import json
import math
import os
import time
from dataclasses import dataclass
from typing import Callable, Mapping


STATUS_STATES = frozenset({"idle", "working", "waiting", "completed", "blocked"})
MAX_STATUS_LIFETIME_S = 60 * 60


@dataclass(frozen=True)
class CodingStatus:
    """One privacy-preserving status event from a coding-agent bridge."""

    state: str
    revision: int
    updated_at: float
    expires_at: float | None

    @classmethod
    def from_mapping(cls, value: object) -> "CodingStatus | None":
        """Return a bounded status object, or reject malformed input safely."""
        if not isinstance(value, dict):
            return None
        state = value.get("state")
        revision = value.get("revision")
        updated_at = value.get("updated_at")
        expires_at = value.get("expires_at")
        if not isinstance(state, str) or state not in STATUS_STATES:
            return None
        if isinstance(revision, bool) or not isinstance(revision, int):
            return None
        if not 0 < revision < 2**63 or isinstance(updated_at, bool) or not isinstance(updated_at, (int, float)):
            return None
        try:
            updated_at = float(updated_at)
        except OverflowError:
            return None
        if not math.isfinite(updated_at):
            return None
        if state == "idle":
            if expires_at is not None:
                return None
            return cls(state, revision, updated_at, None)
        if isinstance(expires_at, bool) or not isinstance(expires_at, (int, float)):
            return None
        try:
            expires_at = float(expires_at)
        except OverflowError:
            return None
        if not math.isfinite(expires_at):
            return None
        if expires_at <= updated_at or expires_at - updated_at > MAX_STATUS_LIFETIME_S:
            return None
        return cls(state, revision, updated_at, expires_at)

    def active(self, now: float) -> bool:
        """Return whether this non-idle event has not reached its expiry."""
        return self.state != "idle" and self.expires_at is not None and now < self.expires_at


@dataclass(frozen=True)
class StatusTransition:
    """A semantic change the screen should render exactly once."""

    previous: CodingStatus | None
    current: CodingStatus | None


class CodingStatusReader:
    """Poll an atomic JSON handoff without allowing stale events to revive."""

    def __init__(self, path: str, *, clock: Callable[[], float] = time.time,
                 poll_interval_s: float = 1.0):
        self.path = path
        self._clock = clock
        self.poll_interval_s = poll_interval_s
        self._last_checked_at = float("-inf")
        self._last_mtime_ns: int | None = None
        self._highest_revision = 0
        self._current: CodingStatus | None = None

    @property
    def current(self) -> CodingStatus | None:
        """Return the latest valid status without exposing file contents."""
        return self._current

    def poll(self, now: float | None = None) -> StatusTransition | None:
        """Read at most once per interval and return only visible transitions."""
        now = self._clock() if now is None else now
        if now - self._last_checked_at >= self.poll_interval_s:
            self._last_checked_at = now
            candidate = self._read_if_changed()
            if candidate is not None and candidate.revision > self._highest_revision:
                self._highest_revision = candidate.revision
                next_status = candidate if candidate.active(now) else None
                if self._is_visible_change(self._current, next_status):
                    previous = self._current
                    self._current = next_status
                    return StatusTransition(previous, next_status)
                self._current = next_status

        if self._current is not None and not self._current.active(now):
            previous = self._current
            self._current = None
            return StatusTransition(previous, None)
        return None

    @staticmethod
    def _is_visible_change(previous: CodingStatus | None,
                           current: CodingStatus | None) -> bool:
        if previous is None or current is None:
            return previous != current
        return previous.state != current.state

    def _read_if_changed(self) -> CodingStatus | None:
        try:
            stat = os.stat(self.path)
        except OSError:
            return None
        if stat.st_mtime_ns == self._last_mtime_ns:
            return None
        try:
            with open(self.path, encoding="utf-8") as stream:
                payload = json.load(stream)
        except (OSError, ValueError, TypeError):
            return None
        self._last_mtime_ns = stat.st_mtime_ns
        return CodingStatus.from_mapping(payload)


class CodingStatusCoordinator:
    """Select one visible status from independent local and relay sources.

    Each source owns its revision sequence.  The coordinator uses the arrival
    order of visible state changes, never cross-machine clocks or revisions, to
    decide which active source is currently displayed.
    """

    def __init__(self, readers: Mapping[str, CodingStatusReader]):
        if not readers:
            raise ValueError("at least one coding status reader is required")
        self._readers = dict(readers)
        self._statuses: dict[str, CodingStatus | None] = {
            source: None for source in self._readers
        }
        self._last_arrival: dict[str, int] = {
            source: 0 for source in self._readers
        }
        self._arrival = 0
        self._current: CodingStatus | None = None

    def poll(self, now: float | None = None) -> StatusTransition | None:
        """Return one transition when the selected visible source changes."""
        changed = False
        for source, reader in self._readers.items():
            previous = self._statuses[source]
            reader.poll(now)
            current = reader.current
            if previous == current:
                continue
            self._statuses[source] = current
            if current is not None and (previous is None or previous.state != current.state):
                self._arrival += 1
                self._last_arrival[source] = self._arrival
            changed = True

        if not changed:
            return None
        next_status = self._select_current()
        if not CodingStatusReader._is_visible_change(self._current, next_status):
            self._current = next_status
            return None
        previous = self._current
        self._current = next_status
        return StatusTransition(previous, next_status)

    def _select_current(self) -> CodingStatus | None:
        active = [
            (self._last_arrival[source], status)
            for source, status in self._statuses.items()
            if status is not None
        ]
        return max(active, default=(0, None), key=lambda item: item[0])[1]


def display_state(status: CodingStatus) -> dict[str, object]:
    """Map a status enum to local artwork text without exposing work content."""
    states = {
        "working": {
            "mood": "working",
            "line": "我在协助主人处理任务",
            "sub": "Coding Agent · 工作中",
            "look": (2, 0),
        },
        "waiting": {
            "mood": "thinking",
            "line": "等主人决定下一步",
            "sub": "Coding Agent · 等待确认",
            "look": (3, -3),
        },
        "completed": {
            "mood": "happy",
            "line": "这部分处理好啦",
            "sub": "Coding Agent · 已完成",
            "look": (0, 0),
        },
        "blocked": {
            "mood": "talk",
            "line": "有一件事需要主人确认",
            "sub": "Coding Agent · 已暂停",
            "look": (0, 0),
        },
    }
    return dict(states[status.state])
