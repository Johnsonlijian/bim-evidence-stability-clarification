"""R10 results: aggregate E1-E4 for the development (D), held-out (H), strict held-out (S) and pooled (A) sets.

Usage: python -E -P make_results.py <R10 dir>
Writes outputs/results/results.json, outputs/tables/*.tex and manuscript/numbers.tex (all manuscript numbers).
"""
import json
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
from scipy import stats

R10 = Path(sys.argv[1])
OUT = R10 / "outputs"
TAB = OUT / "tables"
TAB.mkdir(parents=True, exist_ok=True)
(OUT / "results").mkdir(parents=True, exist_ok=True)

DEV = ["city_house_munich", "duplex", "fantasy_office_building_1", "wbdg_office"]
HELD = ["fantasy_hotel_1", "fantasy_hotel_2", "fantasy_office_building_2", "fantasy_office_building_3",
        "fantasy_residential_building_1", "hitos", "molio", "sixty5", "west_riverside_hospital"]
SETS = {"D": set(DEV), "H": set(HELD), "S": set(HELD) - {"molio", "sixty5"}, "A": set(DEV) | set(HELD)}
SETWORD = {"D": "Dev", "H": "Held", "S": "Strict", "A": "All"}
FAMILIES = ["door", "stair", "railing", "space"]
POLICIES = ["naive", "complete", "conf0.8", "conf0.9", "conf0.95", "conf0.99", "value", "random", "fixed", "degree",
            "ec2", "sv", "oracle"]
ADAPTIVE = ["value", "random", "fixed", "degree", "ec2", "sv"]
NUM_FIELDS = ["cost", "checks", "wrong", "escalated", "n_clarify", "n_value", "false_violation", "missed_violation",
              "secs"] + [f"cost_{f}" for f in FAMILIES] + [f"wrong_{f}" for f in FAMILIES]
rng = np.random.default_rng(20261011)
NBOOT = 10000


def load(path):
    if not path.exists():
        return []
    rows, bad = [], 0
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                bad += 1
    if bad:
        print(f"WARNING: {bad} unreadable line(s) in {path} (file still being written?)")
    return rows


def load_both(rel):
    return load(OUT / "dev" / rel) + load(OUT / "heldout" / rel)


def ci95(x):
    x = np.asarray(x, dtype=float)
    if len(x) < 2:
        return float(x.mean()) if len(x) else 0.0, 0.0
    return float(x.mean()), float(stats.t.ppf(0.975, len(x) - 1) * x.std(ddof=1) / math.sqrt(len(x)))


def clopper(k, n):
    if n == 0:
        return (0.0, 1.0)
    lo = 0.0 if k == 0 else stats.beta.ppf(0.025, k, n - k + 1)
    hi = 1.0 if k == n else stats.beta.ppf(0.975, k + 1, n - k)
    return float(lo), float(hi)


def wilcox(a, b):
    a, b = np.asarray(a), np.asarray(b)
    if np.allclose(a - b, 0):
        return 1.0
    try:
        return float(stats.wilcoxon(a, b, zero_method="wilcox").pvalue)
    except ValueError:
        return 1.0


def boot_ratio(per_model_num, per_model_den):
    """Model-level bootstrap of sum(num)/sum(den); returns (point, lo, hi)."""
    num, den = np.asarray(per_model_num, float), np.asarray(per_model_den, float)
    k = len(num)
    pt = num.sum() / den.sum() if den.sum() > 0 else float("nan")
    if k < 2:
        return pt, pt, pt
    idx = rng.integers(0, k, size=(NBOOT, k))
    r = num[idx].sum(1) / np.maximum(den[idx].sum(1), 1e-12)
    return float(pt), float(np.percentile(r, 2.5)), float(np.percentile(r, 97.5))


R = {"sets": {k: sorted(v) for k, v in SETS.items()}}

# ============================================================== dataset
lineage = {}
for f in ("dev_lineage.json", "heldout_lineage.json"):
    for d in json.loads((R10 / "lineage" / f).read_text(encoding="utf-8")):
        lineage[Path(d["path"]).parent.name] = d
TOOL = {}
for p, d in lineage.items():
    o = (d.get("originating_system") or "") + " " + (d.get("preprocessor") or "")
    if "ARCHICAD" in o.upper():
        TOOL[p] = "ArchiCAD"
    elif "REVIT" in o.upper() or "EXPORTER" in o.upper():
        TOOL[p] = "Revit"
    elif "SOLIBRI" in o.upper():
        TOOL[p] = "Revit"  # Solibri IFC Optimizer post-processing of Revit exports (header FILE_NAME)
    else:
        TOOL[p] = "unknown"
# authoring tool verified from the IfcApplication entity of each file (headers can name post-processors)
TOOL.update({"city_house_munich": "Revit", "duplex": "Revit", "fantasy_office_building_1": "Revit",
             "wbdg_office": "Revit", "fantasy_hotel_1": "Revit", "fantasy_hotel_2": "Revit",
             "fantasy_office_building_2": "Revit", "fantasy_office_building_3": "Revit",
             "fantasy_residential_building_1": "Revit", "hitos": "ArchiCAD", "molio": "ArchiCAD",
             "sixty5": "ArchiCAD", "west_riverside_hospital": "Revit"})
ds = []
for setname, projs in (("D", DEV), ("H", HELD)):
    sub = "dev" if setname == "D" else "heldout"
    for p in projs:
        lf = OUT / sub / "ledgers" / f"ledger_{p}.json"
        L = json.loads(lf.read_text(encoding="utf-8"))
        fam, types = Counter(), Counter()
        for g in L["groups"].values():
            fam[g["family"]] += g["multiplicity"]
        for c in L["clusters"].values():
            types[c["family"]] += 1
        ds.append({"project": p, "set": setname, "schema": L["schema"], "occupancy": L["occupancy"],
                   "tool": TOOL.get(p, "unknown"), "unit": "foot" if abs(L["length_scale_m"] - 0.3048) < 1e-6 else "metre",
                   "doors": fam["door"], "door_types": types["door"], "flights": fam["stair"] // 2,
                   "stair_checks": fam["stair"], "railings": fam["railing"], "spaces": fam["space"],
                   "checks": sum(fam.values()), "groups": len(L["groups"]),
                   "lineage_clean": bool(lineage.get(p, {}).get("clean", False))})
R["dataset"] = ds
DSP = {d["project"]: d for d in ds}

# ============================================================== E1
e1 = load_both(Path("e1") / "e1_audit_rows.jsonl")


def e1_counts(rows):
    c = Counter()
    for r in rows:
        m = r["mult"]
        c["checks"] += m
        c[r["status"]] += m
        c["naive_" + r["naive"]] += m
        if r["fault_types"]:
            c["with_conflict"] += m
        for t in r["fault_types"]:
            c["fault_" + t] += m
    return c


