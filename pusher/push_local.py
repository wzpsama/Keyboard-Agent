# -*- coding: utf-8 -*-
"""Windows 本地推屏：GIF → Image2Bin → SerialPortTool → COM3。

与 pusher/push_anim.py 同一条官方链路，但用 subprocess 在 **Windows 本机**调用，
供 win_agent.py（Windows 本地常驻）使用。

为什么用这条链：
  - Image2Bin.exe 是驱动自带官方 GIF→.bin 转换器，产出的 .bin 头是屏幕固件能
    正确解析的**动画格式**（头被解析、不显示），所以顶部无污染。
  - SerialPortTool.exe 是官方流式推屏工具，稳定可靠。
  - 之前 push_cdc.py 单帧直写是错的（屏幕大端 + 头格式不对），才有错色+顶部污染。

用法：
  push_local.push_gif("out/look_left.gif")   # GIF → .bin → 推屏
  push_local.push_bin("out/look_left.bin")   # 直接推已转好的 .bin（最快）
"""
from __future__ import annotations

import os
import subprocess
import sys

# 官方驱动安装目录（默认位置）；串口默认 COM3。均可用环境变量覆盖，
# 便于不同机器/不同串口号：AULA_QT_TOOL、AULA_COM。
QT_TOOL = os.environ.get("AULA_QT_TOOL", r"C:\Program Files (x86)\AULA L99\qt-tool")
IMAGE2BIN = os.path.join(QT_TOOL, "Image2Bin.exe")
SERIAL_TOOL = os.path.join(QT_TOOL, "SerialPortTool.exe")
PORT = os.environ.get("AULA_COM", "COM3")
BASE_ADDR = "0x4240000"   # 写入地址基准（= 0x04240000）


def gif_to_bin(gif_path: str, timeout: float = 30.0) -> str:
    """GIF → .bin（Image2Bin 官方转换，.bin 落在 GIF 同目录同 basename）。"""
    bin_path = os.path.splitext(gif_path)[0] + ".bin"
    subprocess.run([IMAGE2BIN, gif_path], cwd=QT_TOOL,
                   check=True, capture_output=True, timeout=timeout)
    return bin_path


def push_bin(bin_path: str, timeout: float = 60.0) -> None:
    """把 .bin 推到屏幕（SerialPortTool 官方工具，串口直写）。

    注意：timeout 只作**最后兜底**，正常传输 ~25ms 根本不会触发。之前设 5s
    太激进——屏幕在快速连点下单次推屏可能到 130ms+，超时后 subprocess.run
    会**半途杀掉 SerialPortTool**，而屏幕固件正在写 flash，半途中断会冻屏
    （gavindi/Aula_L99_Linux README 明确警告），这就是「卡主没响应」的真凶。
    因此把超时放大到 60s：正常永不触发，真卡死才兜底。

    慢推屏/失败时把 SerialPortTool 的 stdout/stderr 打到日志：它没有日志
    文件，输出是「面板饱和卡住时」的唯一现场证据（2026-08-24 起）。
    """
    import time as _t
    t0 = _t.time()
    r = subprocess.run([SERIAL_TOOL, bin_path, PORT, BASE_ADDR],
                       cwd=QT_TOOL, capture_output=True, timeout=timeout)
    dt = _t.time() - t0
    if dt > 1.0 or r.returncode != 0:
        out = (r.stdout or b"").decode("utf-8", "replace").strip()
        err = (r.stderr or b"").decode("utf-8", "replace").strip()
        print(f"[push] SerialPortTool {dt*1000:.0f}ms rc={r.returncode}"
              + (f" stdout={out[:300]!r}" if out else "")
              + (f" stderr={err[:300]!r}" if err else ""))
    if r.returncode != 0:
        raise RuntimeError(f"SerialPortTool rc={r.returncode}")


def push_gif(gif_path: str) -> str:
    """GIF → .bin → 推屏，一步到位。返回 .bin 路径。"""
    bin_path = gif_to_bin(gif_path)
    push_bin(bin_path)
    return bin_path


if __name__ == "__main__":
    # CLI：python push_local.py <gif 或 bin>
    if len(sys.argv) < 2:
        print("用法：python push_local.py <file.gif|file.bin>")
        sys.exit(1)
    path = sys.argv[1]
    if path.lower().endswith(".gif"):
        print(push_gif(path))
    else:
        push_bin(path)
        print("DONE", path)
