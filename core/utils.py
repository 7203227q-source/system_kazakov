import os
import uuid
import requests
import imghdr
from urllib.parse import urlparse
from bs4 import BeautifulSoup
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage

def get_extension_from_content(content):
    """
    Tries to detect image extension from raw bytes.
    Returns .svg for SVG content, or uses imghdr for others.
    Defaults to .jpg if unknown.
    """
    # Quick check for SVG
    if b'<svg' in content[:1024]:
        return '.svg'
        
    ext = imghdr.what(None, h=content)
    if ext:
        if ext == 'jpeg':
            return '.jpg'
        return f".{ext}"
    return '.jpg'

def download_and_replace_images(html_content, task_fipi_id, theme, base_url=None):
    """
    Parses HTML content, finds all <img> tags, downloads the remote images,
    saves them locally, and updates the src attributes.
    """
    if not html_content:
        return html_content

    soup = BeautifulSoup(html_content, 'html.parser')
    images = soup.find_all('img')
    
    if not images:
        return html_content

    for idx, img in enumerate(images):
        img_url = img.get('src')
        
        # Clean up the URL from extra quotes that might come from CSV escaping
        if img_url:
            img_url = img_url.strip('"\'')
            
        if not img_url or img_url.startswith('data:') or img_url.startswith('/media/'):
            continue

        # Handle relative URLs if any
        if img_url.startswith('//'):
            img_url = 'https:' + img_url
        elif img_url.startswith('/'):
            # If the HTML contains relative paths, assume they are from sdamgia.ru
            origin = (base_url or 'https://math-ege.sdamgia.ru').rstrip('/')
            img_url = origin + img_url
            
        try:
            headers = {'User-Agent': 'Mozilla/5.0'}
            response = requests.get(img_url, headers=headers, timeout=10)
            if response.status_code == 200:
                # Always determine extension from the actual downloaded content
                ext = get_extension_from_content(response.content)
                
                # Generate unique filename (we overwrite to avoid duplicating on re-imports)
                filename = f"tasks/{task_fipi_id}_{theme}_{idx}{ext}"
                
                # Check if file exists with this specific extension, if so delete it
                if default_storage.exists(filename):
                    default_storage.delete(filename)
                
                # Also delete potential old versions with different extensions
                for old_ext in ['.jpg', '.png', '.gif', '.svg']:
                    if old_ext != ext:
                        old_filename = f"tasks/{task_fipi_id}_{theme}_{idx}{old_ext}"
                        if default_storage.exists(old_filename):
                            default_storage.delete(old_filename)
                
                # Save file
                saved_path = default_storage.save(filename, ContentFile(response.content))
                
                # Update img src
                img['src'] = f"/media/{saved_path}"
        except Exception as e:
            print(f"Failed to download image {img_url}: {e}")
            
    return str(soup)