E1 = {}
for sk, projs in SETS.items():
    for rb in ("US", "DE_DOOR"):
        for lv in ("min", "std", "full"):
            for fam in FAMILIES + ["all"]:
                rs = [r for r in e1 if r["project"] in projs and r["rulebook"] == rb and r["level"] == lv
                      and (fam == "all" or r["family"] == fam)]
                if rs:
                    E1[f"{sk}|{rb}|{lv}|{fam}"] = dict(e1_counts(rs))
R["e1"] = E1
# per-model shares (US, full) and model-level bootstrap
E1M = {}
for p in DEV + HELD:
    c = e1_counts([r for r in e1 if r["project"] == p and r["rulebook"] == "US" and r["level"] == "full"])
    E1M[p] = dict(c)
R["e1_model"] = E1M
E1B = {}
for sk, projs in SETS.items():
    ps = [p for p in DEV + HELD if p in projs and E1M.get(p, {}).get("checks")]
    n = [E1M[p]["checks"] for p in ps]
    for key, num in (("stable", [E1M[p].get("STABLE_N", 0) + E1M[p].get("STABLE_V", 0) for p in ps]),
                     ("unsupported", [E1M[p].get("naive_decided_without_sufficient_evidence", 0) for p in ps]),
                     ("contradicts", [E1M[p].get("naive_contradicts_evidence", 0) for p in ps])):
        E1B[f"{sk}|{key}"] = boot_ratio(num, n)
    shares = [(E1M[p].get("STABLE_N", 0) + E1M[p].get("STABLE_V", 0)) / E1M[p]["checks"] for p in ps]
    E1B[f"{sk}|stable_model_median"] = float(np.median(shares)) if shares else float("nan")
    E1B[f"{sk}|stable_model_range"] = (float(min(shares)), float(max(shares))) if shares else (0, 0)
R["e1_boot"] = E1B
# conflict examples (full, US)
ex = defaultdict(Counter)
for r in e1:
    if r["rulebook"] == "US" and r["level"] == "full" and r["faulted_sources"]:
        for fs in r["faulted_sources"]:
            ex[r["project"]][f"{r['family']}::{fs}"] += r["mult"]
R["e1_fault_examples"] = {k: v.most_common(15) for k, v in ex.items()}

# ============================================================== E4
e4 = load_both(Path("e4") / "e4_rows.jsonl")
E4 = {}
for sk, projs in SETS.items():
    for rb in ("US", "DE_DOOR"):
        for fam in FAMILIES + ["all"]:
            rs = [r for r in e4 if r["project"] in projs and r["rulebook"] == rb and (fam == "all" or r["family"] == fam)]
            if not rs:
                continue
            c = Counter()
            for r in rs:
                m = r["mult"]
                c["with_explicit"] += m
                if r["ref_decision"] is None:
                    c["ref_indeterminate"] += m
                    continue
                c["ref"] += m
                if r["ind_decision"] is None:
                    c["ind_open"] += m
                elif r["ind_decision"] == r["ref_decision"]:
                    c["ind_agree"] += m
                else:
                    c["ind_wrong"] += m
                if r["naive_decision"] is None:
                    c["naive_pending"] += m
                elif r["naive_decision"] == r["ref_decision"]:
                    c["naive_agree"] += m
                else:
                    c["naive_wrong"] += m
            rec = dict(c)
            st = c["ind_agree"] + c["ind_wrong"]
            rec["ind_stable"] = st
            rec["ind_err"] = c["ind_wrong"] / st if st else 0.0
            rec["ind_err_ci"] = clopper(c["ind_wrong"], st)
            nd = c["naive_agree"] + c["naive_wrong"]
            rec["naive_decided"] = nd
            rec["naive_err"] = c["naive_wrong"] / nd if nd else 0.0
            rec["naive_err_ci"] = clopper(c["naive_wrong"], nd)
            rec["coverage"] = st / c["ref"] if c["ref"] else 0.0
            E4[f"{sk}|{rb}|{fam}"] = rec
R["e4"] = E4
R["e4_disagreements"] = [r for r in e4 if r["ref_decision"] and r["ind_decision"]
                         and r["ref_decision"] != r["ind_decision"]]
R["e4_naive_wrong"] = [{k: r[k] for k in ("project", "rulebook", "group", "family", "mult", "explicit", "naive_value",
                                          "naive_decision", "ref_decision", "ref_support")}
                       for r in e4 if r["ref_decision"] and r["naive_decision"]
                       and r["ref_decision"] != r["naive_decision"]]


# ============================================================== E2
def portfolio(rows, projs):
    acc = defaultdict(lambda: defaultdict(float))
    for r in rows:
        if r["project"] not in projs:
            continue
        k = (r["seed"], r["level"], r["policy"])
        for f in NUM_FIELDS:
            v = r.get(f)
            if v is not None:
                acc[k][f] += float(v)
    seeds = sorted({k[0] for k in acc})
    out = {}
    for lv, pol in sorted({(k[1], k[2]) for k in acc}):
        out[(lv, pol)] = {f: np.array([acc[(s, lv, pol)].get(f, 0.0) for s in seeds if (s, lv, pol) in acc])
                          for f in NUM_FIELDS}
    return out, seeds


def summarise(P):
    res = {}
    for (lv, pol), d in P.items():
        n = d["checks"].mean()
        rec = {"checks": float(n)}
        for f in ("cost", "wrong", "escalated", "n_clarify", "n_value", "false_violation", "missed_violation", "secs"):
            rec[f], rec[f + "_ci"] = ci95(d[f])
        rec["wrong_pct"] = 100 * d["wrong"].mean() / n
        rec["wrong_pct_ci"] = 100 * ci95(d["wrong"] / d["checks"])[1]
        rec["escalated_pct"] = 100 * d["escalated"].mean() / n
        for f in FAMILIES:
            rec[f"cost_{f}"] = float(d[f"cost_{f}"].mean())
            rec[f"wrong_{f}"] = float(d[f"wrong_{f}"].mean())
        res[f"{lv}|{pol}"] = rec
    return res


e2rows = load_both(Path("e2") / "e2_main.jsonl")
E2, REL, E2B, ANY = {}, {}, {}, {}
BUDGETS = [0, 1, 2, 3, 4, 5, 6, 8, 10, 12, 15, 20, 25, 30, 40, 50, 60, 80, 100, 120, 150, 200, 250, 300]
permodel = defaultdict(lambda: defaultdict(list))
for r in e2rows:
    for f in ["cost", "wrong", "secs", "checks", "escalated", "n_clarify", "n_value"] + [f"wrong_{x}" for x in FAMILIES] + \
             [f"cost_{x}" for x in FAMILIES]:
        permodel[(r["project"], r["level"], r["policy"])][f].append(r.get(f, 0.0) or 0.0)
R["e2_model"] = {f"{k[0]}|{k[1]}|{k[2]}": {f: float(np.mean(v)) for f, v in d.items()} for k, d in permodel.items()}


