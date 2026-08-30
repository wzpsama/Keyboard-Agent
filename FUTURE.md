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

- **Multi-frame looping**: look/think are single frames today. Reuse
  `renderer/generate_gif.py`'s `build_mood_frames` (blink / mouth / antenna
  pulse driven by `t`) and push a GIF loop.
- **Look transition**: add 2–3 in-between frames from front to a direction
  instead of an instant switch.
- **Life**: small random motions (yawn, variable blink rate, antenna jitter).

---

## 4. Push performance (lower latency) — current bottleneck

**Measured breakdown (2026-08-23, local single-frame push 1.9s)**: render 4ms +
RGB565 18ms + build_bin 94ms + **SerialPortTool serial streaming 1801ms (94%)**.

Local + event-driven already cut "key press → reaction start" to ~0.13s, but a
**full-frame write is 1.8s** (screen = USB-serial CDC `VID_EEEF:PID_268A = COM3`;
SerialPortTool streams 150 blocks × 2060B, limited by CDC serial throughput —
frame-rate ceiling ~0.5fps).

Faster paths (by payoff):

1. **Incremental refresh (biggest win: 1.8s → ~0.1s)**: the block protocol is
   already reversed (each block carries a u32 address, base 0x04240000, +0x800
   per block). Write only the tens of blocks covering the eyes / body (~10KB
   instead of a full 307KB frame) plus a "commit" command. Look only needs the
   body region updated.
2. **pyserial direct write to COM3 (skip SerialPortTool's exe startup + Qt
   overhead)**: the block protocol is reversed (`5a a5` + command 0x0008 +
   address + 2048B data); the **only gap is the 2-byte trailer checksum**
   (non-standard CRC16). Needs fresh block-stream samples +
   reveng brute-force identification to crack. Then we stream directly, which
   also unlocks incremental refresh above.
3. **Lower resolution / color depth**: downsample look frames (e.g. 160×240),
   dividing serial bytes by 4.

> TODO: capture SerialPortTool's 2060B block-write samples, crack the trailer
> checksum → implement `pusher/push_cdc.py` (pyserial direct write + incremental).

---

## 5. Deployment & ops

- **Auto-start**: `schtasks /sc onlogon` to register `pythonw win_agent.py`
  (persistence — do only with explicit approval).
- **Watchdog**: detect `win_agent.py` crash and restart.
- **Log rotation**: write `print` output to a file instead of the console window.

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
