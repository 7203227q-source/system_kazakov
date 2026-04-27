import urllib.request
try:
    req = urllib.request.urlopen("https://kazakov-system.ru/")
    print("Status:", req.status)
except Exception as e:
    print("Error:", e)
