"""扩展交互集（A 键盘 / B 前台应用 / C 系统指标 / E 成长·陪伴 / D 音乐）。

每个交互是一个 Interaction 子类，只依赖 ctx 的鸭子类型接口（.say / .memory /
.keys / .last_idle_s / .set_quiet / .is_quiet / ._quiet_reason）与 agent.sensors。
全部用 RateLimit 限频，避免刷屏；识别不准的信号宁可少说。

防冲突：每个交互声明 priority（high 可抢占 / med / low 更长间隔）与 group
（互斥组，如 "keyboard"），由 AgentContext.say 统一仲裁，见 win_agent.py。
防阻塞：sensors.foreground_app / system_metrics 内部有缓存，多交互共享同一次采样。
"""
from __future__ import annotations

import datetime
import time

from agent import keys, sensors, weather
from agent.core import Interaction, RateLimit


# =====================================================================
#  A. 键盘层
# =====================================================================
class SpaceMash(Interaction):
    """连续狂按空格（快进/游戏跳跃）→ 兴奋。"""
    name = "space"
    channels = ()
    priority = "med"
    group = "keyboard"

    def __init__(self):
        self._rl = RateLimit(90.0)

    def on_tick(self, now, ctx):
        if ctx.keys.space_count(now, span=8) >= 8 and self._rl.ready(now):
            ctx.say("主人狂按什么呀？好兴奋！", mood="excite")
            print("[space] 狂按空格")


class PasteSpam(Interaction):
    """Ctrl+V 狂按 → 吐槽搬砖。"""
    name = "paste"
    channels = ()
    priority = "med"
    group = "keyboard"

    def __init__(self):
        self._rl = RateLimit(300.0)

    def on_tick(self, now, ctx):
        if ctx.keys.ctrl_v_count(now, span=60) >= 8 and self._rl.ready(now):
            ctx.say("又在搬砖啦，主人", mood="talk")
            print("[paste] Ctrl+V 狂按")


class DeleteCry(Interaction):
    """删除/退格 → 望向删除键（左上）夸张哭泣。

    合并了原「改稿安慰(backspace)」交互：快速连删（4s 内 3+ 次）或持续改稿
    （60s 内 20+ 次）都走哭这一条，不再单独说「改稿很痛苦吧」。

    priority="high"：哭是主人明确想要、且易被「狂打字(typing)」等同组键盘交互
    抢先触发的反应。high 可绕过互斥组时间窗 + 最小说话间隔，
    保证「连删就哭」稳定触发（主人反馈「快速敲击不会触发流泪」）。"""
    name = "delete_cry"
    channels = ()
    priority = "high"
    group = "keyboard"

    def __init__(self):
        self._rl = RateLimit(150.0)

    def on_tick(self, now, ctx):
        if self._rl.ready(now) and (
                ctx.keys.backspace_count(now, span=4) >= 3       # 快速连删
                or ctx.keys.backspace_count(now, span=60) >= 20):  # 持续改稿
            ctx.say("呜呜呜 主人在删什么鸭", mood="cry", look=(-5, -5),
                    sub="别删了嘛～")
            print("[delete_cry] 连删哭泣")


class CapsLockAlert(Interaction):
    """大写锁误开 + 正常打字 → 提醒。"""
    name = "capslock"
    channels = ()
    priority = "med"

    def __init__(self):
        self._rl = RateLimit(600.0)

    def on_tick(self, now, ctx):
        if (sensors.caps_lock_on()
                and ctx.keys.kpm(now, span=20) >= 30
                and self._rl.ready(now)):
            ctx.say("主人，大写锁开着哦", mood="talk")
            print("[capslock] 大写锁提醒")


class TypingRush(Interaction):
    """打字节奏异常快 → 手速/冷静。"""
    name = "typing"
    channels = ()
    priority = "med"
    group = "keyboard"

    def __init__(self):
        self._rl_fast = RateLimit(180.0)
        self._rl_calm = RateLimit(600.0)

    def on_tick(self, now, ctx):
        kpm = ctx.keys.kpm(now, span=20)
        if kpm >= 220 and self._rl_calm.ready(now):
            ctx.say("冷静冷静，主人！", mood="talk")
            print("[typing] 超快手速")
        elif kpm >= 140 and self._rl_fast.ready(now):
            ctx.say("主人手速好快！", mood="excite")
            print("[typing] 快手速")


