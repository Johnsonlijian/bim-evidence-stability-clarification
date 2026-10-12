"""Characterise the evidence behind held-out E1 conclusions per family (full level, US).

Usage: python -E -P family_sources.py <R10 dir> <family> [n_examples]
Prints, per model: element checks, stable share, share of checks whose groups carry geometry sources (weight 2),
explicit sources, and the most common source ids; then a few example groups with their sources.
"""
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

R10 = Path(sys.argv[1])
fam = sys.argv[2]
nex = int(sys.argv[3]) if len(sys.argv) > 3 else 3
rows = [json.loads(l) for l in open(R10 / "outputs/heldout/e1/e1_audit_rows.jsonl", encoding="utf-8") if l.strip()]
rows = [r for r in rows if r["family"] == fam and r["level"] == "full" and r["rulebook"] == "US"]
status = {r["group"]: r for r in rows}
bymodel = defaultdict(list)
for r in rows:
    bymodel[r["project"]].append(r)
for p, rs in bymodel.items():
    L = json.loads((R10 / f"outputs/heldout/ledgers/ledger_{p}.json").read_text(encoding="utf-8"))
    n = sum(r["mult"] for r in rs)
    st = sum(r["mult"] for r in rs if r["status"].startswith("STABLE"))
    sid_counter = Counter()
    geo = 0
    kinds = Counter()
    for r in rs:
        g = L["groups"].get(r["group"]) or {}
        srcs = g.get("sources") or g.get("numeric") or []
        if isinstance(srcs, dict):
            srcs = list(srcs.values())
        has_geo = any(float(s.get("weight", 1)) == 2.0 for s in srcs if isinstance(s, dict))
        geo += r["mult"] if has_geo else 0
        for s in srcs:
            if isinstance(s, dict):
                sid = str(s.get("sid", "?"))
                sid_counter[sid.split(":")[0] + ":" + (s.get("note") or "")] += r["mult"]
        kinds[(r["status"], tuple(sorted(r.get("fault_types") or [])))] += r["mult"]
    print(f"{p}: checks {n}, stable {st} ({100*st/n:.1f}%), with weight-2 source {geo} ({100*geo/n:.1f}%)")
    print("   status/faults:", dict(kinds.most_common(6)))
    print("   sources:", dict(sid_counter.most_common(10)))
# examples
print("\nexample groups:")
shown = 0
for r in rows:
    if shown >= nex:
        break
    L = json.loads((R10 / f"outputs/heldout/ledgers/ledger_{r['project']}.json").read_text(encoding="utf-8"))
    g = L["groups"][r["group"]]
    print(r["group"], r["status"], r.get("admissible_lo"), r.get("admissible_hi"), r.get("fault_types"))
    print("   keys:", list(g.keys()))
    for k in ("sources", "numeric", "categorical"):
        if k in g:
            v = g[k]
            v = list(v.values()) if isinstance(v, dict) else v
            for s in v[:12]:
                print("     ", k, json.dumps(s)[:240])
    shown += 1