def closure_at(traj, b):
    best = traj[0][1]
    for c, f, _ in traj:
        if c <= b + 1e-9:
            best = f
    return best


for sk, projs in SETS.items():
    P, seeds = portfolio(e2rows, projs)
    if not P:
        continue
    E2[sk] = summarise(P)
    E2[sk]["_seeds"] = len(seeds)
    for lv in ("min", "std", "full"):
        if (lv, "sv") not in P:
            continue
        sv = P[(lv, "sv")]["cost"]
        for pol in POLICIES:
            if (lv, pol) not in P or pol == "sv":
                continue
            o = P[(lv, pol)]["cost"]
            REL[f"{sk}|{lv}|{pol}"] = {"saving_pct": float(100 * (1 - sv.mean() / o.mean())) if o.mean() > 0 else None,
                                       "p_wilcoxon": wilcox(sv, o), "sv_better_share": float(np.mean(sv < o - 1e-9)),
                                       "sv_tie_share": float(np.mean(np.abs(sv - o) <= 1e-9))}
        # oracle bound check and model-level bootstrap of savings
        ok = sum(1 for i in range(len(sv)) if all(P[(lv, "oracle")]["cost"][i] <= P[(lv, p)]["cost"][i] + 1e-9
                                                    for p in ADAPTIVE if (lv, p) in P))
        E2B[f"{sk}|{lv}|oracle_bound"] = (ok, len(sv))
        ps = [p for p in DEV + HELD if p in projs]
        for other in ("complete", "degree", "fixed", "ec2", "oracle"):
            num = [np.mean(permodel[(p, lv, "sv")]["cost"]) for p in ps]
            den = [np.mean(permodel[(p, lv, other)]["cost"]) for p in ps]
            E2B[f"{sk}|{lv}|sv_over_{other}"] = boot_ratio(num, den)
    # anytime (plain closure share)
    by = defaultdict(list)
    for r in e2rows:
        if r["project"] in projs and r.get("traj"):
            by[(r["level"], r["policy"], r["seed"])].append(r)
    for (lv, pol, seed), rs in by.items():
        tot = sum(r["checks"] for r in rs)
        ANY.setdefault(f"{sk}|{lv}|{pol}", []).append(
            [sum(closure_at(r["traj"], b) * r["checks"] for r in rs) / tot for b in BUDGETS])
R["e2"] = E2
R["e2_rel"] = REL
R["e2_boot"] = E2B
R["anytime_budgets"] = BUDGETS
R["anytime"] = {k: list(np.mean(np.array(v, dtype=float), axis=0)) for k, v in ANY.items()}

# ============================================================== E3
E3 = {}
for name in ("cost1.5", "cost6", "de_door", "mis050", "mis100", "cons050", "cons100", "cons050_decl", "nogeom"):
    rows = load_both(Path("e3") / f"e3_{name}.jsonl")
    for sk, projs in SETS.items():
        P, seeds = portfolio(rows, projs)
        if P:
            E3[f"{sk}|{name}"] = summarise(P)
            E3[f"{sk}|{name}"]["_seeds"] = len(seeds)
R["e3"] = E3

(OUT / "results" / "results.json").write_text(json.dumps(R, indent=1, default=float), encoding="utf-8")

# ============================================================== LaTeX tables
NAMES = {"city_house_munich": "City house Munich", "duplex": "Duplex apartment",
         "fantasy_office_building_1": "Student office 1", "wbdg_office": "WBDG office",
         "fantasy_hotel_1": "Student hotel 1", "fantasy_hotel_2": "Student hotel 2",
         "fantasy_office_building_2": "Student office 2", "fantasy_office_building_3": "Student office 3",
         "fantasy_residential_building_1": "Student residential 1", "hitos": "HITOS", "molio": "Molio demo building",
         "sixty5": "Sixty5 (Strijp-S)", "west_riverside_hospital": "West Riverside hospital"}
USE = {"city_house_munich": "townhouse", "duplex": "two-family", "fantasy_office_building_1": "office",
       "wbdg_office": "office", "fantasy_hotel_1": "hotel", "fantasy_hotel_2": "hotel",
       "fantasy_office_building_2": "office", "fantasy_office_building_3": "office",
       "fantasy_residential_building_1": "residential", "hitos": "office", "molio": "office",
       "sixty5": "apartments", "west_riverside_hospital": "hospital"}
SCHEMA = {"IFC2X3": "IFC2x3", "IFC4": "IFC4", "IFC4X3": "IFC4x3", "IFC4X3_ADD2": "IFC4x3"}
lines = [r"\begin{tabular}{@{}lllllrrrrr@{}}", r"\toprule",
         r"Model & Set & Tool & Schema & Use (code) & Doors (types) & Flights & Railings & Spaces & Checks \\",
         r"\midrule"]
for setname in ("D", "H"):
    for d in [x for x in ds if x["set"] == setname]:
        code = "IRC" if d["occupancy"] == "residential" else "IBC"
        lines.append(f"{NAMES[d['project']]} & {setname} & {d['tool']} & {SCHEMA.get(d['schema'], d['schema'])} & "
                     f"{USE[d['project']]} ({code}) & {d['doors']:,} ({d['door_types']}) & {d['flights']} & "
                     f"{d['railings']:,} & {d['spaces']:,} & {d['checks']:,} \\\\")
    tot = {k: sum(x[k] for x in ds if x["set"] == setname) for k in ("doors", "door_types", "flights", "railings",
                                                                      "spaces", "checks")}
    lines.append(rf"\emph{{Total {setname}}} & & & & & {tot['doors']:,} ({tot['door_types']}) & {tot['flights']} & "
                 f"{tot['railings']:,} & {tot['spaces']:,} & {tot['checks']:,} \\\\")
    if setname == "D":
        lines.append(r"\addlinespace")
lines += [r"\bottomrule", r"\end{tabular}"]
(TAB / "tab_dataset.tex").write_text("\n".join(lines) + "\n", encoding="utf-8")

FAM_LABEL = {"door": "Door clear width", "stair": "Stair riser and tread", "railing": "Guard and handrail height",
             "space": "Ceiling height", "all": "All checks"}


def pc(c, k):
    return f"{100 * c.get(k, 0) / c['checks']:.1f}" if c.get("checks") else "--"


lines = [r"\begin{tabular}{@{}llrrrrrrr@{}}", r"\toprule",
         r" & & & \multicolumn{3}{c}{Conclusion from the evidence (\%)} & \multicolumn{3}{c}{Single-source checker (\%)} \\",
         r"\cmidrule(lr){4-6}\cmidrule(l){7-9}",
         r"Rule family & Set & Checks & No violation & Violation & Not stable & Contradicts & Unsupported & No source \\",
         r"\midrule"]
