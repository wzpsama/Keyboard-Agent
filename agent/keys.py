"""键盘/鼠标分析：从 (vk, 时间) 事件流算出手速/键簇/热键等信号（纯逻辑，可单测）。

不碰任何 Windows API —— ctrl 状态、时间戳都由调用方（win_agent 的钩子）传入，
这样本模块可以在 Linux 上直接跑单测。
"""
from __future__ import annotations

import collections

# ---- Windows 虚拟键码（VK）----
VK_CTRL = 0x11
VK_SPACE = 0x20
VK_V = 0x56
VK_BACK = 0x08
VK_DELETE = 0x2E
VK_CAPSLOCK = 0x14

WASD = {0x57, 0x41, 0x53, 0x44}          # W A S D
ARROWS = {0x25, 0x26, 0x27, 0x28}        # ← ↑ → ↓
GAME_KEYS = WASD | ARROWS | {VK_SPACE}


class KeyAnalyst:
    """滑动窗口键盘统计。

    add(vk, ctrl_down, t) 喂原始按键；各查询按 span（秒，默认 window）过滤。
    """

    def __init__(self, window: float = 90.0):
        self.window = window
        self._ev: collections.deque = collections.deque()   # (vk, ctrl_down, t)

    def add(self, vk: int, ctrl_down: bool, t: float) -> None:
        self._ev.append((vk, ctrl_down, t))
        self._prune(t)

    def _prune(self, t: float) -> None:
        while self._ev and t - self._ev[0][2] > self.window:
            self._ev.popleft()

    def _recent(self, t: float, span: float | None):
        self._prune(t)
        span = self.window if span is None else span
        return [e for e in self._ev if t - e[2] <= span]

    def kpm(self, t: float, span: float | None = None) -> float:
        """span 内按键速率（键/分钟）。"""
        ev = self._recent(t, span)
        if not ev:
            return 0.0
        span_s = max(t - ev[0][2], 0.001)
        return len(ev) / span_s * 60.0

    def count_in(self, vk_set, t: float, span: float | None = None) -> int:
        return sum(1 for vk, _, _ in self._recent(t, span) if vk in vk_set)

    def ctrl_v_count(self, t: float, span: float | None = None) -> int:
        """span 内 Ctrl+V（粘贴）次数。"""
        return sum(1 for vk, ctrl, _ in self._recent(t, span) if vk == VK_V and ctrl)

    def backspace_count(self, t: float, span: float | None = None) -> int:
        return self.count_in({VK_BACK, VK_DELETE}, t, span)

    def space_count(self, t: float, span: float | None = None) -> int:
        return self.count_in({VK_SPACE}, t, span)

    def game_count(self, t: float, span: float | None = None) -> int:
        return self.count_in(GAME_KEYS, t, span)

    def game_share(self, t: float, span: float | None = None) -> float:
        """span 内游戏键簇（WASD/方向/空格）占比（0~1）。"""
        ev = self._recent(t, span)
        if not ev:
            return 0.0
        return sum(1 for vk, _, _ in ev if vk in GAME_KEYS) / len(ev)


class ClickAnalyst:
    """滑动窗口鼠标点击统计。add(t) 喂左键点击时间。"""

    def __init__(self, window: float = 60.0):
        self.window = window
        self._ts: collections.deque = collections.deque()

    def add(self, t: float) -> None:
        self._ts.append(t)
        self._prune(t)

    def _prune(self, t: float) -> None:
        while self._ts and t - self._ts[0] > self.window:
            self._ts.popleft()

    def apm(self, t: float, span: float | None = None) -> float:
        """span 内点击速率（次/分钟）。"""
        self._prune(t)
        ts = self._ts
        if span is not None:
            ts = [x for x in ts if t - x <= span]
        if not ts:
            return 0.0
        span_s = max(t - ts[0], 0.001)
        return len(ts) / span_s * 60.0
