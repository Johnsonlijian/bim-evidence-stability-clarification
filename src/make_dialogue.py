"""Example dialogue: the planner's first requests on one held-out model.

Usage: python -E -P make_dialogue.py <R10 dir> <n_rows>
Selection rule (stated in the manuscript): the held-out model with the most checks left open by the delivered
evidence (Experiment 1, full level, US rulebook); within it, the hidden-state draw with the median planner effort.
Writes outputs/tables/tab_dialogue.tex, outputs/results/dialogue.json and manuscript/numbers_dialogue.tex.
"""
import json
import sys
import zlib
from collections import Counter
from pathlib import Path

import numpy as np

R10 = Path(sys.argv[1])
nrows = int(sys.argv[2])
sys.path.insert(0, str(R10 / "src"))
from bimev.engine import build_clusters  # noqa: E402
from bimev.planner import World, choose, sample_truth  # noqa: E402

OUT = R10 / "outputs"
NAMES = {"fantasy_hotel_1": "Student hotel 1", "fantasy_hotel_2": "Student hotel 2",
         "fantasy_office_building_2": "Student office 2", "fantasy_office_building_3": "Student office 3",
         "fantasy_residential_building_1": "Student residential 1", "hitos": "HITOS", "molio": "Molio demo building",
         "sixty5": "Sixty5", "west_riverside_hospital": "West Riverside hospital"}
open_checks = Counter()
with open(OUT / "heldout" / "e1" / "e1_audit_rows.jsonl", encoding="utf-8") as fh:
    for line in fh:
        r = json.loads(line)
        if r["rulebook"] == "US" and r["level"] == "full" and r["status"] == "UNSTABLE":
            open_checks[r["project"]] += r["mult"]
proj = open_checks.most_common(1)[0][0]
costs = []
with open(OUT / "heldout" / "e2" / "e2_main.jsonl", encoding="utf-8") as fh:
    for line in fh:
        r = json.loads(line)
        if r["project"] == proj and r["level"] == "full" and r["policy"] == "sv":
            costs.append((r["cost"], r["seed"]))
