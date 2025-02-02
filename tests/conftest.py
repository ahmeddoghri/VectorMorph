import pytest
import os
import tempfile
import shutil
from config import CONVERTED_DIR

@pytest.fixture(autouse=True)
def setup_and_cleanup():
    """Setup and cleanup for all tests"""
    # Setup: Create temporary directories if needed
    os.makedirs(CONVERTED_DIR, exist_ok=True)
    
    yield
    
    # Cleanup: Remove all files in CONVERTED_DIR
    for filename in os.listdir(CONVERTED_DIR):
        file_path = os.path.join(CONVERTED_DIR, filename)
        try:
            if os.path.isfile(file_path):
                os.unlink(file_path)
        except Exception as e:
            print(f'Error deleting {file_path}: {e}')