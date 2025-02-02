import pytest
from PIL import Image
import os
import tempfile
from utils.image_processing import convert_svg_to_png, blend_frames, fade_frames, save_animation

@pytest.fixture
def sample_svg():
    return """<?xml version="1.0" encoding="UTF-8"?>
    <svg width="100" height="100" xmlns="http://www.w3.org/2000/svg">
        <rect width="100" height="100" fill="blue"/>
    </svg>"""

@pytest.fixture
def test_frames():
    """Create test frames for animation testing"""
    frames = []
    for color in [(255, 0, 0), (0, 255, 0)]:  # Red and Green frames
        img = Image.new('RGB', (100, 100), color)
        frames.append(img)
    return frames

def test_convert_svg_to_png(sample_svg, tmp_path):
    """Test SVG to PNG conversion"""
    svg_file = tmp_path / "test.svg"
    png_file = tmp_path / "test.png"
    
    # Write sample SVG
    svg_file.write_text(sample_svg)
    
    # Test conversion
    result = convert_svg_to_png(str(svg_file), str(png_file))
    assert result == True
    assert png_file.exists()
    
    # Test with background color
    result_bg = convert_svg_to_png(str(svg_file), str(png_file), background_color="white")
    assert result_bg == True

def test_blend_frames(test_frames):
    """Test frame blending"""
    blended = blend_frames(test_frames, blend_amount=0.5)
    assert len(blended) == 3  # Original frames + 1 blended frame
    assert isinstance(blended[0], Image.Image)

def test_fade_frames(test_frames):
    """Test frame fading"""
    faded = fade_frames(test_frames, fade_steps=2)
    assert len(faded) == 4  # 2 original + 2 fade steps + 1 final
    assert isinstance(faded[0], Image.Image)

def test_save_animation(test_frames, tmp_path):
    """Test saving animation in different formats"""
    # Test WebP
    webp_path = tmp_path / "test.webp"
    assert save_animation(test_frames, str(webp_path), duration=100, format="WEBP")
    assert webp_path.exists()
    
    # Test GIF
    gif_path = tmp_path / "test.gif"
    assert save_animation(test_frames, str(gif_path), duration=100, format="GIF")
    assert gif_path.exists()