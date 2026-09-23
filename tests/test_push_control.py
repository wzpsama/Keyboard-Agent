"""Hardware-free checks for display pacing and error handling."""

from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock

from PIL import Image, ImageChops

from agent.push_control import (
    DisplayScene,
    DisplayState,
    PushPacer,
    PushQueue,
    SceneDirector,
)
from agent.runtime_log import RuntimeLog
from pusher import push_local
from renderer.gif_loop import save_loop_gif
from renderer.render import render_frame
from renderer.vega import AMBIENT_DURATIONS_MS, render_vega


class FakeTime:
    def __init__(self):
        self.now = 100.0

    def clock(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


class PushQueueTests(unittest.TestCase):
    def test_latest_look_preempts_bounded_animation_queue(self):
        clock = FakeTime()
        q = PushQueue(clock=clock.clock)
        for number in range(6):
            q.put_task("think", number)
        q.put_look("left")
        q.put_look("center")
        look = q.get()
        self.assertEqual((look.kind, look.payload), ("look", "center"))
        self.assertEqual([q.get().payload for _ in range(4)], [2, 3, 4, 5])

    def test_routine_and_cache_tasks_replace_older_versions(self):
        q = PushQueue()
        q.put_task("think", "old", routine=True)
        q.put_task("think", "reaction")
        q.put_task("think", "new", routine=True)
        q.put_task("look-cache", "idle")
        q.put_task("look-cache", "happy")
        self.assertEqual([q.get().payload for _ in range(3)],
                         ["reaction", "new", "happy"])

    def test_urgent_status_preempts_looks_and_discards_old_animations(self):
        q = PushQueue()
        q.put_task("think", "routine", routine=True)
        q.put_task("think", "reaction")
        q.put_task("look-cache", "idle")
        q.put_look("left")
        q.put_task("think", "coding-status", urgent=True)

        urgent = q.get()
        self.assertEqual((urgent.kind, urgent.payload, urgent.urgent),
                         ("think", "coding-status", True))
        cached = q.get()
        self.assertEqual((cached.kind, cached.payload), ("look-cache", "idle"))


class PushPacerTests(unittest.TestCase):
    def test_normal_official_write_stays_at_the_minimum_gap(self):
        clock = FakeTime()
        pacer = PushPacer(clock=clock.clock, sleep=clock.sleep)
        self.assertEqual(pacer.succeeded(1.7), 2.5)

    def test_slow_success_and_failures_cool_down_all_writes(self):
        clock = FakeTime()
        pacer = PushPacer(clock=clock.clock, sleep=clock.sleep)
        self.assertEqual(pacer.succeeded(16.0), 16.0)
        self.assertFalse(pacer.ready())
        pacer.wait()
        self.assertEqual(clock.now, 116.0)
        self.assertEqual(pacer.failed(), 30.0)
        pacer.wait()
        self.assertEqual(clock.now, 146.0)
        self.assertEqual(pacer.failed(), 60.0)
        pacer.wait()
        self.assertEqual(clock.now, 206.0)
        self.assertGreaterEqual(pacer.succeeded(0.2), 2.5)
        self.assertEqual(pacer.failure_streak, 0)


class DisplayStateTests(unittest.TestCase):
    def test_only_a_successfully_marked_identical_payload_is_current(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "frame.bin")
            with open(path, "wb") as stream:
                stream.write(b"first")

            display = DisplayState()
            unchanged, digest = display.compare(path)
            self.assertFalse(unchanged)
            display.mark(digest)
            self.assertTrue(display.compare(path)[0])

            with open(path, "wb") as stream:
                stream.write(b"second")
            self.assertFalse(display.compare(path)[0])
            display.invalidate()
            self.assertFalse(display.compare(path)[0])


class SceneDirectorTests(unittest.TestCase):
    def test_only_scene_transitions_need_a_new_screen_write(self):
        director = SceneDirector()
        idle = DisplayScene("look", ("idle", "center"))
        left = DisplayScene("look", ("idle", "left"))
        self.assertTrue(director.needs_transition(idle))
        director.mark_displayed(idle)
        self.assertFalse(director.needs_transition(idle))
        self.assertTrue(director.needs_transition(left))
        director.mark_displayed(left)
        self.assertTrue(director.needs_transition(idle))
        director.invalidate()
        self.assertTrue(director.needs_transition(idle))


class AmbientAnimationTests(unittest.TestCase):
    def test_ambient_frames_keep_the_character_still_and_include_blink(self):
        base = {"look": (0, 0), "mood": "idle", "ambient": True}
        exhale = render_vega({**base, "ambient_phase": 0.75}, height=220)
        inhale = render_vega({**base, "ambient_phase": 0.25}, height=220)
        blink = render_vega(
            {**base, "ambient_phase": 0.5, "blink": True}, height=220)
        self.assertEqual(len(AMBIENT_DURATIONS_MS), 4)
        self.assertEqual(exhale.size, inhale.size)
        self.assertEqual(exhale.tobytes(), inhale.tobytes())
        self.assertNotEqual(inhale.tobytes(), blink.tobytes())

    def test_gif_encoder_keeps_open_eye_body_pixels_identical(self):
        frames = []
        for index in range(len(AMBIENT_DURATIONS_MS)):
            frames.append(render_frame({
                "character": "vega", "mood": "idle", "line": "",
                "sub": "idle", "clock": "12:34", "look": (0, 0),
                "ambient": True, "ambient_phase": index / len(AMBIENT_DURATIONS_MS),
                "blink": index == len(AMBIENT_DURATIONS_MS) // 2,
            }))
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "ambient.gif")
            save_loop_gif(frames, path, AMBIENT_DURATIONS_MS)
            decoded = []
            with Image.open(path) as image:
                for index in range(image.n_frames):
                    image.seek(index)
                    decoded.append(image.convert("RGB").copy())

        body = (40, 156, 280, 376)
        self.assertIsNone(ImageChops.difference(
            decoded[0].crop(body), decoded[1].crop(body)).getbbox())
        self.assertIsNotNone(ImageChops.difference(
            decoded[1].crop(body), decoded[2].crop(body)).getbbox())


