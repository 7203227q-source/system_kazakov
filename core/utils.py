import os
import uuid
import requests
import imghdr
import gzip
from urllib.parse import urlparse, quote
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
        img_url = img.get('src') or img.get('data-src') or img.get('data-original')
        
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

        use_proxy = False
        try:
            p = urlparse(img_url)
            use_proxy = p.scheme in ('http', 'https') and p.netloc and p.netloc.endswith('sdamgia.ru')
        except Exception:
            use_proxy = False

        if use_proxy:
            img['src'] = f"/proxy-image/?url={quote(img_url, safe='')}"
        else:
            img['src'] = img_url
            
        try:
            origin = (base_url or 'https://math-ege.sdamgia.ru').rstrip('/')
            headers = {
                'User-Agent': 'Mozilla/5.0',
                'Accept': 'image/avif,image/webp,image/apng,image/*,*/*;q=0.8',
                'Referer': origin + '/',
            }
            response = requests.get(img_url, headers=headers, timeout=15)
            if response.status_code == 200 and response.content:
                raw = response.content
                if raw[:2] == b'\x1f\x8b':
                    try:
                        raw = gzip.decompress(raw)
                    except Exception:
                        pass

                content_type = (response.headers.get('Content-Type') or '').lower()
                if 'text/html' in content_type or raw.lstrip().startswith(b'<!doctype html') or raw.lstrip().startswith(b'<html'):
                    continue
                if content_type and not content_type.startswith('image/') and b'<svg' not in raw[:1024]:
                    continue
                # Always determine extension from the actual downloaded content
                ext = get_extension_from_content(raw)
                
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
                saved_path = default_storage.save(filename, ContentFile(raw))
                
                # Update img src
                img['src'] = f"/media/{saved_path}"
                if img.has_attr('data-src'):
                    del img['data-src']
                if img.has_attr('data-original'):
                    del img['data-original']
        except Exception as e:
            print(f"Failed to download image {img_url}: {e}")
            
    return str(soup)
