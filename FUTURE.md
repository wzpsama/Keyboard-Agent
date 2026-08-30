# 未来开发拓展清单

「看向按键」是第一个交互。本文件记录后续要做的方向，按优先级排序。
Windows 本地版（`win_agent.py`）已搭好「事件总线 + 交互注册表」骨架，
多数新交互只需**写一个 `Interaction` 子类并注册进 `INTERACTIONS`**，核心循环一行不改。

---

## 1. 在线大脑（Claude API）—— 接口已预留

**现状**：`win_agent.py` 走离线大脑 `states.offline_next`（情绪随机游走，不花 token）。

**预留接口**：`agent/brain.py` 的 `Brain(offline=False)` 已实现完整在线路径
（`claude-opus-5` + 记忆摘要 + 活跃度感知）。启用步骤：

1. `pip install anthropic`
2. 配 `ANTHROPIC_API_KEY` 环境变量
3. 把 `win_agent.py` 里 `ctx.think()` 改成走 `Brain` 实例（`think` 调用 `_think_api`）

**注意**：在线调用有网络延迟（几百 ms~几秒），会阻塞钩子消息循环 → 应把在线
`think` 放到**后台线程**，通过队列把结果送回主循环推屏。这是启用在线前要做的改造。

---

## 2. 更多交互（各写一个 Interaction 子类）

| 交互 | 触发事件 | 响应草图 |
|---|---|---|
| 喂食 | 特定按键 / 定时 | 团子张嘴吃 + 亲密度 +1 |
| 戳一下 | 快速连按 | 团子抖动 / 害羞 |
| 久坐提醒 | 活跃度持续 active > N 分钟 | 气泡「起来活动一下呀」 |
| 作息关心 | 时间 / 记忆（熬夜） | 气泡问候（`memory.slept_late_last_night` 已备） |
| 天气/时间播报 | 定时 tick | 气泡显示天气/整点报时 |

新交互模板：

```python
class FeedPet(Interaction):
    name = "feed"
    channels = ("key",)           # 关心的通道：key / idle / timer ...
    def on_event(self, ev, ctx):
        ctx.push_frame({...})     # 响应：渲染 + 推屏
    def on_tick(self, now, ctx):
        pass                      # 定时逻辑（可选）
```

---

## 3. 动画与表现

- **多帧循环动画**：现在看向/思考都是单帧。可复用 `renderer/generate_gif.py`
  的 `build_mood_frames`（眨眼/嘴动/天线脉动随 t 驱动），推 GIF 循环。
- **看向过渡**：从正视到看向方向加 2~3 帧中间态，而非跳变。
- **生命感**：随机小动作（打呵欠、眨眼频率变化、天线随机抖动）。

---

## 4. 推屏性能（进一步降延迟）—— 当前最大瓶颈

**实测拆解（2026-08-23，本地单帧推屏 1.9s）**：渲染 4ms + RGB565 转换 18ms +
build_bin 94ms + **SerialPortTool 串口流式 1801ms（占 94%）**。

即：本地化 + 事件驱动已把「敲键 → 开始反应」降到 ~0.13s，但**整帧写屏本身
要 1.8s**（屏幕 = USB-serial CDC `VID_EEEF:PID_268A = COM3`，SerialPortTool 分块
流式写 150 块 × 2060B，受 CDC 串口吞吐限制，帧率上限 ~0.5fps）。

进一步提速的路径（按收益排序）：

1. **增量刷新（最大收益：1.8s → ~0.1s）**：协议已逆向出「每块带 u32 地址、
   基准 0x04240000、每块 +0x800」。理论可只写「眼睛/团子」所在的那几十块
   （~10KB，而非整帧 307KB），配合「提交」命令结束。看向只需更新团子区域。
2. **pyserial 直写 COM3（绕开 SerialPortTool 的 exe 启动 + Qt 开销）**：分块
   协议已逆向（`5a a5` + 命令 0x0008 + 地址 + 2048B 数据），**唯一缺口是 2 字节
   尾校验算法未破**（非标准 CRC16，需用 `win_frida_spawn_spt.py` 重新抓分块流
   样本 + reveng 暴力识别）。破掉后即可自行流式写，也解锁了上面的增量刷新。
3. **降低帧分辨率/色深**：视线反应帧降采样（如 160×240）再推，串口字节数 ÷4。

> 待办：用 `win_frida_spawn_spt.py` 捕获 SerialPortTool 的 2060B 分块写样本，
> 破尾校验算法 → 实现 `pusher/push_cdc.py`（pyserial 直写 + 增量刷新）。

---

## 5. 部署与运维

- **开机自启**：`schtasks /sc onlogon` 注册 `pythonw win_agent.py`（涉及持久化，
  需你明确授权后我再配）。
- **看门狗**：探测 `win_agent.py` 崩溃后自动重启。
- **日志轮转**：`print` 落到文件，避免控制台窗口积累。

---

## 6. 感知增强

- **多键语义**：现在只取「最近一次按键方向」；可识别**组合/节奏**（如快速双击
  = 戳、长按 = 抚摸），扩展交互词汇表。
- **屏幕内容感知**：读取主人正在看的窗口标题（GetForegroundWindow），团子「猜你在干嘛」。

---

## 7. 扬声器发声（已调研，暂不实现 —— 2026-08-28）

**结论**：键盘（屏幕）自带的「按键音」扬声器**不是 USB 音频设备**。Windows 声音
设备里的 "USB Audio Device" 是用户的 DualSense 手柄（VID_054C），不是键盘。键盘
本体 = 0C45:800A（USB Composite HID，4 个接口全是 HID，无音频接口）。

**现状**：按键音由键盘 MCU 固件本地发声；AULA 软件的「按键音」开关是通过 HID
vendor 命令发给 MCU。PC 侧无法像普通音箱那样 `winsound` / 放 wav 到它。

**若要 Vega 从它发声**，只有逆向 AULA 软件控制声音的 vendor 命令（类似当初逆向
屏幕推屏协议），两点不确定：
1. 命令可能只支持「开关按键音」，不支持播放任意音调/音效；
2. 即便能触发，多半是固定「咔哒」声，不是可编程音频。

**若能触发「哔一声」即可做的交互**：注意力提醒（说话前哔一声）、情绪音色（开心两
短哔 / 警报一长哔）、打字同步咔哒声。

**待办**（独立小工程，风险可能白做，未启动）：用 HID 抓包（frida / enum_all_hid）
抓 AULA 软件开关按键音时的 feature report，定位 vendor 声音命令。
