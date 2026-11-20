import json, textwrap, re, sys
sys.stdout.reconfigure(encoding="utf-8")
recs = json.load(open(r"E:\Proyecto X\research\api.json", encoding="utf-8"))
by = {}
for r in recs: by.setdefault(r["name"], r)
d = by["SetMediaTrackInfo_Value"]["desc"]
# print the D_VOL / D_PAN / I_SOLO / I_CUSTOMCOLOR fragments
for key in ["D_VOL", "D_PAN ", "I_SOLO", "I_CUSTOMCOLOR", "B_MUTE", "I_RECARM"]:
    i = d.find(key)
    print("...", d[i:i+220].replace("\n"," "), "\n")
print("LUA:", by["SetMediaTrackInfo_Value"]["lua"])
