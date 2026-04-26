import os
import uuid
import requests
from urllib.parse import urlparse
from bs4 import BeautifulSoup
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage

def download_and_replace_images(html_content, task_fipi_id, theme):
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
            # If the CSV contains relative paths, assume they are from sdamgia.ru
            img_url = 'https://math-ege.sdamgia.ru' + img_url
            
        try:
            headers = {'User-Agent': 'Mozilla/5.0'}
            response = requests.get(img_url, headers=headers, timeout=10)
            if response.status_code == 200:
                # Extract extension from URL or use .jpg as default
                parsed_url = urlparse(img_url)
                ext = os.path.splitext(parsed_url.path)[1]
                if not ext:
                    ext = '.jpg'
                
                # Generate unique filename
                filename = f"tasks/{task_fipi_id}_{theme}_{idx}{ext}"
                
                # Save file
                saved_path = default_storage.save(filename, ContentFile(response.content))
                
                # Update img src
                img['src'] = f"/media/{saved_path}"
        except Exception as e:
            print(f"Failed to download image {img_url}: {e}")
            
    return str(soup)
