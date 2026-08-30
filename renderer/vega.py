"""用户自绘「织女/Vega」精灵渲染 —— 方向 → 静态 PNG；哭泣/动作 → 多帧动画。

方向视图：front / left / left_top / top（用户生成，已处理成透明底、统一裁切）。
「哭泣」：用主人另绘的 6 帧哭脸（assets/vega/cry/cry_1..6.png，透明底、已按双眼
锚点统一裁切对齐），按时间 t 循环播放。
「动作动画」：scripts/build_action_sprites.py 程序化生成的 4 套 4 帧动画
（bounce 开心跳跳 / sleepy 犯困打盹 / surprised 惊讶瞪眼 / music 音乐律动），
也是按时间 t 循环播放。动作动画由 state["motion"] 显式指定（不是由 mood 推断），
这样「看向按键」的方向精灵（look bin）不会被动作动画覆盖——动作只出现在
「说话/反应」的瞬时 GIF 里，看向始终用 front/left/left_top/top。

与 avatar.py 的 render_avatar 接口对齐：输入 state（含 look/mood/motion/t），
输出 RGBA 头像。

clean 精灵、哭态精灵、动作精灵都已处理成 447×415 全身（scripts/build_*_sprites.py），
不再裁底，头/脚位置、尺度一致（全身含脚）。
"""
from __future__ import annotations

import os

from PIL import Image

_VEGA_ROOT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "assets", "vega",
)
_ASSET_DIR = os.path.join(_VEGA_ROOT, "clean")
_CRY_DIR = os.path.join(_VEGA_ROOT, "cry")
_CACHE: dict[str, Image.Image] = {}
NAMES = ("front", "left", "left_top", "top")

# 哭脸帧数（assets/vega/cry/cry_1..6.png），循环播放。
_CRY_FRAMES = 6
# 每帧时长（ms），主人指定：第 1..6 帧分别 180/100/100/140/90/220ms，整圈 830ms。
_CRY_DURATIONS_MS = [180, 100, 100, 140, 90, 220]
_CRY_LOOP_MS = sum(_CRY_DURATIONS_MS)

# ---- 动作动画（scripts/build_action_sprites.py 生成，每套 4 帧循环）----
# action 名 -> (资产目录名, 每帧时长 ms)
_ACTIONS = {
    "bounce":    ("bounce",    [140, 150, 210, 120]),
    "sleepy":    ("sleepy",    [240, 300, 300, 240]),
    "surprised": ("surprised", [300, 130, 180, 130]),
    "music":     ("music",     [180, 120, 180, 120]),
}

# mood → 动作动画（反应情绪对应哪个动作）。
MOOD_TO_ACTION = {
    "happy":  "bounce",     # 开心 → 跳跳
    "sleepy": "sleepy",     # 犯困 → 打盹
    "excite": "surprised",  # 超兴奋 → 瞪眼
    "music":  "music",      # 听歌 → 律动
}


def mood_to_action(mood: str) -> str | None:
    """返回某 mood 对应的动作动画名（无则 None）。"""
    return MOOD_TO_ACTION.get(mood)


def action_durations(action: str) -> list[int]:
    """返回某动作动画的每帧时长（ms）列表。"""
    return _ACTIONS[action][1]


def _cry_index(t: float) -> int:
    """按非均匀帧时长把时间 t（秒，单调递增）映射到帧号 1.._CRY_FRAMES。"""
    ms = int(t * 1000) % _CRY_LOOP_MS
    acc = 0
    for i, d in enumerate(_CRY_DURATIONS_MS):
        acc += d
        if ms < acc:
            return i + 1
    return _CRY_FRAMES


def _sprite(name: str) -> Image.Image:
    if name not in _CACHE:
        im = Image.open(os.path.join(_ASSET_DIR, name + ".png")).convert("RGBA")
        _CACHE[name] = im
    return _CACHE[name]


def _cry_sprite(index: int) -> Image.Image:
    """index ∈ 1.._CRY_FRAMES，加载哭脸帧（已 447×415 透明底，无需再裁）。"""
    key = f"cry:{index}"
    if key not in _CACHE:
        im = Image.open(os.path.join(_CRY_DIR, f"cry_{index}.png")).convert("RGBA")
        _CACHE[key] = im
    return _CACHE[key]


def _action_frame(action: str, index: int) -> Image.Image:
    """加载某动作动画的第 index（1..N）帧（已 447×415 透明底）。"""
    key = f"action:{action}:{index}"
    if key not in _CACHE:
        d = _ACTIONS[action][0]
        im = Image.open(
            os.path.join(_VEGA_ROOT, d, f"{d}_{index}.png")).convert("RGBA")
        _CACHE[key] = im
    return _CACHE[key]


def _action_index(action: str, t: float) -> int:
    """按非均匀帧时长把时间 t 映射到动作动画帧号 1..N。"""
    durs = _ACTIONS[action][1]
    loop = sum(durs)
    ms = int(t * 1000) % loop
    acc = 0
    for i, d in enumerate(durs):
        acc += d
        if ms < acc:
            return i + 1
    return len(durs)


def pick_sprite(look) -> str:
    """把连续视线方向离散到用户给的 4 个方向视图。"""
    dx, dy = (look or (0, 0))
    T = 3
    up = dy <= -T
    left = dx <= -T
    if up and left:
        return "left_top"
    if up:
        return "top"
    if left:
        return "left"
    return "front"


def render_vega(state: dict, height: int = 220) -> Image.Image:
    t = float(state.get("t", 0.0))
    motion = state.get("motion")
    if motion in _ACTIONS:
        # 动作动画（说话/反应时的瞬时 GIF），按 t 循环
        sp = _action_frame(motion, _action_index(motion, t))
    elif state.get("mood") == "cry":
        sp = _cry_sprite(_cry_index(t))
    else:
        sp = _sprite(pick_sprite(state.get("look", (0, 0))))
    w = max(1, round(sp.width * height / sp.height))
    return sp.resize((w, height), Image.LANCZOS)