class GameWatch(Interaction):
    """WASD/方向键/空格键簇占比高 → 观战模式。"""
    name = "game"
    channels = ()
    priority = "med"
    group = "keyboard"

    def __init__(self):
        self._rl = RateLimit(90.0)
        self._lines = ["这把能赢！", "主人加油！", "漂亮！", "稳住，能打！"]
        self._i = 0

    def on_tick(self, now, ctx):
        dt = datetime.datetime.fromtimestamp(now)
        if dt.weekday() < 5 and 9 <= dt.hour < 18:
            return   # 工作时段交给 Slacking「摸鱼被抓」，避免一边加油一边抓摸鱼自相矛盾
        if (ctx.keys.game_share(now, span=20) >= 0.5
                and ctx.keys.game_count(now, span=20) >= 8
                and self._rl.ready(now)):
            line = self._lines[self._i % len(self._lines)]
            self._i += 1
            ctx.say(line, mood="excite")
            print("[game] 观战：" + line)


class SwitchPanic(Interaction):
    """短时间频繁切换前台窗口（找东西/慌乱）→ 关心。"""
    name = "switch"
    channels = ()
    priority = "med"
    group = "keyboard"

    def __init__(self):
        self._rl = RateLimit(120.0)

    def on_tick(self, now, ctx):
        sensors.foreground_app()   # 确保快照刷新（含切换计数）
        if sensors.foreground_changes(now, span=20) >= 6 and self._rl.ready(now):
            ctx.say("主人找什么呀？我来帮你盯着", mood="talk")
            print("[switch] 频繁切窗")


class ReturnWelcome(Interaction):
    """长时间离开（idle ≥20 分钟）后回来第一次输入 → 欢迎回来。"""
    name = "return"
    channels = ()
    priority = "med"

    def __init__(self):
        self._rl = RateLimit(300.0)
        self._was_away = False

    def on_tick(self, now, ctx):
        idle = ctx.last_idle_s
        if idle >= 1200:
            self._was_away = True
            return
        if self._was_away and idle < 5 and self._rl.ready(now):
            ctx.say("主人回来啦，想你了", mood="happy")
            print("[return] 发呆回归")
            self._was_away = False


# =====================================================================
#  B. 前台应用识别
# =====================================================================
class AppAware(Interaction):
    """识别前台应用切换，按类别说一句话；会议类 → 静默。"""
    name = "app"
    channels = ()
    priority = "low"
    POLL = 8.0

    def __init__(self):
        self._poll = RateLimit(self.POLL)
        self._last_cat = None
        self._said = {}          # category -> 上次说话时间戳

    def on_tick(self, now, ctx):
        if not self._poll.ready(now):
            return
        if ctx.is_quiet(now):
            return
        fa = sensors.foreground_app()
        if fa is None:
            return
        cat = sensors.classify_app(fa[0])
        if cat == self._last_cat:
            return
        self._last_cat = cat
        self._on_enter(cat, now, ctx, fa)

    def _on_enter(self, cat, now, ctx, fa):
        if cat == "meeting":
            ctx.set_quiet(30 * 60, reason="meeting")
            ctx.say("开会中，我安静陪你", mood="talk", sub="会议中 · 已静音")
            print("[app] 会议中 → 静默 30min")
            return
        if now - self._said.get(cat, 0.0) < 600:
            return
        lines = {
            "ide": ("写代码中？加油，主人", "thinking"),
            "browser": ("上网冲浪呀", "idle"),
            "office": ("处理文档呀，主人", "working"),
            "game": ("游戏时间！主人加油", "excite"),
            "terminal": ("敲命令行呀，主人", "thinking"),
            "media": ("一起看/听呀", "happy"),
        }
        if cat in lines:
            line, mood = lines[cat]
            self._said[cat] = now
            ctx.say(line, mood=mood)
            print(f"[app] 进入 {cat}（{fa[0]}）")