class RuntimeLogTests(unittest.TestCase):
    def test_windowless_log_has_timestamps_and_rotates(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "agent_run.log")
            log = RuntimeLog(path, console=None, max_bytes=60, backups=2)
            log.write("first line\n")
            log.write("second line\n")
            log.write("third line\n")
            log.close()
            self.assertTrue(os.path.exists(path + ".1"))
            with open(path, encoding="utf-8") as current:
                self.assertIn("third line", current.read())
            with open(path + ".1", encoding="utf-8") as older:
                self.assertIn("first line", older.read())


class OfficialToolTests(unittest.TestCase):
    @unittest.skipUnless(os.name == "nt", "Windows process flags")
    def test_official_tools_start_without_a_console_window(self):
        options = push_local._hidden_process_options()
        self.assertEqual(options["creationflags"], subprocess.CREATE_NO_WINDOW)
        self.assertEqual(options["startupinfo"].wShowWindow, subprocess.SW_HIDE)

    def test_serial_timeout_does_not_expose_full_command(self):
        exc = subprocess.TimeoutExpired(["secret-path", "COM3"], 60)
        with mock.patch.object(push_local, "serial_port_exists", return_value=True), \
                mock.patch.object(push_local, "serial_tool_running", return_value=False), \
                mock.patch.object(push_local.subprocess, "run", side_effect=exc):
            with self.assertRaisesRegex(RuntimeError, "SerialPortTool timeout") as caught:
                push_local.push_bin("frame.bin")
        self.assertNotIn("secret-path", str(caught.exception))

    def test_success_uses_official_serial_tool(self):
        result = SimpleNamespace(returncode=0, stdout=b"", stderr=b"")
        with mock.patch.object(push_local, "serial_port_exists", return_value=True), \
                mock.patch.object(push_local, "serial_tool_running", return_value=False), \
                mock.patch.object(push_local.subprocess, "run", return_value=result) as run:
            push_local.push_bin("frame.bin")
        self.assertEqual(run.call_args.args[0][0], push_local.SERIAL_TOOL)
        self.assertEqual(run.call_args.args[0][1:],
                         ["frame.bin", push_local.PORT, push_local.BASE_ADDR])

    def test_missing_serial_port_stops_before_launch(self):
        with mock.patch.object(push_local, "serial_port_exists", return_value=False), \
                mock.patch.object(push_local.subprocess, "run") as run:
            with self.assertRaisesRegex(RuntimeError, "is not available"):
                push_local.push_bin("frame.bin")
        run.assert_not_called()

    def test_existing_serial_tool_stops_before_launch(self):
        with mock.patch.object(push_local, "serial_port_exists", return_value=True), \
                mock.patch.object(push_local, "serial_tool_running", return_value=True), \
                mock.patch.object(push_local.subprocess, "run") as run:
            with self.assertRaisesRegex(RuntimeError, "already running"):
                push_local.push_bin("frame.bin")
        run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
