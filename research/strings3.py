import re
data = open(r"C:\Program Files\REAPER (x64)\reaper.exe","rb").read()
strs = [s.decode("ascii","replace") for s in re.findall(rb"[ -~]{3,}", data)]
for i,s in enumerate(strs):
    low = s.lower()
    if "nonewinst" in low or "usage" in low or ("reaper.exe" in low and "[" in s):
        print("---- idx", i)
        for j in range(max(0,i-6), min(len(strs), i+8)):
            print("   ", repr(strs[j])[:300])
