from flask import Flask, request, render_template, send_from_directory, url_for
from flask_socketio import SocketIO
import os
import tempfile
from PIL import Image

from config import Config, CONVERTED_DIR, logger
from utils.image_processing import convert_svg_to_png, blend_frames, fade_frames, save_animation
from utils.file_utils import get_unique_filename, get_base64_data, allowed_file

app = Flask(__name__)
app.config.from_object(Config)
socketio = SocketIO(app, async_mode='eventlet')

@app.route('/')
def index():
    return render_template('index.html')


@app.route('/convert', methods=['POST'])
def convert():
    try:
        files = request.files.getlist("files")
        if not files:
            return "No files uploaded.", 400

        duration = int(request.form.get("duration", 100))
        smart_animation = request.form.get("smart_animation", "none")
        background_color = request.form.get("background_color", "rgba(255,255,255,1)")
        blend_amount = float(request.form.get("blend_amount", 0.5))
        fade_steps = int(request.form.get("fade_steps", 4))
        output_format = request.form.get("output_format", "webp")

        if background_color == "rgba(0,0,0,0)":
            background_color = None

        with tempfile.TemporaryDirectory() as temp_dir:
            # Process SVG files
            frames = process_svg_files(files, temp_dir, background_color)
            if not frames:
                return "Error processing SVG files.", 400

            # Apply animations
            frames = apply_animations(frames, smart_animation, blend_amount, fade_steps)

            # Save output file
            output_path = save_output_file(frames, output_format, duration)
            if not output_path:
                return "Error saving output file.", 500

            filename = os.path.basename(output_path)
            
            # For WebP/GIF, use base64 encoding
            return render_template(
                'result.html',
                filename=filename,
                media_type='image',
                base64_data=get_base64_data(output_path)
            )

    except Exception as e:
        logger.error(f"Conversion error: {str(e)}")
        return "An error occurred during conversion.", 500
    
@app.route('/download/<filename>')
def download(filename):
    try:
        return send_from_directory(
            CONVERTED_DIR,
            filename,
            as_attachment=True,
            download_name=filename
        )
    except Exception as e:
        logger.error(f"Download error: {str(e)}")
        return "File not found.", 404

def process_svg_files(files, temp_dir, background_color):
    """Process uploaded SVG files and convert to frames."""
    frames = []
    for index, file in enumerate(files):
        if file.filename.lower().endswith(".svg"):
            svg_path = os.path.join(temp_dir, file.filename)
            png_path = svg_path.replace(".svg", ".png")
            
            file.save(svg_path)
            if convert_svg_to_png(svg_path, png_path, background_color):
                frames.append(Image.open(png_path))

            # Emit progress update
            progress = int((index + 1) / len(files) * 20)
            socketio.emit("progress", {"progress": progress})
            socketio.sleep(0.0001)

    return frames

def apply_animations(frames, smart_animation, blend_amount, fade_steps):
    """Apply selected animation effects to frames."""
    if smart_animation == "blend":
        return blend_frames(frames, blend_amount)
    elif smart_animation == "fade":
        return fade_frames(frames, fade_steps)
    return frames

def save_output_file(frames, output_format, duration):
    """Save frames in the specified output format."""
    base_name = "animate"
    extension = f".{output_format}"
    output_path = get_unique_filename(CONVERTED_DIR, base_name, extension)

    if output_format in ["webp", "gif"]:
        if save_animation(frames, output_path, duration, output_format.upper()):
            return output_path
    return None

if __name__ == "__main__":
    socketio.run(app, debug=True, host="0.0.0.0", port=5001)