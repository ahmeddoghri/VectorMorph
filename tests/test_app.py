import pytest
from app import app
import io
import os

@pytest.fixture
def client():
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client

@pytest.fixture
def sample_svg():
    return """<?xml version="1.0" encoding="UTF-8"?>
    <svg width="100" height="100" xmlns="http://www.w3.org/2000/svg">
        <rect width="100" height="100" fill="blue"/>
    </svg>"""

def test_index_route(client):
    """Test the index route"""
    response = client.get('/')
    assert response.status_code == 200

def test_convert_route_no_files(client):
    """Test convert route with no files"""
    response = client.post('/convert')
    assert response.status_code == 400

def test_convert_route_with_file(client, sample_svg):
    """Test convert route with valid SVG file"""
    data = {
        'files': (io.BytesIO(sample_svg.encode()), 'test.svg'),
        'duration': '100',
        'smart_animation': 'none',
        'background_color': 'rgba(255,255,255,1)',
        'blend_amount': '0.5',
        'fade_steps': '4',
        'output_format': 'webp'
    }
    
    response = client.post(
        '/convert',
        data=data,
        content_type='multipart/form-data'
    )
    assert response.status_code == 200

def test_download_route_nonexistent(client):
    """Test download route with nonexistent file"""
    response = client.get('/download/nonexistent.webp')
    assert response.status_code == 404