class Slacking(Interaction):
    """工作日工作时段 + 游戏键簇 → 摸鱼被抓。"""
    name = "slack"
    channels = ()
    priority = "med"

    def __init__(self):
        self._rl = RateLimit(1800.0)

    def on_tick(self, now, ctx):
        dt = datetime.datetime.fromtimestamp(now)
        if dt.weekday() >= 5 or not (9 <= dt.hour < 18):
            return
        if (ctx.keys.game_share(now, span=30) >= 0.4
                and ctx.keys.game_count(now, span=30) >= 12
                and self._rl.ready(now)):
            ctx.say("工作时间摸鱼被抓到啦，主人！", mood="talk")
            print("[slack] 摸鱼检测")


class Overtime(Interaction):
    """工作日深夜 + IDE/办公前台 → 加班提醒。"""
    name = "overtime"
    channels = ()
    priority = "med"

    def __init__(self):
        self._poll = RateLimit(15.0)
        self._rl = RateLimit(2700.0)

    def on_tick(self, now, ctx):
        dt = datetime.datetime.fromtimestamp(now)
        if dt.weekday() >= 5 or not (22 <= dt.hour < 24):
            return
        if not self._poll.ready(now):
            return
        fa = sensors.foreground_app()
        if fa and sensors.classify_app(fa[0]) in ("ide", "office"):
            if self._rl.ready(now):
                ctx.say("主人还在加班？早点休息呀", mood="talk")
                print("[overtime] 加班提醒")


class FlowProtect(Interaction):
    """IDE 前台持续 ≥20 分钟 → 主动静默陪伴（心流保护）。"""
    name = "flow"
    channels = ()
    priority = "high"
    LIMIT = 20 * 60

    def __init__(self):
        self._rl = RateLimit(1800.0)
        self._ide_since = None

    def on_tick(self, now, ctx):
        fa = sensors.foreground_app()
        in_ide = fa and sensors.classify_app(fa[0]) == "ide"
        if in_ide:
            if self._ide_since is None:
                self._ide_since = now
            if now - self._ide_since >= self.LIMIT and self._rl.ready(now):
                ctx.set_quiet(30 * 60, reason="flow")
                ctx.say("主人专注，我安静陪着", mood="talk", sub="心流模式 · 已静音")
                print("[flow] 心流保护")
                self._ide_since = now
        else:
            self._ide_since = None


class BingeWatch(Interaction):
    """前台媒体播放持续 ≥1 小时 → 护眼提醒。"""
    name = "binge"
    channels = ()
    priority = "low"
    LIMIT = 60 * 60

    def __init__(self):
        self._rl = RateLimit(1800.0)
        self._since = None
        self._last_in = 0.0

    def on_tick(self, now, ctx):
        fa = sensors.foreground_app()
        in_media = fa and sensors.classify_app(fa[0]) == "media"
        if in_media:
            if self._since is None:
                self._since = now
            self._last_in = now
            if now - self._since >= self.LIMIT and self._rl.ready(now):
                ctx.say("眼睛歇歇呀，主人", mood="talk")
                print("[binge] 刷剧护眼")
                self._since = now
        else:
            if self._since is not None and now - self._last_in > 120:
                self._since = None


class MeetingEnd(Interaction):
    """会议静默结束后切回 → 问候。"""
    name = "meeting_end"
    channels = ()
    priority = "med"

    def __init__(self):
        self._was_quiet = False

    def on_tick(self, now, ctx):
        quiet = ctx.is_quiet(now)
        if self._was_quiet and not quiet \
                and getattr(ctx, "_quiet_reason", None) == "meeting":
            ctx._quiet_reason = None
            ctx.say("开完会啦？辛苦主人", mood="talk")
            print("[meeting_end] 会议结束")
        self._was_quiet = quiet


# =====================================================================
#  C. 系统指标 / 锁屏
# =====================================================================
class SystemLoad(Interaction):
    """CPU/内存持续高 → 关心。"""
    name = "sysload"
    channels = ()
    priority = "high"

    def __init__(self):
        self._poll = RateLimit(60.0)
        self._rl = RateLimit(900.0)

    def on_tick(self, now, ctx):
        if not self._poll.ready(now):
            return
        m = sensors.system_metrics()
        if not m:
            return
        if (m.get("cpu", 0) >= 90 or m.get("mem", 0) >= 92) and self._rl.ready(now):
            ctx.say("电脑好烫，主人歇会儿吧", mood="talk", sub=f"CPU {m['cpu']:.0f}% · 内存 {m['mem']:.0f}%")
            print("[sysload] 系统高负载")


