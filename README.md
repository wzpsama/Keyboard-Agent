# Keyboard-Agent — an AI pet that lives in your keyboard

Turn the 3.98" IPS screen (320×480) of the **AULA L99** mechanical keyboard into
the face of a cyberpunk AI pet — **Vega**, a silver-haired, red-eyed girl who
waits for you at home.

**Runs as a single local process on your Windows PC**, talking to the screen
directly through the keyboard's official driver chain (Image2Bin →
SerialPortTool → COM3).

<p align="center">
  <img src="docs/hero.png" alt="Vega living in the AULA L99 keyboard screen" width="720">
</p>

## Quick start

1. Install the official **AULA L99 driver** (bundles `Image2Bin.exe` and
   `SerialPortTool.exe`, default at `C:\Program Files (x86)\AULA L99\qt-tool`).
2. Plug the keyboard in via USB (serial port defaults to `COM3`).
3. Double-click `setup_windows.bat` — creates a venv, installs Pillow, and
   renders a self-test frame.
4. Double-click `start_agent.bat` — runs in the foreground with logs.
   `run_agent.bat` runs it silently in the background (logs to `agent.log`).

> Port not `COM3`? Set the `AULA_COM` environment variable, or edit `PORT` /
> `QT_TOOL` at the top of `pusher/push_local.py`.

## How it works

```
             ┌──────────────────────────────────────────────┐
             │  win_agent.py  (single local process)        │
             │                                              │
             │  WH_KEYBOARD_LL hook — keys around the screen│
             │  GetLastInputInfo     — user activity        │
             │  Event bus + interaction registry (pluggable)│
             │  Offline brain (states.offline_next)         │
             │  renderer/            — state → 320×480 frame│
             │  pusher/push_local.py — GIF → Image2Bin →    │
             │       SerialPortTool → keyboard screen (COM3)│
             └──────────────────────────────────────────────┘
```

- **Offline & free** — no API by default; mood is driven by a local state machine.
  `agent/brain.py` ships an optional Claude online brain (set `ANTHROPIC_API_KEY`,
  `pip install anthropic`, flip `Brain(offline=False)`).
- **Near-instant key reactions** — keys around the screen (↑/↓/←/→/Home/PgUp/…)
  make Vega turn to look, using pre-rendered `.bin` frames.
- **Why the official chain** — the screen only accepts the animated `.bin` header
  that `Image2Bin` produces; hand-rolled single frames cause a garbled top row and
  swapped colors. The driver's own toolchain is stable and correct.

## Moods & animations

`renderer/vega.py` picks the sprite from `mood` / `motion`:

| Mood | Status | Animation |
|---|---|---|
| `idle` / `working` / `talk` / `thinking` | — | Directional sprites (front / left / left_top / top — follows your keys) |
| `happy` | Happy | bounce |
| `excite` | Excited | surprised |
| `sleepy` | Sleepy | sleepy (eye mask + floating z's) |
| `music` | Listening | music |
| `cry` | Crying | 6-frame hand-drawn crying |

| bounce | sleepy | surprised |
|---|---|---|
| <img src="docs/bounce.gif" width="220"> | <img src="docs/sleepy.gif" width="220"> | <img src="docs/surprised.gif" width="220"> |

| music | cry | look around |
|---|---|---|
| <img src="docs/music.gif" width="220"> | <img src="docs/cry.gif" width="220"> | <img src="docs/look.gif" width="220"> |

Action animations only appear in the transient "speak / react" GIFs; the
directional look sprites are unaffected.

## Interactions

28 hand-crafted reactions in `agent/interactions.py`. Highlights:

### Keyboard

| Situation | Vega… |
|---|---|
| You mash the spacebar | gets excited and jumps along |
| You hammer Ctrl+V | teases you about "moving bricks again" |
| You delete a lot while editing | bursts into exaggerated tears toward the delete key |
| Caps Lock is left on while you type | gently points it out |
| You type really fast | cheers your hand speed — or tells you to calm down |
| You start gaming | turns into a spectator and roots for you |
| You frantically flip between windows | offers to help you find whatever you lost |
| You come back after a long break | welcomes you home |

### Foreground app

| Situation | Vega… |
|---|---|
| You switch to IDE / browser / office / game / terminal / media | greets you in that app's mood |
| You join a meeting | goes quiet and silently keeps you company |
| You game during work hours | catches you slacking off |
| You work late in the IDE | urges you to rest |
| You stay focused in the IDE | enters "flow mode" and stops interrupting |
| You binge videos for a long stretch | reminds you to rest your eyes |
| Your meeting ends | welcomes you back |

### System

| Situation | Vega… |
|---|---|
| The CPU / RAM runs hot | worries about the machine |
| The load settles back down | reports that it "cooled down" |
| You lock the screen | says goodbye |

### Music · weather · guessing

| Situation | Vega… |
|---|---|
| You start or change a song | grooves along and rates your taste |
| It rains or snows | reminds you about an umbrella / a warm coat |
| Morning | reads you the day's weather |
| You open a familiar app | guesses what you're up to (without ever reading titles aloud) |

### Companionship

| Situation | Vega… |
|---|---|
| A milestone together (7 / 30 / 100 days) | celebrates |
| Her intimacy level rises | says she feels closer to you |
| You stayed up late last night | asks if you've had your coffee |
| You're up past midnight | worries about you in real time |
| Late at night, you step away | yawns and dozes off (eye mask + floating z's) |
| Lunchtime | reminds you to eat |
| Friday evening | wishes you a happy weekend |
| Monthly anniversary | celebrates another month together |

Each interaction declares a `priority` (high preempts / med / low) and a `group`
(mutex groups like `"keyboard"`), arbitrated by `AgentContext.say` to avoid spam.

## Layout

```
win_agent.py                entry point (local resident agent)
agent/                      interactions, sensing, memory, state machine, brain
renderer/vega.py            Vega sprite rendering (directions + cry + actions)
renderer/render.py          state → 320×480 frame (RGB565 + PNG/GIF)
renderer/avatar.py          programmatic "dango" alt character + mood labels
pusher/push_local.py        GIF → Image2Bin → SerialPortTool (official chain)
assets/vega/                sprites (clean / cry / bounce / sleepy / surprised / music)
docs/                       README images & GIFs
scripts/                    sprite build / re-processing scripts
setup_windows.bat           one-click install
start_agent.bat / run_agent.bat   launch scripts
```

## Rebuilding sprites

- `scripts/process_vega.py` — white-background source → transparent direction sprites.
- `scripts/build_clean_sprites.py` — unify direction sprites to 447×415 full body.
- `scripts/build_cry_sprites.py` — 6 hand-drawn cry frames → cry sprites.
- `scripts/build_action_sprites.py` — generate the 4 action sets from `front.png`.

## Privacy

The pet's memory (intimacy, sleep profile, active hours) lives only in the local
`data/pet_memory.json` — never uploaded. If the online brain is enabled, only
"current time + activity + memory summary" is sent to Claude, not raw window
titles (activity guessing is coarse-grained and never reads titles aloud).
