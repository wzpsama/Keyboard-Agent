# Future roadmap

"Look at your keys" was the first interaction. This file tracks what's next,
in priority order. The Windows local version (`win_agent.py`) already has the
"event bus + interaction registry" skeleton — most new interactions are just a
new `Interaction` subclass registered in `INTERACTIONS`, with the core loop
untouched.

---

## 1. Online brain (Claude API) — interface already reserved

**Current**: `win_agent.py` uses the offline brain `states.offline_next`
(random mood walk, no tokens).

**Reserved interface**: `agent/brain.py` `Brain(offline=False)` already
implements the full online path (`claude-opus-5` + memory summary + activity
awareness). To enable it:

1. `pip install anthropic`
2. Set the `ANTHROPIC_API_KEY` environment variable
3. Point `win_agent.py`'s `ctx.think()` at a `Brain` instance (`think` calls `_think_api`)

**Note**: online calls have network latency (hundreds of ms to seconds) and would
block the hook message loop — so online `think` should run on a **background
thread** and push results back to the main loop via a queue. This is required
before enabling online mode.

---

## 2. More interactions (each a new `Interaction` subclass)

| Interaction | Trigger | Response sketch |
|---|---|---|
| Feed | specific key / timer | opens mouth to eat + intimacy +1 |
| Poke | rapid double-tap | shiver / shy |
| Sit-too-long reminder | active > N minutes | bubble "get up and stretch" |
| Sleep care | time / memory (stayed up late) | bubble greeting (`memory.slept_late_last_night` ready) |
| Weather / time | periodic tick | bubble shows weather / hourly chime |

New-interaction template:

```python
class FeedPet(Interaction):
    name = "feed"
    channels = ("key",)           # channels: key / idle / timer ...
    def on_event(self, ev, ctx):
        ctx.push_frame({...})     # response: render + push
    def on_tick(self, now, ctx):
        pass                      # timed logic (optional)
```

---

## 3. Animation & expression

**Current**: centered ambient scenes use compact GIF loops with blinking and a
pulsing status light while keeping the character's scale fixed. Reactions such
as completion keep their dedicated action animations. The PC sends each loop
once; the keyboard screen keeps replaying it. Off-center looks remain static to
keep key reactions small and responsive. Shared palettes reduce frame-to-frame
color changes.

Next candidates:

- **Look transition**: add 2–3 in-between frames from front to a direction only
  if the extra transfer size does not make key reactions feel slower.
- **More life**: add bounded loops such as a yawn, variable blink timing, or
  antenna jitter while preserving a fixed character canvas.
- **Animation budget**: formalize frame-count and encoded-size limits so new
  expressions cannot silently degrade serial responsiveness.

---

## 4. Push performance (lower latency) — current bottleneck

**Current**: scene uploads and the screen's processing time remain the limiting
factors. Production keeps the official compressed GIF → Image2Bin →
SerialPortTool → COM3 path, with pre-converted scenes, panel-side animation
loops, duplicate suppression, bounded queues, and failure backoff.

The earlier raw-frame experiments do not establish partial updates for the
compressed animation format. Neither instant asset switching nor a safe direct
serial replacement has been verified. Earlier latency estimates for those
ideas were hypotheses, not production guarantees.

Next candidates:

1. **Measure the official path**: compare encoded size, conversion time, upload
   time, and keyboard responsiveness for representative scenes.
2. **Reduce unnecessary transfers**: preserve scene-level deduplication and
   keep new animation assets within an explicit size budget.
3. **Research only with evidence**: capture official-tool traffic and verify
   acknowledgement and checksum behavior before any owner-supervised protocol
   experiment. Partial updates require separate proof for compressed payloads.

See [Screen transport research](docs/SCREEN_TRANSPORT_RESEARCH.md) for the
evidence gates. No direct sender or firmware change is enabled by this release.

---

## 5. Deployment & ops

- **Auto-start**: implemented with a per-user Startup shortcut via
  `setup_autostart.bat`. The shortcut launches `pythonw` directly.
- **Coding-agent lifecycle bridge**: implemented for local Windows Codex and a
  remote Codex relay. The handoff is fixed-enum only and keeps independent
  revision sequences per source; see `docs/CODING_STATUS_BRIDGE.md`.
- **Additional coding agents**: validate a Claude Code adapter against the same
  status protocol before documenting it as supported.
- **Watchdog**: detect `win_agent.py` crash and restart.
- **Log rotation**: implemented in the local `agent_run.log` files.

---

## 6. Perception upgrades

- **Multi-key semantics**: currently only the latest key direction is used;
  recognize combos / rhythm (fast double-tap = poke, hold = pet) to expand the
  interaction vocabulary.
- **Screen-content awareness**: read the foreground window title
  (GetForegroundWindow) and have the pet "guess what you're doing".

---

## 7. Speaker sound (researched, not implementing — 2026-08-28)

**Conclusion**: the keyboard's built-in "key tone" speaker is **not a USB audio
device**. The "USB Audio Device" in Windows sound settings is the user's
DualSense controller (VID_054C), not the keyboard. The keyboard itself =
0C45:800A (USB Composite HID — all 4 interfaces are HID, no audio interface).

**Current state**: key tones are produced locally by the keyboard MCU firmware;
AULA's "key tone" switch sends a HID vendor command to the MCU. The PC can't
`winsound` / play a wav to it like a normal speaker.

**To make Vega speak from it**, we'd reverse AULA's vendor sound command (like
the earlier screen-push reverse engineering), with two uncertainties:
1. the command may only toggle key tones, not play arbitrary tones / effects;
2. even if triggerable, it's likely a fixed "click", not programmable audio.

**Interactions possible from a "beep"**: attention alert (beep before speaking),
emotion tones (two short happy beeps / one long alarm), type-synced clicks.

**TODO** (separate small project, may not pan out, not started): HID capture
(frida / enum_all_hid) of AULA's feature report when toggling key tones, to
locate the vendor sound command.
