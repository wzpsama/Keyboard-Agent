"""Console-safe rotating output for foreground Python and windowless pythonw."""

from __future__ import annotations

import datetime
import os
import threading


class RuntimeLog:
    """Mirror output to an optional console and keep bounded local log files."""

    encoding = "utf-8"

    def __init__(self, path: str, console=None, max_bytes: int = 5_000_000,
                 backups: int = 3):
        self.path = path
        self.console = console
        self.max_bytes = max_bytes
        self.backups = backups
        self._lock = threading.Lock()
        self._at_line_start = True
        self._file = open(path, "a", encoding=self.encoding, buffering=1)

    def _rotate_if_needed(self) -> None:
        if self._file.tell() < self.max_bytes:
            return
        self._file.close()
        try:
            for index in range(self.backups, 1, -1):
                older = f"{self.path}.{index - 1}"
                newer = f"{self.path}.{index}"
                if os.path.exists(older):
                    os.replace(older, newer)
            if self.backups and os.path.exists(self.path):
                os.replace(self.path, f"{self.path}.1")
        finally:
            self._file = open(self.path, "a", encoding=self.encoding, buffering=1)

    def write(self, value: str) -> int:
        if not value:
            return 0
        with self._lock:
            if self.console is not None:
                self.console.write(value)
            for part in value.splitlines(keepends=True):
                if self._at_line_start:
                    self._rotate_if_needed()
                    stamp = datetime.datetime.now().isoformat(timespec="seconds")
                    self._file.write(f"{stamp} ")
                self._file.write(part)
                self._at_line_start = part.endswith(("\n", "\r"))
            self._file.flush()
        return len(value)

    def flush(self) -> None:
        with self._lock:
            if self.console is not None:
                self.console.flush()
            self._file.flush()

    def isatty(self) -> bool:
        return False

    def close(self) -> None:
        with self._lock:
            self._file.close()
