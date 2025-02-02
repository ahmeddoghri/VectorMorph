import os
import pytest
import logging
from config import BASE_DIR, STATIC_DIR, CONVERTED_DIR, LOGS_DIR, Config, logger

def test_directory_structure():
    """Test if all required directories are created"""
    assert os.path.exists(STATIC_DIR)
    assert os.path.exists(CONVERTED_DIR)
    assert os.path.exists(LOGS_DIR)

def test_logger_configuration():
    """Test logger configuration"""
    assert isinstance(logger, logging.Logger)
    assert logger.level <= logging.DEBUG
    assert len(logger.handlers) > 0
    
def test_config_class():
    """Test Config class attributes"""
    assert hasattr(Config, 'SECRET_KEY')
    assert hasattr(Config, 'MAX_CONTENT_LENGTH')
    assert hasattr(Config, 'ALLOWED_EXTENSIONS')
    assert Config.MAX_CONTENT_LENGTH == 16 * 1024 * 1024
    assert Config.ALLOWED_EXTENSIONS == {'svg'}