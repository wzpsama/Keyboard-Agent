"""状态 → 完整 320×480 帧（AULA L99 屏幕分辨率）。

输出：
  - PIL RGBA Image（供 PNG 预览 / GIF）
  - RGB565 字节流（307200 字节/帧，供推帧用，待协议逆向确认像素格式）

state 约定：
  mood : idle | happy | thinking | sleepy | working | talk | excite
  line : 气泡台词（可空）
  sub  : 状态栏副标题（可空）
  look : (dx, dy) 瞳孔偏移（可空，按 mood 给默认值）
  t    : 秒（驱动动画相位；blink 自动计算）
  clock: 顶部时钟字符串（可空，默认取本机时间）
"""
from __future__ import annotations

import datetime
import math

from PIL import Image, ImageDraw, ImageFont

from renderer.avatar import MOODS, render_avatar
from renderer.vega import render_vega

W, H = 320, 480

# ---- 配色（暗色底，配合键盘 RGB 环境）----
BG         = (19, 19, 32)
PANEL      = (27, 27, 40)
PANEL_LINE = (42, 42, 58)
TEXT       = (232, 232, 240)
TEXT_DIM   = (150, 150, 170)
GLOW       = (94, 224, 255)

# ---- 字体（按机器逐个尝试，中文优先）----
FONT_CANDIDATES = [
    # Linux
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
    "/usr/share/fonts/truetype/arphic/uming.ttc",
    # Windows（最终推帧机）
    "C:/Windows/Fonts/msyh.ttc",
    "C:/Windows/Fonts/msyh.ttf",
    "C:/Windows/Fonts/simhei.ttf",
    # macOS
    "/System/Library/Fonts/PingFang.ttc",
    "/System/Library/Fonts/STHeiti Light.ttc",
    # 兜底：PIL 内置位图字体（仅 ASCII）
]

_font_cache: dict[int, ImageFont.FreeTypeFont] = {}
_has_cjk = True


def get_font(size: int) -> ImageFont.FreeTypeFont:
    if size not in _font_cache:
        for path in FONT_CANDIDATES:
            try:
                _font_cache[size] = ImageFont.truetype(path, size)
                break
            except OSError:
                continue
        else:
            try:
                _font_cache[size] = ImageFont.load_default(size)
            except TypeError:  # 老版本 Pillow
                _font_cache[size] = ImageFont.load_default()
            global _has_cjk
            _has_cjk = False
    return _font_cache[size]


def has_cjk() -> bool:
    """当前机器是否有中文字体（决定提示语）"""
    get_font(14)
    return _has_cjk


def wrap_text(text: str, font, max_w: int) -> list[str]:
    """逐字贪心换行（中文无空格，需按字符切）。"""
    lines, cur = [], ""
    for ch in text:
        if font.getlength(cur + ch) > max_w:
            lines.append(cur)
            cur = ch
        else:
            cur += ch
    if cur:
        lines.append(cur)
    return lines


def _default_look(mood: str, t: float) -> tuple[int, int]:
    if mood == "thinking":
        return (3, -3)
    if mood == "working":
        # 眼睛左右小幅度扫动
        return (int(2 * (1 if (int(t * 0.8) % 2) == 0 else -1)), 0)
    return (0, 0)


