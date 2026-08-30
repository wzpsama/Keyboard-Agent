"""情绪状态机 + 离线调度 —— brain 的兜底模式。

在线模式下由 Claude 决定 mood/line；离线（无 API key 或网络失败）时用这里。
"""
from __future__ import annotations

import random

MOODS = ("idle", "happy", "thinking", "working", "talk", "excite")

# 每种情绪的离线台词库（气泡里显示的，≤20 字）—— Vega/织女 人设
LINES = {
    "idle":    ["（看着主人的屏幕）", "数据流很安静", "我在键盘里等主人"],
    "happy":   ["嘿嘿", "连上主人啦", "有主人在真好"],
    "thinking":["让我想想…", "跑一遍逻辑…", "嗯…这个有意思"],
    "working": ["替主人盯着呢", "进程都正常", "我守着"],
    "talk":    ["我在呢", "主人，听到啦", "主人，我在听"],
    "excite":  ["！", "主人回来啦！", "太棒了！"],
}

# 基础权重（离线随机游走的倾向）
BASE_WEIGHTS = {
    "idle": 20, "happy": 10, "thinking": 10,
    "working": 25, "talk": 10, "excite": 10,
}


def offline_next(now_hour: int, last_mood: str | None = None,
                 rng: random.Random | None = None,
                 active: bool | None = None,
                 relationship: float = 0.0) -> dict:
    """按时间 + 主人活跃度 + 关系生成下一个状态。

    active=True  主人正在敲键盘 → 更爱搭话/开心/工作，不爱困
    active=False 主人离开       → 更爱发呆/犯困
    relationship 越高越爱说话（idle 也少沉默）
    """
    rng = rng or random
    w = dict(BASE_WEIGHTS)
    if now_hour >= 23 or now_hour < 7:
        w["idle"] *= 2
        w["working"] *= 0.3
    elif 8 <= now_hour <= 10:
        w["excite"] *= 2
    elif 10 <= now_hour <= 18:
        w["working"] *= 1.5
    # 主人活动状态影响
    if active is True:
        w["talk"] *= 2
        w["happy"] *= 1.5
        w["working"] *= 1.3
    elif active is False:
        w["idle"] *= 1.5
        w["talk"] *= 0.5
        w["working"] *= 0.6
    # 避免连续重复同一个情绪
    if last_mood and last_mood in w:
        w[last_mood] = max(1, w[last_mood] // 3)
    mood = rng.choices(list(w), weights=list(w.values()), k=1)[0]
    line = rng.choice(LINES[mood])
    # 关系越亲密越爱说话：idle 沉默概率从 50% 降到 10%
    if mood == "idle" and rng.random() < max(0.1, 0.5 - relationship / 100):
        line = ""
    return {"mood": mood, "line": line}


# 离线模式状态栏副标题
SUBS = {
    "working": "离线模式 · 替主人盯着",
}
