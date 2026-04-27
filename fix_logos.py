import os
import glob

html_files = glob.glob('core/templates/core/**/*.html', recursive=True)
for filepath in html_files:
    with open(filepath, 'r') as f:
        content = f.read()
    
    if '<span class="text-xl font-bold text-gray-800">Система Казакова</span>' in content:
        content = content.replace(
            '<span class="text-xl font-bold text-gray-800">Система Казакова</span>',
            '<span class="text-xl font-extrabold text-gray-800 tracking-tight" style="font-family: \'Montserrat\', sans-serif;">Система Казакова</span>'
        )
        if 'fonts.googleapis.com' not in content:
            # We don't want to inject it repeatedly, but it's safe to add to <head> if it exists
            content = content.replace('</head>', '    <link href="https://fonts.googleapis.com/css2?family=Montserrat:wght@700;800&display=swap" rel="stylesheet">\n</head>')
        
        with open(filepath, 'w') as f:
            f.write(content)
            print(f"Updated {filepath}")

    if '<h1 class="text-3xl font-bold mb-1">Система Казакова</h1>' in content:
        content = content.replace(
            '<h1 class="text-3xl font-bold mb-1">Система Казакова</h1>',
            '<h1 class="text-3xl font-extrabold mb-1 tracking-tight" style="font-family: \'Montserrat\', sans-serif;">Система Казакова</h1>'
        )
        if 'fonts.googleapis.com' not in content:
            content = content.replace('</head>', '    <link href="https://fonts.googleapis.com/css2?family=Montserrat:wght@700;800&display=swap" rel="stylesheet">\n</head>')
        with open(filepath, 'w') as f:
            f.write(content)
            print(f"Updated {filepath}")

