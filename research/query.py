# -*- coding: utf-8 -*-
import json, sys, io

recs = json.load(open(r"E:\Proyecto X\research\api.json", encoding="utf-8"))
byname = {}
for r in recs:
    byname.setdefault(r["name"], r)

names = sys.argv[1:]
out = []
for n in names:
    r = byname.get(n)
    if not r:
        out.append("### %s : NOT FOUND IN C-API LIST" % n)
        continue
    out.append("### %s\nC: %s\nLUA: %s\nDESC: %s\n" % (n, r["c"], r["lua"], r["desc"]))
txt = "\n".join(out)
sys.stdout.reconfigure(encoding="utf-8")
print(txt)
