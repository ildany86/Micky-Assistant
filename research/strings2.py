import re
data = open(r"C:\Program Files\REAPER (x64)\reaper.exe","rb").read()
strs = re.findall(rb"[ -~]{3,}", data)
for s in strs:
    low = s.lower()
    if b"portab" in low or b"reaper.ini" in low or b"cfgfile" in low or b"importconfig" in low:
        print(repr(s.decode("ascii","replace"))[:220])
