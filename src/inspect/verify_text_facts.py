"""Re-derive the descriptive facts quoted in the manuscript text from the evidence ledgers.

Usage: python -E -P verify_text_facts.py <R10 dir>
Every count printed here is quoted in the text (Sections 1 and 6.1); aggregate results are macros in numbers.tex.
"""
import copy
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

R10 = Path(sys.argv[1])
sys.path.insert(0, str(R10 / "src"))
from bimev.engine import build_clusters  # noqa: E402

LED = {}
for sub in ("dev", "heldout"):
    for lf in sorted((R10 / "outputs" / sub / "ledgers").glob("ledger_*.json")):
        LED[lf.stem[len("ledger_"):]] = json.loads(lf.read_text(encoding="utf-8"))
HELD = ["fantasy_hotel_1", "fantasy_hotel_2", "fantasy_office_building_2", "fantasy_office_building_3",
        "fantasy_residential_building_1", "hitos", "molio", "sixty5", "west_riverside_hospital"]


def num_sources(g, pattern):
    return [s for s in g["sources"] if s["kind"] == "num" and re.search(pattern, s["label"], re.I)]


print("1. Doors whose OverallWidth is 890 mm and whose explicit clear-passage properties state 800 mm")
for p, L in LED.items():
    n = 0
    for g in L["groups"].values():
        if g["family"] != "door":
            continue
        ow = [s for s in num_sources(g, r"OverallWidth") if s.get("value_mm") and abs(s["value_mm"] - 890) < 0.5]
        cl = [s for s in g["sources"] if s.get("note") in ("CLEAR", "CLEAR_ACTIVE") and s.get("value_mm")
              and abs(s["value_mm"] - 800) < 0.5]
        if ow and len(cl) >= 2:
            n += g["multiplicity"]
    if n:
        print(f"   {p}: {n} doors")

print("2. Railings whose Pset_RailingCommon.Height is 1219.2 mm (four feet), per model")
for p in HELD:
    L = LED[p]
    tot = sum(g["multiplicity"] for g in L["groups"].values() if g["family"] == "railing")
    n = sum(g["multiplicity"] for g in L["groups"].values() if g["family"] == "railing" and any(
        s.get("value_mm") and abs(s["value_mm"] - 1219.2) < 0.05 for s in num_sources(g, r"Pset_RailingCommon\.Height")))
    if n:
        print(f"   {p}: {n} of {tot} railings")

print("3. Office model: railing-type height parameter next to the 1219.2 mm property")
for g in LED["fantasy_office_building_2"]["groups"].values():
    if g["family"] == "railing":
        own = [round(s["value_mm"]) for s in num_sources(g, r"Railing Height") if s.get("value_mm")]
        print(f"   {g['names'][0][:50]} x{g['multiplicity']}: own height parameter {own}")

print("4. Hospital railings by type name")
c = Counter()
for g in LED["west_riverside_hospital"]["groups"].values():
    if g["family"] == "railing":
        nm = g["names"][0]
        key = "named 1100mm" if "1100mm" in nm else ("named 42 in" if re.search(r"42\s*[\"”″]", nm) else "other")
        c[key] += g["multiplicity"]
print("  ", dict(c))

print("5. Spaces whose clear and finish ceiling heights are 1000 mm")
for p in HELD:
    L = LED[p]
    tot = sum(g["multiplicity"] for g in L["groups"].values() if g["family"] == "space")
    n = sum(g["multiplicity"] for g in L["groups"].values() if g["family"] == "space" and any(
        s.get("note") == "CLEAR" and s.get("value_mm") and abs(s["value_mm"] - 1000) < 0.5 for s in g["sources"]))
    if n:
        print(f"   {p}: {n} of {tot} spaces")

print("6. Stair checks with a 304.8 mm placeholder (suspected default)")
for p in HELD:
    n = sum(g["multiplicity"] for g in LED[p]["groups"].values() if g["family"] == "stair" and any(
        s.get("suspect") and s.get("value_mm") and abs(s["value_mm"] - 304.8) < 0.05 for s in g["sources"]))
    if n:
        print(f"   {p}: {n} checks")

print("7. Masonry-opening values (mm -> doors) and the other width sources of the 760 mm doors")
for p, L in LED.items():
    c, other = Counter(), Counter()
    for g in L["groups"].values():
        mo = [s for s in num_sources(g, r"Maueröffnungsmaß") if s.get("value_mm") is not None]
        for s in mo:
            c[round(s["value_mm"])] += g["multiplicity"]
            if round(s["value_mm"]) == 760:
                for t in num_sources(g, r"OverallWidth|Breite|Width"):
                    if t is not s and t.get("value_mm"):
                        other[round(t["value_mm"])] += g["multiplicity"]
    if c:
        print(f"   {p}: {dict(c.most_common(6))}; other width values on the 760 mm doors: {dict(other.most_common(4))}")

print("8. 'Nominal Leaf Width Side 1' sources and the effect of removing them (Molio)")
L = LED["molio"]
L2 = copy.deepcopy(L)
removed = Counter()
for g in L2["groups"].values():
    keep = [s for s in g["sources"] if "Side 1" not in s["label"]]
    if len(keep) != len(g["sources"]):
        removed["doors"] += g["multiplicity"]
    g["sources"] = keep
print("   doors carrying the source:", removed["doors"])
for rb in ("US", "DE_DOOR"):
    a, b = build_clusters(L, "full", rb), build_clusters(L2, "full", rb)
    diff = sum(gm.mult for cid, cm in a.items() for gm in cm.groups
               if gm.family == "door" and cm.status(gm.gid)[0] != b[cid].status(gm.gid)[0])
    print(f"   {rb}: door checks whose status changes: {diff}")

print("9. Development flights whose risers exceed the calculation rule of their stair type")
for p in ("city_house_munich", "duplex", "fantasy_office_building_1", "wbdg_office"):
    for g in LED[p]["groups"].values():
        if g["family"] != "stair" or "riser" not in g.get("cluster", "") and "riser" not in str(g.get("quantity")):
            continue
        rule = [s for s in g["sources"] if s.get("note") == "INTENT" and s.get("value_mm")]
        vals = [round(s["value_mm"], 1) for s in g["sources"] if s["kind"] == "num" and s.get("note") != "INTENT"
                and s.get("value_mm") and not str(s.get("sid", "")).startswith("geom")]
        if rule and vals and min(vals) > max(s["value_mm"] for s in rule) + 0.5:
            print(f"   {p} {g['names'][0][:40]}: riser values {vals} > rule {[round(s['value_mm']) for s in rule]}")