costs.sort()
med_cost, seed = costs[len(costs) // 2]
L = json.loads((OUT / "heldout" / "ledgers" / f"ledger_{proj}.json").read_text(encoding="utf-8"))
base = zlib.crc32(f"{proj}|{seed}".encode()) & 0x7FFFFFFF
tv, tq = sample_truth(build_clusters(L, "full"), np.random.default_rng(base))
w = World(L, "full", "US", tv, tq)
QTY = {"door_clear_width": "clear width", "stair_riser": "riser height", "stair_tread": "tread depth",
       "railing_height": "height", "ceiling_height": "ceiling height"}
ANS = {"OPENING": "opening", "LEAF": "leaf", "CLEAR": "finished ceiling", "GROSS": "upper limit",
       "SWING": "single swing", "DOUBLE": "double leaf", "SLIDING": "sliding", "OTHER": "not applicable",
       "PASSAGE": "yes", "NONPASSAGE": "no", "GUARD": "guard", "HANDRAIL": "handrail",
       "OCCUPIABLE": "occupiable", "SERVICE": "service", "NONOCC": "not occupiable"}


def tex(s):
    return s.replace("\\", "/").replace("_", r"\_").replace("&", r"\&").replace("#", r"\#").replace("%", r"\%")


def closed():
    return sum(gm.mult for _, gm in w.order if not w.open_group(gm.gid))


def describe(a):
    cl = L["clusters"][a.cid]
    fam = cl["family"]
    if a.kind == "CLARIFY":
        meta = L["vars"][a.target]
        k = meta["kind"]
        tname = tex(cl["label"])
        if k == "sem" and fam == "door":
            prop = a.target.split("|sem|")[-1]
            prop = "the nominal size in the type name" if prop == "Name" else r"\texttt{" + tex(prop) + "}"
            q = f"Does {prop} of door type {tname} denote the leaf or the opening?"
        elif k == "sem" and fam == "space":
            q = "Is the room-height parameter set at the finished ceiling? (all spaces)"
        elif k == "cfg":
            q = f"Leaf configuration of door type {tname}?"
        elif k == "app":
            q = f"Is door type {tname} a passage door?"
        elif k == "fn":
            q = f"Is railing type {tname} a guard or a handrail?"
        elif k == "cat":
            q = f"Use category of space {tex(L['groups'][meta['group']]['names'][0])}?"
        else:
            q = f"Value of {tex(meta['label'])}?"
        return "Clarify", q, ANS.get(str(tv.get(a.target)), str(tv.get(a.target)))
    g0 = L["groups"][a.groups[0]]
    if a.target == a.cid:
        scope = {"door": "door type", "railing": "railing type"}.get(fam, "") + " " + tex(cl["label"])
    else:
        scope = {"stair": "flight", "space": "space"}.get(fam, "") + " " + tex(g0["names"][0])
    q = [round(tq[g]) for g in a.groups if g in tq]
    return "Value", f"Certified {QTY[g0['quantity']]} of {scope.strip()}", (f"{q[0]}\\,mm" if q else "")


rows = []
c0 = closed()
total = sum(gm.mult for _, gm in w.order)
print(f"{proj} full: seed {seed} (median planner effort {med_cost}); initially closed {c0}/{total}")
for i in range(nrows):
    a = choose(w, "sv", np.random.default_rng(0))
    if a is None:
        break
    kind, text, ans = describe(a)
    before = closed()
    w.apply(a)
    after = closed()
    rows.append((i + 1, kind, text, ans, a.cost, after - before, after))
    print(i + 1, kind, text, "->", ans, f"cost {a.cost}", f"+{after - before}", f"closed {after}/{total}")
lines = [r"\begin{tabularx}{\textwidth}{@{}rlXlrrr@{}}", r"\toprule",
         r"\# & Kind & Request & Answer & Effort & Settled & Concluded \\", r"\midrule",
         f" & & \\emph{{Delivered model (full evidence level)}} & & & & {c0:,} / {total:,} \\\\"]
for i, kind, text, ans, cost, gain, cum in rows:
    lines.append(f"{i} & {kind} & {text} & {ans} & {cost:g} & {gain:,} & {cum:,} \\\\")
lines += [r"\bottomrule", r"\end{tabularx}"]
(OUT / "tables" / "tab_dialogue.tex").write_text("\n".join(lines) + "\n", encoding="utf-8")
(OUT / "results" / "dialogue.json").write_text(json.dumps({"project": proj, "seed": seed, "median_cost": med_cost,
                                                           "initial_closed": c0, "total": total, "rows": rows},
                                                          indent=1), encoding="utf-8")
mac = {"DlgModel": NAMES.get(proj, proj), "DlgSeed": str(seed), "DlgMedianEffort": f"{med_cost:g}",
       "DlgInitial": f"{c0:,}", "DlgTotal": f"{total:,}", "DlgOpen": f"{open_checks[proj]:,}",
       "DlgFirstGain": f"{rows[0][5]:,}" if rows else "0", "DlgRows": str(len(rows)),
       "DlgAfterRows": f"{rows[-1][6]:,}" if rows else f"{c0:,}",
       "DlgEffortRows": f"{sum(r[4] for r in rows):g}", "DlgZeroGain": str(sum(1 for r in rows if r[5] == 0)),
       "DlgMaxGain": f"{max((r[5] for r in rows), default=0):,}",
       "DlgMaxGainRow": str(1 + max(range(len(rows)), key=lambda i: rows[i][5])) if rows else "0"}
# counterfactual for the first request when it is a question: checks settled under every possible answer
w0 = World(L, "full", "US", tv, tq)
a0 = choose(w0, "sv", np.random.default_rng(0))
if a0 is not None and a0.kind == "CLARIFY":
    alt = {}
    for ans in L["vars"][a0.target]["domain"]:
        tv2 = dict(tv)
        tv2[a0.target] = ans
        w2 = World(L, "full", "US", tv2, tq)
        a2 = choose(w2, "sv", np.random.default_rng(0))
        before = sum(gm.mult for _, gm in w2.order if not w2.open_group(gm.gid))
        w2.apply(a2)
        alt[ans] = sum(gm.mult for _, gm in w2.order if not w2.open_group(gm.gid)) - before
    best = max((k for k in alt if k != tv[a0.target]), key=lambda k: alt[k], default=None)
    if best is not None:
        mac["DlgFirstAltAnswer"] = ANS.get(best, best.lower())
        mac["DlgFirstAltGain"] = f"{alt[best]:,}"
    print("first question, checks settled per answer:", alt)
(R10 / "manuscript" / "numbers_dialogue.tex").write_text(
    "% Generated by make_dialogue.py -- do not edit by hand\n" +
    "".join(f"\\newcommand{{\\{k}}}{{{v}}}\n" for k, v in mac.items()), encoding="utf-8")
