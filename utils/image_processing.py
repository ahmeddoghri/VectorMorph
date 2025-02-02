from PIL import Image, ImageChops
import cairosvg
import os
from config import logger

def convert_svg_to_png(svg_file, png_file, background_color=None):
    """Convert SVG file to PNG using CairoSVG."""
    try:
        cairosvg.svg2png(
            url=svg_file,
            write_to=png_file,
            background_color=background_color
        )
        return True
    except Exception as e:
        logger.error(f"Error converting SVG to PNG: {str(e)}")
        return False

def blend_frames(frames, blend_amount=0.5):
    """Blend each frame with the next with a user-defined blend amount."""
    new_frames = []
    try:
        for i in range(len(frames) - 1):
            blended = ImageChops.blend(frames[i], frames[i + 1], alpha=blend_amount)
            new_frames.append(frames[i])
            new_frames.append(blended)
        new_frames.append(frames[-1])
        return new_frames
    except Exception as e:
        logger.error(f"Error blending frames: {str(e)}")
        return frames

def fade_frames(frames, fade_steps=4):
    """Fade transition between consecutive frames."""
    fade_frames = []
    try:
        for i in range(len(frames) - 1):
            fade_frames.append(frames[i])
            for j in range(1, fade_steps + 1):
                alpha = j / (fade_steps + 1)
                fade = ImageChops.blend(frames[i], frames[i + 1], alpha=alpha)
                fade_frames.append(fade)
        fade_frames.append(frames[-1])
        return fade_frames
    except Exception as e:
        logger.error(f"Error creating fade frames: {str(e)}")
        return frames

def save_animation(frames, output_path, duration, format="WEBP"):
    """Save frames as an animated image file."""
    try:
        frames[0].save(
            output_path,
            format=format,
            save_all=True,
            append_images=frames[1:],
            duration=duration,
            loop=0,
        )
        return True
    except Exception as e:
        logger.error(f"Error saving animation: {str(e)}")
        return False