for fam in FAMILIES + ["all"]:
    for sk in ("D", "H"):
        c = E1.get(f"{sk}|US|full|{fam}")
        if not c:
            continue
        lab = FAM_LABEL[fam] if sk == "D" or not E1.get(f"D|US|full|{fam}") else ""
        lines.append(f"{lab} & {sk} & {c['checks']:,} & {pc(c, 'STABLE_N')} & {pc(c, 'STABLE_V')} & {pc(c, 'UNSTABLE')} & "
                     f"{pc(c, 'naive_contradicts_evidence')} & {pc(c, 'naive_decided_without_sufficient_evidence')} & "
                     f"{pc(c, 'naive_no_designated_source')} \\\\")
    if fam != "all":
        lines.append(r"\addlinespace")
lines += [r"\bottomrule", r"\end{tabular}"]
(TAB / "tab_e1.tex").write_text("\n".join(lines) + "\n", encoding="utf-8")

lines = [r"\begin{tabular}{@{}lrrrrrrr@{}}", r"\toprule",
         r" & & \multicolumn{3}{c}{Decision-stable conclusion} & \multicolumn{3}{c}{Face-value checker} \\",
         r"\cmidrule(lr){3-5}\cmidrule(l){6-8}",
         r"Rule family & References & Concluded & Wrong & Wrong (95\% CI) & Decided & Wrong & Wrong (95\% CI) \\",
         r"\midrule"]
for fam in FAMILIES + ["all"]:
    c = E4.get(f"A|US|{fam}")
    if not c or not c.get("ref"):
        continue
    lo, hi = c["ind_err_ci"]
    nlo, nhi = c["naive_err_ci"]
    lines.append(f"{FAM_LABEL[fam]} & {c['ref']:,} & {c['ind_stable']:,} & {c.get('ind_wrong', 0):,} & "
                 f"{100 * c['ind_err']:.1f} ({100 * lo:.1f}--{100 * hi:.1f}) & {c['naive_decided']:,} & "
                 f"{c.get('naive_wrong', 0):,} & " +
                 (f"{100 * c['naive_err']:.1f} ({100 * nlo:.1f}--{100 * nhi:.1f})" if c["naive_decided"] else "--") +
                 r" \\")
    if fam == "space":
        lines.append(r"\addlinespace")
lines += [r"\bottomrule", r"\end{tabular}"]
(TAB / "tab_e4.tex").write_text("\n".join(lines) + "\n", encoding="utf-8")

SHORT = {"naive": "Single-source (no requests)", "complete": "Completeness-first (IDS-style)",
         "conf0.9": r"Confidence-gated, $\tau=0.90$", "conf0.95": r"Confidence-gated, $\tau=0.95$",
         "value": "Value requests first", "random": "Random request", "fixed": "Model order, cheapest first",
         "degree": "Residual degree", "ec2": "EC$^2$ ambiguity reduction", "sv": r"\textbf{Stability-based VOI (proposed)}",
         "oracle": "Hindsight reference (clairvoyant)"}
for sk in ("H", "D", "A", "S"):
    if sk not in E2:
        continue
    lines = [r"\begin{tabular}{@{}lrrrrrrrr@{}}", r"\toprule",
             r" & \multicolumn{2}{c}{\emph{min} level} & \multicolumn{2}{c}{\emph{std} level} & \multicolumn{4}{c}{\emph{full} level} \\",
             r"\cmidrule(lr){2-3}\cmidrule(lr){4-5}\cmidrule(l){6-9}",
             r"Policy & Effort & Wrong (\%) & Effort & Wrong (\%) & Effort & Wrong (\%) & Questions & Values \\", r"\midrule"]
    for pol in ["naive", "complete", "conf0.9", "conf0.95", "value", "random", "fixed", "degree", "ec2", "sv", "oracle"]:
        if pol == "value":
            lines.append(r"\multicolumn{9}{@{}l}{\emph{Stability-gated policies}} \\")
        cells = []
        for lv in ("min", "std", "full"):
            e = E2[sk].get(f"{lv}|{pol}")
            if e is None:
                cells += ["--"] * (4 if lv == "full" else 2)
                continue
            cells += [f"{e['cost']:,.0f}", "--" if pol == "oracle" else f"{e['wrong_pct']:.2f}"]
            if lv == "full":
                cells += ([f"{e['n_clarify']:,.0f}", f"{e['n_value']:,.0f}"] if pol != "naive" else ["--", "--"])
        name = (r"\quad " if pol in ADAPTIVE else "") + SHORT[pol]
        lines.append(name + " & " + " & ".join(cells) + r" \\")
        if pol in ("complete", "conf0.95", "sv"):
            lines.append(r"\addlinespace")
    lines += [r"\bottomrule", r"\end{tabular}"]
    (TAB / f"tab_e2_{sk}.tex").write_text("\n".join(lines) + "\n", encoding="utf-8")

# E3 compact table (held-out)
lines = [r"\begin{tabular}{@{}lrrrrrrr@{}}", r"\toprule",
         r" & \multicolumn{3}{c}{Effort (units)} & \multicolumn{4}{c}{Wrong conclusions (\%)} \\",
         r"\cmidrule(lr){2-4}\cmidrule(l){5-8}",
         r"Variation & \shortstack{Stability\\VOI} & \shortstack{Residual\\degree} & \shortstack{Compl.-\\first} & "
         r"\shortstack{Stability\\VOI} & \shortstack{Value\\first} & \shortstack{Compl.-\\first} & \shortstack{Single-\\source} \\",
         r"\midrule"]
VAR = [("E2", "Declared catalogue (Experiment 3)"), ("cost1.5", "Value request costs 1.5"), ("cost6", "Value request costs 6"),
       ("de_door", "DIN 18040-1 door rule"), ("mis050", "Truth from catalogue widened by 50\\%"),
       ("mis100", "Truth from catalogue widened by 100\\%"), ("cons050", "Planner and truth on catalogue +50\\%"),
       ("cons100", "Planner and truth on catalogue +100\\%"), ("cons050_decl", "Planner on catalogue +50\\%, truth declared"),
       ("nogeom", "No geometry-derived evidence")]
for key, lab in VAR:
    src = E2.get("H") if key == "E2" else E3.get(f"H|{key}")
    if not src:
        continue
    def g(pol, f):
        e = src.get(f"full|{pol}")
        return e[f] if e else float("nan")
    lines.append(f"{lab} & {g('sv', 'cost'):,.0f} & {g('degree', 'cost'):,.0f} & {g('complete', 'cost'):,.0f} & "
                 f"{g('sv', 'wrong_pct'):.2f} & {g('value', 'wrong_pct'):.2f} & "
                 f"{g('complete', 'wrong_pct'):.2f} & {g('naive', 'wrong_pct'):.2f} \\\\")
lines += [r"\bottomrule", r"\end{tabular}"]
(TAB / "tab_e3.tex").write_text("\n".join(lines) + "\n", encoding="utf-8")

