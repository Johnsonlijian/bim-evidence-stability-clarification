"""Experiment 1: as-is evidence audit (no hidden state, no sampling).

For every check at a given evidence level this module reports the conclusion status, the size of the admissible
set, the fault explanations retained by the minimum-weight diagnosis (alternative unit, gross error, suspected
export default, contradicted categorical evidence) and how a single-source checker relates to the evidence.
"""
from __future__ import annotations

from collections import Counter

from .engine import build_clusters, classify_segment, decision
from .planner import NAIVE_LABELS, _naive_category, _visible_raw


def _source_mode(gm, s, assign, x):
    """Cheapest reading of numeric source s that contains value x under an assignment."""
    from .engine import _key
    row = s["table"].get(_key([assign[d] for d in s["deps"]])) or {}
    best = None
    for mode, (lo, hi) in row.items():
        if lo <= x <= hi:
            if mode == "ok":
                return "ok"
            best = best or mode
    if best is not None:
        return "unit"
    if float(s.get("weight", 1.0)) == 0.0:
        return "intent"
    return "suspect_default" if s["suspect"] else "gross"


def audit_ledger(ledger, level="full", rulebook="US"):
    cl = build_clusters(ledger, level, rulebook)
    rows = []
    for cid, cm in cl.items():
        for gm in cm.groups:
            kind, mV, mN, sub = cm.status(gm.gid)
            hyps = cm.vs[gm.gid]
            faults = Counter()
            cat_faults = 0
            interp = set()
            for h in hyps:
                assign = {**dict(zip(cm.shared, h.a)), **h.b}
                interp.add(tuple(sorted((k.split("|")[-1], v) for k, v in assign.items())))
                for s in gm.cat_sources:
                    if assign[s["var"]] not in s["allowed"]:
                        cat_faults += 1
                for l, u in h.segs:
                    x = 0.5 * (l + u)
                    for s in gm.num_sources:
                        m = _source_mode(gm, s, assign, x)
                        if m != "ok":
                            faults[(m, "; ".join(s["labels"])[:80])] += 1
            lo, hi = cm.support(gm.gid)
            # naive single-source decision
            v = _visible_raw(gm, NAIVE_LABELS[gm.quantity], exact=(gm.family != "space"))
            if v is None:
                naive = "no_designated_source"
            else:
                nd = decision(classify_segment(v, v, gm.requirement(_naive_category(gm, cm)))[0][2])
                if kind == "UNSTABLE":
                    naive = "decided_without_sufficient_evidence"
                elif (kind == "STABLE_V" and nd == "V") or (kind == "STABLE_N" and nd == "N"):
                    naive = "agrees"
                else:
                    naive = "contradicts_evidence"
            rows.append({
                "project": ledger["project"], "cluster": cid, "group": gm.gid, "family": gm.family,
                "quantity": gm.quantity, "mult": gm.mult, "names": gm.g["names"][:1], "status": kind,
                "p_violation": round(mV, 4), "admissible_lo": lo, "admissible_hi": hi,
                "n_num_sources": len(gm.num_sources), "n_cat_sources": len(gm.cat_sources),
                "cluster_min_cost": cm.min_cost, "n_interpretations": len(interp),
                "fault_types": sorted({k[0] for k in faults} | ({"categorical"} if cat_faults else set())),
                "faulted_sources": sorted({f"{k[0]}:{k[1]}" for k in faults}),
                "pass_share": round(sub["PASS"], 4), "na_share": round(sub["NA"], 4),
                "naive": naive, "naive_value": v,
            })
    return rows
