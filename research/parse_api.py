# -*- coding: utf-8 -*-
import json, re

src = r"E:\Proyecto X\research\reascripthelp.txt"
lines = open(src, encoding="utf-8").read().split("\n")

recs = []
cur = None
for ln in lines:
    m = re.match(r"^C: (.+?) ([A-Za-z_][A-Za-z0-9_]*)\((.*)\)\s*$", ln)
    if m:
        if cur:
            recs.append(cur)
        cur = {"ret_c": m.group(1), "name": m.group(2), "c": ln[3:], "lua": "", "python": "", "eel": "", "desc": []}
        continue
    if cur is None:
        continue
    if ln.startswith("Lua: "):
        cur["lua"] = ln[5:]
    elif ln.startswith("Python: "):
        cur["python"] = ln[8:]
    elif ln.startswith("EEL2: "):
        cur["eel"] = ln[6:]
    elif ln.strip() == "":
        pass
    else:
        cur["desc"].append(ln.strip())
if cur:
    recs.append(cur)

for r in recs:
    r["desc"] = " ".join(r["desc"])
    # trim trailing boilerplate about FX containers
    r["desc_short"] = re.split(r" FX indices can have 0x2000000| FX indices for tracks can have 0x1000000", r["desc"])[0].strip()

with open(r"E:\Proyecto X\research\api.json", "w", encoding="utf-8") as f:
    json.dump(recs, f, ensure_ascii=False, indent=1)

print("functions:", len(recs))

want = """defer atexit EnumerateFiles EnumerateSubdirectories InsertTrackAtIndex DeleteTrack GetSetMediaTrackInfo_String GetSetMediaTrackInfo SetMediaTrackInfo_Value GetMediaTrackInfo_Value SetTrackColor GetTrackColor CreateTrackSend SetTrackSendInfo_Value GetSetTrackSendInfo TrackFX_AddByName TrackFX_SetParam TrackFX_SetParamNormalized TrackFX_GetParamNormalized TrackFX_GetCount TrackFX_GetFXName TrackFX_SetEnabled TrackFX_GetEnabled TrackFX_CopyToTrack TrackFX_Delete TrackFX_GetParam TrackFX_GetFormattedParamValue GetPlayState GetPlayPosition GetCursorPosition GetSet_LoopTimeRange Master_GetTempo SetCurrentBPM GetSetProjectInfo GetSetProjectInfo_String AddProjectMarker2 DeleteProjectMarker Undo_BeginBlock Undo_EndBlock Undo_OnStateChange Undo_EndBlock2 PreventUIRefresh GetResourcePath GetProjectPath GetNumTracks CountTracks GetTrack Main_OnCommand kbd_EnumerateActions kbd_getTextFromCmd SetExtState GetExtState GetSetRepeat SetEditCurPos UpdateArrange Track_GetPeakInfo GetMasterPeak""".split()

byname = {}
for r in recs:
    byname.setdefault(r["name"], []).append(r)

for w in want:
    rs = byname.get(w)
    if not rs:
        print("\n### MISSING:", w)
        continue
    r = rs[0]
    print("\n### %s" % w)
    print("C   :", r["c"])
    print("LUA :", r["lua"])
    print("DESC:", r["desc_short"][:600])

