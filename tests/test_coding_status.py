"""Hardware-free checks for the coding-agent status handoff."""

from __future__ import annotations

import json
import os
import tempfile
import unittest

from agent.coding_status import (
    CodingStatus,
    CodingStatusCoordinator,
    CodingStatusReader,
    display_state,
)


class FakeClock:
    def __init__(self):
        self.now = 100.0

    def __call__(self):
        return self.now


def write_status(path: str, **payload) -> None:
    with open(path, "w", encoding="utf-8") as stream:
        json.dump(payload, stream)
    os.utime(path, None)


class CodingStatusTests(unittest.TestCase):
    def test_working_heartbeats_extend_expiry_without_repainting(self):
        clock = FakeClock()
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "coding_status.json")
            reader = CodingStatusReader(path, clock=clock, poll_interval_s=0)
            write_status(path, state="working", revision=1, updated_at=100,
                         expires_at=160)
            first = reader.poll()
            self.assertEqual(first.current.state, "working")

            clock.now = 120
            write_status(path, state="working", revision=2, updated_at=120,
                         expires_at=180)
            self.assertIsNone(reader.poll())

            clock.now = 181
            expired = reader.poll()
            self.assertEqual(expired.previous.state, "working")
            self.assertIsNone(expired.current)

    def test_lower_revision_cannot_overwrite_newer_event(self):
        clock = FakeClock()
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "coding_status.json")
            reader = CodingStatusReader(path, clock=clock, poll_interval_s=0)
            write_status(path, state="completed", revision=8, updated_at=100,
                         expires_at=130)
            self.assertEqual(reader.poll().current.state, "completed")

            clock.now = 101
            write_status(path, state="working", revision=7, updated_at=101,
                         expires_at=200)
            self.assertIsNone(reader.poll())

    def test_invalid_payload_never_clears_current_status(self):
        clock = FakeClock()
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "coding_status.json")
            reader = CodingStatusReader(path, clock=clock, poll_interval_s=0)
            write_status(path, state="waiting", revision=1, updated_at=100,
                         expires_at=300)
            self.assertEqual(reader.poll().current.state, "waiting")
            write_status(path, state="working", revision="not-a-number", updated_at=101,
                         expires_at=300)
            self.assertIsNone(reader.poll())

    def test_status_art_uses_only_fixed_local_text(self):
        completed = CodingStatus("completed", 1, 100, 130)
        frame = display_state(completed)
        self.assertEqual(frame["mood"], "happy")
        self.assertEqual(frame["sub"], "Coding Agent · 已完成")
        self.assertNotIn("prompt", frame)

    def test_structured_states_are_rejected_without_interrupting_polling(self):
        clock = FakeClock()
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "coding_status.json")
            reader = CodingStatusReader(path, clock=clock, poll_interval_s=0)
            write_status(path, state="working", revision=1, updated_at=100,
                         expires_at=160)
            self.assertEqual(reader.poll().current.state, "working")
            for state in ([], {}, ["working"], {"state": "working"}):
                with self.subTest(state=state):
                    write_status(path, state=state, revision=2, updated_at=101,
                                 expires_at=161)
                    self.assertIsNone(reader.poll())
                    self.assertEqual(reader.current.state, "working")
            write_status(path, state="completed", revision=2, updated_at=102,
                         expires_at=132)
            self.assertEqual(reader.poll().current.state, "completed")

    def test_non_finite_and_oversized_timestamps_are_rejected(self):
        payload = dict(state="working", revision=1, updated_at=100, expires_at=160)
        for field in ("updated_at", "expires_at"):
            for value in (float("nan"), float("inf"), float("-inf"), 10**400):
                with self.subTest(field=field, value=value):
                    self.assertIsNone(CodingStatus.from_mapping({**payload, field: value}))
        self.assertIsNone(CodingStatus.from_mapping({
            **payload, "state": "idle", "updated_at": float("nan"), "expires_at": None,
        }))

    def test_independent_sources_do_not_compete_on_revision_numbers(self):
        clock = FakeClock()
        with tempfile.TemporaryDirectory() as directory:
            local_path = os.path.join(directory, "coding_status.json")
            remote_path = os.path.join(directory, "coding_status_remote.json")
            coordinator = CodingStatusCoordinator({
                "local": CodingStatusReader(local_path, clock=clock, poll_interval_s=0),
                "remote": CodingStatusReader(remote_path, clock=clock, poll_interval_s=0),
            })

            write_status(local_path, state="working", revision=100, updated_at=100,
                         expires_at=300)
            self.assertEqual(coordinator.poll().current.state, "working")

            clock.now = 101
            write_status(remote_path, state="completed", revision=1, updated_at=101,
                         expires_at=131)
            self.assertEqual(coordinator.poll().current.state, "completed")

    def test_expired_newer_source_restores_active_older_source(self):
        clock = FakeClock()
        with tempfile.TemporaryDirectory() as directory:
            local_path = os.path.join(directory, "coding_status.json")
            remote_path = os.path.join(directory, "coding_status_remote.json")
            coordinator = CodingStatusCoordinator({
                "local": CodingStatusReader(local_path, clock=clock, poll_interval_s=0),
                "remote": CodingStatusReader(remote_path, clock=clock, poll_interval_s=0),
            })

            write_status(local_path, state="working", revision=7, updated_at=100,
                         expires_at=300)
            coordinator.poll()
            clock.now = 101
            write_status(remote_path, state="waiting", revision=1, updated_at=101,
                         expires_at=110)
            self.assertEqual(coordinator.poll().current.state, "waiting")

            clock.now = 111
            restored = coordinator.poll()
            self.assertEqual(restored.previous.state, "waiting")
            self.assertEqual(restored.current.state, "working")


if __name__ == "__main__":
    unittest.main()