class LoadRecover(Interaction):
    """高负载回落到正常 → 报平安。"""
    name = "recover"
    channels = ()
    priority = "med"

    def __init__(self):
        self._rl = RateLimit(600.0)
        self._high = False

    def on_tick(self, now, ctx):
        m = sensors.system_metrics()
        if not m:
            return
        cpu = m.get("cpu", 0)
        mem = m.get("mem", 0)
        if cpu >= 90 or mem >= 92:
            self._high = True
        elif self._high and cpu < 70 and mem < 80 and self._rl.ready(now):
            ctx.say("凉快下来啦，主人", mood="happy")
            print("[recover] 负载回落")
            self._high = False


class LockGoodnight(Interaction):
    """锁屏 → 道别。"""
    name = "lock"
    channels = ()
    priority = "high"

    def __init__(self):
        self._poll = RateLimit(5.0)
        self._locked = False

    def on_tick(self, now, ctx):
        if not self._poll.ready(now):
            return
        locked = sensors.is_locked()
        if locked and not self._locked:
            ctx.say("主人，回头见", mood="talk", sub="等你回来")
            print("[lock] 锁屏道别")
        self._locked = locked


# =====================================================================
#  E. 成长 / 陪伴
# =====================================================================
class StreakCelebrate(Interaction):
    """连续陪伴天数里程碑 → 庆祝（7/30/100 天）。"""
    name = "streak"
    channels = ()
    priority = "high"
    MILESTONES = (7, 30, 100)

    def __init__(self):
        self._greeted = False

    def on_tick(self, now, ctx):
        dt = datetime.datetime.fromtimestamp(now)
        streak = ctx.memory.touch_day(dt)
        if self._greeted:
            return
        self._greeted = True
        celebrated = ctx.memory.data.get("celebrated_streak", 0)
        for m in self.MILESTONES:
            if streak >= m and celebrated < m:
                ctx.memory.data["celebrated_streak"] = m
                ctx.memory.save()
                ctx.say(f"今天是我们认识的第 {streak} 天啦！", mood="excite", sub="谢谢主人一直陪着我")
                print(f"[streak] 第 {streak} 天庆祝")
                return


class StageUp(Interaction):
    """亲密度跨阶段（刚认识→有点熟→很熟了→家人）→ 一次庆祝。"""
    name = "stageup"
    channels = ()
    priority = "high"

    def on_tick(self, now, ctx):
        stage = ctx.memory.stage()
        celebrated = ctx.memory.data.get("celebrated_stage", "刚认识")
        if stage == celebrated:
            return
        ctx.memory.data["celebrated_stage"] = stage
        ctx.memory.save()
        ctx.say("我觉得和主人更亲近了", mood="happy", sub=stage)
        print(f"[stageup] 关系升级：{stage}")


class LateNightCare(Interaction):
    """昨晚熬夜 → 次日关心（复用 memory 的 slept_late_last_night）。"""
    name = "latenight"
    channels = ()
    priority = "med"

    def __init__(self):
        self._done = None

    def on_tick(self, now, ctx):
        dt = datetime.datetime.fromtimestamp(now)
        if not ctx.memory.slept_late_last_night(dt):
            return
        day = dt.date().isoformat()
        if self._done == day:
            return
        self._done = day
        ctx.memory.mark_noticed_late(dt)
        ctx.memory.save()
        ctx.say("主人昨晚睡那么晚，今天喝咖啡了吗", mood="talk")
        print("[latenight] 熬夜关心")


class Midnight(Interaction):
    """凌晨 0-5 点仍活跃 → 实时关心。"""
    name = "midnight"
    channels = ()
    priority = "med"

    def __init__(self):
        self._rl = RateLimit(1800.0)

    def on_tick(self, now, ctx):
        dt = datetime.datetime.fromtimestamp(now)
        if not (0 <= dt.hour < 5):
            return
        if ctx.last_idle_s < 60 and self._rl.ready(now):
            ctx.say("这么晚还不睡呀，主人", mood="talk")
            print("[midnight] 深夜关心")


