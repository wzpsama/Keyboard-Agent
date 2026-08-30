"""Windows 平台传感器：前台窗口、系统指标、锁屏、媒体会话（尽力而为）。

全部为纯函数 + 一个后台媒体轮询线程；无 win_agent 依赖，缺依赖/非 Windows 时
优雅降级，保证 win_agent 离线也能稳定跑。慢操作（媒体/网络）绝不阻塞主线程。
"""
from __future__ import annotations

import collections
import ctypes
import threading
import time
from ctypes import wintypes

_IS_WIN = hasattr(ctypes, "WinDLL")

user32 = ctypes.WinDLL("user32", use_last_error=True) if _IS_WIN else None
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True) if _IS_WIN else None

_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
_GENERIC_READ = 0x80000000


def _setup() -> None:
    if user32 is None:
        return
    user32.GetForegroundWindow.restype = wintypes.HWND
    user32.GetWindowTextW.argtypes = (wintypes.HWND, wintypes.LPWSTR, ctypes.c_int)
    user32.GetWindowTextW.restype = ctypes.c_int
    user32.GetWindowThreadProcessId.argtypes = (
        wintypes.HWND, ctypes.POINTER(wintypes.DWORD))
    user32.GetWindowThreadProcessId.restype = wintypes.DWORD
    user32.GetKeyState.argtypes = (ctypes.c_int,)
    user32.GetKeyState.restype = ctypes.c_short
    user32.OpenInputDesktop.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    user32.OpenInputDesktop.restype = ctypes.c_void_p
    user32.CloseDesktop.argtypes = (ctypes.c_void_p,)
    user32.CloseDesktop.restype = wintypes.BOOL
    kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    kernel32.OpenProcess.restype = ctypes.c_void_p
    kernel32.QueryFullProcessImageNameW.argtypes = (
        ctypes.c_void_p, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD))
    kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = (ctypes.c_void_p,)


_setup()


# ---- 前台窗口 ----
def _window_text(hwnd) -> str:
    buf = ctypes.create_unicode_buffer(256)
    user32.GetWindowTextW(hwnd, buf, 256)
    return buf.value


def _process_name(pid: int) -> str:
    try:
        h = kernel32.OpenProcess(_PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not h:
            return ""
        buf = ctypes.create_unicode_buffer(512)
        size = wintypes.DWORD(512)
        ok = kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size))
        kernel32.CloseHandle(h)
        if not ok:
            return ""
        return buf.value.rsplit("\\", 1)[-1].lower()
    except Exception:
        return ""


# 前台窗口缓存 + 切换计数（防阻塞：多交互共享同一次采样，避免各自 OpenProcess）
_fg_cache: tuple = (0.0, None)          # (上次采样时间戳, (name, title))
_fg_last_name = None                     # 上次采样的进程名（用于检测切换）
_fg_changes = collections.deque()        # 前台进程变化时间戳（近 60s）


def _foreground_app_raw():
    if user32 is None:
        return None
    try:
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return None
        title = _window_text(hwnd)
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        name = _process_name(pid.value)
        return (name, title)
    except Exception:
        return None


def foreground_app():
    """返回 (进程名小写, 窗口标题) 或 None；带 ~1s 缓存，顺带记录进程切换。"""
    global _fg_last_name, _fg_cache
    now = time.time()
    ts, val = _fg_cache
    if now - ts < 1.0:
        return val
    val = _foreground_app_raw()
    _fg_cache = (now, val)
    if val and val[0] != _fg_last_name:
        _fg_changes.append(now)
        _fg_last_name = val[0]
    while _fg_changes and now - _fg_changes[0] > 60.0:
        _fg_changes.popleft()
    return val


def foreground_changes(t: float, span: float = 20.0) -> int:
    """近 span 秒内前台进程切换次数。"""
    while _fg_changes and t - _fg_changes[0] > span:
        _fg_changes.popleft()
    return len(_fg_changes)


