"""Hardware-free tests for the private-config coding status relay hook."""

from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


HOOK_PATH = Path(__file__).resolve().parents[1] / "scripts" / "codex_status_hook.py"
SPEC = importlib.util.spec_from_file_location("coding_status_hook", HOOK_PATH)
assert SPEC is not None and SPEC.loader is not None
coding_status_hook = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(coding_status_hook)


class CodingStatusHookTests(unittest.TestCase):
    def test_state_updates_are_deduplicated_and_expire(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"
            self.assertTrue(coding_status_hook.update_status(path, "working", now=100))
            self.assertFalse(coding_status_hook.update_status(path, "working", now=110))
            self.assertTrue(coding_status_hook.update_status(path, "working", now=161))

            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(payload["state"], "working")
            self.assertEqual(payload["revision"], 2)
            self.assertEqual(payload["expires_at"], 1061)

    def test_relay_copies_only_the_state_file_with_private_config(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state_file = root / "state.json"
            config_file = root / "relay.json"
            coding_status_hook.update_status(state_file, "completed", now=100)
            config_file.write_text(json.dumps({
                "destination": "host-alias:/private/inbox.json",
                "identity_file": "/private/key",
            }), encoding="utf-8")

            result = SimpleNamespace(returncode=0)
            with mock.patch.object(coding_status_hook.subprocess, "run", return_value=result) as run:
                self.assertTrue(coding_status_hook.deliver(state_file, config_file))

            command = run.call_args.args[0]
            self.assertEqual(command[:6], ["scp", "-q", "-o", "BatchMode=yes", "-o", "ConnectTimeout=5"])
            self.assertIn("-i", command)
            self.assertEqual(command[-2], str(state_file))
            self.assertEqual(command[-1], "host-alias:/private/inbox.json")
