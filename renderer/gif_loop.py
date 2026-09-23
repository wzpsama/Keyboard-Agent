"""Stable GIF encoding for animations rendered by the keyboard agent."""

from __future__ import annotations

from collections.abc import Sequence

from PIL import Image

_NO_DITHER = getattr(getattr(Image, "Dither", Image), "NONE", 0)


def save_loop_gif(frames: Sequence[Image.Image], path: str,
                  durations: int | Sequence[int]) -> None:
    """Save same-sized frames with one palette and no frame-to-frame dithering."""
    if not frames:
        raise ValueError("GIF needs at least one frame")
    size = frames[0].size
    if any(frame.size != size for frame in frames):
        raise ValueError("GIF frames must have one shared size")

    rgb_frames = [frame.convert("RGB") for frame in frames]
    palette_source = Image.new("RGB", (size[0], size[1] * len(rgb_frames)))
    for index, frame in enumerate(rgb_frames):
        palette_source.paste(frame, (0, index * size[1]))
    palette = palette_source.quantize(colors=256, dither=_NO_DITHER)
    paletted = [frame.quantize(palette=palette, dither=_NO_DITHER)
                for frame in rgb_frames]
    paletted[0].save(
        path,
        save_all=True,
        append_images=paletted[1:],
        duration=durations,
        loop=0,
        optimize=False,
        disposal=2,
    )