# per-model appendix table (US, full): E1 stable share, unsupported, contradicts; E2 effort and wrong conclusions
lines = [r"\begin{tabular}{@{}llrrrrrrrrr@{}}", r"\toprule",
         r" & & & \multicolumn{3}{c}{Experiment 1 (\%)} & \multicolumn{3}{c}{Experiment 3: effort} & "
         r"\multicolumn{2}{c}{Experiment 3: wrong (\%)} \\",
         r"\cmidrule(lr){4-6}\cmidrule(lr){7-9}\cmidrule(l){10-11}",
         r"Model & Set & Checks & Stable & \shortstack{Unsup-\\ported} & \shortstack{Contra-\\dicts} & "
         r"\shortstack{Stability\\VOI} & \shortstack{Compl.-\\first} & \shortstack{Residual\\degree} & "
         r"\shortstack{Compl.-\\first} & \shortstack{Single-\\source} \\",
         r"\midrule"]
for d in ds:
    p = d["project"]
    c = E1M.get(p, {})
    if not c.get("checks"):
        continue
    def em(pol):
        v = R["e2_model"].get(f"{p}|full|{pol}")
        return f"{v['cost']:,.1f}" if v else "--"
    def ew(pol):
        v = R["e2_model"].get(f"{p}|full|{pol}")
        return f"{100 * v['wrong'] / v['checks']:.1f}" if v and v.get("checks") else "--"
    lines.append(f"{NAMES[p]} & {d['set']} & {c['checks']:,} & {100 * (c.get('STABLE_N', 0) + c.get('STABLE_V', 0)) / c['checks']:.1f} & "
                 f"{100 * c.get('naive_decided_without_sufficient_evidence', 0) / c['checks']:.1f} & "
                 f"{100 * c.get('naive_contradicts_evidence', 0) / c['checks']:.1f} & {em('sv')} & {em('complete')} & "
                 f"{em('degree')} & {ew('complete')} & {ew('naive')} \\\\")
    if p == DEV[-1]:
        lines.append(r"\addlinespace")
lines += [r"\bottomrule", r"\end{tabular}"]
(TAB / "tab_models.tex").write_text("\n".join(lines) + "\n", encoding="utf-8")


# pre-registered primary endpoints P1-P4 on the held-out set (H) and without molio and sixty5 (S, deviation D1)
def endpoint_cells(sk):
    out = {}
    c = E1.get(f"{sk}|US|full|all")
    if c:
        n = c["checks"]
        out["p1s"] = f"{100 * (c.get('STABLE_N', 0) + c.get('STABLE_V', 0)) / n:.1f}"
        out["p1u"] = f"{100 * c.get('naive_decided_without_sufficient_evidence', 0) / n:.1f}"
        out["p1c"] = f"{100 * c.get('naive_contradicts_evidence', 0) / n:.1f}"
    c4 = E4.get(f"{sk}|US|all")
    if c4:
        out["p2m"] = f"{c4.get('ind_wrong', 0):,} of {c4.get('ind_stable', 0):,} ({100 * c4['ind_err_ci'][1]:.1f})"
        out["p2n"] = f"{c4.get('naive_wrong', 0):,} of {c4.get('naive_decided', 0):,}"
        out["p2r"] = f"{c4.get('ref', 0):,}"
    e = E2.get(sk, {})
    if "full|sv" in e:
        for pol, key in (("complete", "p3c"), ("degree", "p3d"), ("ec2", "p3e"), ("fixed", "p3f")):
            rel = REL.get(f"{sk}|full|{pol}")
            if rel:
                pv = rel["p_wilcoxon"]
                out[key] = (f"{rel['saving_pct']:.1f} ({100 * rel['sv_better_share']:.0f}; "
                            + (r"$<$0.001" if pv < 0.001 else f"{pv:.3f}") + ")")
        if "full|oracle" in e:
            out["p3o"] = f"{100 * (e['full|sv']['cost'] / e['full|oracle']['cost'] - 1):.1f}"
        out["p3w"] = f"{e['full|sv']['wrong_pct']:.2f}"
    for lam, key in (("mis050", "p4a"), ("mis100", "p4b")):
        e3 = E3.get(f"{sk}|{lam}")
        if e3 and all(f"full|{p}" in e3 for p in ("sv", "value", "complete")):
            out[key] = " / ".join(f"{e3[f'full|{p}']['wrong_pct']:.2f}" for p in ("sv", "value", "complete"))
    prem = []
    for cons in ("cons050", "cons100"):
        e3 = E3.get(f"{sk}|{cons}")
        if e3 and "full|sv" in e3 and "full|sv" in e:
            prem.append(f"{100 * (e3['full|sv']['cost'] / e['full|sv']['cost'] - 1):.1f}")
    if prem:
        out["p4p"] = " / ".join(prem)
    return out


EH, ES = endpoint_cells("H"), endpoint_cells("S")
ROWS = [("P1", "Stable conclusions from the delivered evidence (\\%)", "p1s"),
        ("", "Single-source checker: decided without sufficient evidence (\\%)", "p1u"),
        ("", "Single-source checker: contradicts the stable conclusion (\\%)", "p1c"),
        ("P2", "Checks with withheld explicit values (references)", "p2r"),
        ("", "Stable conclusions from the remaining evidence: wrong of concluded (95\\% upper bound, \\%)", "p2m"),
        ("", "Face-value checker on the same evidence: wrong of decided", "p2n"),
        ("P3", "Effort saving of stability-based VOI over completeness-first (\\%; draws cheaper, \\%; $p$)", "p3c"),
        ("", "\\quad over residual degree", "p3d"), ("", "\\quad over EC$^2$", "p3e"), ("", "\\quad over model order", "p3f"),
        ("", "Effort above the hindsight reference (\\%)", "p3o"),
        ("", "Wrong conclusions of stability-based VOI (\\%)", "p3w"),
        ("P4", "Wrong conclusions, truth from catalogue +50\\%: stability-based VOI / value first / completeness-first (\\%)", "p4a"),
        ("", "Wrong conclusions, truth from catalogue +100\\% (same policies, \\%)", "p4b"),
        ("", "Effort premium of the catalogue widened by 50\\% / 100\\% (\\%)", "p4p")]
lines = [r"\begin{tabularx}{\textwidth}{@{}lXrr@{}}", r"\toprule",
         rf" & Endpoint (full evidence level, US rulebook) & \shortstack{{Held-out\\({len(SETS['H'])} models)}} & "
         rf"\shortstack{{Without the two\\large models ({len(SETS['S'])})}} \\", r"\midrule"]
for tag, lab, key in ROWS:
    if tag and tag != "P1":
        lines.append(r"\addlinespace")
    lines.append(f"{tag} & {lab} & {EH.get(key, '--')} & {ES.get(key, '--')} \\\\")
