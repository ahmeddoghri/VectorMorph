import os
import base64
from config import logger

def get_unique_filename(directory, base_name, extension):
    """Generate a unique filename in the specified directory."""
    counter = 0
    while True:
        if counter == 0:
            unique_name = f"{base_name}{extension}"
        else:
            unique_name = f"{base_name} ({counter}){extension}"
        full_path = os.path.join(directory, unique_name)
        if not os.path.exists(full_path):
            return full_path
        counter += 1

def get_base64_data(filepath):
    """Convert file content to base64 string."""
    try:
        with open(filepath, "rb") as file:
            return base64.b64encode(file.read()).decode('utf-8')
    except Exception as e:
        logger.error(f"Error converting file to base64: {str(e)}")
        return ""

def allowed_file(filename, allowed_extensions):
    """Check if file has an allowed extension."""
    return '.' in filename and \
        filename.rsplit('.', 1)[1].lower() in allowed_extensions