# ---- 应用分类 ----
_APP_MAP = {
    # ide / 编辑器
    "code.exe": "ide", "cursor.exe": "ide", "windsurf.exe": "ide",
    "pycharm64.exe": "ide", "pycharm.exe": "ide", "idea64.exe": "ide",
    "idea.exe": "ide", "sublime_text.exe": "ide", "devenv.exe": "ide",
    "notepad++.exe": "ide", "atom.exe": "ide", "vim.exe": "terminal",
    # 浏览器
    "chrome.exe": "browser", "msedge.exe": "browser", "firefox.exe": "browser",
    "brave.exe": "browser", "opera.exe": "browser", "iexplore.exe": "browser",
    # 办公
    "winword.exe": "office", "excel.exe": "office", "powerpnt.exe": "office",
    "outlook.exe": "office", "wps.exe": "office", "wpp.exe": "office",
    "et.exe": "office", "onenote.exe": "office",
    # 会议 / 通讯（前台 = 可能开会/通话 → 静默）
    "ms-teams.exe": "meeting", "teams.exe": "meeting", "zoom.exe": "meeting",
    "cpthost.exe": "meeting", "wechat.exe": "meeting", "wechatweb.exe": "meeting",
    "dingtalk.exe": "meeting", "qq.exe": "meeting", "discord.exe": "meeting",
    "slack.exe": "meeting",
    # 游戏（进程名不可靠，仅作弱信号，主要靠键盘键簇）
    "steam.exe": "game", "epicgameslauncher.exe": "game",
    "leagueclient.exe": "game", "league of legends.exe": "game",
    "valorant.exe": "game", "cs2.exe": "game", "csgo.exe": "game",
    "overwatch.exe": "game", "minecraft.exe": "game",
    # 终端
    "cmd.exe": "terminal", "powershell.exe": "terminal",
    "windowsterminal.exe": "terminal", "wt.exe": "terminal",
    # 媒体播放器
    "vlc.exe": "media", "mpv.exe": "media", "potplayermini64.exe": "media",
    "spotify.exe": "media",
}


def classify_app(proc_name: str) -> str:
    """进程名 → 类别（ide/browser/office/meeting/game/terminal/media/other）。"""
    if not proc_name:
        return "other"
    return _APP_MAP.get(proc_name.lower(), "other")


# ---- 系统指标（psutil，缺依赖时 None）----
_sys_cache: tuple = (0.0, None)   # (上次采样时间戳, 指标 dict)


def _system_metrics_raw():
    try:
        import psutil
    except ImportError:
        return None
    try:
        m = {"cpu": psutil.cpu_percent(interval=None),
             "mem": psutil.virtual_memory().percent,
             "battery": None, "plugged": None}
        b = psutil.sensors_battery()
        if b is not None:
            m["battery"] = round(b.percent)
            m["plugged"] = b.power_plugged
        return m
    except Exception:
        return None


def system_metrics():
    """返回 {cpu, mem, battery, plugged}；带 ~2s 缓存，无 psutil 时为 None。"""
    global _sys_cache
    now = time.time()
    ts, val = _sys_cache
    if now - ts < 2.0:
        return val
    val = _system_metrics_raw()
    _sys_cache = (now, val)
    return val


# ---- 键盘状态 / 锁屏 ----
def caps_lock_on() -> bool:
    if user32 is None:
        return False
    try:
        return bool(user32.GetKeyState(0x14) & 1)
    except Exception:
        return False


def is_locked() -> bool:
    """锁屏检测：输入桌面切到 Winlogon 时 OpenInputDesktop 失败。"""
    if user32 is None:
        return False
    try:
        h = user32.OpenInputDesktop(0, False, _GENERIC_READ)
        if h:
            user32.CloseDesktop(h)
            return False
        return True
    except Exception:
        return False


# ---- 媒体会话（winrt，尽力而为 + 后台轮询，失败自动禁用）----
_media_poller = None


def _media_available() -> bool:
    try:
        import winrt.windows.media.control  # noqa: F401
        return True
    except Exception:
        return False


def _fetch_media():
    """取当前正在播放的 (艺术家, 曲名)；无播放/失败返回 None。"""
    import asyncio
    from winrt.windows.media.control import \
        GlobalSystemMediaTransportControlsSessionManager as _Mgr

    async def _get():
        sessions = await _Mgr.request_async()
        cur = sessions.get_current_session()
        if cur is None:
            return None
        props = await cur.try_get_media_properties_async()
        title = (props.title or "").strip()
        if not title:
            return None
        return ((props.artist or "").strip(), title)

    return asyncio.run(_get())


class MediaPoller(threading.Thread):
    """后台轮询媒体会话，缓存最近曲目。任何异常 → 禁用自身，不再重试。"""

    def __init__(self, interval: float = 30.0):
        super().__init__(daemon=True, name="media-poller")
        self.interval = interval
        self.track = None          # (artist, title) or None
        self.enabled = _media_available()
        self._stop = False

    def run(self) -> None:
        while not self._stop:
            if self.enabled:
                try:
                    self.track = _fetch_media()
                except Exception:
                    self.enabled = False
            time.sleep(self.interval)

    def stop(self) -> None:
        self._stop = True


def start_media_poller(interval: float = 30.0) -> None:
    global _media_poller
    if _media_poller is None:
        _media_poller = MediaPoller(interval)
        if _media_poller.enabled:
            _media_poller.start()
        else:
            print("[sensors] 未安装 winrt 媒体库，音乐识别禁用（可忽略）")


def media_track():
    """当前正在播放的 (artist, title)，无则 None。"""
    p = _media_poller
    if p is None or not p.enabled:
        return None
    return p.track
