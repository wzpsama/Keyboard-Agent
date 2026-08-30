# -*- coding: utf-8 -*-
"""把主人手绘的 6 帧哭脸 (preview/cry_1..6.png) 处理成 Vega 哭态精灵。

新素材（2026-08-30）与旧素材不同：**已经是 220×220 透明底 RGBA**，6 帧人物
包围盒完全一致（x[26..203] y[1..212]，178×212，宽/高≈0.840），一致性极好，
所以不再需要 flood-fill 去背景、并集盒对齐、头部质心对齐那套流程。

处理流程：
1. 取 6 帧前景并集包围盒（本就一致），裁出人物。
2. **全身适配到 415 高内（脚踩到底、脚不裁）**：哭脸人物是全身图（头→脚），
   按 `s_y=(H_C-TOP)/uh` 把整身缩到 415-TOP 高、宽度压窄到 0.835 比例
   （源≈0.840，几乎不用压）。注意：**不能**放大到 clean 的整身 522 再裁 415，
   那样会把脚裁掉 → 主人看到「只有头」。
3. 透明像素先填「白」再 LANCZOS 缩放 + 最终画布也填「白」，边缘向白过渡，
   对齐 clean Vega 的白底抗锯齿，避免黑边/脏边。
4. 顶部留 TOP、横向居中、脚踩到画布底 y=415（**露出全身含脚**）。

输出：assets/vega/cry/cry_1..6.png（RGBA 透明底 447×415，全身人物）。
"""
from __future__ import annotations

import os
from PIL import Image, ImageFilter

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(HERE, "assets", "vega", "cry_src")
OUT = os.path.join(HERE, "assets", "vega", "cry")
W_C, H_C = 447, 415              # 目标尺寸（= clean 精灵 _CROP_BOTTOM 后的尺寸）
TARGET_ASPECT = 0.835            # clean Vega 人物宽/高
FRAMES = 6
TOP = 6                          # 人物顶部留白（像素）；全身脚踩到底、脚不裁


def _fg_bbox(rgba, thr=10):
    w, h = rgba.size
    px = rgba.load()
    fg = [(x, y) for y in range(h) for x in range(w) if px[x, y][3] > thr]
    minx = min(p[0] for p in fg); maxx = max(p[0] for p in fg)
    miny = min(p[1] for p in fg); maxy = max(p[1] for p in fg)
    return minx, miny, maxx, maxy


def main():
    os.makedirs(OUT, exist_ok=True)

    # 1) 读 6 帧，算并集包围盒（新素材本就一致，这里只是防御性并集）
    frames = []
    for n in range(1, FRAMES + 1):
        im = Image.open(os.path.join(SRC, f"cry_{n}.png")).convert("RGBA")
        frames.append(im)
    boxes = [_fg_bbox(im) for im in frames]
    ux0 = min(b[0] for b in boxes); uy0 = min(b[1] for b in boxes)
    ux1 = max(b[2] for b in boxes); uy1 = max(b[3] for b in boxes)
    uw, uh = ux1 - ux0 + 1, uy1 - uy0 + 1
    print(f"union bbox x[{ux0}..{ux1}] y[{uy0}..{uy1}] w={uw} h={uh} aspect={uw/uh:.3f}")

    # 2) 缩放：全身高度适配到 415 内（脚踩到底、脚不裁），宽度压窄到 0.835（源 0.840）
    s_y = (H_C - TOP) / uh
    s_x = s_y * (TARGET_ASPECT / (uw / uh))
    out_w = max(1, round(uw * s_x))
    out_h = max(1, round(uh * s_y))
    ox = (W_C - out_w) // 2
    oy = TOP
    print(f"scale sx={s_x:.4f} sy={s_y:.4f} -> out {out_w}x{out_h} paste@({ox},{oy})")

    # 3) 每帧：裁并集盒 → 透明像素填白 → LANCZOS → 轻微羽化 → 白画布合成
    for n, im in enumerate(frames, start=1):
        crop = im.crop((ux0, uy0, ux1 + 1, uy1 + 1))
        # 透明像素填「白」：LANCZOS 缩放时边缘向白过渡（对齐 clean 白底抗锯齿）
        cw, ch = crop.size
        white_alpha = Image.new("RGBA", (cw, ch), (255, 255, 255, 0))
        white_alpha.paste(crop, (0, 0), crop)
        resized = white_alpha.resize((out_w, out_h), Image.LANCZOS)
        alpha = resized.getchannel("A").filter(ImageFilter.GaussianBlur(1.0))
        resized.putalpha(alpha)
        # 最终画布也填「白」，否则 paste 按 alpha 合成到黑底会压暗边缘 → 黑边
        out = Image.new("RGBA", (W_C, H_C), (255, 255, 255, 0))
        out.paste(resized, (ox, oy), resized)
        out.save(os.path.join(OUT, f"cry_{n}.png"))
        print(f"saved cry_{n}.png ({out_w}x{out_h} -> {ox},{oy})")
    print("DONE")


if __name__ == "__main__":
    main()
