"""Build README status previews with the production renderer; no device I/O."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from agent.coding_status import CodingStatus, display_state  # noqa: E402
from renderer.gif_loop import save_loop_gif  # noqa: E402
from renderer.render import get_font, render_frame  # noqa: E402
from renderer.vega import (  # noqa: E402
    AMBIENT_DURATIONS_MS,
    action_durations,
    mood_to_action,
)

BG = "#0c1120"
CARD = "#151d30"
TEXT = "#f0f4ff"
MUTED = "#a9b7cc"
BORDER = "#2a3952"
STATES = (
    ("working", "Working", "#67d9ef"),
    ("waiting", "Waiting for you", "#f5c575"),
    ("completed", "Turn complete", "#91e5bb"),
)


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    """Use a local Latin font for captions; the renderer chooses its CJK font."""
    try:
        return ImageFont.truetype(
            "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf", size
        )
    except OSError:
        return get_font(size)


def status_frames(name: str) -> tuple[list[Image.Image], list[int]]:
    """Match win_agent's state mapping and frame timing without importing it."""
    status = CodingStatus(name, 1, 0.0, 900.0)
    base = display_state(status)
    base.update(character="vega", clock="12:34")
    motion = mood_to_action(str(base["mood"]))
    durations = list(action_durations(motion) if motion else AMBIENT_DURATIONS_MS)
    frames = []
    elapsed_ms = 0
    for index, duration in enumerate(durations):
        state = dict(base, t=elapsed_ms / 1000, motion=motion)
        if not motion:
            state.update(
                ambient=True,
                ambient_phase=index / len(durations),
                blink=index == len(durations) // 2,
            )
        frames.append(render_frame(state).convert("RGB"))
        elapsed_ms += duration
    return frames, durations


def poster(scenes: dict[str, tuple[list[Image.Image], list[int]]]) -> Image.Image:
    """Keep all three 320x480 screen frames at their native pixel dimensions."""
    image = Image.new("RGB", (1120, 840), BG)
    draw = ImageDraw.Draw(image)
    draw.text((32, 25), "KEYBOARD-AGENT / CODING COMPANION", font=font(14, True),
              fill=STATES[0][2])
    draw.text((32, 58), "Your coding agent, on your keyboard.", font=font(36, True),
              fill=TEXT)
    draw.text((32, 113), "Start a task. See when it needs you. Notice when the turn ends.",
              font=font(18), fill=MUTED)
    badges = (
        (32, 443, "Codex: local + remote verified", STATES[2][2]),
        (459, 1088, "Claude Code: hook setup / validation pending", STATES[1][2]),
    )
    for left, right, label, color in badges:
        draw.rounded_rectangle((left, 157, right, 193), radius=12,
                               fill=CARD, outline=BORDER)
        draw.text((left + 14, 165), label, font=font(15), fill=color)
    for index, (name, title, color) in enumerate(STATES):
        left = 32 + index * 360
        draw.rounded_rectangle((left, 220, left + 336, 770), radius=16,
                               fill=CARD, outline=BORDER)
        draw.ellipse((left + 16, 239, left + 24, 247), fill=color)
        draw.text((left + 36, 230), title, font=font(21, True), fill=TEXT)
        image.paste(scenes[name][0][0], (left + 8, 276))
        if index < 2:
            tip = left + 350
            draw.line([(tip - 5, 484), (tip + 2, 492), (tip - 5, 500)],
                      fill=MUTED, width=2)
    draw.text((32, 795), "Actual 320 x 480 renderer output. Default pet dialogue is Chinese.",
              font=font(15), fill=MUTED)
    return image


def demo_frame(screen: Image.Image, title: str, color: str) -> Image.Image:
    image = Image.new("RGB", (384, 650), BG)
    draw = ImageDraw.Draw(image)
    draw.text((32, 18), "VEGA / CODING COMPANION", font=font(13, True), fill=MUTED)
    draw.ellipse((32, 56, 42, 66), fill=color)
    draw.text((54, 43), title, font=font(23, True), fill=TEXT)
    draw.rounded_rectangle((25, 89, 358, 584), radius=12, fill=CARD, outline=BORDER)
    image.paste(screen, (32, 96))
    draw.text((32, 602), "Renderer demo / example sequence", font=font(14), fill=MUTED)
    draw.text((32, 624), "Display timing is illustrative.", font=font(13), fill=MUTED)
    return image


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=PROJECT_ROOT / "docs")
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    scenes = {name: status_frames(name) for name, _, _ in STATES}
    poster_path = args.output_dir / "coding-status.png"
    poster(scenes).save(poster_path)

    frames = []
    durations = []
    for name, title, color in STATES:
        scene_frames, scene_durations = scenes[name]
        # Repeat the short bounce so its completion scene remains legible.
        repeats = 5 if name == "completed" else 1
        for _ in range(repeats):
            frames.extend(demo_frame(frame, title, color) for frame in scene_frames)
            durations.extend(scene_durations)
    gif_path = args.output_dir / "coding-status.gif"
    save_loop_gif(frames, str(gif_path), durations)
    print(f"Built {poster_path.name} and {gif_path.name} ({sum(durations)} ms demo)")


if __name__ == "__main__":
    main()
