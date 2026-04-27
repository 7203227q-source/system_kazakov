import os
import glob
import re

html_files = glob.glob('core/templates/core/**/*.html', recursive=True)

for filepath in html_files:
    with open(filepath, 'r') as f:
        content = f.read()

    modified = False

    # Remove the <link> to Montserrat
    content, n = re.subn(r'<link href="https://fonts\.googleapis\.com/css2\?family=Montserrat:[^"]+" rel="stylesheet">\n?', '', content)
    if n > 0: modified = True

    # Remove the inline <style> block for Montserrat
    content, n = re.subn(r'<style>\.logo-font\s*\{[^}]+\}\s*</style>\n?', '', content)
    if n > 0: modified = True

    # Restore logo class in sidebar
    content, n = re.subn(
        r'<span class="text-xl font-extrabold text-gray-800 logo-font">Система Казакова</span>',
        '<span class="text-xl font-bold text-gray-800">Система Казакова</span>',
        content
    )
    if n > 0: modified = True

    # Restore logo class in headers
    content, n = re.subn(
        r'<span class="text-xl font-extrabold text-gray-800 tracking-tight" style="font-family: \'Montserrat\', sans-serif;">Система Казакова</span>',
        '<span class="text-xl font-bold text-gray-800">Система Казакова</span>',
        content
    )
    if n > 0: modified = True
    
    # Restore logo class in login/register
    content, n = re.subn(
        r'<h1 class="text-3xl font-extrabold mb-1 tracking-tight" style="font-family: \'Montserrat\', sans-serif;">Система Казакова</h1>',
        '<h1 class="text-3xl font-bold mb-1">Система Казакова</h1>',
        content
    )
    if n > 0: modified = True

    if modified:
        with open(filepath, 'w') as f:
            f.write(content)
        print(f"Updated {filepath}")