def render_frame(state: dict) -> Image.Image:
    """渲染一帧 320×480 RGBA。"""
    mood = state.get("mood", "idle")
    t = float(state.get("t", 0.0))
    line = state.get("line") or ""
    sub = state.get("sub") or "住在你的键盘里"
    clock = state.get("clock") or datetime.datetime.now().strftime("%H:%M")
    character = state.get("character", "dango")

    img = Image.new("RGBA", (W, H), BG)
    draw = ImageDraw.Draw(img)

    # ---- 背景噪点（低对比度，防纯色死板）----
    for y in range(0, H, 8):
        for x in range(0, W, 8):
            if (x * 7 + y * 13) % 97 == 0:
                draw.point((x + 3, y + 3), fill=(28, 28, 44, 255))

    # ---- 顶栏 ----
    f_small = get_font(13)
    f_clock = get_font(14)
    draw.text((16, 8), state.get("title") or ("Vega" if character == "vega" else "Keyboard Agent"),
              font=f_clock, fill=TEXT)
    draw.text((16, 27), "Empowered by WZPSAMA", font=f_small, fill=TEXT_DIM)
    draw.text((W - 16 - f_clock.getlength(clock), 8), clock,
              font=f_clock, fill=TEXT)

    # ---- 气泡 ----
    f_line = get_font(15)
    if line:
        draw.rounded_rectangle((16, 52, W - 16, 148), radius=14,
                               fill=PANEL, outline=PANEL_LINE, width=2)
        # 气泡尾巴指向角色头顶（vega 居中指向头顶，dango 指天线）
        if character == "vega":
            draw.polygon([(142, 148), (178, 148), (160, 156)],
                         fill=PANEL, outline=PANEL_LINE)
        else:
            draw.polygon([(138, 148), (162, 148), (150, 168)],
                         fill=PANEL, outline=PANEL_LINE)
        lines = wrap_text(line, f_line, W - 64)
        if len(lines) > 3:
            lines = lines[:3]
            lines[-1] = lines[-1][:-1] + "…"
        for i, ln in enumerate(lines):
            draw.text((32, 66 + i * 24), ln, font=f_line, fill=TEXT)

    # ---- 角色头像 ----
    if character == "vega":
        avatar = render_vega(state, height=220)
        ax = (W - avatar.width) // 2
        ay = 156  # 固定垂直位置：气泡出现与否，角色都不上下移动
        draw.ellipse((ax + 40, ay + avatar.height - 10, ax + avatar.width - 40,
                      ay + avatar.height + 4), fill=(0, 0, 0, 70))
        img.paste(avatar, (ax, ay), avatar)
    else:
        # ---- 团子 ----
        blink = (t % 4.2) > 4.05  # 每 4.2 秒眨一次
        avatar = render_avatar({
            "mood": mood,
            "look": state.get("look") or _default_look(mood, t),
            "t": t,
            "blink": blink,
        })
        # 影子
        draw.ellipse((110, 314, 210, 332), fill=(0, 0, 0, 70))
        img.paste(avatar, (64, 146), avatar)

    # ---- 状态栏 ----
    draw.rounded_rectangle((16, 394, W - 16, H - 16), radius=14,
                           fill=PANEL, outline=PANEL_LINE, width=2)
    f_status = get_font(17)
    draw.text((30, 403), MOODS.get(mood, mood), font=f_status, fill=TEXT)
    draw.text((30, 430), sub, font=f_small, fill=TEXT_DIM)
    # The ambient GIF keeps the character still; its pulse carries the breath.
    if state.get("ambient"):
        pulse = 0.5 + 0.5 * math.sin(float(state.get("ambient_phase", 0.0)) * math.tau)
    else:
        pulse = 0.5 + 0.5 * math.sin(t * 4)
    pr = 3 + int(2 * pulse)
    draw.ellipse((282 - pr, 412 - pr, 282 + pr, 412 + pr), fill=GLOW)

    return img


# ---- RGB565 打包 ----
_R5 = [(v & 0xF8) << 8 for v in range(256)]
_G6 = [(v & 0xFC) << 3 for v in range(256)]
_B5 = [v >> 3 for v in range(256)]


def to_rgb565(img: Image.Image) -> bytes:
    """RGBA → RGB565 字节流（小端 16bit/像素，共 W*H*2 字节）。

    屏幕实测为**小端**：红 0xF800 → 字节 ``00 f8``（低字节在前）。

    旧链路的 SerialPortTool 会把 .bin 的 11 字节文件头一并流进帧缓冲，奇数
    偏移把字节对调，才让「大端文件 + 头」碰巧显示正确；直写（去头）后必须
    用小端，本函数直接输出小端。
    """
    px = img.convert("RGB").tobytes()  # RGBRGB... 每像素 3 字节
    buf = bytearray(len(px) // 3 * 2)
    j = 0
    for i in range(0, len(px), 3):
        v = _R5[px[i]] | _G6[px[i + 1]] | _B5[px[i + 2]]
        buf[j] = v & 0xFF        # 低字节在前（小端）
        buf[j + 1] = v >> 8
        j += 2
    return bytes(buf)


def crc16_modbus(data: bytes) -> int:
    """CRC16-MODBUS（poly 0xA001 反射、init 0xFFFF、无 xorout）。"""
    crc = 0xFFFF
    for b in data:
        crc ^= b
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if crc & 1 else crc >> 1
    return crc & 0xFFFF


def build_bin(pixels: bytes) -> bytes:
    """把 RGB565 像素流包装成屏幕 .bin（11 字节头 + 像素）。

    头：``<IHH`` 数据大小(307200) / 宽(320) / 高(480) + 0x00 + CRC16-MODBUS(像素)。
    """
    import struct
    assert len(pixels) == W * H * 2, f"bad pixel len {len(pixels)}"
    crc = crc16_modbus(pixels)
    hdr = struct.pack("<IHH", W * H * 2, W, H) + b"\x00" + struct.pack("<H", crc)
    return hdr + pixels


def save_frame(img: Image.Image, path_prefix: str) -> None:
    """保存 PNG 预览 + 完整 .bin（11 字节头 + RGB565 像素）。"""
    img.save(f"{path_prefix}.png")
    with open(f"{path_prefix}.bin", "wb") as f:
        f.write(build_bin(to_rgb565(img)))
