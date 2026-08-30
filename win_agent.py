"""Windows 本地常驻 agent（离线版）—— 官方 Image2Bin + SerialPortTool 推屏。

把原先「mini PC 渲染 + SSH 遥控 Windows」的架构收敛成**在键盘机（Windows）本地
单进程跑**：屏幕（COM3）、键盘（USB HID）、官方推屏工具（Image2Bin.exe /
SerialPortTool.exe）都在本机，无需任何 SSH 往返。

单进程内的职责：
  1. 键盘钩子（WH_KEYBOARD_LL）—— 捕获「屏幕周围一圈」的按键，映射成视线方向
  2. 本地感知（GetLastInputInfo）—— 主人活跃度（active / idle / away）
  3. 事件总线 + 交互注册表 —— 每个交互是一个 handler，可插拔扩展
  4. 离线大脑（states.offline_next）—— 情绪随机游走（不花 token）
  5. 本地推屏 —— 看向用**预渲染 .bin**（快，~300ms）；思考用 GIF→Image2Bin→
     SerialPortTool（官方动画链，屏幕正确解析头、顶部无污染）

推屏为什么用官方链（Image2Bin 动画格式）而不是直写：
  - 屏幕实测**大端**、且只认 Image2Bin 产出的动画 .bin 头；手写单帧 .bin 头
    （push_cdc 的做法）会被屏幕当像素显示成顶部污染 + 字节序错色。
  - 官方链是驱动自带、稳定正确；预渲染把「看向」的渲染+转换提前做好，按下键
    时只推现成 .bin，做到亚秒级响应。

跑法（在键盘机 Windows 上，本文件所在目录）：
  python  win_agent.py              # 前台，看日志，Ctrl+C 退出
  python  win_agent.py --interval 15
  pythonw win_agent.py              # 无窗口后台

依赖：Pillow（已装）。离线模式无需 anthropic / API key。
在线大脑（Claude API）接口已预留：见 FUTURE.md「在线大脑」——未来 pip install
anthropic + 配 ANTHROPIC_API_KEY 后，把 Brain(offline=True) 换成 False 即可。
"""
from __future__ import annotations

import argparse
import collections
import ctypes
import datetime
import os
import queue
import sys
import threading
import time
from ctypes import wintypes

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
if hasattr(sys.stdout, "reconfigure"):  # Windows 控制台 cp932/gbk 兜底 + 行缓冲
    sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)

from renderer.render import render_frame  # noqa: E402
from renderer.vega import mood_to_action, action_durations  # noqa: E402
from agent.states import offline_next, SUBS  # noqa: E402
from agent.memory import PetMemory  # noqa: E402
from agent.core import Interaction, EventBus  # noqa: E402
from agent import keys, sensors, weather  # noqa: E402
from agent.interactions import EXTRA_INTERACTIONS  # noqa: E402
from pusher.push_local import push_bin, push_gif, gif_to_bin  # noqa: E402

# ---- 常量 ----
OUT_DIR = os.path.join(HERE, "out")
DATA_DIR = os.path.join(HERE, "data")
CHARACTER = "vega"           # 当前角色：织女/Vega（精灵版）；切回 "dango" 用程序化团子

ACTIVE_S = 60                # < 60s 未输入视为「正在用电脑」
DEFAULT_INTERVAL = 30.0      # 慢思考间隔（秒）

# 说话仲裁（防冲突）：全局节流 + 互斥组。优先级 high 可抢占，med/low 受最小间隔约束。
SPEECH_MIN_GAP = 8.0         # med 优先级最小说话间隔（秒）
SPEECH_LOW_GAP = 20.0        # low 优先级更长间隔（秒）
GROUP_WINDOW = 15.0          # 互斥组时间窗（秒）：同组此窗内只允许一个发声
CRY_HOLD = 4.0               # 哭/表情锁定：此秒数内看向被抑制，让哭动画完整播完不被转头覆盖
# 思考动画单循环时长/帧率：屏幕会循环播放 GIF，短循环即可表达「在思考」。
# 实测 48 帧 = 305KB .bin（大推屏 + Image2Bin 转换都会长时间阻塞看向线程）；
# 4 帧 ≈ 27KB：比旧 9 帧再轻一半多（2026-08-25 用户反馈随机表情刷新仍阻塞）。
THINK_DURATION = 1.0
THINK_FPS = 4
LOOK_FPS = 8
LOOK_FRAMES = 1              # 看向用单帧静态图：屏幕端解压量降到 1/4，连点不积压

