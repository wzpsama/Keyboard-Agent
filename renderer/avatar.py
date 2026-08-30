"""像素风 agent 宠物头像 —— 一只住在键盘屏幕里的小团子。

在 96×96 的逻辑网格上绘制，再由 render.py 用 NEAREST 放大 2 倍，
得到锐利的像素感。所有坐标都在 96×96 网格内。

state 约定：
  mood : idle | happy | thinking | sleepy | working | talk | excite
  look : (dx, dy)  视线方向，范围约 -8..8（瞳孔+天线+眼睛框朝该方向偏）
  t    : 秒，驱动周期性动画（天线脉冲、说话嘴动、眨眼由 render 层决定）
"""
from __future__ import annotations

import math

from PIL import Image, ImageDraw

# ---- 调色板 ----
BODY       = (246, 210, 120)   # 团子主体
BODY_DARK  = (198, 158, 72)    # 主体暗部（底边阴影用）
OUTLINE    = (56, 44, 30)      # 描边
EYE_WHITE  = (250, 250, 252)   # 眼白
PUPIL      = (24, 24, 34)      # 瞳孔
GLOW       = (94, 224, 255)    # 天线光 / 特效
BLUSH      = (255, 152, 168, 160)  # 腮红（带 alpha）

GRID = 96

MOODS = {
    "idle":    "发呆中",
    "happy":   "开心",
    "thinking":"思考中",
    "sleepy":  "困了",
    "working": "工作中",
    "talk":    "说话中",
    "excite":  "超兴奋",
    "cry":     "哭泣中",
    "music":   "听歌中",
}


def new_avatar_canvas() -> Image.Image:
    return Image.new("RGBA", (GRID, GRID), (0, 0, 0, 0))


