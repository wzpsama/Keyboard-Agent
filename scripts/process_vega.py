"""把用户生成的织女精灵图（白底、无 alpha）处理成透明背景的干净 PNG。

输入 assets/vega/{front,left,left_top,top}.png（1254×1254 RGB 白底）
输出 assets/vega/clean/{name}.png（透明底、统一裁切框、统一尺寸）

flood fill：从四边泛洪连通的"近白"区域 = 背景，其余（含被描边圈住的银白发）= 前景。
"""
from __future__ import annotations

import os
import sys
from collections import deque

from PIL import Image, ImageFilter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

SRC = os.path.join("assets", "vega")
DST = os.path.join(SRC, "clean")
NAMES = ["front", "left", "left_top", "top"]
WORK = 627          # 半分辨率做 flood fill，够用且快
THRESH = 200        # min(r,g,b) > 200 视为近白背景
PAD = 4             # 裁切框四周留白像素


def flood_mask(im: Image.Image) -> tuple[bytearray, int, int]:
    W = H = im.size[0]
    px = im.load()
    whiteish = bytearray(W * H)
    for y in range(H):
        for x in range(W):
            r, g, b = px[x, y][:3]
            whiteish[y * W + x] = 1 if min(r, g, b) > THRESH else 0
    visited = bytearray(W * H)
    q: deque = deque()
    for x in range(W):
        for y in (0, H - 1):
            i = y * W + x
            if whiteish[i] and not visited[i]:
                visited[i] = 1
                q.append(i)
    for y in range(H):
        for x in (0, W - 1):
            i = y * W + x
            if whiteish[i] and not visited[i]:
                visited[i] = 1
                q.append(i)
    while q:
        i = q.popleft()
        x = i % W
        y = i // W
        for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if 0 <= nx < W and 0 <= ny < H:
                j = ny * W + nx
                if whiteish[j] and not visited[j]:
                    visited[j] = 1
                    q.append(j)
    fg = bytearray(W * H)
    for i in range(W * H):
        fg[i] = 1 if not (whiteish[i] and visited[i]) else 0
    return fg, W, H


def main() -> None:
    os.makedirs(DST, exist_ok=True)
    imgs, masks = {}, {}
    for name in NAMES:
        im = Image.open(os.path.join(SRC, name + ".png")).convert("RGB").resize(
            (WORK, WORK), Image.LANCZOS)
        fg, W, H = flood_mask(im)
        imgs[name] = im
        masks[name] = fg

    # 统一裁切框（四张图的前景并集），保证切换方向时角色不跳动
    xs, ys = [], []
    for name in NAMES:
        fg = masks[name]
        for y in range(H):
            for x in range(W):
                if fg[y * W + x]:
                    xs.append(x)
                    ys.append(y)
    x0, y0, x1, y1 = min(xs), min(ys), max(xs), max(ys)
    print(f"union bbox (work={WORK}): {(x0, y0, x1, y1)}  size={(x1-x0+1)}x{(y1-y0+1)}")
    x0 = max(0, x0 - PAD)
    y0 = max(0, y0 - PAD)
    x1 = min(W - 1, x1 + PAD)
    y1 = min(H - 1, y1 + PAD)

    for name in NAMES:
        im = imgs[name].crop((x0, y0, x1, y1))
        fg = masks[name]
        alpha = Image.new("L", (W, H), 0)
        alpha.putdata([255 if fg[i] else 0 for i in range(W * H)])
        alpha = alpha.crop((x0, y0, x1, y1)).filter(ImageFilter.GaussianBlur(1.0))
        out = im.convert("RGBA")
        out.putalpha(alpha)
        p = os.path.join(DST, name + ".png")
        out.save(p)
        print(f"saved {p}  size={out.size}  alpha_extrema={alpha.getextrema()}")


if __name__ == "__main__":
    main()