# 面板背压限速（2026-08-24 卡死根因）：
# 屏幕 flash 消化一个 ~10KB 看向要 ~2.5s（500ms/块）。喂太快 → 面板饱和 →
# SerialPortTool 写入阻塞在驱动缓冲区（实测单次推到 13.7s = 「卡死」观感）。
# 实测 300 连推全快是因为推屏背靠背无间隔；真实用户按键有节奏，面板边推边消化，
# 一旦积压就进入「每推 ~11.5s」的稳定饱和态。所以：看向限速 + 慢推屏触发冷却排水。
# 方案④ 自适应限速（2026-08-25，叠加其上）：推屏耗时 dt 本身=积压传感器
# （面板空时单推 ~300ms；缓冲积压时 dt 变长）。AIMD 闭环调速：
#   健康 dt≤1.5s 连续 HEALTHY_TO_SPEED 次 → gap×0.7 提速（下限 LOOK_GAP_MIN）；
#   慢推屏 dt>1.5s → gap×2 退避（上限 LOOK_GAP_MAX）+ 冷却 = 本次 dt（排水量
#   与积压成正比，取代固定 8s）；
#   推屏失败（串口被杀）→ 直接回饱和档。
# 校准（2026-08-25 用户实测无卡后调激进）：看向 ~9KB ≈ 面板消化 ~2.2s——
# 连续快速打字的看向节奏上限就是 ~2.2s/个（物理消化速度，任何阈值都突破不了，
# 积压会自动被退避拉回）。LOOK_GAP_MIN 只决定「零散按键（间隔>2.2s）」的响应
# 快慢，可低到推屏链自身成本 ~0.3s 附近。
LOOK_GAP_MIN = 0.4           # 面板健康时的看向最小间隔（秒）
LOOK_GAP_MAX = 8.0           # 饱和退避上限（秒）
LOOK_GAP_START = 1.2         # 启动/失败复位档（自适应半分钟内收敛到实际档位）
LOOK_FAST_MS = 1500          # 单推耗时 ≤ 此值 = 健康；超过 = 饱和信号
HEALTHY_TO_SPEED = 2         # 连续健康 N 次才提速一档（收敛更快）

# 饱和期「别太拼」关心帧（2026-08-25）：频繁快速敲击 → 面板积压（dt>阈值）时，
# 把一次方向看向替换成单帧关心图（仍是 ~9KB 单帧，不加重面板负担），把「等待」
# 包装成宠物的关心。触发 = 已有的饱和信号，无需另做敲击频率检测。
HW_LINE = "主人工作得太努力了"  # 气泡台词
HW_SUB = "休息一下下～"       # 状态栏副标题
HW_MOOD = "talk"              # 关心表情（brain.py 的 mood）
HW_RATE_LIMIT = 12.0          # 饱和期最多每 12s 显示一次（避免刷屏）

# 方向 → 视线偏移 (dx, dy)。dx 正=右，dy 正=下
DIR_LOOK = {
    "up": (0, -6),        # 抬头看上方键（PrintScreen/Scroll/Pause）
    "left-up": (-5, -5),  # 左上（Home/PageUp/↑）
    "left": (-6, 0),      # 左（键盘主体）
    "center": (0, 0),     # 正视
}

# VK code → 方向（屏幕在键盘最右边，上/左被按键环绕）
_VK = {
    "up":      [0x2C, 0x91, 0x13],              # PrintScreen, Scroll Lock, Pause
    "left-up": [0x24, 0x21, 0x26, 0x2E],        # Home, PageUp, ↑, Delete
    "left":    [0x22, 0x23, 0x25, 0x27, 0x28],  # PageDown, End, ←, →, ↓
}
_DIR = {c: d for d, codes in _VK.items() for c in codes}


def dir_for(vk: int) -> str:
    return _DIR.get(vk, "left")  # 未列出的键默认在屏幕左侧


# =====================================================================
#  推屏：官方链 + 看向「最新覆盖」+ 后台线程（不阻塞按键泵）
# =====================================================================
class _PushQueue:
    """串行推屏队列：看向是「单槽覆盖」只保留最新方向（丢弃过期帧）；
    思考/渲染任务按 FIFO 串行。get() 优先返回看向，保证按键实时响应。"""
    def __init__(self):
        self._cond = threading.Condition()
        self._look = None                       # 最新看向方向（None=无待推）
        self._thinks = collections.deque()      # ("think", state) / ("look-cache", mood)

    def put_look(self, direction: str) -> None:
        with self._cond:
            self._look = direction
            self._cond.notify()

    def put_think(self, task) -> None:
        with self._cond:
            self._thinks.append(task)
            self._cond.notify()

    def get(self):
        with self._cond:
            while self._look is None and not self._thinks:
                self._cond.wait()
            if self._look is not None:
                d = self._look
                self._look = None
                return ("look", d)
            return self._thinks.popleft()

    def take_look(self):
        """取出并清空最新看向（无则返回 None）。供限速等待/长渲染期间重取最新方向。"""
        with self._cond:
            d = self._look
            self._look = None
            return d

    def clear_look(self):
        """丢弃待推看向（无则 no-op）。哭/表情锁定时用，让哭动画立即插队不被转头抢先。"""
        with self._cond:
            self._look = None