lines += [r"\bottomrule", r"\end{tabularx}"]
(TAB / "tab_endpoints.tex").write_text("\n".join(lines) + "\n", encoding="utf-8")

# ============================================================== numbers.tex
M = {}


def f0(x):
    return f"{x:,.0f}"


def f1(x):
    return f"{x:.1f}"


def f2(x):
    return f"{x:.2f}"


def pct(a, b, d=1):
    return f"{100.0 * a / b:.{d}f}" if b else "0"


for sk in ("D", "H", "S", "A"):
    W = SETWORD[sk]
    projs = SETS[sk]
    sub = [d for d in ds if d["project"] in projs]
    M[f"N{W}Models"] = str(len(sub))
    M[f"N{W}Checks"] = f0(sum(d["checks"] for d in sub))
    M[f"N{W}Doors"] = f0(sum(d["doors"] for d in sub))
    M[f"N{W}Railings"] = f0(sum(d["railings"] for d in sub))
    M[f"N{W}Spaces"] = f0(sum(d["spaces"] for d in sub))
    M[f"N{W}StairChecks"] = f0(sum(d["stair_checks"] for d in sub))
    c = E1.get(f"{sk}|US|full|all")
    if c:
        n = c["checks"]
        st = c.get("STABLE_N", 0) + c.get("STABLE_V", 0)
        M[f"Eone{W}Stable"] = f0(st)
        M[f"Eone{W}StablePct"] = pct(st, n)
        M[f"Eone{W}StableN"] = f0(c.get("STABLE_N", 0))
        M[f"Eone{W}StableV"] = f0(c.get("STABLE_V", 0))
        M[f"Eone{W}UnsupPct"] = pct(c.get("naive_decided_without_sufficient_evidence", 0), n)
        M[f"Eone{W}Unsup"] = f0(c.get("naive_decided_without_sufficient_evidence", 0))
        M[f"Eone{W}ContraPct"] = pct(c.get("naive_contradicts_evidence", 0), n)
        M[f"Eone{W}Contra"] = f0(c.get("naive_contradicts_evidence", 0))
        M[f"Eone{W}Conflict"] = f0(c.get("with_conflict", 0))
        M[f"Eone{W}ConflictPct"] = pct(c.get("with_conflict", 0), n)
        for ft in ("unit", "gross", "suspect_default", "intent", "categorical"):
            M[f"Eone{W}Fault{ft.replace('_', '').capitalize()}"] = f0(c.get("fault_" + ft, 0))
        for lv, ln in (("min", "Min"), ("std", "Std")):
            cc = E1.get(f"{sk}|US|{lv}|all")
            if cc:
                M[f"Eone{W}Stable{ln}Pct"] = pct(cc.get("STABLE_N", 0) + cc.get("STABLE_V", 0), cc["checks"])
        for fam in FAMILIES:
            cf = E1.get(f"{sk}|US|full|{fam}")
            if cf:
                M[f"Eone{W}{fam.capitalize()}StablePct"] = pct(cf.get("STABLE_N", 0) + cf.get("STABLE_V", 0), cf["checks"])
                M[f"Eone{W}{fam.capitalize()}UnsupPct"] = pct(cf.get("naive_decided_without_sufficient_evidence", 0), cf["checks"])
        de = E1.get(f"{sk}|DE_DOOR|full|door")
        if de:
            M[f"Eone{W}DeDoors"] = f0(de["checks"])
            M[f"Eone{W}DeStableV"] = f0(de.get("STABLE_V", 0))
            M[f"Eone{W}DeNaiveAccept"] = f0(de.get("naive_contradicts_evidence", 0))
        b = E1B.get(f"{sk}|stable")
        if b:
            M[f"Eone{W}StableBootLo"], M[f"Eone{W}StableBootHi"] = pct(b[1], 1), pct(b[2], 1)
            ub = E1B[f"{sk}|unsupported"]
            M[f"Eone{W}UnsupBootLo"], M[f"Eone{W}UnsupBootHi"] = pct(ub[1], 1), pct(ub[2], 1)
            lo, hi = E1B[f"{sk}|stable_model_range"]
            M[f"Eone{W}StableModelMin"], M[f"Eone{W}StableModelMax"] = pct(lo, 1), pct(hi, 1)
            M[f"Eone{W}StableModelMedian"] = pct(E1B[f"{sk}|stable_model_median"], 1)
    for fam in FAMILIES + ["all"]:
        c4 = E4.get(f"{sk}|US|{fam}")
        if not c4:
            continue
        F = "All" if fam == "all" else fam.capitalize()
        M[f"Efour{W}{F}Ref"] = f0(c4.get("ref", 0))
        M[f"Efour{W}{F}Explicit"] = f0(c4.get("with_explicit", 0))
        M[f"Efour{W}{F}Concluded"] = f0(c4.get("ind_stable", 0))
        M[f"Efour{W}{F}CoveragePct"] = f1(100 * c4.get("coverage", 0))
        M[f"Efour{W}{F}Wrong"] = f0(c4.get("ind_wrong", 0))
        M[f"Efour{W}{F}ErrPct"] = f1(100 * c4.get("ind_err", 0))
        M[f"Efour{W}{F}ErrHi"] = f1(100 * c4["ind_err_ci"][1])
        M[f"Efour{W}{F}NaiveDecided"] = f0(c4.get("naive_decided", 0))
        M[f"Efour{W}{F}NaiveWrong"] = f0(c4.get("naive_wrong", 0))
        M[f"Efour{W}{F}NaiveErrPct"] = f1(100 * c4.get("naive_err", 0))
        M[f"Efour{W}{F}NaiveErrLo"] = f1(100 * c4["naive_err_ci"][0])
        M[f"Efour{W}{F}NaiveErrHi"] = f1(100 * c4["naive_err_ci"][1])
    c4d = E4.get(f"{sk}|DE_DOOR|door")
    if c4d:
        M[f"Efour{W}DeRef"] = f0(c4d.get("ref", 0))
        M[f"Efour{W}DeConcluded"] = f0(c4d.get("ind_stable", 0))
        M[f"Efour{W}DeWrong"] = f0(c4d.get("ind_wrong", 0))
        M[f"Efour{W}DeNaiveDecided"] = f0(c4d.get("naive_decided", 0))
        M[f"Efour{W}DeNaiveWrong"] = f0(c4d.get("naive_wrong", 0))
    if sk in E2:
        e = E2[sk]
        M[f"NSeeds{W}"] = str(e["_seeds"])
        for lv, ln in (("min", "Min"), ("std", "Std"), ("full", "Full")):
            if f"{lv}|sv" not in e:
                continue
            sv = e[f"{lv}|sv"]["cost"]
            M[f"Etwo{W}CostSv{ln}"] = f0(sv)
            M[f"Etwo{W}CostSv{ln}Ci"] = f0(e[f"{lv}|sv"]["cost_ci"])
            M[f"Etwo{W}WrongSv{ln}"] = f"{e[f'{lv}|sv']['wrong_pct']:.3f}"
            M[f"Etwo{W}WrongCountSv{ln}"] = f2(e[f"{lv}|sv"]["wrong"])
            M[f"Etwo{W}ClarifySv{ln}"] = f0(e[f"{lv}|sv"]["n_clarify"])
            M[f"Etwo{W}ValueSv{ln}"] = f0(e[f"{lv}|sv"]["n_value"])
            for pol, pn in (("complete", "Complete"), ("fixed", "Fixed"), ("degree", "Degree"), ("ec2", "Ec"),
                            ("value", "Value"), ("random", "Random"), ("oracle", "Oracle"), ("conf0.9", "ConfNinety"),
                            ("conf0.95", "ConfNinetyFive"), ("naive", "Naive")):
                if f"{lv}|{pol}" not in e:
                    continue
                ec = e[f"{lv}|{pol}"]
                M[f"Etwo{W}Cost{pn}{ln}"] = f0(ec["cost"])
                M[f"Etwo{W}Wrong{pn}{ln}"] = f2(ec["wrong_pct"])
                M[f"Etwo{W}Clarify{pn}{ln}"] = f0(ec["n_clarify"])
                M[f"Etwo{W}ValueReq{pn}{ln}"] = f0(ec["n_value"])
                M[f"Etwo{W}Missed{pn}{ln}"] = f0(ec["missed_violation"])
                M[f"Etwo{W}False{pn}{ln}"] = f0(ec["false_violation"])
                M[f"Etwo{W}WrongCount{pn}{ln}"] = f0(ec["wrong"])
                rel = REL.get(f"{sk}|{lv}|{pol}")
                if rel and rel["saving_pct"] is not None:
                    if pol == "oracle":
                        M[f"Etwo{W}GapOracle{ln}"] = f1(100 * (sv / ec["cost"] - 1))
                    else:
                        M[f"Etwo{W}Save{pn}{ln}"] = f1(rel["saving_pct"])
                        M[f"Etwo{W}Better{pn}{ln}"] = f0(100 * rel["sv_better_share"])
                        p = rel["p_wilcoxon"]
                        M[f"Etwo{W}P{pn}{ln}"] = r"$<$\,0.001" if p < 0.001 else f"= {p:.3f}"
            for other, on in (("complete", "Complete"), ("degree", "Degree"), ("fixed", "Fixed"), ("oracle", "Oracle")):
                b = E2B.get(f"{sk}|{lv}|sv_over_{other}")
                if b:
                    M[f"Etwo{W}Boot{on}{ln}Lo"] = f1(100 * (1 - b[2]))
                    M[f"Etwo{W}Boot{on}{ln}Hi"] = f1(100 * (1 - b[1]))
            ob = E2B.get(f"{sk}|{lv}|oracle_bound")
            if ob:
                M[f"Etwo{W}OracleBound{ln}"] = f"{ob[0]}/{ob[1]}"
            cf = e.get(f"{lv}|conf0.9")
            if cf and cf["wrong"] > 0:
                M[f"Etwo{W}ConfMissedShare{ln}"] = f0(100 * cf["missed_violation"] / cf["wrong"])
            for fam in ("door", "space", "stair", "railing"):
                M[f"Etwo{W}{fam.capitalize()}CostSv{ln}"] = f1(e[f"{lv}|sv"].get(f"cost_{fam}", 0.0))
                if f"{lv}|complete" in e:
                    M[f"Etwo{W}{fam.capitalize()}CostComplete{ln}"] = f1(e[f"{lv}|complete"].get(f"cost_{fam}", 0.0))
            M[f"Etwo{W}SecsSv{ln}"] = f2(e[f"{lv}|sv"]["secs"])
            M[f"Etwo{W}OpenSv{ln}"] = f2(e[f"{lv}|sv"]["escalated_pct"])
        sav = [REL[f"{sk}|{lv}|complete"]["saving_pct"] for lv in ("min", "std", "full")
               if f"{sk}|{lv}|complete" in REL and REL[f"{sk}|{lv}|complete"]["saving_pct"] is not None]
        if sav:
            M[f"Etwo{W}SaveCompleteLevelLo"], M[f"Etwo{W}SaveCompleteLevelHi"] = f1(min(sav)), f1(max(sav))
        a = R["anytime"]
        bi = BUDGETS.index(10)
        for pol, pn in (("sv", "Sv"), ("degree", "Degree"), ("fixed", "Fixed"), ("ec2", "Ec"), ("value", "Value")):
            k = f"{sk}|full|{pol}"
            if k in a:
                M[f"Etwo{W}AnyTen{pn}"] = f1(100 * a[k][bi])
                M[f"Etwo{W}AnyZero"] = f1(100 * a[k][0])
    for name, nm in (("cost1.5", "CostLow"), ("cost6", "CostHigh"), ("de_door", "De"), ("mis050", "MisFifty"),
                     ("mis100", "MisHundred"), ("cons050", "ConsFifty"), ("cons100", "ConsHundred"),
                     ("cons050_decl", "ConsFiftyDecl"), ("nogeom", "NoGeom")):
        e3 = E3.get(f"{sk}|{name}")
        if not e3:
            continue
        for pol, pn in (("sv", "Sv"), ("value", "Value"), ("complete", "Complete"), ("naive", "Naive"),
                        ("conf0.9", "ConfNinety"), ("degree", "Degree"), ("fixed", "Fixed"), ("oracle", "Oracle")):
            ee = e3.get(f"full|{pol}")
            if ee:
                M[f"Ethree{W}{nm}Cost{pn}"] = f0(ee["cost"])
                M[f"Ethree{W}{nm}Wrong{pn}"] = f2(ee["wrong_pct"])
                M[f"Ethree{W}{nm}WrongCount{pn}"] = f1(ee["wrong"])
        sv3 = e3.get("full|sv")
        if sv3 and sv3["wrong"] > 0:
            M[f"Ethree{W}{nm}MissedShareSv"] = f0(100 * sv3["missed_violation"] / sv3["wrong"])
            M[f"Ethree{W}{nm}DoorShareSv"] = f0(100 * sv3["wrong_door"] / sv3["wrong"])
        if sv3:
            M[f"Ethree{W}{nm}ValueReqSv"] = f0(sv3["n_value"])
            M[f"Ethree{W}{nm}ClarifySv"] = f0(sv3["n_clarify"])
        if sv3 and e3.get("full|degree"):
            M[f"Ethree{W}{nm}SaveDegree"] = f1(100 * (1 - sv3["cost"] / e3["full|degree"]["cost"]))
        if sv3 and sk in E2 and "full|sv" in E2[sk]:
            M[f"Ethree{W}{nm}ExtraSv"] = f0(100 * (sv3["cost"] / E2[sk]["full|sv"]["cost"] - 1))
            comp = e3.get("full|complete")
            if comp:
                M[f"Ethree{W}{nm}SaveComplete"] = f1(100 * (1 - sv3["cost"] / comp["cost"]))
        if name == "nogeom":
            for lv, ln in (("min", "Min"), ("std", "Std")):
                for pol, pn in (("sv", "Sv"), ("value", "Value")):
                    ee = e3.get(f"{lv}|{pol}")
                    if ee:
                        M[f"Ethree{W}NoGeom{ln}Cost{pn}"] = f0(ee["cost"])
            if sv3 and sk in E2:
                M[f"Ethree{W}NoGeomFold"] = f1(sv3["cost"] / E2[sk]["full|sv"]["cost"])
    # in how many variations the planner needed less effort than residual degree (full information)
    done = [E3[f"{sk}|{k}"] for k in ("cost1.5", "cost6", "de_door", "mis050", "mis100", "cons050", "cons100",
                                      "cons050_decl", "nogeom") if f"{sk}|{k}" in E3]
    done = [e for e in done if e.get("full|sv") and e.get("full|degree")]
    if done:
        M[f"Ethree{W}SvBelowDegree"] = str(sum(1 for e in done if e["full|sv"]["cost"] < e["full|degree"]["cost"] - 1e-9))
        M[f"Ethree{W}Variations"] = str(len(done))
        sd = [100 * (1 - e["full|sv"]["cost"] / e["full|degree"]["cost"]) for e in done]
        M[f"Ethree{W}SaveDegreeLo"], M[f"Ethree{W}SaveDegreeHi"] = f1(min(sd)), f1(max(sd))
