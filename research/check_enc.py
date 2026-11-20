import io, json, sys
sys.stdout.reconfigure(encoding="utf-8")
p = r"E:\Proyecto X\research\out\results.txt"
data = open(p, "rb").read()
print("bytes:", len(data))
try:
    txt = data.decode("utf-8")
    print("utf8 decode OK")
except UnicodeDecodeError as e:
    print("utf8 decode FAIL:", e)
    txt = data.decode("cp1252", "replace")
for line in txt.splitlines():
    if "ENUM abs" in line or "ñand" in line or "nand" in line:
        print(repr(line))
# check leftover file
import os
print("leftover exists:", os.path.exists(r"E:\Proyecto X\research\out\io_test.txt.renamed"))
