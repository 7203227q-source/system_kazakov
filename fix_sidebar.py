import os

filepath = 'core/templates/core/includes/_tutor_sidebar.html'
with open(filepath, 'r') as f:
    content = f.read()

# Fix CSS
content = content.replace(
    '<aside class="w-64 bg-white border-r border-gray-200 flex flex-col shrink-0">',
    '<aside class="w-64 bg-white border-r border-gray-200 flex flex-col shrink-0 h-full overflow-hidden">'
)
content = content.replace(
    '<nav class="flex-1 px-4 py-6 space-y-2 overflow-y-auto">',
    '<nav class="flex-1 px-4 py-6 space-y-2 overflow-y-auto min-h-0">'
)

# Fix Logo Font
# We will inject a Google font for the logo
font_link = '<link href="https://fonts.googleapis.com/css2?family=Montserrat:wght@700;800&display=swap" rel="stylesheet">\n<style>.logo-font { font-family: "Montserrat", sans-serif; letter-spacing: -0.5px; }</style>'
content = font_link + '\n' + content
content = content.replace(
    '<span class="text-xl font-bold text-gray-800">Система Казакова</span>',
    '<span class="text-xl font-extrabold text-gray-800 logo-font">Система Казакова</span>'
)

with open(filepath, 'w') as f:
    f.write(content)

print("Sidebar fixed.")
