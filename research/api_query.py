"""Consulta rapida del API de ReaScript parseado en api.json.

Uso: python api_query.py NombreFuncion [NombreFuncion ...]
"""
import json
import sys

API_PATH = r"E:\Proyecto X\research\api.json"

api = {f["name"]: f for f in json.load(open(API_PATH, encoding="utf-8"))}

for name in sys.argv[1:]:
    f = api.get(name)
    if not f:
        print(f"--- {name}: NO EXISTE")
        continue
    print(f"--- {name}")
    print(f"  LUA : {f['lua']}")
    desc = (f.get("desc") or "").strip()
    if desc:
        print(f"  DESC: {desc[:900]}")
