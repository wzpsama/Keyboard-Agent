# -*- coding: utf-8 -*-
"""由 front.png 程序化生成 4 套「创意动作」多帧精灵（每套 4 帧，447×415 全身透明底）。

动作（主人指定先做这 4 个）：
  bounce   开心跳跳   整体上下弹跳 + 下蹲蓄力/跳起拉伸（纯几何变换）
  sleepy   犯困打盹   头微垂点头 + 闭眼（程序化画眼皮/睫毛弧）+ 飘「z z z」
  surprised 惊讶瞪眼  眼睛瞪大（程序化重画更大的白眼白+缩小虹膜）+ 身体后仰
  music    音乐律动   身体左右摇摆（纯旋转）

原则（沿用 build_cry_sprites.py / 之前踩坑的教训）：
  - 所有变换/旋转用「白底填白 + LANCZOS」，避免黑边/脏边；
  - 最终画布也填白，paste 按 alpha 合成到白底（不是黑底）；
  - 脚踩到底、全身含脚，与 cry / clean 尺度一致，切换不跳。

输出：
  assets/vega/{bounce,sleepy,surprised,music}/{name}_1..4.png
  preview/{name}_preview.gif（暗底合成，方便主人预览判断美观）
"""
from __future__ import annotations

import os

from PIL import Image, ImageDraw, ImageFilter, ImageFont

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(HERE, "assets", "vega", "clean", "front.png")
OUT_ROOT = os.path.join(HERE, "assets", "vega")
PREVIEW = os.path.join(HERE, "preview")
W_C, H_C = 447, 415

# ---- 颜色（实测自 front.png）----
WHITE = (255, 255, 255, 0)      # 填白画布/旋转 fill
BG_DARK = (19, 19, 32, 255)     # 预览暗底（与 render.py BG 一致）
SKIN = (240, 212, 204, 255)     # 脸部皮肤（鼻梁处采样）
DARK = (6, 5, 25, 255)          # 眼部描边
WHITE_EYE = (250, 250, 252, 255)  # 眼白
IRIS = (30, 170, 225, 255)      # 虹膜青蓝
PUPIL = (10, 10, 30, 255)       # 瞳孔

# ---- 睡眠眼罩（犯困打盹用，主人反馈闭眼程序画太假 → 改戴眼罩）----
MASK_FILL = (198, 182, 232, 255)   # 眼罩主体：柔和薰衣草紫
MASK_EDGE = (126, 102, 168, 255)   # 眼罩描边：深一点的紫
MASK_BUMP = (182, 164, 222, 255)   # 眼罩下的眼睛凸起（略深，暗示闭眼）
MASK_STRAP = (168, 148, 208, 255)  # 头顶绑带

# ---- 双眼几何（实测自 front.png：中心 / 半径）----
# (cx, cy, rx, ry)：左眼、右眼的杏仁形眼区（含上眼皮描边 + 虹膜 + 下缘）。
# rx/ry 略放大，确保「闭眼」时能完整盖掉旧眼的描边+虹膜（不留边）。
EYES = [
    (157, 252, 40, 32),
    (277, 252, 40, 32),
]


def _transform(img: Image.Image, scale=(1.0, 1.0), dy=0, rot=0.0) -> Image.Image:
    """整体变换：旋转(白底) → 缩放(LANCZOS) → 白画布居中 + 平移。返回 447×415 RGBA。"""
    im = img.copy()
    if rot:
        im = im.rotate(rot, resample=Image.BICUBIC, expand=True, fillcolor=WHITE)
    w, h = im.size
    nw = max(1, round(w * scale[0]))
    nh = max(1, round(h * scale[1]))
    im = im.resize((nw, nh), Image.LANCZOS)
    out = Image.new("RGBA", (W_C, H_C), WHITE)
    ox = (W_C - nw) // 2
    oy = (H_C - nh) // 2 + dy
    out.paste(im, (ox, oy), im)
    return out