_push_q = _PushQueue()
_look_bins: dict[str, str] = {}                       # direction -> .bin（当前 mood）
_look_bins_cache: dict[tuple[str, str], str] = {}     # (mood, direction) -> .bin
_hardworking_bin: str = ""                            # 饱和期关心帧 .bin 路径（懒渲染，独立于 mood）


def _render_gif(state: dict, name: str, frames: int, fps: int,
                durations=None, on_progress=None) -> str:
    """把单个状态渲染成一段循环动画 GIF（眨眼/动作随 t 自动驱动），返回路径。

    durations 为每帧时长(ms)列表时，按非均匀节奏渲染（动作动画用），帧数取
    len(durations)；否则按 frames×fps 均匀节奏。on_progress(i, frames) 每渲染
    一帧后回调一次，供思考长动画期间让看向插队推屏。
    """
    import datetime as _dt
    imgs = []
    dt = 1.0 / fps
    clock = state.get("clock") or _dt.datetime.now().strftime("%H:%M")
    t0 = float(state.get("t", 0.0))
    n = len(durations) if durations else frames
    for i in range(n):
        s = dict(state)
        # 非均匀：t 前进累计时长，让 render_vega 的动作帧选取与 GIF 帧时长对齐
        s["t"] = t0 + (sum(durations[:i]) / 1000.0 if durations else i * dt)
        s["clock"] = clock
        s.setdefault("character", CHARACTER)  # 默认用 Vega 精灵（含方向视图）
        imgs.append(render_frame(s))
        if on_progress is not None:
            on_progress(i, n)
    gif = os.path.join(OUT_DIR, name)
    gif_duration = durations if durations else int(1000 / fps)
    imgs[0].save(gif, save_all=True, append_images=imgs[1:],
                 duration=gif_duration, loop=0, optimize=False)
    return gif


def _render_look_bins(mood: str) -> dict[str, str]:
    """渲染 + 转换某 mood 的 4 个看向 .bin（后台线程调用，~1s）。"""
    os.makedirs(OUT_DIR, exist_ok=True)
    bins: dict[str, str] = {}
    for direction in DIR_LOOK:
        key = (mood, direction)
        if key in _look_bins_cache:
            bins[direction] = _look_bins_cache[key]
            continue
        sub = "看到主人啦" if direction != "center" else "住在你的键盘里"
        state = {"mood": mood, "line": "", "sub": sub,
                 "look": DIR_LOOK[direction], "t": 0.0}
        gif = _render_gif(state, f"look_{mood}_{direction}.gif", LOOK_FRAMES, LOOK_FPS)
        path = gif_to_bin(gif)
        _look_bins_cache[key] = path
        bins[direction] = path
    return bins


def _ensure_hardworking_bin() -> None:
    """懒渲染饱和期「别太拼」关心帧（单帧 ~9KB，与看向同体积，不加重面板负担）。"""
    global _hardworking_bin
    if _hardworking_bin:
        return
    os.makedirs(OUT_DIR, exist_ok=True)
    state = {"mood": HW_MOOD, "line": HW_LINE, "sub": HW_SUB,
             "look": (0, 0), "t": 0.0}
    gif = _render_gif(state, "look_hardworking.gif", LOOK_FRAMES, LOOK_FPS)
    _hardworking_bin = gif_to_bin(gif)
    print(f"[push] 「别太拼」关心帧已就绪：{os.path.basename(_hardworking_bin)}")


def prepare_look_bins(mood: str = "idle", blocking: bool = False) -> None:
    """确保当前 mood 的看向 .bin 就绪。

    命中缓存 → 秒切；未命中 → 丢后台线程渲染（期间沿用旧 mood，按键不丢响应）。
    blocking=True 用于启动时：同步渲染首个 mood，避免按键泵启动前无 .bin 可推。
    """
    global _look_bins
    if all((mood, d) in _look_bins_cache for d in DIR_LOOK):
        _look_bins = {d: _look_bins_cache[(mood, d)] for d in DIR_LOOK}
        return
    if blocking:
        _look_bins = _render_look_bins(mood)
        print(f"[push] 看向 .bin 已缓存（mood={mood}）: "
              f"{', '.join(os.path.basename(p) for p in _look_bins.values())}")
    else:
        _push_q.put_think(("look-cache", mood))