class SleepyYawn(Interaction):
    """深夜主人离开键盘 → 宠物犯困打盹（戴眼罩 + 飘 z 的动作动画）。"""
    name = "sleepy"
    channels = ()
    priority = "low"

    def __init__(self):
        self._rl = RateLimit(1800.0)   # 最多每 30 分钟打一次盹

    def on_tick(self, now, ctx):
        if ctx.is_quiet(now):
            return
        dt = datetime.datetime.fromtimestamp(now)
        if not (dt.hour >= 22 or dt.hour < 6):
            return
        if ctx.last_idle_s >= 300 and self._rl.ready(now):
            ctx.say("主人不在，我先打个盹…", mood="sleepy", sub="困了困了")
            print("[sleepy] 深夜犯困打盹")


class Mealtime(Interaction):
    """饭点（12-13 点）活跃 → 提醒吃午饭。每天一次。"""
    name = "mealtime"
    channels = ()
    priority = "med"

    def __init__(self):
        self._done = None

    def on_tick(self, now, ctx):
        if ctx.is_quiet(now):
            return
        dt = datetime.datetime.fromtimestamp(now)
        if not (12 <= dt.hour < 13):
            return
        day = dt.strftime("%Y-%m-%d")
        if self._done == day:
            return
        if ctx.last_idle_s < 60:
            self._done = day
            ctx.say("主人该吃午饭啦", mood="talk")
            print("[mealtime] 饭点提醒")


class Weekend(Interaction):
    """周五 17 点后活跃 → 周末祝福。每周一次。"""
    name = "weekend"
    channels = ()
    priority = "low"

    def __init__(self):
        self._done = None

    def on_tick(self, now, ctx):
        if ctx.is_quiet(now):
            return
        dt = datetime.datetime.fromtimestamp(now)
        if dt.weekday() != 4 or dt.hour < 17:
            return
        key = dt.strftime("%Y-W%W")
        if self._done == key:
            return
        if ctx.last_idle_s < 60:
            self._done = key
            ctx.say("周五啦！周末快乐，主人", mood="happy")
            print("[weekend] 周末祝福")


# =====================================================================
#  D. 音乐 / 天气 / 猜你在干嘛
# =====================================================================
class MusicCompanion(Interaction):
    """音乐共鸣：开始放歌 / 切歌各说一句；停歌不打扰。"""
    name = "music"
    channels = ()
    priority = "low"

    def __init__(self):
        self._last = None           # 上次 (artist, title)
        self._rl = RateLimit(120.0)
        self._lines = ["这首歌不错呢", "一起听～", "♪ 主人品味我喜欢", "这旋律好听"]
        self._i = 0

    def on_tick(self, now, ctx):
        track = sensors.media_track()
        if track == self._last:
            return
        prev, self._last = self._last, track
        if not self._rl.ready(now):
            return
        if prev is None and track is not None:
            artist, title = track
            who = f" · {artist}" if artist else ""
            ctx.say("放音乐啦，主人", mood="music", sub=f"{title[:16]}{who}")
            print("[music] 开始播放：" + title)
        elif prev is not None and track is not None:
            _, title = track
            line = self._lines[self._i % len(self._lines)]
            self._i += 1
            ctx.say(line, mood="music", sub=title[:20])
            print("[music] 切歌：" + title)
        # prev → None（停歌）不说话，避免打断


class WeatherMood(Interaction):
    """天气感知：雨/雪带伞提醒 + 早晨天气播报（每天各一次）。"""
    name = "weather"
    channels = ()
    priority = "low"

    def __init__(self):
        self._poll = RateLimit(30.0)
        self._said_day = None      # 已播报天气的日期
        self._rain_day = None      # 已提醒带伞/添衣的日期

    def on_tick(self, now, ctx):
        if not self._poll.ready(now):
            return
        w = weather.get_weather()
        if not w:
            return
        dt = datetime.datetime.fromtimestamp(now)
        day = dt.strftime("%Y-%m-%d")
        cat, desc, temp = w["cat"], w["desc"], w["temp"]
        # 雨 / 雪 → 带伞 / 添衣提醒（每天一次，优先于播报）
        if cat == "rain" and self._rain_day != day:
            self._rain_day = day
            ctx.say(f"外面{desc}，记得带伞哦", mood="talk", sub=f"{temp}°C")
            print(f"[weather] 带伞提醒：{desc}")
            return
        if cat == "snow" and self._rain_day != day:
            self._rain_day = day
            ctx.say(f"下{desc}啦，多穿点哦", mood="talk", sub=f"{temp}°C")
            print(f"[weather] 添衣提醒：{desc}")
            return
        # 早晨天气播报（每天一次，主人活跃时）
        if 6 <= dt.hour < 11 and self._said_day != day and ctx.last_idle_s < 60:
            self._said_day = day
            ctx.say(f"今天{desc}，{temp}°C", mood="happy")
            print(f"[weather] 天气播报：{desc} {temp}°C")


