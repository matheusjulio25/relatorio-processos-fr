#!/usr/bin/env python3
"""Lista os .txt (VOTO/EMENTA, e SENTENCA p/ derrotas) de uma fatia do manifest.
Uso: python3 bin/analise_files.py <TEMA> <wins|losses> <from> <to>"""
import json, sys
theme, role, a, b = sys.argv[1], sys.argv[2], int(sys.argv[3]), int(sys.argv[4])
m = json.load(open("mapas/_analise/manifest.json", encoding="utf-8"))
for c in m.get(theme, {}).get(role, [])[a:b]:
    for f in c.get("files", []):
        bn = f.lower()
        if "_voto" in bn or "_ementa" in bn or (role == "losses" and "_sentenca" in bn):
            print(f)