def push_look(direction: str) -> None:
    """推预渲染看向 .bin（最新覆盖，~300ms，不阻塞按键泵）。"""
    if direction in _look_bins:
        _push_q.put_look(direction)


def push_think(state: dict) -> None:
    """把思考状态渲染成动画 GIF → Image2Bin → SerialPortTool（后台线程）。"""
    _push_q.put_think(("think", state))


def _push_worker() -> None:
    """后台推屏线程：优先推看向（实时），再串行处理思考/渲染。

    面板背压（2026-08-24 卡死根因修复）：屏幕消化一个 ~10KB 看向要 ~2.5s，
    喂太快会饱和 → SerialPortTool 阻塞（实测 13.7s）。因此：
      ①看向按 look_gap 限速 + latest-wins 只推最新方向；
      ②方案④ 自适应：dt>1.5s 判饱和 → gap×2 退避 + 按 dt 冷却排水，
        冷却期间丢弃过期看向（睡醒后重取最新方向补推一次）；
        连续健康则 gap 逐步回落到 1.2s（宠物更灵敏）。
    推屏超时由 push_bin 内部杀掉 SerialPortTool 释放串口，自动重开复位自愈。
    """
    global _look_bins
    last_look_t = 0.0         # 上次看向推屏完成时刻（限速用）
    cooldown_until = 0.0      # 面板饱和冷却截止时刻（0=未冷却）
    look_gap = LOOK_GAP_START # 方案④：当前看向最小间隔，按面板健康度自适应
    healthy_streak = 0        # 连续健康推屏计数（攒满提速）
    pending_hw = False        # 饱和期：下一次看向替换成「别太拼」关心帧
    last_hw_t = 0.0           # 上次显示关心帧时刻（限频）

    def do_look(payload, sleep_ok=True):
        """推一个看向 .bin：限速门控 + 推前重取最新方向 + 方案④ 自适应调速。
        饱和期按 HW_RATE_LIMIT 频度把方向看向替换成「别太拼」关心帧。
        sleep_ok=False 供思考渲染间隙调用（不阻塞渲染，超限速直接跳过）。"""
        nonlocal last_look_t, cooldown_until, look_gap, healthy_streak, pending_hw, last_hw_t
        now = time.time()
        if now < cooldown_until:
            if not sleep_ok:
                return
            time.sleep(cooldown_until - now)
            cooldown_until = 0.0
        elif now - last_look_t < look_gap:
            if not sleep_ok:
                return
            time.sleep(last_look_t + look_gap - now)
        if pending_hw and _hardworking_bin:
            pending_hw = False
            _push_q.take_look()       # 丢弃这次方向看向（被关心帧取代）
            target, label = _hardworking_bin, "别太拼"
        else:
            d = _push_q.take_look()   # 睡醒重取：期间新看向已覆盖旧方向
            if d is not None:
                payload = d
            target, label = _look_bins[payload], payload
        t0 = time.time()
        try:
            push_bin(target)
        except Exception:
            # 推屏失败（串口被杀等）：面板状态未知 → 回饱和档，交给外层自愈
            look_gap = LOOK_GAP_MAX
            healthy_streak = 0
            cooldown_until = time.time() + LOOK_GAP_MAX
            raise
        dt = time.time() - t0
        last_look_t = time.time()
        if dt * 1000 > LOOK_FAST_MS:
            # 饱和：指数退避 + 冷却排水（冷却量 = 本次积压耗时 dt，随积压自适应）
            look_gap = min(LOOK_GAP_MAX, look_gap * 2)
            healthy_streak = 0
            cooldown_until = last_look_t + dt
            if last_look_t - last_hw_t >= HW_RATE_LIMIT:
                pending_hw = True
                last_hw_t = last_look_t
            print(f"[push] 看向 {label} ({dt*1000:.0f}ms) — 面板饱和，"
                  f"退避 gap={look_gap:.1f}s + 冷却 {dt:.1f}s 排水")
        else:
            healthy_streak += 1
            if healthy_streak >= HEALTHY_TO_SPEED:
                healthy_streak = 0
                look_gap = max(LOOK_GAP_MIN, look_gap * 0.7)
                print(f"[push] 看向 {label} ({dt*1000:.0f}ms) — 面板健康，"
                      f"提速 gap={look_gap:.1f}s")
            else:
                print(f"[push] 看向 {label} ({dt*1000:.0f}ms)")

    while True:
        kind, payload = _push_q.get()
        try:
            if kind == "look":
                do_look(payload)
            elif kind == "think":
                # 思考长动画：每渲染几帧检查一次待推看向并先推，避免阻塞按键响应。
                def _yield_look(i, frames):
                    if i % 3 == 0:
                        d = _push_q.take_look()
                        if d is not None:
                            try:
                                do_look(d, sleep_ok=False)
                            except Exception as e:
                                print(f"[push] 看向 {d} 间隙推屏失败：{e}")
                # 动作动画（motion）按自身非均匀帧时长渲染；普通思考按均匀节奏
                motion = payload.get("motion")
                durations = action_durations(motion) if motion else None
                frames = len(durations) if durations else int(THINK_DURATION * THINK_FPS)
                gif = _render_gif(payload, "think.gif", frames, THINK_FPS,
                                  durations=durations, on_progress=_yield_look)
                # 渲染期间面板持续排水；若仍在饱和冷却，推大 .bin 前先等冷却结束。
                if time.time() < cooldown_until:
                    time.sleep(cooldown_until - time.time())
                    cooldown_until = 0.0
                push_gif(gif)
                print(f"[push] 思考「{payload.get('line') or ''}」推屏完成")
            elif kind == "look-cache":
                _look_bins = _render_look_bins(payload)
                print(f"[push] 看向 .bin 已缓存（mood={payload}）")
        except Exception as e:
            print(f"[push] 推屏异常：{e}（串口已释放，后续推屏会自动重开复位）")