# per-model macros (E1 stable share; E2 effort and wrong conclusions at full information)
MKEY = {"city_house_munich": "CityHouse", "duplex": "Duplex", "fantasy_office_building_1": "OfficeOne",
        "wbdg_office": "Wbdg", "fantasy_hotel_1": "HotelOne", "fantasy_hotel_2": "HotelTwo",
        "fantasy_office_building_2": "OfficeTwo", "fantasy_office_building_3": "OfficeThree",
        "fantasy_residential_building_1": "ResidentialOne", "hitos": "Hitos", "molio": "Molio", "sixty5": "Sixtyfive",
        "west_riverside_hospital": "Hospital"}
FAMN = {"door": "doors", "stair": "stair_checks", "railing": "railings", "space": "spaces"}
for p, K in MKEY.items():
    c = E1M.get(p, {})
    if c.get("checks"):
        M[f"EoneMdl{K}StablePct"] = pct(c.get("STABLE_N", 0) + c.get("STABLE_V", 0), c["checks"])
        M[f"EoneMdl{K}UnsupPct"] = pct(c.get("naive_decided_without_sufficient_evidence", 0), c["checks"])
    for pol, pn in (("sv", "Sv"), ("complete", "Complete"), ("degree", "Degree"), ("naive", "Naive")):
        v = R["e2_model"].get(f"{p}|full|{pol}")
        if not v:
            continue
        M[f"EtwoMdl{K}Cost{pn}"] = f1(v["cost"])
        M[f"EtwoMdl{K}Wrong{pn}Pct"] = pct(v["wrong"], v["checks"])
        for fam in FAMILIES:
            nf = DSP[p][FAMN[fam]]
            if nf:
                M[f"EtwoMdl{K}Wrong{pn}{fam.capitalize()}Pct"] = pct(v.get(f"wrong_{fam}", 0.0), nf)
                M[f"EtwoMdl{K}Cost{pn}{fam.capitalize()}"] = f1(v.get(f"cost_{fam}", 0.0))
