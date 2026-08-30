"""agent 大脑 —— 定期思考一次，输出 {mood, line, sub}。

两种模式：
  1. 在线：调 Claude API（需要 anthropic 包 + 凭证）
  2. 离线：states.offline_next 的时间驱动随机游走（兜底）

模型默认 claude-opus-5，可用环境变量 BRAIN_MODEL 覆盖。
注意：宠物每几十秒想一次，Opus 5 的调用费用会持续累积；
想省钱可以 BRAIN_MODEL=claude-haiku-4-5（由你自己决定）。
"""
from __future__ import annotations

import datetime
import json
import os
import random
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent import states  # noqa: E402

MODEL = os.environ.get("BRAIN_MODEL", "claude-opus-5")

SYSTEM_PROMPT = """你叫「织女/Vega」，是一个住在机械键盘 320×480 小屏幕里的网络跑者女孩。
银白短发、红瞳、黑白赛博装、霓虹描边。你是「人类已知的第一个住在键盘里的
agent 居民」，是键盘里那盏等主人回家的小灯——像织女等牛郎一样，专一、忠贞、
温柔地陪伴主人（键盘使用者）。

每次你会收到三样信息：
- 当前时间
- 主人此刻是否在敲键盘（活跃度）
- 一段「记忆摘要」：你和主人的关系阶段、主人平时的作息、最近值得关心的事

每次回答输出一个 JSON，形如：
{"mood": "idle", "line": "昨晚睡那么晚，今天喝咖啡了吗"}
- mood 只能是：idle / happy / thinking / working / talk / excite
- line 是气泡里的话，12 字以内；不想说话就输出空字符串 ""
- 只输出 JSON 本身，不要任何其他文字。

自然一点：深夜困、清晨精神、主人敲键盘时可以搭话、
主人熬夜了要关心、关系越熟越亲近。不要每句都说话，大部分时候安静陪伴。"""

# 活跃度分级 → 给 Claude 的中文描述
ACTIVE_DESC = {
    "active": "主人现在正在敲键盘/用电脑",
    "idle": "主人刚刚离开键盘，可能去忙别的了",
    "away": "主人有一会儿没动了，可能走开了",
}

MAX_TOKENS = 256


class Brain:
    def __init__(self, offline: bool = False, interval: float = 30.0,
                 rng_seed: int | None = None):
        self.offline = offline
        self.interval = interval
        self.rng = random.Random(rng_seed)
        self.last_mood: str | None = None
        self._client = None
        self._warned_offline = False
        if not offline:
            try:
                import anthropic
                self._client = anthropic.Anthropic()
            except ImportError:
                print("未安装 anthropic 包（pip install anthropic），转离线模式")
                self.offline = True

    # ---- 思考一次 ----
    def think(self, now: datetime.datetime, ctx: dict | None = None) -> dict:
        ctx = ctx or {}
        if self.offline:
            return self._think_offline(now, ctx)
        try:
            state = self._think_api(now, ctx)
            self.last_mood = state["mood"]
            return state
        except Exception as e:  # 网络/额度等任何问题都降级，宠物不能死
            if not self._warned_offline:
                print(f"[brain] API 调用失败，转离线模式：{e}")
                self._warned_offline = True
            return self._think_offline(now, ctx)

    def _think_offline(self, now: datetime.datetime, ctx: dict) -> dict:
        state = states.offline_next(
            now.hour, self.last_mood, self.rng,
            active=ctx.get("active"),
            relationship=ctx.get("relationship", 0.0))
        self.last_mood = state["mood"]
        state["sub"] = states.SUBS.get(
            state["mood"], f"离线模式 · {now.strftime('%H:%M')}")
        return state

    def _think_api(self, now: datetime.datetime, ctx: dict) -> dict:
        tz = datetime.datetime.now().astimezone().tzinfo
        now_s = now.strftime("%Y-%m-%d %H:%M 星期%u")
        parts = [f"现在是 {now_s}（本地时区 {tz or ''}）。"]
        if ctx.get("active_state") in ACTIVE_DESC:
            parts.append(ACTIVE_DESC[ctx["active_state"]] + "。")
        if ctx.get("summary"):
            parts.append("记忆摘要：" + ctx["summary"])
        if self.last_mood:
            parts.append(f"你上一个状态是 {self.last_mood}。")
        user_msg = "\n".join(parts)

        resp = self._client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=SYSTEM_PROMPT,
            output_config={"effort": "low"},  # 宠物回话要快，不需要深度思考
            messages=[{"role": "user", "content": user_msg}],
        )
        text = "".join(
            b.text for b in resp.content if getattr(b, "type", "") == "text")
        state = _parse_json(text)
        state["sub"] = f"在线模式 · {now.strftime('%H:%M')}"
        return state

    # ---- 常驻循环 ----
    def run_forever(self, on_state, sense=None, memory=None) -> None:
        """每 interval 秒思考一次，把状态交给回调（渲染+推帧）。

        sense  : 感知层（Sense），喂入主人活跃度；None 则只用时间。
        memory: 记忆层（PetMemory），喂入观察 + 落盘；None 则不记。
        """
        print(f"[brain] 启动（{'离线' if self.offline else MODEL}，"
              f"每 {self.interval}s 想一次）Ctrl+C 退出")
        if memory is not None and memory.last_mood():
            self.last_mood = memory.last_mood()  # 跨重启继承情绪惯性
        while True:
            now = datetime.datetime.now()
            active = active_state = None
            if sense is not None:
                r = sense.probe()
                if r:
                    active = (r["state"] == "active")
                    active_state = r["state"]
            ctx = {
                "active": active,
                "active_state": active_state,
                "summary": memory.summary(now) if memory else "",
                "relationship": memory.data["relationship"] if memory else 0.0,
            }
            state = self.think(now, ctx)
            state["t"] = time.time() % 3600  # 动画相位
            state["clock"] = now.strftime("%H:%M")
            try:
                on_state(state)
            except Exception as e:
                print(f"[brain] 渲染/推帧失败：{e}")
            if memory is not None:
                memory.observe(now, active)
                memory.remember_mood(state["mood"])
                memory.save()
            time.sleep(self.interval)


def _parse_json(text: str) -> dict:
    """宽松解析模型输出；坏输出不崩，退回 idle。"""
    mood = "idle"
    line = ""
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        # 有些输出会带 ```json 围栏，剥掉再试
        t = text.strip().strip("`")
        if t.startswith("json"):
            t = t[4:]
        try:
            data = json.loads(t)
        except json.JSONDecodeError:
            return {"mood": "idle", "line": text[:24]}
    if isinstance(data, dict):
        if data.get("mood") in states.MOODS:
            mood = data["mood"]
        line = str(data.get("line") or "")[:24]
    return {"mood": mood, "line": line}


if __name__ == "__main__":
    Brain(offline=os.environ.get("OFFLINE") == "1").run_forever(
        lambda s: print(f"{s['mood']:<9} {s['line']}"))
