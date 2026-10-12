"""Experiment 4: validation against withheld explicit values (no simulation).

For every check that carries an explicit, non-suspect source of the code quantity (an explicit clear-width property
of a door, a riser or tread value of a flight, a railing-height property, an explicit clear-height property of a
space), two reduced evidence sets are evaluated with the unchanged engine at the full evidence level:

  reference: the explicit non-suspect sources plus all categorical evidence;
  indirect:  every numeric source that is not explicit, plus all categorical evidence.

A reference decision exists when the reference set alone yields a stable conclusion. The test compares the stable
conclusion of the indirect set with that reference decision. The face-value baseline is the single-source checker of
Experiment 1 applied to the indirect set (it falls back to the next designated source or reports pending).

Usage: python -E -P run_e4_validation.py <ledger_dir> <out_jsonl> [rulebook ...]
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from bimev import catalog as C  # noqa: E402
from bimev.engine import ClusterModel, classify_segment, decision  # noqa: E402
from bimev.planner import NAIVE_LABELS, _naive_category, _visible_raw  # noqa: E402


def is_explicit(family: str, s: dict) -> bool:
    """Explicit measurement of the code quantity (pre-declared in PREREGISTRATION.md, section E4)."""
    if s["kind"] != "num":
        return False
    sid, note = s["sid"], (s.get("note") or "")
    if family == "door":
        return note in ("CLEAR", "CLEAR_ACTIVE")
    if family == "stair":
        return sid in ("attr", "stair") or sid.startswith("p:") or sid.startswith("t:")
    if family == "railing":
        return sid.startswith("p:")
    if family == "space":
        return sid.startswith("p:") and note == "CLEAR"
    return False


def evaluate(L: dict, gid: str, keep, rulebook: str):
    g = L["groups"][gid]
    g2 = {**g, "sources": [s for s in g["sources"] if keep(s)]}
    L2 = {**L, "groups": {**L["groups"], gid: g2}}
    cm = ClusterModel(g["cluster"], L2, C.LEVEL_RANK["full"], rulebook)
    cm.solve()
    gm = next(x for x in cm.groups if x.gid == gid)
    kind = cm.status(gid)[0]
    lo, hi = cm.support(gid)
    dec = {"STABLE_V": "V", "STABLE_N": "N"}.get(kind)
    return cm, gm, kind, dec, lo, hi


def main():
    led_dir, out = Path(sys.argv[1]), Path(sys.argv[2])
    rulebooks = sys.argv[3:] or ["US"]
    out.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with out.open("w", encoding="utf-8") as fh:
        for lf in sorted(led_dir.glob("ledger_*.json")):
            L = json.loads(lf.read_text(encoding="utf-8"))
            for rb in rulebooks:
                for gid, g in L["groups"].items():
                    fam = g["family"]
                    if rb == "DE_DOOR" and fam != "door":
                        continue
                    exp = [s for s in g["sources"] if is_explicit(fam, s)]
                    ref_src = [s for s in exp if not s.get("suspect")]
                    if not ref_src:
                        continue
                    ref_ids = {id(s) for s in ref_src}
                    _, _, rkind, rdec, rlo, rhi = evaluate(
                        L, gid, lambda s: s["kind"] == "cat" or id(s) in ref_ids, rb)
                    cmi, gmi, ikind, idec, ilo, ihi = evaluate(
                        L, gid, lambda s: s["kind"] == "cat" or not is_explicit(fam, s), rb)
                    v = _visible_raw(gmi, NAIVE_LABELS[gmi.quantity], exact=(fam != "space"))
                    if v is None:
                        ndec = None
                    else:
                        ndec = decision(classify_segment(v, v, gmi.requirement(_naive_category(gmi, cmi)))[0][2])
                    rec = {"project": L["project"], "rulebook": rb, "group": gid, "family": fam,
                           "quantity": g["quantity"], "mult": int(g["multiplicity"]),
                           "explicit": [[s["label"], s.get("value_mm")] for s in ref_src],
                           "n_indirect_num": sum(1 for s in g["sources"] if s["kind"] == "num"
                                                 and not is_explicit(fam, s)),
                           "ref_status": rkind, "ref_decision": rdec, "ref_support": [rlo, rhi],
                           "ind_status": ikind, "ind_decision": idec, "ind_support": [ilo, ihi],
                           "naive_value": v, "naive_decision": ndec}
                    fh.write(json.dumps(rec) + "\n")
                    n += 1
            print(f"{lf.stem}: done", flush=True)
    print(f"{n} records written to {out}")


if __name__ == "__main__":
    main()