# =====================================================================
#  本地感知：GetLastInputInfo（主人活跃度）
# =====================================================================
class LASTINPUTINFO(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.UINT), ("dwTime", wintypes.DWORD)]


user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)


def idle_s() -> float:
    """距上次键盘/鼠标输入的时间（秒）。本地调用，反映真实交互桌面活动。"""
    lii = LASTINPUTINFO()
    lii.cbSize = ctypes.sizeof(LASTINPUTINFO)
    if not user32.GetLastInputInfo(ctypes.byref(lii)):
        return 0.0
    return (kernel32.GetTickCount() - lii.dwTime) / 1000.0


# =====================================================================
#  交互注册表（可扩展：以后加「喂食 / 戳一下 / 久坐提醒」只写新 handler）
# =====================================================================
class AgentContext:
    """交互处理器共享的上下文：当前情绪、记忆、推屏、思考。"""

    def __init__(self):
        self.memory = PetMemory(os.path.join(DATA_DIR, "pet_memory.json"))
        self.cur_mood = self.memory.last_mood() or "idle"
        self.quiet_until = 0.0          # 静默截止时间戳（会议等场景）
        self._quiet_reason = None       # 本次静默的原因（"meeting"/"flow"/None）
        self.last_idle_s = 0.0          # 最近一次 GetLastInputInfo 的秒数
        self.keys = keys.KeyAnalyst()   # 键盘滑动窗口统计
        self._speaker = None            # 当前正在 tick 的交互（供 say 读 priority/group）
        self.last_speech = 0.0          # 上次说话时间戳（全局节流）
        self.last_group = {}            # group -> 上次该组说话时间戳（互斥组）
        self.look_suppress_until = 0.0  # 哭/表情锁定截止时间戳：此时间前看向被抑制

    def is_quiet(self, now: float) -> bool:
        return now < self.quiet_until

    def set_quiet(self, secs: float, reason: str | None = None) -> None:
        self.quiet_until = max(self.quiet_until, time.time() + secs)
        if reason is not None:
            self._quiet_reason = reason

    def think(self, active: bool | None) -> dict:
        """离线大脑思考一次，返回 {mood, line, ...}，并更新当前情绪。"""
        now = datetime.datetime.now()
        state = offline_next(
            now.hour, self.memory.last_mood(), None,
            active=active, relationship=self.memory.data["relationship"])
        self.cur_mood = state["mood"]
        state["sub"] = SUBS.get(state["mood"], f"离线模式 · {now.strftime('%H:%M')}")
        state["clock"] = now.strftime("%H:%M")
        state["t"] = time.time() % 3600
        return state

    def observe(self, active: bool | None) -> None:
        now = datetime.datetime.now()
        self.memory.observe(now, active)
        self.memory.remember_mood(self.cur_mood)
        self.memory.save()

    def _allow_speech(self, now: float, priority: str, group: str | None) -> bool:
        gap = now - self.last_speech
        if group and now - self.last_group.get(group, 0.0) < GROUP_WINDOW \
                and priority != "high":
            return False
        if priority == "high":
            return True
        if priority == "med":
            return gap >= SPEECH_MIN_GAP
        return gap >= SPEECH_LOW_GAP          # low

    def _mark_speech(self, now: float, group: str | None) -> None:
        self.last_speech = now
        if group:
            self.last_group[group] = now

    def speak_state(self, state: dict, priority: str = "med",
                    group: str | None = None) -> dict | None:
        """带节流的推一句（状态已渲染好）。被节流挡下时返回 None。"""
        now = time.time()
        if not self._allow_speech(now, priority, group):
            return None
        self._mark_speech(now, group)
        # 哭/表情锁定：锁定期内丢弃看向并抑制后续看向，让哭动画立即插队、
        # 完整播完，不被「转头 / 看向恢复正视」覆盖（主人反馈「快速敲击不触发哭」）。
        if state.get("mood") == "cry":
            self.look_suppress_until = now + CRY_HOLD
            _push_q.clear_look()
        # 反应动作：mood → 动作动画。只出现在「说话/反应」的瞬时 GIF 里，
        # 看向按键的方向精灵（look bin）不设 motion，故不受影响。
        state["motion"] = mood_to_action(state.get("mood", ""))
        push_think(state)
        return state

    def say(self, line: str, mood: str = "talk", sub: str | None = None,
            look: tuple | None = None) -> dict | None:
        """推一句一次性台词（时段问候/久坐提醒等交互用）。

        优先级/互斥组取自当前正在 tick 的交互（EventBus 写入 _speaker）。
        look 可指定视线方向（如 (-5,-5)=左上），供「看向 + 表情」场景。
        """
        speaker = getattr(self, "_speaker", None)
        priority = getattr(speaker, "priority", "med")
        group = getattr(speaker, "group", None)
        now = datetime.datetime.now()
        state = {"mood": mood, "line": line, "sub": sub,
                 "clock": now.strftime("%H:%M"), "t": time.time() % 3600}
        if look is not None:
            state["look"] = look
        return self.speak_state(state, priority, group)


