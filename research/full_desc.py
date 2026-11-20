import json, textwrap, sys
recs = json.load(open(r"E:\Proyecto X\research\api.json", encoding="utf-8"))
byname = {}
for r in recs:
    byname.setdefault(r["name"], r)
for n in ["GetSetProjectInfo", "GetSetProjectInfo_String"]:
    r = byname[n]
    print("### " + n)
    print("LUA: " + r["lua"])
    print(textwrap.fill(r["desc"], 160))
    print()
