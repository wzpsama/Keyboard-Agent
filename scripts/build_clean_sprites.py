# -*- coding: utf-8 -*-
"""把 clean 方向精灵（447×526 全身）等比缩放到 447×415 全身，与哭态精灵一致。

问题：之前 renderer/vega.py 用 `_CROP_BOTTOM=415` 把 clean 的 526 高裁到 415，
裁掉了脚/腿 → 主人看到「只有头」（与哭态全身不一致）。

现在：clean 全身**等比缩放**到与哭态同尺度（`s=(415-6)/522`，front 全身 436×522
→ 342×409，脚踩到底、脚不裁），renderer 不再裁。四方向共用同一个缩放比例，
转向时角色不跳、头/脚位置与哭态对齐。

输入 assets/vega/clean/{name}.png（447×526 透明底，已统一裁切框）
输出 assets/vega/clean/{name}.png（447×415 透明底，全身）
原 526 版本已备份到 assets/vega/clean_full/。
"""
from __future__ import annotations

import os

from PIL import Image

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(HERE, "assets", "vega", "clean")
W_C, H_C = 447, 415              # 目标尺寸（与哭态精灵 cry_*.png 一致）
REF_H = 522                      # clean/front 全身人物高度（union bbox 高），缩放基准
TOP = 6                          # 顶部留白（对齐哭态精灵）
NAMES = ["front", "left", "left_top", "top"]


def main() -> None:
    s = (H_C - TOP) / REF_H       # 全身等比缩放到 409 高（与哭态同尺度）
    out_w = round(447 * s)
    out_h = round(526 * s)
    ox = (W_C - out_w) // 2
    oy = TOP
    print(f"scale s={s:.4f} -> canvas {out_w}x{out_h} paste@({ox},{oy})")
    for name in NAMES:
        im = Image.open(os.path.join(SRC, name + ".png")).convert("RGBA")
        resized = im.resize((out_w, out_h), Image.LANCZOS)
        out = Image.new("RGBA", (W_C, H_C), (255, 255, 255, 0))  # 白画布，避免边缘压暗
        out.paste(resized, (ox, oy), resized)
        out.save(os.path.join(SRC, name + ".png"))
        print(f"saved {name}.png ({out_w}x{out_h} -> {ox},{oy})")
    print("DONE")


if __name__ == "__main__":
    main()