class LookTowardKeys(Interaction):
    """交互 1：看向按键方向。

    主人敲屏幕周围一圈的键 → 宠物立即把视线转向那个方向（推预渲染 .bin，快）；
    一段时间没再按键 → 视线回到正中。
    """
    name = "look"
    channels = ("key",)
    LOOK_HOLD = 2.5          # 看向保持秒数，之后恢复正视

    def __init__(self):
        self.last_dir = None
        self.look_until = 0.0

    def on_event(self, ev: dict, ctx: AgentContext) -> None:
        if time.time() < ctx.look_suppress_until:
            return                       # 哭/表情锁定中：不转头，避免覆盖哭动画
        d = ev["direction"]
        self.look_until = time.time() + self.LOOK_HOLD
        if d == self.last_dir:
            return                       # 同方向不重复推屏
        self.last_dir = d
        push_look(d)
        print(f"[look] 看向 {d}")

    def on_tick(self, now: float, ctx: AgentContext) -> None:
        if now < ctx.look_suppress_until:
            self.look_until = 0.0
            self.last_dir = None
            return                       # 锁定中不恢复正视，让哭动画持续
        if self.look_until and now >= self.look_until:
            self.look_until = 0.0
            self.last_dir = None
            push_look("center")


class TimeGreeting(Interaction):
    """交互 2：时段问候。

    每天早上（5-10 点）第一次检测到时道早安，深夜（23-2 点）提醒休息。
    每个时段每天最多一次，避免刷屏。
    """
    name = "greet"
    channels = ()
    _PERIODS = (
        ("morning", 5, 10, "主人早安，今天也一起加油", "happy"),
        ("night",   23, 2, "夜深了，主人早点休息", "talk"),
    )

    def __init__(self):
        self._done: dict[str, str] = {}   # period -> 上次触发的日期

    def on_tick(self, now: float, ctx: AgentContext) -> None:
        if ctx.is_quiet(now):
            return
        dt = datetime.datetime.fromtimestamp(now)
        h = dt.hour
        day = dt.strftime("%Y-%m-%d")
        for period, lo, hi, line, mood in self._PERIODS:
            in_range = (lo <= h < hi) if lo < hi else (h >= lo or h < hi)
            if not in_range or self._done.get(period) == day:
                continue
            self._done[period] = day
            ctx.say(line, mood=mood)
            print(f"[greet] {period}: {line}")


