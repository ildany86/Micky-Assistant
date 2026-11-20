"""Vuelca la descripcion completa (sin truncar) de una funcion a stdout."""
import json
import sys

API = {f["name"]: f for f in json.load(open(r"E:\Proyecto X\research\api.json", encoding="utf-8"))}

for name in sys.argv[1:]:
    f = API.get(name)
    if not f:
        print(f"--- {name}: NO EXISTE")
        continue
    print(f"===== {name}")
    print(f"LUA: {f['lua']}")
    print(f.get("desc") or "")
    print()
