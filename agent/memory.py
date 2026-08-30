"""记忆层 —— 小团子对主人和自身的持久记忆。

一个 JSON 文件，跨进程/跨重启保存：
  - 关系阶段（亲密度 0~100 → 刚认识/有点熟/很熟了/家人）
  - 主人作息画像（24 小时活跃直方图 + 最近一次活跃的小时）
  - 情绪历史（供惯性，避免情绪乱跳）
  - 关键记忆（如「昨晚睡很晚」，次日可用来问候）

每次思考后 observe() 喂入活跃度与情绪，save() 落盘；summary() 产出给 brain
（含 Claude）的「记忆摘要」，让宠物的话有上下文、有连续性。
"""
from __future__ import annotations

import datetime
import json
import os

STAGES = [  # (亲密度下限, 阶段名)
    (0, "刚认识"),
    (15, "有点熟"),
    (35, "很熟了"),
    (60, "家人"),
]


def _iso(now: datetime.datetime) -> str:
    return now.strftime("%Y-%m-%d %H:%M")


class PetMemory:
    def __init__(self, path: str = "data/pet_memory.json"):
        self.path = path
        self.data = self._default()
        self.load()

    def _default(self) -> dict:
        return {
            "created": datetime.date.today().isoformat(),
            "relationship": 0.0,
            "mood_history": [],
            "awake_hours": [0] * 24,
            "latest_active_hour": None,   # 最近一次活跃的小时（0-23）
            "noticed_late": None,          # 已提示过「睡很晚」的日期
            "last_active_at": None,
            "total_thoughts": 0,
            "streak_days": 0,             # 连续陪伴天数
            "last_seen_date": None,        # 最近一次「见过面」的日期
            "celebrated_streak": 0,        # 已庆祝过的连续天数里程碑
            "celebrated_stage": "刚认识",   # 已庆祝过的关系阶段（初始最低阶段不庆祝）
        }

    def load(self) -> None:
        if os.path.exists(self.path):
            try:
                with open(self.path, encoding="utf-8") as f:
                    self.data.update(json.load(f))
            except (json.JSONDecodeError, OSError) as e:
                print(f"[memory] 记忆文件损坏，重建：{e}")

    def save(self) -> None:
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, self.path)

    # ---- 观察与更新 ----
    def observe(self, now: datetime.datetime, active: bool | None) -> None:
        """喂入本轮感知结果，更新作息画像与亲密度。"""
        self.data["total_thoughts"] += 1
        if active is True:
            h = now.hour
            self.data["awake_hours"][h] += 1
            self.data["latest_active_hour"] = h
            self.data["last_active_at"] = _iso(now)
            # 有互动，亲密度缓慢上升（约每 100 次活跃 +30）
            self.data["relationship"] = min(100.0, self.data["relationship"] + 0.3)

    def remember_mood(self, mood: str) -> None:
        self.data["mood_history"].append(mood)
        self.data["mood_history"] = self.data["mood_history"][-16:]

    # ---- 查询 ----
    def stage(self) -> str:
        rel = self.data["relationship"]
        name = STAGES[0][1]
        for threshold, label in STAGES:
            if rel >= threshold:
                name = label
        return name

    def last_mood(self) -> str | None:
        return self.data["mood_history"][-1] if self.data["mood_history"] else None

    def slept_late_last_night(self, now: datetime.datetime) -> bool:
        """判断「昨晚」是否睡得很晚（凌晨 1 点后仍活跃），且今天还没提过。"""
        if now.hour < 12 and (self.data.get("latest_active_hour") or -1) >= 1:
            if self.data.get("noticed_late") != now.date().isoformat():
                return True
        return False

    def mark_noticed_late(self, now: datetime.datetime) -> None:
        self.data["noticed_late"] = now.date().isoformat()

    def touch_day(self, now: datetime.datetime) -> int:
        """登记今天「见过面」，返回连续陪伴天数（隔天 +1，断档归 1）。"""
        today = now.date()
        last = self.data.get("last_seen_date")
        if last == today.isoformat():
            return int(self.data.get("streak_days", 1))
        streak = 1
        if last:
            try:
                prev = datetime.date.fromisoformat(last)
                if (today - prev).days == 1:
                    streak = int(self.data.get("streak_days", 0)) + 1
            except ValueError:
                pass
        self.data["streak_days"] = streak
        self.data["last_seen_date"] = today.isoformat()
        return streak

    # ---- 给 brain 的摘要 ----
    def summary(self, now: datetime.datetime) -> str:
        bits = [f"你和主人的关系是「{self.stage()}」"
                f"（亲密度 {self.data['relationship']:.0f}/100）。"]
        if self.slept_late_last_night(now):
            bits.append("主人昨晚睡得很晚（凌晨还在敲键盘），可以关心一句。")
        if any(self.data["awake_hours"]):
            top = sorted(range(24),
                         key=lambda h: self.data["awake_hours"][h],
                         reverse=True)[:3]
            bits.append(f"主人常在 {','.join(str(h) for h in sorted(top))} 点活动。")
        return " ".join(bits)


if __name__ == "__main__":
    import datetime as _dt
    m = PetMemory()
    now = _dt.datetime.now()
    print(m.summary(now))
    print("stage:", m.stage(), "rel:", round(m.data["relationship"], 1))
