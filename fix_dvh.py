import glob
import re

html_files = glob.glob('core/templates/core/**/*.html', recursive=True)

for filepath in html_files:
    with open(filepath, 'r') as f:
        content = f.read()

    modified = False

    # Replace class="... h-screen ..." with class="... h-[100dvh] ..."
    if 'h-screen' in content:
        content = content.replace('h-screen', 'h-[100dvh]')
        modified = True

    if modified:
        with open(filepath, 'w') as f:
            f.write(content)
        print(f"Updated {filepath}")

