"""Experiment 1: as-is evidence audit for all models, levels and rulebooks.

Usage: python -E -P run_e1_audit.py <ledger_dir> <out_dir>
Writes e1_audit_rows.jsonl and e1_audit_summary.json
"""
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from bimev.audit import audit_ledger  # noqa: E402


def main(led_dir: Path, out: Path):
    out.mkdir(parents=True, exist_ok=True)
    all_rows = []
    for p in sorted(led_dir.glob("ledger_*.json")):
        L = json.loads(p.read_text(encoding="utf-8"))
        for rb in ("US", "DE_DOOR"):
            for level in ("min", "std", "full"):
                if rb == "DE_DOOR" and level != "full":
                    continue
                for r in audit_ledger(L, level, rb):
                    if rb == "DE_DOOR" and r["family"] != "door":
                        continue
                    r["level"], r["rulebook"] = level, rb
                    all_rows.append(r)
    with (out / "e1_audit_rows.jsonl").open("w", encoding="utf-8") as fh:
        for r in all_rows:
            fh.write(json.dumps(r, ensure_ascii=False, default=str) + "\n")
    # summary: element-weighted counts per rulebook/level/family
    summ = defaultdict(Counter)
    for r in all_rows:
        key = f"{r['rulebook']}|{r['level']}|{r['family']}"
        m = r["mult"]
        summ[key]["checks"] += m
        summ[key][r["status"]] += m
        summ[key]["naive_" + r["naive"]] += m
        if r["fault_types"]:
            summ[key]["with_conflict"] += m
        for t in r["fault_types"]:
            summ[key]["fault_" + t] += m
        if r["n_interpretations"] > 1:
            summ[key]["multi_interpretation"] += m
        summ[key]["groups"] += 1
    (out / "e1_audit_summary.json").write_text(json.dumps({k: dict(v) for k, v in sorted(summ.items())}, indent=1),
                                               encoding="utf-8")
    for k, v in sorted(summ.items()):
        print(k.ljust(26), dict(v))


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]))