class GuessActivity(Interaction):
    """猜你在干嘛：按前台窗口标题的关键词调侃一句。只做粗分类，绝不原样
    念出窗口标题（隐私）。进入新的可识别活动才说，避免同一窗口重复。"""
    name = "guess"
    channels = ()
    priority = "low"
    POLL = 12.0

    # 标题关键词（小写）→ (活动, 台词)
    _MATCH = (
        (("youtube", "bilibili", "netflix", "腾讯视频", "爱奇艺", "斗鱼", "twitch", "niconico"),
         "video", "看视频摸鱼呢，主人"),
        (("github", "gitlab", "stackoverflow", "leetcode", "力扣"), "code", "又在写代码呀，主人"),
        (("steam", "epic", "原神", "genshin", "valorant", "英雄联盟"), "game", "游戏时间！"),
        (("word", "excel", "powerpoint", "ppt", "wps", "文档"), "doc", "在写文档呀"),
    )

    def __init__(self):
        self._poll = RateLimit(self.POLL)
        self._last_act = None
        self._rl = RateLimit(1500.0)

    def on_tick(self, now, ctx):
        if not self._poll.ready(now):
            return
        if ctx.is_quiet(now):
            return
        fa = sensors.foreground_app()
        if not fa:
            return
        title = (fa[1] or "").lower()
        act = None
        line = None
        for kws, a, ln in self._MATCH:
            if any(k in title for k in kws):
                act, line = a, ln
                break
        if act is None:
            self._last_act = None
            return
        if act == self._last_act:
            return
        self._last_act = act
        if self._rl.ready(now):
            ctx.say(line, mood="talk")
            print(f"[guess] 猜你在：{act}")


class Anniversary(Interaction):
    """相识纪念日：每月「认识满 N 个月」的那天庆祝一次（基于 created 绝对天数，
    与连续陪伴 streak 无关）。"""
    name = "anniv"
    channels = ()
    priority = "med"

    def on_tick(self, now, ctx):
        if ctx.is_quiet(now):
            return
        created_s = ctx.memory.data.get("created")
        if not created_s:
            return
        try:
            created = datetime.date.fromisoformat(created_s)
        except ValueError:
            return
        dt = datetime.datetime.fromtimestamp(now)
        today = dt.date()
        if today.day != created.day:
            return
        months = (today.year - created.year) * 12 + (today.month - created.month)
        if months < 1:
            return
        key = f"{today.year}-{today.month}"
        if ctx.memory.data.get("celebrated_anniv") == key:
            return
        ctx.memory.data["celebrated_anniv"] = key
        ctx.memory.save()
        if months == 12:
            ctx.say("我们认识满一年啦！", mood="excite", sub="谢谢主人陪了我这么久")
        else:
            ctx.say(f"今天是我们认识满 {months} 个月啦", mood="happy", sub="以后也要一起哦")
        print(f"[anniv] 相识满 {months} 个月")


EXTRA_INTERACTIONS = [
    # A. 键盘层
    SpaceMash(), PasteSpam(), DeleteCry(), CapsLockAlert(),
    TypingRush(), GameWatch(), SwitchPanic(), ReturnWelcome(),
    # B. 前台应用
    AppAware(), Slacking(), Overtime(), FlowProtect(), BingeWatch(), MeetingEnd(),
    # C. 系统 / 锁屏
    SystemLoad(), LoadRecover(), LockGoodnight(),
    # D. 音乐 / 天气 / 猜你在干嘛
    MusicCompanion(), WeatherMood(), GuessActivity(),
    # E. 成长 / 陪伴
    StreakCelebrate(), StageUp(), LateNightCare(), Midnight(), SleepyYawn(),
    Mealtime(), Weekend(), Anniversary(),
]