def draw_avatar(draw: ImageDraw.ImageDraw, mood: str, look=(0, 0), t=0.0,
                blink=False) -> None:
    """在 96×96 的画布上画团子。

    转头（2026-08-25 强化）：三层叠加，比旧版只动瞳孔明显得多——
      ①身体整体按 bx/by 朝视线方向微倾；
      ②脸（眼+嘴+腮红）按 fx/fy 朝方向平移（相对身体更明显，读出「转头」）；
      ③瞳孔再在眼白内 px/py 微移。
    """
    gx = max(-8, min(8, look[0]))
    gy = max(-8, min(8, look[1]))
    bx = round(gx * 0.5)       # 身体（团子整体）朝方向微倾
    by = round(gy * 0.5)
    fx = round(gx * 1.1)       # 脸（眼+嘴+腮红）朝方向平移 → 转头感
    fy = round(gy * 1.1)
    px = max(-4, min(4, gx))   # 瞳孔在眼白内的额外偏移
    py = max(-4, min(4, gy))

    # ---- 天线（带呼吸光晕，顶端朝视线方向明显倾斜）----
    pulse = 1.0 + 0.6 * math.sin(t * 5.0)
    tip_r = 4 + int(1.5 * pulse)
    base_x, base_y = 48 + bx, 22 + by
    tip_x = base_x + round(gx * 0.9)
    tip_y = 11 + by + round(gy * 0.9)
    draw.line((base_x, base_y, tip_x, tip_y), fill=OUTLINE, width=3)
    draw.ellipse((tip_x - tip_r, tip_y - tip_r + 3, tip_x + tip_r, tip_y + tip_r + 3),
                 fill=GLOW)
    draw.ellipse((tip_x - 2, tip_y - 5, tip_x + 2, tip_y - 1),
                 fill=(230, 250, 255))

    # ---- 身体 ----
    draw.ellipse((11 + bx, 20 + by, 85 + bx, 86 + by), fill=BODY,
                 outline=OUTLINE, width=3)
    # 底部暗部，让团子有点立体感
    draw.arc((11 + bx, 20 + by, 85 + bx, 86 + by), 35, 145, fill=BODY_DARK, width=4)

    # ---- 举起来的小手（excite 专用）----
    if mood == "excite":
        draw.line((20 + bx, 62 + by, 8 + bx, 50 + by), fill=OUTLINE, width=3)
        draw.ellipse((4 + bx, 46 + by, 12 + bx, 54 + by), fill=BODY,
                     outline=OUTLINE, width=2)
        draw.line((76 + bx, 62 + by, 88 + bx, 50 + by), fill=OUTLINE, width=3)
        draw.ellipse((84 + bx, 46 + by, 92 + bx, 54 + by), fill=BODY,
                     outline=OUTLINE, width=2)

    # ---- 眼睛 ----
    eye_l = (29, 44, 44, 59)
    eye_r = (52, 44, 67, 59)
    if mood == "sleepy":
        # 闭眼 = 向下弯的弧（∩ 形）
        draw.arc(eye_l, 0, 180, fill=OUTLINE, width=3)
        draw.arc(eye_r, 0, 180, fill=OUTLINE, width=3)
    elif blink:
        # 眨眼 = 一条横线
        draw.line((30 + fx, 52 + fy, 43 + fx, 52 + fy), fill=OUTLINE, width=3)
        draw.line((53 + fx, 52 + fy, 66 + fx, 52 + fy), fill=OUTLINE, width=3)
    else:
        for x0 in (eye_l[0], eye_r[0]):
            draw.rounded_rectangle((x0 + fx, 44 + fy, x0 + 15 + fx, 59 + fy),
                                   radius=6, fill=EYE_WHITE, outline=OUTLINE, width=2)
        for cx in (36.5, 59.5):
            ex_ = cx + fx + px
            ey_ = 51.5 + fy + py
            draw.ellipse((ex_ - 4.5, ey_ - 4.5, ex_ + 4.5, ey_ + 4.5), fill=PUPIL)
            # 双高光，眼睛更水润可爱
            draw.ellipse((ex_ - 3.5, ey_ - 3.5, ex_ - 1.5, ey_ - 1.5),
                         fill=(255, 255, 255))
            draw.ellipse((ex_ + 1.0, ey_ + 1.0, ex_ + 2.6, ey_ + 2.6),
                         fill=(255, 255, 255))

    # ---- 腮红 ----
    if mood in ("idle", "happy", "excite", "talk"):
        draw.ellipse((20 + fx, 58 + fy, 30 + fx, 68 + fy), fill=BLUSH)
        draw.ellipse((66 + fx, 58 + fy, 76 + fx, 68 + fy), fill=BLUSH)

    # ---- 嘴 ----
    if mood == "idle":
        draw.arc((42 + fx, 62 + fy, 54 + fx, 71 + fy), 180, 360, fill=OUTLINE, width=3)
    elif mood == "happy":
        draw.arc((37 + fx, 59 + fy, 59 + fx, 77 + fy), 180, 360, fill=OUTLINE, width=3)
    elif mood == "excite":
        # 张嘴欢呼
        draw.pieslice((38 + fx, 57 + fy, 58 + fx, 79 + fy), 180, 360, fill=OUTLINE)
    elif mood == "talk":
        r = 4 + int(2.0 * math.sin(t * 12.0))
        draw.ellipse((48 + fx - r, 67 + fy - r, 48 + fx + r, 67 + fy + r),
                     fill=OUTLINE)
    elif mood == "thinking":
        draw.ellipse((49 + fx, 65 + fy, 55 + fx, 70 + fy), fill=OUTLINE)
    elif mood == "sleepy":
        draw.ellipse((45 + fx, 66 + fy, 51 + fx, 71 + fy), fill=OUTLINE)
    else:  # working
        draw.line((44 + fx, 68 + fy, 52 + fx, 68 + fy), fill=OUTLINE, width=2)

    # ---- 附加特效 ----
    if mood == "thinking":
        draw.text((76 + fx, 12 + fy), "?", fill=GLOW)
    elif mood == "sleepy":
        draw.text((68 + fx, 18 + fy), "z", fill=GLOW)
        draw.text((78 + fx, 4 + fy), "Z", fill=GLOW)


def render_avatar(state: dict) -> Image.Image:
    """state → 192×192 像素图（96 网格放大 2 倍）。"""
    canvas = new_avatar_canvas()
    draw_avatar(
        ImageDraw.Draw(canvas),
        mood=state.get("mood", "idle"),
        look=state.get("look", (0, 0)),
        t=state.get("t", 0.0),
        blink=state.get("blink", False),
    )
    return canvas.resize((GRID * 2, GRID * 2), Image.Resampling.NEAREST)