class SedentaryReminder(Interaction):
    """交互 3：久坐提醒。

    主人连续使用超过 ACTIVE_LIMIT 秒（中间没有 >60s 的中断）时提醒活动一下；
    提醒后冷却 COOLDOWN 秒，避免唠叨。
    """
    name = "sedentary"
    channels = ()
    ACTIVE_LIMIT = 60 * 60      # 连续使用 1 小时
    COOLDOWN = 45 * 60          # 提醒后 45 分钟内不再提醒

    def __init__(self):
        self.active_since: float | None = None
        self.last_remind = 0.0

    def on_tick(self, now: float, ctx: AgentContext) -> None:
        if ctx.is_quiet(now):
            return
        if idle_s() >= ACTIVE_S:
            self.active_since = None
            return
        if self.active_since is None:
            self.active_since = now
        if now - self.active_since >= self.ACTIVE_LIMIT and now - self.last_remind >= self.COOLDOWN:
            self.last_remind = now
            self.active_since = now          # 重新计时，避免持续触发
            ctx.say("主人坐很久啦，起来活动一下", mood="talk", sub="我替主人盯着")
            print("[sedentary] 提醒活动一下")


INTERACTIONS = [LookTowardKeys(), TimeGreeting(), SedentaryReminder()] + EXTRA_INTERACTIONS


# =====================================================================
#  键盘钩子（WH_KEYBOARD_LL）—— 回调在主线程消息循环里被调用
# =====================================================================
WH_KEYBOARD_LL = 13
WM_KEYDOWN = 0x0100
WM_SYSKEYDOWN = 0x0104
PM_REMOVE = 1

_key_events: list[str] = []                 # 钩子回调只入队方向（轻量），主循环消费
_raw_keys: list[tuple[int, bool, float]] = []   # (vk, ctrl_down, t) → 键盘分析器


class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("vkCode", wintypes.DWORD),
        ("scanCode", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    ]


class MSG(ctypes.Structure):
    _fields_ = [
        ("hwnd", wintypes.HWND),
        ("message", wintypes.UINT),
        ("wParam", wintypes.WPARAM),
        ("lParam", wintypes.LPARAM),
        ("time", wintypes.DWORD),
        ("pt", wintypes.POINT),
    ]


LowLevelKeyboardProc = ctypes.WINFUNCTYPE(
    ctypes.c_ssize_t, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)


