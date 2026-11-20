import re
data = open(r"C:\Program Files\REAPER (x64)\reaper.exe","rb").read()
strs = re.findall(rb"[ -~]{4,}", data)
pats = [b"cfgfile", b"portable", b"renderproject", b"noaudio", b"nonewinst", b"saveas", b"newinst", b"recursive"]
seen = set()
for s in strs:
    low = s.lower()
    for p in pats:
        if p in low and s not in seen:
            seen.add(s)
            print(s.decode("ascii", "replace")[:200])
            break
