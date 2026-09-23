# -*- coding: utf-8 -*-
"""Push a GIF through the official Image2Bin and SerialPortTool chain.

The converter creates the animated header understood by the keyboard screen.
Directly writing a hand-built single-frame header caused color and top-row
corruption, so both conversion and transmission use the vendor tools.
"""
from __future__ import annotations

import ctypes
import os
import subprocess
import sys
import time
from ctypes import wintypes

# Driver installation path and serial port can be overridden locally.
QT_TOOL = os.environ.get("AULA_QT_TOOL", r"C:\Program Files (x86)\AULA L99\qt-tool")
IMAGE2BIN = os.path.join(QT_TOOL, "Image2Bin.exe")
SERIAL_TOOL = os.path.join(QT_TOOL, "SerialPortTool.exe")
PORT = os.environ.get("AULA_COM", "COM3")
BASE_ADDR = "0x4240000"


class _PROCESSENTRY32W(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD),
        ("cntUsage", wintypes.DWORD),
        ("th32ProcessID", wintypes.DWORD),
        ("th32DefaultHeapID", ctypes.c_size_t),
        ("th32ModuleID", wintypes.DWORD),
        ("cntThreads", wintypes.DWORD),
        ("th32ParentProcessID", wintypes.DWORD),
        ("pcPriClassBase", wintypes.LONG),
        ("dwFlags", wintypes.DWORD),
        ("szExeFile", wintypes.WCHAR * 260),
    ]


def serial_port_exists(port: str = PORT) -> bool:
    """Return whether Windows currently exposes the configured COM device."""
    if os.name != "nt":
        return True
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.QueryDosDeviceW.argtypes = (
        wintypes.LPCWSTR, wintypes.LPWSTR, wintypes.DWORD)
    kernel32.QueryDosDeviceW.restype = wintypes.DWORD
    target = port.rstrip(":")
    buffer = ctypes.create_unicode_buffer(32768)
    return bool(kernel32.QueryDosDeviceW(target, buffer, len(buffer)))


def serial_tool_running() -> bool:
    """Return whether another vendor serial-tool process is still alive."""
    if os.name != "nt":
        return False
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateToolhelp32Snapshot.argtypes = (wintypes.DWORD, wintypes.DWORD)
    kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    kernel32.Process32FirstW.argtypes = (
        wintypes.HANDLE, ctypes.POINTER(_PROCESSENTRY32W))
    kernel32.Process32FirstW.restype = wintypes.BOOL
    kernel32.Process32NextW.argtypes = (
        wintypes.HANDLE, ctypes.POINTER(_PROCESSENTRY32W))
    kernel32.Process32NextW.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)

    snapshot = kernel32.CreateToolhelp32Snapshot(0x00000002, 0)
    if snapshot == ctypes.c_void_p(-1).value:
        return False
    target = os.path.basename(SERIAL_TOOL).casefold()
    entry = _PROCESSENTRY32W()
    entry.dwSize = ctypes.sizeof(entry)
    try:
        found = kernel32.Process32FirstW(snapshot, ctypes.byref(entry))
        while found:
            if entry.szExeFile.casefold() == target:
                return True
            found = kernel32.Process32NextW(snapshot, ctypes.byref(entry))
        return False
    finally:
        kernel32.CloseHandle(snapshot)


def _hidden_process_options() -> dict:
    """Prevent official command-line tools from opening a console over a game."""
    if os.name != "nt":
        return {}
    startup = subprocess.STARTUPINFO()
    startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startup.wShowWindow = subprocess.SW_HIDE
    return {"startupinfo": startup,
            "creationflags": subprocess.CREATE_NO_WINDOW}


def gif_to_bin(gif_path: str, timeout: float = 30.0) -> str:
    """Convert a GIF to a same-name .bin file with the official converter."""
    bin_path = os.path.splitext(gif_path)[0] + ".bin"
    try:
        subprocess.run([IMAGE2BIN, gif_path], cwd=QT_TOOL,
                       check=True, capture_output=True, timeout=timeout,
                       **_hidden_process_options())
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"Image2Bin timeout after {timeout:.0f}s") from None
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(f"Image2Bin rc={exc.returncode}") from None
    except OSError as exc:
        raise RuntimeError(f"Image2Bin launch failed: {exc}") from None
    return bin_path


def push_bin(bin_path: str, timeout: float = 60.0) -> None:
    """Stream a prepared .bin file through the official serial tool.

    The 60-second timeout is a last resort. Killing a write midway may leave
    the panel in an unknown state, so the caller must cool down after failure.
    Slow calls and failures retain the tool's output in the local log.
    """
    if not serial_port_exists(PORT):
        raise RuntimeError(f"Serial port {PORT} is not available")
    if serial_tool_running():
        raise RuntimeError("SerialPortTool is already running")
    t0 = time.monotonic()
    try:
        r = subprocess.run([SERIAL_TOOL, bin_path, PORT, BASE_ADDR],
                           cwd=QT_TOOL, capture_output=True, timeout=timeout,
                           **_hidden_process_options())
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"SerialPortTool timeout after {timeout:.0f}s") from None
    except OSError as exc:
        raise RuntimeError(f"SerialPortTool launch failed: {exc}") from None
    dt = time.monotonic() - t0
    if dt > 1.0 or r.returncode != 0:
        out = (r.stdout or b"").decode("utf-8", "replace").strip()
        err = (r.stderr or b"").decode("utf-8", "replace").strip()
        print(f"[push] SerialPortTool {dt*1000:.0f}ms rc={r.returncode}"
              + (f" stdout={out[:300]!r}" if out else "")
              + (f" stderr={err[:300]!r}" if err else ""))
    if r.returncode != 0:
        raise RuntimeError(f"SerialPortTool rc={r.returncode}")


def push_gif(gif_path: str) -> str:
    """Convert and send a GIF; return the resulting .bin path."""
    bin_path = gif_to_bin(gif_path)
    push_bin(bin_path)
    return bin_path


if __name__ == "__main__":
    # Manual command-line entry point.
    if len(sys.argv) < 2:
        print("Usage: python push_local.py <file.gif|file.bin>")
        sys.exit(1)
    path = sys.argv[1]
    if path.lower().endswith(".gif"):
        print(push_gif(path))
    else:
        push_bin(path)
        print("DONE", path)
