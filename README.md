# Vega · 住在键盘里的 AI 宠物（织女）

把狼蛛 **AULA L99** 键盘那块 3.98" IPS 屏（320×480）变成一只常驻 AI 宠物
「织女 / Vega」的脸。银白短发、红瞳的赛博女孩住在键盘里，等你回家。

**在 Windows 键盘机本地单进程运行**，直接通过键盘自带的官方驱动（Image2Bin +
SerialPortTool）与屏幕通信——不需要任何 mini PC / SSH 中转。

---

## 快速开始

1. 装好 **AULA L99 官方驱动**（自带 `Image2Bin.exe` / `SerialPortTool.exe`，
   默认在 `C:\Program Files (x86)\AULA L99\qt-tool`）。
2. 键盘用 USB 连上 Windows（串口默认 `COM3`）。
3. 双击 `setup_windows.bat` —— 自动装 Python 依赖（只需 Pillow）并渲染一帧自检。
4. 双击 `start_agent.bat` —— 前台启动，看日志；`run_agent.bat` 后台静默启动。

> 串口不是 COM3？改环境变量 `AULA_COM`，或直接编辑 `pusher/push_local.py` 顶部的
> `PORT` / `QT_TOOL`。

## 工作原理

```
              ┌──────────────────────────────────────────────┐
              │  win_agent.py（Windows 本地单进程）           │
              │                                              │
              │  键盘钩子 WH_KEYBOARD_LL ── 捕捉屏幕周围按键   │
              │  本地感知 GetLastInputInfo ── 主人活跃度       │
              │  事件总线 + 交互注册表（可插拔）               │
              │  离线大脑 states.offline_next ── 情绪随机游走  │
              │  渲染器 renderer/ ── 状态 → 320×480 帧        │
              │  推屏 pusher/push_local.py ── GIF→Image2Bin→   │
              │        SerialPortTool → 键盘屏幕（COM3）      │
              └──────────────────────────────────────────────┘
```

- **离线零成本**：默认不用 API，情绪由本地状态机驱动；`agent/brain.py` 预留了
  Claude API 在线大脑（配 `ANTHROPIC_API_KEY` + `pip install anthropic` 后把
  `Brain(offline=True)` 换 `False`）。
- **按键实时响应**：屏幕周围的键（↑/↓/←/→/Home/PageUp/Delete/PrintScreen…）会让
  宠物转头看过去，用预渲染的 `.bin` 做到亚秒级。
- **推屏为什么用官方链**：屏幕只认 `Image2Bin` 产出的动画 `.bin` 头，手写单帧
  会顶部污染 + 字节序错色；官方链是驱动自带、稳定正确。

## 情绪与动作动画

`renderer/vega.py` 按状态里的 `mood` / `motion` 选择精灵：

| 情绪 mood | 状态栏 | 动作动画 |
|---|---|---|
| `idle` / `working` / `talk` / `thinking` | … | 方向精灵（front/left/left_top/top，随视线转头） |
| `happy` | 开心 | bounce 开心跳跳 |
| `excite` | 超兴奋 | surprised 惊讶瞪眼 |
| `sleepy` | 困了 | sleepy 犯困打盹（戴眼罩 + 飘 z） |
| `music` | 听歌中 | music 音乐律动 |
| `cry` | 哭泣中 | 6 帧哭脸（主人手绘） |

动作动画只出现在「说话 / 反应」的瞬时 GIF 里，看向按键的方向精灵不受影响。

## 交互（`agent/interactions.py`，共 28 个）

- **键盘层**：狂按空格、Ctrl+V 搬砖、连删哭泣、大写锁提醒、快手速、游戏观战、频繁切窗、离开回归。
- **前台应用**：进入 IDE/浏览器/办公/游戏/终端/媒体时搭话；会议自动静默；心流保护；刷剧护眼。
- **系统**：CPU/内存高负载关心、负载回落报平安、锁屏道别。
- **音乐/天气/猜你在干嘛**：放歌切歌（律动）、带伞/添衣提醒、按窗口标题调侃。
- **成长陪伴**：连续陪伴里程碑、亲密度升级、熬夜关心、深夜关心、深夜犯困打盹、饭点/周末/纪念日。

防冲突机制：每个交互声明 `priority`（high 可抢占 / med / low 更长间隔）与 `group`
（互斥组，如 `"keyboard"`），由 `AgentContext.say` 统一仲裁，避免刷屏。

## 目录

```
win_agent.py               Windows 本地常驻 agent（入口）
agent/                     交互、键盘/系统/天气感知、记忆、状态机、在线大脑
renderer/vega.py           Vega 精灵渲染（方向 + 哭脸 + 动作动画）
renderer/render.py         状态 → 320×480 帧（RGB565 + PNG/GIF）
renderer/avatar.py         程序化团子（可选角色）+ mood 中文标签
pusher/push_local.py       GIF → Image2Bin → SerialPortTool 推屏（官方链）
assets/vega/               精灵图（clean/cry/bounce/sleepy/surprised/music）
scripts/                   精灵生成/重处理脚本（改素材时用）
setup_windows.bat          一键安装
start_agent.bat / run_agent.bat   启动脚本
```

## 重新生成 / 改素材

- `scripts/process_vega.py` —— 原图（白底 1254×1254）→ 透明底方向精灵。
- `scripts/build_clean_sprites.py` —— 方向精灵统一到 447×415 全身。
- `scripts/build_cry_sprites.py` —— 主人手绘 6 帧哭脸 → 哭态精灵。
- `scripts/build_action_sprites.py` —— 由 front.png 程序化生成 4 套动作动画。

## 隐私

宠物记忆（亲密度、作息画像、活跃时段）只写在本地 `data/pet_memory.json`，
不上传。在线大脑若启用，只把「当前时间 + 活跃度 + 记忆摘要」发给 Claude，
不含窗口标题原文（猜你在干嘛只做粗分类，不念标题）。
