"""Bounded display work and back off when the official screen tool slows down."""

from __future__ import annotations

import collections
import hashlib
import time
from dataclasses import dataclass


@dataclass(frozen=True)
class PushTask:
    kind: str
    payload: object
    created_at: float
    routine: bool = False
    urgent: bool = False


class PushQueue:
    """Keep the latest look and a small number of useful display tasks."""

    MAX_PENDING = 4

    def __init__(self, clock=time.monotonic):
        import threading

        self._clock = clock
        self._cond = threading.Condition()
        self._look = None
        self._urgent: PushTask | None = None
        self._tasks = collections.deque()

    def put_look(self, direction: str) -> None:
        with self._cond:
            self._look = direction
            self._cond.notify()

    def put_task(self, kind: str, payload: object, *, routine: bool = False,
                 urgent: bool = False) -> None:
        task = PushTask(kind, payload, self._clock(), routine, urgent)
        with self._cond:
            if urgent:
                # A mode-changing status must not be overwritten later by an
                # obsolete reaction. Keep cache work, which never writes pixels.
                self._tasks = collections.deque(
                    old for old in self._tasks if old.kind != "think")
                self._look = None
                self._urgent = task
                self._cond.notify()
                return
            if kind == "look-cache":
                self._tasks = collections.deque(
                    old for old in self._tasks if old.kind != "look-cache")
            elif routine:
                self._tasks = collections.deque(
                    old for old in self._tasks if not old.routine)
            if len(self._tasks) >= self.MAX_PENDING:
                self._tasks.popleft()
            self._tasks.append(task)
            self._cond.notify()

    def get(self) -> PushTask:
        with self._cond:
            while self._urgent is None and self._look is None and not self._tasks:
                self._cond.wait()
            if self._urgent is not None:
                task = self._urgent
                self._urgent = None
                return task
            if self._look is not None:
                direction = self._look
                self._look = None
                return PushTask("look", direction, self._clock())
            return self._tasks.popleft()

    def take_look(self):
        with self._cond:
            direction = self._look
            self._look = None
            return direction

    def has_look(self) -> bool:
        with self._cond:
            return self._look is not None

    def clear_look(self) -> None:
        with self._cond:
            self._look = None


class PushPacer:
    """Apply one cooldown to every serial write, including animated frames."""

    def __init__(self, clock=time.monotonic, sleep=time.sleep,
                 min_gap: float = 2.5, max_gap: float = 30.0,
                 slow_threshold: float = 4.0):
        self._clock = clock
        self._sleep = sleep
        self.min_gap = min_gap
        self.max_gap = max_gap
        self.slow_threshold = slow_threshold
        self.gap = min_gap
        self.next_at = 0.0
        self.healthy_streak = 0
        self.failure_streak = 0

    def ready(self) -> bool:
        return self._clock() >= self.next_at

    def wait(self) -> None:
        delay = self.next_at - self._clock()
        if delay > 0:
            self._sleep(delay)

    def succeeded(self, duration: float) -> float:
        self.failure_streak = 0
        if duration > self.slow_threshold:
            self.healthy_streak = 0
            self.gap = min(self.max_gap, max(self.min_gap, self.gap * 1.5,
                                             duration))
        else:
            self.healthy_streak += 1
            if self.healthy_streak >= 2:
                self.healthy_streak = 0
                self.gap = max(self.min_gap, self.gap * 0.8)
        self.next_at = self._clock() + self.gap
        return self.gap

    def failed(self) -> float:
        self.failure_streak += 1
        self.healthy_streak = 0
        delay = min(300.0, 30.0 * 2 ** min(self.failure_streak - 1, 4))
        self.gap = max(self.gap, self.min_gap)
        self.next_at = self._clock() + delay
        return delay


class DisplayState:
    """Track the last successfully transmitted display payload by content."""

    def __init__(self):
        self._digest: bytes | None = None

    @staticmethod
    def digest(path: str) -> bytes:
        checksum = hashlib.sha256()
        with open(path, "rb") as stream:
            for chunk in iter(lambda: stream.read(64 * 1024), b""):
                checksum.update(chunk)
        return checksum.digest()

    def compare(self, path: str) -> tuple[bool, bytes]:
        digest = self.digest(path)
        return digest == self._digest, digest

    def mark(self, digest: bytes) -> None:
        self._digest = digest

    def invalidate(self) -> None:
        self._digest = None


@dataclass(frozen=True)
class DisplayScene:
    """A semantic screen scene, independent of its encoded payload."""

    kind: str
    key: tuple[str, ...]


class SceneDirector:
    """Send only transitions away from the scene known to be on the panel."""

    def __init__(self):
        self._current: DisplayScene | None = None

    def needs_transition(self, scene: DisplayScene) -> bool:
        return scene != self._current

    def mark_displayed(self, scene: DisplayScene) -> None:
        self._current = scene

    def invalidate(self) -> None:
        self._current = None
