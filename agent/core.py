"""交互框架（纯框架，无 win_agent 依赖，可独立 import / 单测）。

从 win_agent.py 抽出，供 win_agent 与 agent/interactions 共用，避免循环 import。
"""
from __future__ import annotations


class RateLimit:
    """简单限频器：间隔 interval 秒内只放行一次。

    首次 ready() 立即放行（返回 True）—— 让第一次真实触发马上生效；
    之后每满 interval 秒放行一次。防止刷屏靠各交互自己的阈值条件，
    而不是靠吞掉第一次触发。
    """

    def __init__(self, interval: float):
        self.interval = interval
        self._t = 0.0

    def ready(self, now: float) -> bool:
        if now - self._t >= self.interval:
            self._t = now
            return True
        return False


class Interaction:
    """交互处理器基类。子类声明关心的通道 + 事件/定时响应。

    ctx 是 AgentContext（duck-typed）：至少提供 .say / .memory / .keys /
    .mouse / .last_idle_s / .cur_mood / .quiet_until / .is_quiet() / .set_quiet()。
    """
    name = "base"
    channels = ()       # 关心的事件通道，如 ("key",)
    priority = "med"    # 说话优先级：high（可抢占）/ med / low（更长间隔）
    group = None        # 互斥组名（如 "keyboard"）：同组同一时间窗只允许一个发声

    def on_event(self, ev: dict, ctx) -> None:
        pass

    def on_tick(self, now: float, ctx) -> None:
        pass


class EventBus:
    """把事件分发给关心该通道的交互处理器；tick 驱动各交互的定时逻辑。"""

    def __init__(self, ctx, interactions: list):
        self.ctx = ctx
        self.all = list(interactions)
        self.handlers: dict[str, list] = {}
        for it in interactions:
            for ch in it.channels:
                self.handlers.setdefault(ch, []).append(it)

    def emit(self, ev: dict) -> None:
        for it in self.handlers.get(ev.get("channel"), []):
            try:
                self.ctx._speaker = it
                it.on_event(ev, self.ctx)
            except Exception as e:
                print(f"[bus] {it.name} 事件处理失败：{e}")
            finally:
                self.ctx._speaker = None

    def tick(self, now: float) -> None:
        for it in self.all:
            try:
                self.ctx._speaker = it
                it.on_tick(now, self.ctx)
            except Exception as e:
                print(f"[bus] {it.name} tick 失败：{e}")
            finally:
                self.ctx._speaker = None
