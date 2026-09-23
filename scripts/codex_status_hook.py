"""Emit bounded coding-agent states for Keyboard-Agent lifecycle hooks.

The hook never prints task data.  Its optional relay reads a private local
configuration file, so endpoints and key paths do not belong in this repository.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path


STATES = ("idle", "working", "waiting", "completed", "blocked")
TTLS = {
    "working": 15 * 60,
    "waiting": 30 * 60,
    "completed": 30,
    "blocked": 5 * 60,
}
REFRESH_AFTER_S = 60


def default_state_file() -> Path:
    root = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local" / "state"))
    return Path(os.environ.get("VEGA_STATUS_STATE_FILE", root / "keyboard-agent" /
                               "coding_status.json"))


def default_config_file() -> Path:
    return Path(os.environ.get("VEGA_STATUS_RELAY_CONFIG", Path.home() / ".config" /
                               "keyboard-agent" / "status-relay.json"))


def _read_json(path: Path) -> dict:
    try:
        with path.open(encoding="utf-8") as stream:
            value = json.load(stream)
    except (OSError, ValueError, TypeError):
        return {}
    return value if isinstance(value, dict) else {}


def _atomic_write(path: Path, payload: dict) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent,
                                     prefix=f".{path.name}.", suffix=".tmp",
                                     delete=False) as stream:
        json.dump(payload, stream, ensure_ascii=True, separators=(",", ":"))
        stream.write("\n")
        temporary = Path(stream.name)
    os.replace(temporary, path)


def update_status(path: Path, state: str, now: float | None = None) -> bool:
    """Write a new revision only when it changes or refreshes a live state."""
    now = time.time() if now is None else now
    lock_path = path.with_suffix(path.suffix + ".lock")
    lock_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    with lock_path.open("a+") as lock:
        try:
            import fcntl

            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        except (ImportError, OSError):
            pass
        previous = _read_json(path)
        previous_state = previous.get("state")
        previous_updated = previous.get("updated_at")
        if previous_state == state and isinstance(previous_updated, (int, float)) \
                and now - float(previous_updated) < REFRESH_AFTER_S:
            return False
        revision = previous.get("revision", 0)
        revision = revision if isinstance(revision, int) and not isinstance(revision, bool) else 0
        payload = {
            "version": 1,
            "state": state,
            "revision": revision + 1,
            "updated_at": now,
            "expires_at": None if state == "idle" else now + TTLS[state],
        }
        _atomic_write(path, payload)
        return True


def _relay_config(path: Path) -> tuple[str, str | None] | None:
    config = _read_json(path)
    destination = config.get("destination")
    identity_file = config.get("identity_file")
    if not isinstance(destination, str) or not destination or ":" not in destination:
        return None
    if identity_file is not None and not isinstance(identity_file, str):
        return None
    return destination, identity_file


def deliver(state_file: Path, config_file: Path) -> bool:
    """Copy the latest payload with bounded, silent best-effort retries."""
    relay = _relay_config(config_file)
    if relay is None or not state_file.is_file():
        return False
    destination, identity_file = relay
    command = ["scp", "-q", "-o", "BatchMode=yes", "-o", "ConnectTimeout=5"]
    if identity_file:
        command.extend(["-i", identity_file])
    command.extend([str(state_file), destination])
    for delay in (0, 2, 8):
        if delay:
            time.sleep(delay)
        try:
            result = subprocess.run(command, stdin=subprocess.DEVNULL,
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                    timeout=12, check=False)
        except OSError:
            return False
        if result.returncode == 0:
            return True
    return False


def start_delivery(state_file: Path, config_file: Path) -> None:
    """Detach network delivery so hooks never delay the coding-agent turn."""
    subprocess.Popen(
        [sys.executable, os.path.abspath(__file__), "--deliver",
         "--state-file", str(state_file), "--config-file", str(config_file)],
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        close_fds=True, start_new_session=True,
    )


def main() -> int:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--state", choices=STATES)
    parser.add_argument("--state-file", type=Path, default=default_state_file())
    parser.add_argument("--config-file", type=Path, default=default_config_file())
    parser.add_argument("--deliver", action="store_true")
    parser.add_argument("--hook-response", action="store_true")
    args = parser.parse_args()
    try:
        if args.deliver:
            deliver(args.state_file, args.config_file)
        elif args.state and update_status(args.state_file, args.state):
            start_delivery(args.state_file, args.config_file)
    except Exception:
        # Status reporting is observational and must never block the coding agent.
        pass
    if args.hook_response:
        sys.stdout.write('{"continue":true}\n')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