def _local_skin(img: Image.Image, cx, cy, rx, ry) -> tuple[int, int, int, int]:
    """取眼周「皮肤」局部色（采样眼睛下方/外侧一圈的偏肤色像素），让眼皮填色贴合局部肤色。"""
    px = img.load()
    pts = []
    for x in range(cx - rx - 6, cx + rx + 7):
        for y in range(cy + ry + 2, cy + ry + 12):
            if 0 <= x < img.width and 0 <= y < img.height:
                r, g, b, a = px[x, y]
                if a > 200 and r > 170 and g > 140 and b > 130 and r >= g >= b:
                    pts.append((r, g, b))
    if not pts:
        return SKIN
    n = len(pts)
    return (sum(p[0] for p in pts) // n,
            sum(p[1] for p in pts) // n,
            sum(p[2] for p in pts) // n, 255)


def _sleepy_eyes(img: Image.Image, frac: float) -> Image.Image:
    """闭眼程度 frac∈[0,1]：0=全睁，1=全闭。

    做法（主人反馈「眼皮太假/没盖全」后的重构）：
    1. 用「局部皮肤色 + 羽化软边」把整只旧眼（描边+虹膜+高光）彻底盖掉，不留黑边/青边；
    2. 全闭时画一条向下弯的睫毛弧 + 上方一条浅色眼皮褶皱线，做出自然的闭眼。
    """
    for cx, cy, rx, ry in EYES:
        skin = _local_skin(img, cx, cy, rx, ry)
        top, bot = cy - ry, cy + ry
        # 1) 羽化掩膜盖眼：半闭只盖上部（弧形下缘=下垂眼皮），全闭盖满整眼
        mask = Image.new("L", img.size, 0)
        md = ImageDraw.Draw(mask)
        if frac >= 0.95:
            md.ellipse([cx - rx - 2, top - 2, cx + rx + 2, bot + 2], fill=255)
        else:
            eh = max(8, int(2 * ry * frac))
            md.ellipse([cx - rx, top - 2, cx + rx, top + eh], fill=255)
        mask = mask.filter(ImageFilter.GaussianBlur(3))
        skin_layer = Image.composite(
            Image.new("RGBA", img.size, skin),
            Image.new("RGBA", img.size, (0, 0, 0, 0)),
            mask,
        )
        img = Image.alpha_composite(img, skin_layer)
        d = ImageDraw.Draw(img, "RGBA")
        # 2) 全闭时画睫毛弧（向下弯）+ 眼皮褶皱（更浅、更窄，制造立体）
        if frac >= 0.95:
            d.arc([cx - rx + 8, cy - ry + 6, cx + rx - 8, cy + ry - 6],
                  180, 360, fill=DARK, width=6)
            d.arc([cx - rx + 14, cy - ry - 8, cx + rx - 14, cy - ry + 6],
                  180, 360, fill=(168, 152, 172, 255), width=2)
    return img


def _sleep_mask(img: Image.Image) -> Image.Image:
    """给角色戴上一只可爱的睡眠眼罩（覆盖双眼，避开画闭眼的「假」感）。"""
    d = ImageDraw.Draw(img, "RGBA")
    # 1) 头顶绑带：从眼罩上沿伸向头发两侧（简单两条斜带）
    d.line([(120, 220), (96, 196)], fill=MASK_STRAP, width=10)
    d.line([(314, 220), (338, 196)], fill=MASK_STRAP, width=10)
    # 2) 主体：圆角长条盖住双眼
    d.rounded_rectangle([112, 218, 322, 290], radius=30,
                        fill=MASK_FILL, outline=MASK_EDGE, width=3)
    # 3) 眼罩下的眼睛凸起（两条椭圆，暗示闭着的眼）
    for cx, cy in [(157, 254), (277, 254)]:
        d.ellipse([cx - 26, cy - 13, cx + 26, cy + 13], fill=MASK_BUMP)
    # 4) 高光：上缘一道浅白弧，增加立体/可爱
    d.arc([120, 224, 314, 268], 180, 360, fill=(226, 216, 246, 255), width=3)
    # 5) 中间一颗小星星装饰
    mx, my = 217, 254
    d.polygon([(mx, my - 8), (mx + 2, my - 2), (mx + 8, my),
               (mx + 2, my + 2), (mx, my + 8),
               (mx - 2, my + 2), (mx - 8, my), (mx - 2, my - 2)],
              fill=(255, 255, 255, 255))
    return img


def _widen_eyes(img: Image.Image, factor: float) -> Image.Image:
    """瞪眼 factor≥1.0：1.0=正常，越大眼睛越睁大。重画更大的白眼白 + 缩小虹膜/瞳孔。"""
    d = ImageDraw.Draw(img, "RGBA")
    for cx, cy, rx, ry in EYES:
        rxx = int(rx * factor) + 6
        ryy = int(ry * factor) + 6
        d.ellipse([cx - rxx, cy - ryy, cx + rxx, cy + ryy],
                  fill=WHITE_EYE, outline=DARK, width=3)
        ir = max(9, int(15 * (2 - factor)))     # factor 越大虹膜越小（震惊=瞳孔收缩）
        d.ellipse([cx - ir, cy - ir, cx + ir, cy + ir],
                  fill=IRIS, outline=DARK, width=2)
        pr = max(4, ir // 2)
        d.ellipse([cx - pr, cy - pr, cx + pr, cy + pr], fill=PUPIL)
    return img


def _draw_zzz(img: Image.Image, frames_idx: int) -> Image.Image:
    """在头顶右上画「z」飘字（打盹提示）。"""
    d = ImageDraw.Draw(img, "RGBA")
    try:
        font = ImageFont.truetype("DejaVuSans.ttf", 34)
    except OSError:
        font = ImageFont.load_default()
    zzz = ["z", "Z", "z"][min(frames_idx, 2)]
    d.text((305, 42 + frames_idx * 18), zzz, font=font, fill=(180, 200, 230, 255))
    return img


def _frames_for(name: str) -> list[Image.Image]:
    base = Image.open(SRC).convert("RGBA")
    if name == "bounce":
        return [
            _transform(base),
            _transform(base, scale=(1.03, 0.92), dy=5),
            _transform(base, scale=(0.97, 1.06), dy=-16),
            _transform(base),
        ]
    if name == "music":
        return [
            _transform(base, rot=-5, dy=2),
            _transform(base),
            _transform(base, rot=5, dy=2),
            _transform(base),
        ]
    if name == "sleepy":
        return [
            _transform(_sleep_mask(base.copy()), rot=1),
            _draw_zzz(_transform(_sleep_mask(base.copy()), rot=2.5, dy=2), 0),
            _draw_zzz(_transform(_sleep_mask(base.copy()), rot=3.5, dy=3), 1),
            _transform(_sleep_mask(base.copy()), rot=1),
        ]
    if name == "surprised":
        return [
            _transform(base),
            _transform(_widen_eyes(base.copy(), 1.15), rot=-1.5, dy=-1),
            _transform(_widen_eyes(base.copy(), 1.30), rot=-2.5, dy=-2),
            _transform(_widen_eyes(base.copy(), 1.15), rot=-1.5, dy=-1),
        ]
    raise ValueError(name)


# 帧时长（ms，主人可后续指定不均匀节奏；这里先给合理默认）
DURATIONS = {
    "bounce":    [140, 150, 210, 120],
    "sleepy":    [240, 300, 300, 240],
    "surprised": [300, 130, 180, 130],
    "music":     [180, 120, 180, 120],
}


def _preview_gif(name: str, frames: list[Image.Image], durations: list[int]) -> str:
    """暗底合成 + 保存预览 GIF（角色高 ~220，与实机缩放一致）。"""
    H_VIEW = 220
    w = max(1, round(W_C * H_VIEW / H_C))
    comps = []
    for f in frames:
        f = f.resize((w, H_VIEW), Image.LANCZOS)
        bg = Image.new("RGBA", (w, H_VIEW), BG_DARK)
        bg.paste(f, (0, 0), f)
        comps.append(bg.convert("RGB"))
    path = os.path.join(PREVIEW, f"{name}_preview.gif")
    comps[0].save(path, save_all=True, append_images=comps[1:],
                  duration=durations, loop=0)
    return path


def main() -> None:
    os.makedirs(PREVIEW, exist_ok=True)
    for name, durs in DURATIONS.items():
        frames = _frames_for(name)
        out_dir = os.path.join(OUT_ROOT, name)
        os.makedirs(out_dir, exist_ok=True)
        for i, f in enumerate(frames, start=1):
            p = os.path.join(out_dir, f"{name}_{i}.png")
            f.save(p)
        gif = _preview_gif(name, frames, durs)
        print(f"{name}: {len(frames)} 帧 -> {out_dir}  预览 {os.path.basename(gif)}  {durs}ms")
    print("DONE")


if __name__ == "__main__":
    main()
