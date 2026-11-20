import os, sys
sys.stdout.reconfigure(encoding="utf-8")
d = r"E:\Proyecto X\research\out"
for n in os.listdir(d):
    if n.startswith("uni_"):
        print("ON DISK:", repr(n))
        print("matches expected:", n == "uni_ñandú_áéíóú_测试.txt")