held_cmp = [(p, R["e2_model"].get(f"{p}|full|sv"), R["e2_model"].get(f"{p}|full|complete")) for p in HELD]
held_cmp = [(p, a["cost"], b["cost"]) for p, a, b in held_cmp if a and b]
if held_cmp:
    M["EtwoHeldModelsSvBelowComplete"] = str(sum(1 for _, a, b in held_cmp if a < b - 1e-9))
    M["EtwoHeldModelsCompared"] = str(len(held_cmp))
for sk in ("D", "H", "S"):
    for fam in FAMILIES:
        cf = E1.get(f"{sk}|US|full|{fam}")
        if cf:
            M[f"Eone{SETWORD[sk]}{fam.capitalize()}NoSourcePct"] = pct(cf.get("naive_no_designated_source", 0), cf["checks"])
            M[f"Eone{SETWORD[sk]}{fam.capitalize()}Checks"] = f0(cf["checks"])
M["NBoot"] = f0(NBOOT)
_e3seeds =[v["_seeds"] for k, v in E3.items() if k.startswith("H|")]
M["NSeedsEthree"] = str(min(_e3seeds)) if _e3seeds else "0"
M["NEfourDisagree"] = str(len(R["e4_disagreements"]))
with open(R10 / "manuscript" / "numbers.tex", "w", encoding="utf-8") as fh:
    fh.write("% Generated by make_results.py from outputs/results/results.json -- do not edit by hand\n")
    for k in sorted(M):
        v = M[k]
        if v.startswith("-") and v[1:].replace("0", "").replace(".", "") == "":
            v = v[1:]  # negative zero after rounding
        if v.startswith("-") and v[1:2].isdigit():
            v = "$-$" + v[1:]  # typographic minus in text
        fh.write(f"\\newcommand{{\\{k}}}{{{v}}}\n")
(OUT / "results" / "results.json").write_text(json.dumps(R, indent=1, default=float), encoding="utf-8")
print("numbers.tex macros:", len(M))
for sk in ("D", "H", "S", "A"):
    c = E1.get(f"{sk}|US|full|all")
    if c:
        print(sk, "E1 stable", pct(c.get("STABLE_N", 0) + c.get("STABLE_V", 0), c["checks"]), "unsup",
              pct(c.get("naive_decided_without_sufficient_evidence", 0), c["checks"]), "contra",
              pct(c.get("naive_contradicts_evidence", 0), c["checks"]), "checks", c["checks"])
    c4 = E4.get(f"{sk}|US|all")
    if c4:
        print(sk, "E4", {k: c4[k] for k in ("ref", "ind_stable") if k in c4}, "wrong", c4.get("ind_wrong", 0),
              "naive decided/wrong", c4.get("naive_decided"), c4.get("naive_wrong", 0))
    if sk in E2:
        for lv in ("min", "std", "full"):
            line = []
            for pol in POLICIES:
                e = E2[sk].get(f"{lv}|{pol}")
                if e:
                    line.append(f"{pol}:{e['cost']:.0f}/{e['wrong_pct']:.3f}")
            print(sk, lv, " ".join(line))
print("E4 disagreements:", len(R["e4_disagreements"]))
for r in R["e4_disagreements"]:
    print("  ", r["project"], r["rulebook"], r["group"], r["explicit"], r["ref_support"], r["ind_support"],
          r["ind_decision"], r["ref_decision"])
