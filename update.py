import urllib.request
print("Trying to reach...")
try:
    req = urllib.request.urlopen("https://kazakov-system.ru/apply-migrations/")
    print(req.read().decode('utf-8')[:200])
except Exception as e:
    print("Error:", e)
