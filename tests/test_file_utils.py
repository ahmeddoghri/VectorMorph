import os
import pytest
import tempfile
from utils.file_utils import get_unique_filename, get_base64_data, allowed_file

@pytest.fixture
def temp_dir():
    with tempfile.TemporaryDirectory() as tmpdirname:
        yield tmpdirname

def test_get_unique_filename(temp_dir):
    """Test unique filename generation"""
    # Test basic filename
    filename = get_unique_filename(temp_dir, "test", ".txt")
    assert filename == os.path.join(temp_dir, "test.txt")
    
    # Create the file and test counter increment
    with open(filename, 'w') as f:
        f.write('test')
    
    filename2 = get_unique_filename(temp_dir, "test", ".txt")
    assert filename2 == os.path.join(temp_dir, "test (1).txt")

def test_get_base64_data(temp_dir):
    """Test base64 conversion of file content"""
    test_content = b"Hello, World!"
    test_file = os.path.join(temp_dir, "test.txt")
    
    # Create test file
    with open(test_file, 'wb') as f:
        f.write(test_content)
    
    # Test valid file
    base64_data = get_base64_data(test_file)
    assert isinstance(base64_data, str)
    assert len(base64_data) > 0
    
    # Test invalid file
    invalid_base64 = get_base64_data(os.path.join(temp_dir, "nonexistent.txt"))
    assert invalid_base64 == ""

def test_allowed_file():
    """Test file extension validation"""
    allowed_extensions = {'txt', 'pdf'}
    
    assert allowed_file('test.txt', allowed_extensions) == True
    assert allowed_file('test.pdf', allowed_extensions) == True
    assert allowed_file('test.doc', allowed_extensions) == False
    assert allowed_file('test', allowed_extensions) == False