@LowLevelKeyboardProc
def _hook_proc(nCode, wParam, lParam):
    if nCode >= 0 and wParam in (WM_KEYDOWN, WM_SYSKEYDOWN):
        kb = ctypes.cast(lParam, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
        _key_events.append(dir_for(kb.vkCode))
        ctrl = bool(user32.GetKeyState(keys.VK_CTRL) & 0x8000)
        _raw_keys.append((kb.vkCode, ctrl, time.time()))
    return user32.CallNextHookEx(None, nCode, wParam, lParam)


def _setup_prototypes() -> None:
    user32.SetWindowsHookExW.restype = ctypes.c_void_p
    user32.SetWindowsHookExW.argtypes = (
        ctypes.c_int, LowLevelKeyboardProc, wintypes.HINSTANCE, wintypes.DWORD)
    user32.CallNextHookEx.restype = ctypes.c_ssize_t
    user32.CallNextHookEx.argtypes = (
        ctypes.c_void_p, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)
    user32.GetMessageW.argtypes = (
        ctypes.POINTER(MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT)
    user32.GetMessageW.restype = ctypes.c_int
    user32.PeekMessageW.argtypes = (
        ctypes.POINTER(MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT, wintypes.UINT)
    user32.PeekMessageW.restype = ctypes.c_int
    user32.TranslateMessage.argtypes = (ctypes.POINTER(MSG),)
    user32.DispatchMessageW.argtypes = (ctypes.POINTER(MSG),)
    user32.UnhookWindowsHookEx.argtypes = (ctypes.c_void_p,)
    user32.GetLastInputInfo.argtypes = (ctypes.POINTER(LASTINPUTINFO),)
    user32.GetLastInputInfo.restype = wintypes.BOOL
    user32.GetKeyState.argtypes = (ctypes.c_int,)
    user32.GetKeyState.restype = ctypes.c_short
    kernel32.GetTickCount.restype = wintypes.DWORD


def main() -> None:
    ap = argparse.ArgumentParser(description="Windows 本地常驻 agent（离线）")
    ap.add_argument("--interval", type=float, default=DEFAULT_INTERVAL,
                    help="慢思考间隔（秒）")
    ap.add_argument("--debug-keys", action="store_true",
                    help="在控制台打印退格/删除键及其 4s/60s 计数，用于排查哭泣触发")
    args = ap.parse_args()

    # 单实例锁：两个 agent 同时抢 COM3 会让 SerialPortTool 打不开串口、
    # 弹窗挂起（一个 25ms 的推屏卡到超时）→ 屏幕间歇「卡死」。发现已有
    # 实例在跑就退出，宁可让用户去关旧窗口。
    kernel32.CreateMutexW.restype = ctypes.c_void_p
    kernel32.CreateMutexW.argtypes = (ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR)
    kernel32.CreateMutexW(None, False, "AulaPetAgent-win_agent-v1")
    if ctypes.get_last_error() == 183:   # ERROR_ALREADY_EXISTS
        print("[agent] 检测到已有 win_agent 实例在运行（COM3 不能被两个进程共用），"
              "本实例退出。请先关闭旧窗口再启动。")
        return

    # 日志：控制台 + agent_run.log 双写（卡死时留下现场证据，UTF-8 防中文乱码）
    class _Tee:
        def __init__(self, f):
            self.f = f
        def write(self, s):
            sys.__stdout__.write(s)
            self.f.write(s)
            self.f.flush()
        def flush(self):
            sys.__stdout__.flush()
            self.f.flush()
    _logf = open(os.path.join(HERE, "agent_run.log"), "a", encoding="utf-8")
    sys.stdout = _Tee(_logf)
    _logf.write(f"\n===== agent 启动 {datetime.datetime.now()} =====\n")

    _setup_prototypes()
    ctx = AgentContext()
    bus = EventBus(ctx, INTERACTIONS)

    # 后台推屏线程（不阻塞按键泵）
    threading.Thread(target=_push_worker, daemon=True).start()

    # 预渲染 + 预转换看向 .bin（启动时同步渲染首个 mood，之后命中缓存/后台渲染）
    try:
        prepare_look_bins(ctx.cur_mood, blocking=True)
        _ensure_hardworking_bin()   # 饱和期「别太拼」关心帧，一次性就绪
    except Exception as e:
        print(f"[push] 预渲染看向 .bin 失败：{e}")

    # 低级钩子（WH_KEYBOARD_LL）hMod 必须为 NULL（回调在安装线程执行）
    hook = user32.SetWindowsHookExW(WH_KEYBOARD_LL, _hook_proc, None, 0)
    if not hook:
        raise ctypes.WinError(ctypes.get_last_error())

    # 媒体会话轮询（尽力而为，无 winrt 自动禁用）
    sensors.start_media_poller()
    weather.start_poller()   # 天气轮询（尽力而为，无网络静默）

    print(f"[agent] 启动：键盘钩子已挂载，交互={[i.name for i in INTERACTIONS]}，"
          f"思考间隔 {args.interval}s（离线）Ctrl+C 退出")

    # 启动即推一帧思考画面（不再等第一个 interval）
    state = ctx.think(True)
    ctx.speak_state(state, priority="high")
    ctx.observe(True)

    last_think = time.time()   # 启动已推一帧，下一轮慢思考从此刻起算（避免首轮立即双推）
    msg = MSG()
    try:
        while True:
            # 1) 泵消息：钩子回调在这里被系统调用，把方向入队
            while user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, PM_REMOVE):
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessage(ctypes.byref(msg))

            # 2) 消费按键事件 → 看向（事件驱动，~300ms 内响应）
            while _key_events:
                bus.emit({"channel": "key", "direction": _key_events.pop(0)})

            # 2.5) 喂键盘分析器（供扩展交互读信号）
            while _raw_keys:
                vk, ctrl, t = _raw_keys.pop(0)
                ctx.keys.add(vk, ctrl, t)
                if args.debug_keys and vk in (keys.VK_BACK, keys.VK_DELETE):
                    n = time.time()
                    print(f"[debug-keys] {'Backspace' if vk == keys.VK_BACK else 'Delete'} "
                          f"(4s={ctx.keys.backspace_count(n, 4)}, "
                          f"60s={ctx.keys.backspace_count(n, 60)})")

            # 3) 定时逻辑（看向恢复等）
            now = time.time()
            ctx.last_idle_s = idle_s()
            bus.tick(now)

            # 4) 慢思考（离线大脑）
            if now - last_think >= args.interval:
                last_think = now
                active = idle_s() < ACTIVE_S
                state = ctx.think(active)
                if now >= ctx.quiet_until:
                    ctx.speak_state(state)
                else:
                    print("[agent] 静默中，跳过思考推屏")
                try:
                    prepare_look_bins(ctx.cur_mood)  # 随新 mood 刷新看向 .bin
                except Exception as e:
                    print(f"[push] 刷新看向 .bin 失败：{e}")
                ctx.observe(active)
                print(f"[agent] 思考: {state['mood']}「{state.get('line') or ''}」")

            time.sleep(0.03)   # ~33ms 泵一次，按键响应足够快
    finally:
        user32.UnhookWindowsHookEx(hook)
        print("[agent] 已退出")


if __name__ == "__main__":
    main()
