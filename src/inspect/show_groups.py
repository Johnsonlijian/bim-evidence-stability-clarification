"""Show held-out E1 groups of one model and family with names, status and compact source tables.

Usage: python -E -P show_groups.py <R10 dir> <project> <family> [max_groups] [status_filter]
"""
import json
import sys
from collections import Counter
from pathlib import Path

R10 = Path(sys.argv[1])
p, fam = sys.argv[2], sys.argv[3]
mx = int(sys.argv[4]) if len(sys.argv) > 4 else 8
sf = sys.argv[5] if len(sys.argv) > 5 else ""
rows = [json.loads(l) for l in open(R10 / "outputs/heldout/e1/e1_audit_rows.jsonl", encoding="utf-8") if l.strip()]
rows = [r for r in rows if r["project"] == p and r["family"] == fam and r["level"] == "full" and r["rulebook"] == "US"
        and (not sf or r["status"] == sf)]
L = json.loads((R10 / f"outputs/heldout/ledgers/ledger_{p}.json").read_text(encoding="utf-8"))
names = Counter()
for r in rows:
    for n in r["names"][:1]:
        names[n.split(":")[0]] += r["mult"]
print("name stems:", names.most_common(12))
rows.sort(key=lambda r: -r["mult"])
for r in rows[:mx]:
    g = L["groups"][r["group"]]
    print(f"\n{r['group']} x{r['mult']} {r['status']} adm=[{r.get('admissible_lo')}, {r.get('admissible_hi')}] faults={r.get('fault_types')} naive={r.get('naive')} {r.get('naive_value')}")
    print("   names:", r["names"][:2], " cat vars:", g.get("category_vars"), " dz:", g.get("geom_dz_mm"))
    for s in g["sources"]:
        t = s.get("table", {})
        first = next(iter(t.values())) if t else {}
        ok = first.get("ok") if isinstance(first, dict) else None
        print(f"     {s.get('kind')} {s.get('sid')[:60]:60s} w={s.get('weight', 1)} note={s.get('note')} suspect={s.get('suspect')} raw={s.get('raw')} ok={ok} allowed={s.get('allowed')}")
