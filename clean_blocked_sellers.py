#!/usr/bin/env python3
"""
Jednorázový skript: odstraní záznamy blokovaných prodejců z existujících JSON souborů
a opraví počty v index.json.
"""

import json
import os
import glob

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
BLOCKED_SELLERS = ["davo car", "aaa auto"]

files = sorted(glob.glob(os.path.join(DATA_DIR, "cars_*.json")))

for path in files:
    with open(path, "r", encoding="utf-8") as f:
        cars = json.load(f)

    before = len(cars)
    cars = [c for c in cars if not any(b in c.get("details", "").lower() for b in BLOCKED_SELLERS)]
    removed = before - len(cars)

    if removed:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(cars, f, ensure_ascii=False, indent=2)
        print(f"{os.path.basename(path)}: odstraněno {removed} aut")
    else:
        print(f"{os.path.basename(path)}: nic k odstranění")

# Oprav počty v index.json
index_path = os.path.join(DATA_DIR, "index.json")
if os.path.exists(index_path):
    with open(index_path, "r", encoding="utf-8") as f:
        index = json.load(f)
    for day in index["days"]:
        cars_path = os.path.join(DATA_DIR, f"cars_{day['key']}.json")
        if os.path.exists(cars_path):
            with open(cars_path, "r", encoding="utf-8") as f:
                day["count"] = len(json.load(f))
    with open(index_path, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=2)
    print("index.json: počty opraveny")

print("Hotovo.")
