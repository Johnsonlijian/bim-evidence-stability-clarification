"""R10 figures (vector PDF + PNG preview) from outputs/results/results.json and the ledgers.

Usage: python -E -P make_figures.py <R10 dir> [cases,e1,e4,models,anytime,e3,pareto]
Palette: validated categorical order (blue, orange, aqua, yellow, magenta, violet); gray only for 'no conclusion'.
"""
import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
from matplotlib.patches import Patch  # noqa: E402

R10 = Path(sys.argv[1])
sys.path.insert(0, str(R10 / "src"))
from bimev import catalog as C  # noqa: E402
from bimev.engine import ClusterModel, _key  # noqa: E402

OUT = R10 / "outputs"
FIG = R10 / "figures"
FIG.mkdir(parents=True, exist_ok=True)
R = json.loads((OUT / "results" / "results.json").read_text(encoding="utf-8"))

BLUE, ORANGE, AQUA, YELLOW, MAGENTA, VIOLET = "#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#4a3aa7"
INK, INK2, MUTED, GRID, AXIS = "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#a8a69f"
NEUTRAL = "#c9c7c0"
plt.rcParams.update({
    "font.family": "sans-serif", "font.sans-serif": ["Arial", "DejaVu Sans"], "font.size": 7.5,
    "axes.titlesize": 8, "axes.labelsize": 7.5, "xtick.labelsize": 7, "ytick.labelsize": 7, "legend.fontsize": 7,
    "axes.edgecolor": AXIS, "axes.linewidth": 0.6, "xtick.color": INK2, "ytick.color": INK2,
    "xtick.major.width": 0.6, "ytick.major.width": 0.6, "xtick.major.size": 2.5, "ytick.major.size": 2.5,
    "axes.labelcolor": INK, "text.color": INK, "axes.grid": False, "grid.color": GRID, "grid.linewidth": 0.5,
    "axes.spines.top": False, "axes.spines.right": False, "legend.frameon": False, "pdf.fonttype": 42,
    "savefig.dpi": 300, "figure.dpi": 150,
})
W2 = 7.0
NAMES = {"city_house_munich": "City house Munich", "duplex": "Duplex apartment",
         "fantasy_office_building_1": "Student office 1", "wbdg_office": "WBDG office",
         "fantasy_hotel_1": "Student hotel 1", "fantasy_hotel_2": "Student hotel 2",
         "fantasy_office_building_2": "Student office 2", "fantasy_office_building_3": "Student office 3",
         "fantasy_residential_building_1": "Student residential 1", "hitos": "HITOS", "molio": "Molio demo building",
         "sixty5": "Sixty5", "west_riverside_hospital": "West Riverside hospital"}


def save(fig, name):
    fig.savefig(FIG / f"{name}.pdf", bbox_inches="tight", pad_inches=0.02)
    fig.savefig(FIG / f"{name}.png", bbox_inches="tight", pad_inches=0.02, dpi=200)
    plt.close(fig)


# =================================================================== Fig. cases
def case_rows(ledger, gid, rulebook="US"):
    cid = ledger["groups"][gid]["cluster"]
    cm = ClusterModel(cid, ledger, C.LEVEL_RANK["full"], rulebook)
    cm.solve()
    gm = next(g for g in cm.groups if g.gid == gid)
    hyps = cm.vs[gm.gid]
    rows = []
    for s in gm.num_sources:
        used, declared = [], []
        for key, modes in s["table"].items():
            for mode, (lo, hi) in modes.items():
                hit = False
                for h in hyps:
                    assign = {**dict(zip(cm.shared, h.a)), **h.b}
                    if _key([assign[d] for d in s["deps"]]) != key:
                        continue
                    if any(lo - 1e-9 <= 0.5 * (l + u) <= hi + 1e-9 for l, u in h.segs):
                        hit = True
                if hit:
                    used.append((lo, hi, key, mode))
                elif mode == "ok":
                    declared.append((lo, hi, key, mode))
        status = "retained" if any(m == "ok" for *_, m in used) else ("reinterpreted" if used else "overruled")
        rows.append({"label": s["labels"], "value": s.get("value_mm"), "used": used, "declared": declared,
                     "suspect": s["suspect"], "intent": float(s.get("weight", 1.0)) == 0.0, "status": status})
    if gm.family == "door":
        cfgs = {str(({**dict(zip(cm.shared, h.a)), **h.b}).get(gm.cat_vars[0])) for h in hyps}
        for r in rows:
            r["declared"] = [d for d in r["declared"] if d[2].split("|")[-1] in cfgs]
            r["used"] = [d for d in r["used"] if d[2] == "" or d[2].split("|")[-1] in cfgs]
    adm = [(l, u) for h in hyps for l, u in h.segs]
    return gm, rows, adm, cm.status(gm.gid)[0]


LABELS = {
    "Pset_StairFlightCommon.RiserHeight": "riser properties (3, concordant)",
    "Dimensions.Actual Riser Height": "riser properties (3, concordant)",
    "Pset_StairCommon.RiserHeight (stair)": "riser properties (3, concordant)",
    "Calculation Rules.Maximum Riser Height (stair rule)": "stair calculation rule (design intent)",
    "IfcDoor.OverallWidth": "IfcDoor.OverallWidth",
    "Type name nominal width": "nominal size in type name",
    "Dimensions.Angabe Lichter Durchgang Breite": "clear passage (2 properties)",
    "Dimensions.Durchgangsbreite": "clear passage (2 properties)",
    "Dimensions.Angabe Maueröffnungsmaß Breite": "masonry opening property",
    "Dimensions.Rough Width": "rough opening and Qto width (2)",
    "Qto_DoorBaseQuantities.Width": "rough opening and Qto width (2)",
    "Dimensions.Width": "generic width parameter",
    "Body extent (local X)": "body extent along the wall",
    "Type-name nominal height": "nominal height in type name",
    "Pset_RailingCommon.Height": "Pset_RailingCommon.Height",
    "BaseQuantities.ClearHeight": "clear and finish ceiling height (2)",
    "BaseQuantities.FinishCeilingHeight": "clear and finish ceiling height (2)",
    "BaseQuantities.Height": "BaseQuantities.Height",
}


def label_of(labels):
    for lab in labels:
        if lab in LABELS:
            return LABELS[lab]
    for lab in labels:
        if lab.startswith("Body rise"):
            return "flight body rise / riser count"
    lab = labels[0]
    return lab if len(lab) <= 38 else lab[:36] + "…"


def fig_cases():
    led = {}
    for sub in ("dev", "heldout"):
        for f in (OUT / sub / "ledgers").glob("ledger_*.json"):
            led[f.stem.replace("ledger_", "")] = json.loads(f.read_text(encoding="utf-8"))
    cases = [
        ("city_house_munich", "city_house_munich|stair_riser|28915|g0", (140, 260),
         "(a) Stair riser, City house Munich (development)", [(196.0, "IRC max 196", "left")]),
        ("fantasy_office_building_2", "fantasy_office_building_2|door|1|g0", (520, 1000),
         "(b) Door clear width, Student office 2 (held-out)", [(813.0, "IBC 813", "left")]),
        ("west_riverside_hospital", "west_riverside_hospital|rail|0|g0", (820, 1300),
         "(c) Railing height, West Riverside hospital (held-out)",
         [(1067.0, "guard min 1067", "left"), (965.0, "handrail max 965", "right")]),
        ("sixty5", "sixty5|space|370970", (800, 3400), "(d) Ceiling height, Sixty5 (held-out)",
         [(2286.0, "IBC 2286", "left")]),
    ]
    fig, axes = plt.subplots(2, 2, figsize=(W2, 5.0))
    for ax, (proj, gid, xlim, title, thresholds) in zip(axes.flat, cases):
        gm, rows, adm, status = case_rows(led[proj], gid)
        merged, order = {}, []
        for r in rows:
            lab = label_of(r["label"])
            if lab not in merged:
                merged[lab] = r
                order.append(lab)
        span = xlim[1] - xlim[0]
        y = 0
        yt, yl = [], []
        for lab in order:
            r = merged[lab]
            for lo, hi, key, mode in r["declared"]:
                lo2, hi2 = max(lo, xlim[0]), min(hi, xlim[1])
                if hi2 > lo2 + 0.01 * span:
                    ax.plot([lo2, hi2], [y, y], color=NEUTRAL, lw=2.4, solid_capstyle="butt", zorder=1)
                elif xlim[0] <= 0.5 * (lo + hi) <= xlim[1]:
                    ax.plot([0.5 * (lo + hi)], [y], marker="x", ms=4.5, mew=1.1, color=MUTED, zorder=2)
            for lo, hi, key, mode in r["used"]:
                lo2, hi2 = max(lo, xlim[0]), min(hi, xlim[1])
                if hi2 - lo2 > 0.008 * span:
                    ax.plot([lo2, hi2], [y, y], color=BLUE, lw=3.2, solid_capstyle="butt", zorder=3)
                elif xlim[0] <= 0.5 * (lo + hi) <= xlim[1]:
                    ax.plot([0.5 * (lo + hi)], [y], marker="o", ms=4.2, color=BLUE, zorder=4,
                            markeredgecolor="white", markeredgewidth=0.7)
            note = None
            if r["intent"]:
                note = None if r["status"] == "retained" else f"design intent {r['value']:.0f}, not met"
            elif r["status"] == "reinterpreted":
                note = f"stored {r['value']:,.0f} read in another unit"
            elif r["status"] == "overruled":
                note = ("suspected default " if r["suspect"] else "overruled ") + \
                       (f"({r['value']:,.1f})" if r["value"] else "")
            if r["value"] is not None and not r["intent"] and not (xlim[0] <= r["value"] <= xlim[1]) and \
                    r["status"] != "reinterpreted":
                note = (note + "; " if note else "") + f"stored {r['value']:,.0f}"
            if note:
                # above the row whenever a drawn mark reaches into the right part of the axis
                busy = any(min(hi, xlim[1]) > xlim[0] + 0.55 * span and max(lo, xlim[0]) < xlim[1]
                           for lo, hi, _, _ in r["declared"] + r["used"])
                ax.text(xlim[1] - 0.008 * span, y - (0.42 if busy else 0.0), note, color=INK2, fontsize=5.9,
                        ha="right", va="center", bbox=dict(boxstyle="square,pad=0.15", fc="white", ec="none"),
                        zorder=6)
            yt.append(y)
            yl.append(lab + (" *" if r["suspect"] else ""))
            y += 1
        y += 0.35
        for l, u in adm:
            l2, u2 = max(l, xlim[0]), min(u, xlim[1])
            if u2 - l2 > 0.008 * span:
                ax.plot([l2, u2], [y, y], color=ORANGE, lw=5.0, solid_capstyle="butt", zorder=3)
            else:
                ax.plot([0.5 * (l + u)], [y], marker="D", ms=4.6, color=ORANGE, zorder=4,
                        markeredgecolor="white", markeredgewidth=0.7)
        yt.append(y)
        yl.append("admissible set")
        for th, lab, side in thresholds:
            ax.axvline(th, color=INK, lw=0.8, zorder=0)
            ax.text(th + (0.01 if side == "left" else -0.01) * span, -1.05, lab, fontsize=6.1, color=INK,
                    ha=("left" if side == "left" else "right"), va="bottom")
        verdict = {"STABLE_N": "stable: no violation", "STABLE_V": "stable: violation", "UNSTABLE": "not stable"}[status]
        ax.text(xlim[1] - 0.008 * span, y + 0.55, verdict, fontsize=6.3, color=INK, ha="right", va="top",
                fontweight="bold")
        ax.set_yticks(yt, yl)
        ax.set_ylim(y + 1.1, -1.3)
        ax.set_xlim(*xlim)
        ax.set_xlabel("code quantity (mm)")
        ax.set_title(title, loc="left", fontsize=7.4, pad=11)
        ax.tick_params(axis="y", length=0, labelsize=6.6)
        ax.spines["left"].set_visible(False)
        ax.grid(axis="x", color=GRID, lw=0.5)
        ax.set_axisbelow(True)
    handles = [Line2D([0], [0], color=BLUE, lw=3.2, label="retained reading"),
               Line2D([0], [0], color=NEUTRAL, lw=2.4, label="reading not retained"),
               Line2D([0], [0], marker="x", color=MUTED, lw=0, mew=1.1, label="stored value not retained"),
               Line2D([0], [0], color=ORANGE, lw=5.0, label="admissible set"),
               Line2D([0], [0], color=INK, lw=0.8, label="code limit")]
    fig.legend(handles=handles, loc="lower center", ncol=5, bbox_to_anchor=(0.5, -0.02), fontsize=6.4)
    fig.tight_layout(rect=(0, 0.035, 1, 1), h_pad=1.8, w_pad=1.5)
    save(fig, "fig_cases")


# =================================================================== Fig. E1
def fig_e1():
    E1 = R["e1"]
    fams = [("all", "All checks"), ("door", "Door clear width"), ("stair", "Stair riser and tread"),
            ("railing", "Guard and handrail height"), ("space", "Ceiling height")]
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(W2, 3.7), gridspec_kw={"width_ratios": [1.0, 1.1]})
    y = 0.0
    yt, yl, heads = [], [], []
    for fam, flab in fams:
        heads.append((y - 0.75, flab))
        for sk, sl in (("D", "development"), ("H", "held-out")):
            c = E1.get(f"{sk}|US|full|{fam}")
            if not c:
                continue
            n = c["checks"]
            x = 0.0
            for v, col in ((c.get("STABLE_N", 0) / n, BLUE), (c.get("STABLE_V", 0) / n, ORANGE),
                           (c.get("UNSTABLE", 0) / n, NEUTRAL)):
                a1.barh(y, v * 100, left=x * 100, height=0.66, color=col, edgecolor="white", linewidth=0.8)
                x += v
            a1.text(101.5, y, f"{n:,}", fontsize=6.0, va="center", ha="left", color=INK2)
            yt.append(y)
            yl.append(sl)
            y += 1.0
        y += 1.0
    a1.set_xlim(0, 100)
    a1.set_ylim(y - 0.8, -1.4)
    a1.set_yticks(yt, yl)
    a1.set_xlabel("share of element checks (%)")
    a1.tick_params(axis="y", length=0, labelsize=6.6)
    a1.spines["left"].set_visible(False)
    for yy, lab in heads:
        a1.text(-0.42, yy, lab, fontsize=6.9, fontweight="bold", ha="left", va="center",
                transform=a1.get_yaxis_transform())
    a1.set_title("(a) Conclusion from the delivered evidence", loc="left", pad=6, x=-0.42)
    a1.legend(handles=[Patch(color=BLUE, label="stable: no violation"), Patch(color=ORANGE, label="stable: violation"),
                       Patch(color=NEUTRAL, label="not stable")], loc="upper left", bbox_to_anchor=(-0.42, -0.13),
              ncol=3, fontsize=6.4, handlelength=1.2, columnspacing=1.0)
    M = R["e1_model"]
    ds = {d["project"]: d for d in R["dataset"]}
    order = sorted([p for p in M if M[p].get("checks")],
                   key=lambda p: (ds[p]["set"], -(M[p].get("STABLE_N", 0) + M[p].get("STABLE_V", 0)) / M[p]["checks"]))
    for i, p in enumerate(order):
        c = M[p]
        n = c["checks"]
        st = 100 * (c.get("STABLE_N", 0) + c.get("STABLE_V", 0)) / n
        un = 100 * c.get("naive_decided_without_sufficient_evidence", 0) / n
        co = 100 * c.get("naive_contradicts_evidence", 0) / n
        a2.plot([st], [i], marker="o", ms=4.6, color=BLUE, mec="white", mew=0.6, zorder=3)
        a2.plot([un], [i], marker="s", ms=4.0, color=YELLOW, mec="white", mew=0.6, zorder=3)
        a2.plot([co], [i], marker="^", ms=4.4, color=ORANGE, mec="white", mew=0.6, zorder=3)
    a2.set_yticks(range(len(order)), [f"{NAMES[p]} ({ds[p]['set']}, {M[p]['checks']:,})" for p in order])
    a2.set_ylim(len(order) - 0.4, -0.6)
    a2.set_xlim(-2, 102)
    a2.set_xlabel("share of the model's checks (%)")
    a2.tick_params(axis="y", length=0, labelsize=6.3)
    a2.spines["left"].set_visible(False)
    a2.grid(axis="x", color=GRID, lw=0.5)
    a2.set_axisbelow(True)
    nd = sum(1 for p in order if ds[p]["set"] == "D")
    a2.axhline(nd - 0.5, color=AXIS, lw=0.6)
    a2.set_title("(b) Per model (D: development, H: held-out)", loc="left", pad=6)
    a2.legend(handles=[Line2D([0], [0], marker="o", color=BLUE, lw=0, ms=4.6, label="stable"),
                       Line2D([0], [0], marker="s", color=YELLOW, lw=0, ms=4.0,
                              label="single-source decides without sufficient evidence"),
                       Line2D([0], [0], marker="^", color=ORANGE, lw=0, ms=4.4,
                              label="single-source contradicts the evidence")],
              loc="upper left", bbox_to_anchor=(-0.02, -0.13), ncol=1, fontsize=6.3)
    fig.tight_layout(w_pad=2.0)
    save(fig, "fig_e1_status")


# =================================================================== Fig. E4
def fig_e4():
    E4 = R["e4"]
    fams = [("door", "Door clear width"), ("stair", "Stair riser and tread"), ("railing", "Guard and handrail height"),
            ("space", "Ceiling height")]
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(W2, 2.4), sharey=True)
    for i, (fam, lab) in enumerate(fams):
        c = E4.get(f"A|US|{fam}", {})
        n = c.get("ref", 0)
        if not n:
            continue
        ok, wr, op = c.get("ind_agree", 0), c.get("ind_wrong", 0), c.get("ind_open", 0)
        x = 0.0
        for v, col in ((ok, BLUE), (wr, ORANGE), (op, NEUTRAL)):
            a1.barh(i, 100 * v / n, left=100 * x / n, height=0.62, color=col, edgecolor="white", linewidth=0.8)
            x += v
        a1.text(101.5, i, f"{ok + wr:,} of {n:,}", fontsize=6.0, va="center", ha="left", color=INK2)
        na, nw, npend = c.get("naive_agree", 0), c.get("naive_wrong", 0), c.get("naive_pending", 0)
        x = 0.0
        for v, col in ((na, AQUA), (nw, ORANGE), (npend, NEUTRAL)):
            a2.barh(i, 100 * v / n, left=100 * x / n, height=0.62, color=col, edgecolor="white", linewidth=0.8)
            x += v
        a2.text(101.5, i, f"{nw:,} of {na + nw:,}", fontsize=6.0, va="center", ha="left", color=INK2)
    a1.set_yticks(range(len(fams)), [f for _, f in fams])
    a1.set_ylim(len(fams) - 0.4, -0.6)
    for ax in (a1, a2):
        ax.set_xlim(0, 100)
        ax.set_xlabel("share of checks with a withheld explicit value (%)")
        ax.tick_params(axis="y", length=0, labelsize=6.6)
        ax.spines["left"].set_visible(False)
    a1.set_title("(a) Interpretation-invariant conclusion", loc="left", pad=6)
    a2.set_title("(b) Face-value checker", loc="left", pad=6)
    a1.legend(handles=[Patch(color=BLUE, label="agrees with withheld value"), Patch(color=ORANGE, label="contradicts it"),
                       Patch(color=NEUTRAL, label="left open")], loc="upper left", bbox_to_anchor=(-0.5, -0.22),
              ncol=3, fontsize=6.2, handlelength=1.2, columnspacing=0.8)
    a2.legend(handles=[Patch(color=AQUA, label="agrees"), Patch(color=ORANGE, label="contradicts"),
                       Patch(color=NEUTRAL, label="no designated source")], loc="upper left",
              bbox_to_anchor=(0.0, -0.22), ncol=3, fontsize=6.2, handlelength=1.2, columnspacing=0.8)
    fig.tight_layout(w_pad=3.5)
    save(fig, "fig_e4_validation")


# =================================================================== Fig. E2
POLS = [("naive", "Single-source (no requests)"), ("complete", "Completeness-first (IDS-style)"),
        ("conf0.8", r"Confidence-gated, $\tau$ = 0.80"), ("conf0.9", r"Confidence-gated, $\tau$ = 0.90"),
        ("conf0.95", r"Confidence-gated, $\tau$ = 0.95"), ("value", "Value requests first"),
        ("random", "Random request"), ("fixed", "Model order, cheapest first"), ("degree", "Residual degree"),
        ("ec2", "EC$^2$ ambiguity reduction"), ("sv", "Stability VOI (proposed)"), ("oracle", "Hindsight reference")]


def fig_e2_pareto(sk="H"):
    E2 = R["e2"][sk]
    levels = [("min", BLUE, "o"), ("std", ORANGE, "s"), ("full", AQUA, "D")]
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(W2, 3.4), sharey=True, gridspec_kw={"width_ratios": [1.25, 1.0]})
    n = len(POLS)
    xmax_w = 0.0
    for i, (pol, lab) in enumerate(POLS):
        if pol == "sv":
            for ax in (a1, a2):
                ax.axhspan(i - 0.45, i + 0.45, color="#eef4fc", zorder=0, lw=0)
        for j, (lv, col, mk) in enumerate(levels):
            e = E2.get(f"{lv}|{pol}")
            if e is None:
                continue
            dy = (j - 1) * 0.22
            if e["cost"] > 0:
                a1.errorbar(e["cost"], i + dy, xerr=e["cost_ci"], fmt=mk, color=col, ms=3.8, mec="white", mew=0.5,
                            elinewidth=0.7, capsize=0, zorder=3)
            else:
                a1.plot([1.0], [i + dy], marker=mk, color=col, ms=3.8, mec="white", mew=0.5, zorder=3)
            if pol != "oracle":
                a2.errorbar(e["wrong_pct"], i + dy, xerr=e["wrong_pct_ci"], fmt=mk, color=col, ms=3.8, mec="white",
                            mew=0.5, elinewidth=0.7, capsize=0, zorder=3)
                xmax_w = max(xmax_w, e["wrong_pct"] + e["wrong_pct_ci"])
    a1.set_xscale("log")
    hi = max(E2[f"{lv}|complete"]["cost"] for lv, _, _ in levels) * 2.2
    a1.set_xlim(0.8, hi)
    ticks = [t for t in (1, 10, 100, 1000, 10000) if t < hi]
    a1.set_xticks(ticks, ["0" if t == 1 else f"{t:,}" for t in ticks])
    a1.set_xlabel("acquisition effort, held-out portfolio (effort units, log scale)")
    a2.set_xlim(-0.02 * xmax_w, xmax_w * 1.08)
    a2.set_xlabel("wrong conclusions (% of held-out checks)")
    a1.set_yticks(range(n), [lab for _, lab in POLS])
    a1.set_ylim(n - 0.5, -0.6)
    for ax in (a1, a2):
        ax.grid(axis="x", color=GRID, lw=0.5)
        ax.set_axisbelow(True)
        ax.tick_params(axis="y", length=0, labelsize=6.8)
        ax.spines["left"].set_visible(False)
    a1.set_title("(a) Effort", loc="left")
    a2.set_title("(b) Wrong conclusions", loc="left")
    handles = [Line2D([0], [0], marker=mk, color=col, lw=0, ms=4.5, label=f"evidence level: {lv}")
               for lv, col, mk in levels]
    fig.legend(handles=handles, loc="lower center", ncol=3, bbox_to_anchor=(0.6, -0.03), fontsize=6.6)
    fig.tight_layout(rect=(0, 0.05, 1, 1), w_pad=1.2)
    save(fig, "fig_e2_pareto")


def fig_e2_models():
    """Per model at full information: effort relative to completeness-first checking, and wrong conclusions."""
    DEVM = ["city_house_munich", "duplex", "fantasy_office_building_1", "wbdg_office"]
    HELDM = ["fantasy_hotel_1", "fantasy_hotel_2", "fantasy_office_building_2", "fantasy_office_building_3",
             "fantasy_residential_building_1", "hitos", "molio", "sixty5", "west_riverside_hospital"]
    em = R["e2_model"]

    def g(p, pol):
        return em.get(f"{p}|full|{pol}")
    order = sorted(HELDM, key=lambda p: -g(p, "sv")["checks"]) + sorted(DEVM, key=lambda p: -g(p, "sv")["checks"])
    labels = [f"{NAMES[p]} ({'H' if p in HELDM else 'D'}, {g(p, 'sv')['checks']:,.0f})" for p in order]
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(W2, 3.5), sharey=True, gridspec_kw={"width_ratios": [1.35, 1.0]})
    eff = [("oracle", "Hindsight reference", INK2, "o", "white"), ("value", "Value first", YELLOW, "^", None),
           ("degree", "Residual degree", VIOLET, "v", None), ("sv", "Stability VOI (proposed)", BLUE, "D", None)]
    lo_r, hi_r = 1.0, 1.0
    for i, p in enumerate(order):
        base = g(p, "complete")["cost"]
        for k, (pol, lab, col, mk, fc) in enumerate(eff):
            r = g(p, pol)["cost"] / base
            lo_r, hi_r = min(lo_r, r), max(hi_r, r)
            a1.plot(r, i, marker=mk, color=col, mfc=fc or col, ms=4.2 if pol == "sv" else 3.8, mec=col if fc else "white",
                    mew=0.8 if fc else 0.5, lw=0, zorder=4 if pol == "sv" else 3, label=lab if i == 0 else None)
        a1.text(1.02, i, f"{base:,.0f}", transform=a1.get_yaxis_transform(), va="center", ha="left", fontsize=6.0,
                color=INK2)
    a1.axvline(1.0, color=MUTED, lw=0.9, zorder=2)
    a1.set_xscale("log")
    a1.set_xlim(lo_r / 1.4, max(hi_r * 1.4, 1.6))
    a1.set_xticks([0.02, 0.05, 0.1, 0.2, 0.5, 1, 2], ["0.02", "0.05", "0.1", "0.2", "0.5", "1", "2"])
    a1.set_xticks([], minor=True)
    a1.set_xlabel("effort relative to completeness-first checking (log scale)")
    a1.text(1.02, -1.0, "Compl.-first\n(units)", transform=a1.get_yaxis_transform(), va="bottom", ha="left",
            fontsize=5.8, color=INK2, linespacing=1.0)
    wr = [("complete", "Completeness-first", MUTED, "s"), ("naive", "Single-source", INK2, "o"),
          ("sv", "Stability VOI (proposed)", BLUE, "D")]
    xmax = 0.0
    for i, p in enumerate(order):
        for pol, lab, col, mk in wr:
            v = g(p, pol)
            w = 100 * v["wrong"] / v["checks"]
            xmax = max(xmax, w)
            a2.plot(w, i, marker=mk, color=col, ms=3.8, mec="white", mew=0.5, lw=0, zorder=3,
                    label=lab if i == 0 else None)
    a2.set_xlim(-0.03 * xmax, xmax * 1.08)
    a2.set_xlabel("wrong conclusions (% of the model's checks)")
    nh = len(HELDM)
    for ax in (a1, a2):
        ax.axhline(nh - 0.5, color=AXIS, lw=0.6, ls=(0, (2, 2)))
        ax.grid(axis="x", color=GRID, lw=0.5)
        ax.set_axisbelow(True)
        ax.tick_params(axis="y", length=0, labelsize=6.8)
        ax.spines["left"].set_visible(False)
    a1.set_yticks(range(len(order)), labels)
    a1.set_ylim(len(order) - 0.5, -0.7)
    a1.set_title("(a) Effort", loc="left")
    a2.set_title("(b) Wrong conclusions", loc="left")
    a1.legend(loc="upper center", bbox_to_anchor=(0.45, -0.13), ncol=2, fontsize=6.4, handletextpad=0.3,
              columnspacing=1.0)
    a2.legend(loc="upper center", bbox_to_anchor=(0.5, -0.13), ncol=2, fontsize=6.4, handletextpad=0.3,
              columnspacing=1.0)
    fig.tight_layout(w_pad=3.6)
    save(fig, "fig_e2_models")


def fig_e2_anytime(sk="H"):
    B = R["anytime_budgets"]
    # drawing order: lower layers first; EC2 and residual degree nearly coincide, so EC2 is drawn dotted on top
    series = [("random", "Random", MAGENTA, "P"), ("value", "Value first", YELLOW, "^"),
              ("fixed", "Model order", AQUA, "s"), ("degree", "Residual degree", VIOLET, "v"),
              ("ec2", "EC$^2$", ORANGE, "o"), ("sv", "Stability VOI (proposed)", BLUE, "D")]
    style = {"degree": dict(ls="-", lw=1.9), "ec2": dict(ls=(0, (1.2, 1.2)), lw=1.2)}
    fig, axes = plt.subplots(1, 3, figsize=(W2, 2.45), sharey=True)
    for k, (ax, lv) in enumerate(zip(axes, ("min", "std", "full"))):
        for pol, lab, col, mk in series:
            v = R["anytime"].get(f"{sk}|{lv}|{pol}")
            if v is None:
                continue
            st = style.get(pol, dict(ls="-", lw=1.3))
            ax.plot(B, np.array(v) * 100, color=col, marker=mk, ms=2.6, mec="white", mew=0.4, label=lab, **st)
        ax.set_xscale("symlog", linthresh=10)
        ax.set_xlim(0, 300)
        ax.set_xticks([0, 2, 5, 10, 20, 50, 100, 300], ["0", "2", "5", "10", "20", "50", "100", "300"])
        ax.set_xlabel("effort budget per model (effort units)")
        ax.set_title(f"({'abc'[k]}) Evidence level {lv}", loc="left", fontsize=7.6)
        ax.grid(color=GRID, lw=0.5)
        ax.set_axisbelow(True)
    axes[0].set_ylabel("held-out checks with a conclusion (%)")
    h, l = axes[0].get_legend_handles_labels()
    h, l = h[::-1], l[::-1]  # legend in order of merit, proposed first
    fig.legend(h, l, loc="lower center", ncol=6, bbox_to_anchor=(0.5, -0.07), fontsize=6.5)
    fig.tight_layout(rect=(0, 0.05, 1, 1))
    save(fig, "fig_e2_anytime")


def fig_e3(sk="H"):
    E2, E3 = R["e2"][sk], R["e3"]
    fig, axes = plt.subplots(1, 3, figsize=(W2, 3.05))
    leg = dict(loc="upper center", bbox_to_anchor=(0.5, -0.24), fontsize=5.9, ncol=2, handlelength=1.8,
               columnspacing=1.0)
    ax = axes[0]
    lam = [0.0, 0.5, 1.0]
    src = {0.0: E2, 0.5: E3.get(f"{sk}|mis050", {}), 1.0: E3.get(f"{sk}|mis100", {})}
    for pol, lab, col, mk in [("naive", "Single-source", INK2, "s"), ("conf0.9", "Confidence 0.90", ORANGE, "^"),
                              ("sv", "Stability VOI", BLUE, "D"), ("complete", "Completeness-first", MUTED, "s"),
                              ("value", "Value first", YELLOW, "v")]:
        ys = [src[l].get(f"full|{pol}", {}).get("wrong_pct", np.nan) for l in lam]
        es = [src[l].get(f"full|{pol}", {}).get("wrong_pct_ci", 0) for l in lam]
        ax.errorbar(lam, ys, yerr=es, color=col, marker=mk, ms=4, lw=1.3, mec="white", mew=0.5, capsize=0,
                    elinewidth=0.6, label=lab)
    cons = {0.0: E2, 0.5: E3.get(f"{sk}|cons050", {}), 1.0: E3.get(f"{sk}|cons100", {})}
    ys = [cons[l].get("full|sv", {}).get("wrong_pct", np.nan) for l in lam]
    cs = [cons[l].get("full|sv", {}).get("cost", np.nan) for l in lam]
    extra = ", ".join(f"+{100 * (c_ / cs[0] - 1):.0f}%" for c_ in cs[1:] if not np.isnan(c_))
    ax.plot(lam, ys, color=VIOLET, ls="--", marker="D", ms=4, lw=1.3, mec="white", mew=0.5,
            label=f"Stability VOI, widened catalogue (effort {extra})")
    ax.set_xticks(lam, ["declared", "+50%", "+100%"])
    ax.set_xlim(-0.12, 1.12)
    ax.set_xlabel("width of the true interpretation intervals")
    ax.set_ylabel("wrong conclusions (% of checks)")
    ax.set_title("(a) Misspecified catalogue", loc="left")
    h, l = ax.get_legend_handles_labels()
    order = sorted(range(len(l)), key=lambda i: 0 if l[i].startswith("Stability VOI, widened") else -1)
    ax.legend([h[i] for i in order], [l[i] for i in order], **{**leg, "ncol": 1})
    ax.grid(color=GRID, lw=0.5)
    ax.set_axisbelow(True)
    ax = axes[1]
    ratios = [1.5, 3.0, 6.0]
    srcs = {1.5: E3.get(f"{sk}|cost1.5", {}), 3.0: E2, 6.0: E3.get(f"{sk}|cost6", {})}
    for pol, lab, col, mk in [("complete", "Completeness-first", MUTED, "s"), ("value", "Value first", YELLOW, "^"),
                              ("degree", "Residual degree", VIOLET, "v"), ("sv", "Stability VOI", BLUE, "D"),
                              ("oracle", "Hindsight reference", INK, "*")]:
        ys = [srcs[r].get(f"full|{pol}", {}).get("cost", np.nan) for r in ratios]
        ax.plot(ratios, ys, color=col, marker=mk, ms=(6 if mk == "*" else 4), lw=1.3, mec="white", mew=0.5,
                label=lab)
    ax.set_yscale("log")
    yt = [v for v in (500, 700, 1000, 1500, 2000, 3000, 4000, 6000) if ax.get_ylim()[0] <= v <= ax.get_ylim()[1]]
    ax.set_yticks(yt, [f"{v:,}" for v in yt])
    ax.set_yticks([], minor=True)
    ax.set_xticks(ratios, ["1.5", "3", "6"])
    ax.set_xlabel("cost of a value request / cost of a clarification")
    ax.set_ylabel("effort at full information (log scale)")
    ax.set_title("(b) Action-cost ratio", loc="left")
    ax.legend(**leg)
    ax.grid(color=GRID, lw=0.5)
    ax.set_axisbelow(True)
    ax = axes[2]
    ng = E3.get(f"{sk}|nogeom", {})
    xs = np.arange(3)
    w = 0.36
    with_g = [E2[f"{lv}|sv"]["cost"] for lv in ("min", "std", "full")]
    no_g = [ng.get(f"{lv}|sv", {}).get("cost", np.nan) for lv in ("min", "std", "full")]
    ax.bar(xs - w / 2 - 0.01, with_g, width=w, color=BLUE, label="with geometry-derived evidence")
    ax.bar(xs + w / 2 + 0.01, no_g, width=w, facecolor="white", edgecolor=BLUE, hatch="////", lw=0.8,
           label="without geometry-derived evidence")
    top = max([v for v in no_g + with_g if not np.isnan(v)])
    for x, a, b in zip(xs, with_g, no_g):
        ax.text(x - w / 2 - 0.01, a + 0.012 * top, f"{a:,.0f}", ha="center", va="bottom", fontsize=6)
        if not np.isnan(b):
            ax.text(x + w / 2 + 0.01, b + 0.012 * top, f"{b:,.0f}", ha="center", va="bottom", fontsize=6)
    ax.set_xticks(xs, ["min", "std", "full"])
    ax.set_ylim(0, 1.12 * top)
    ax.set_xlabel("evidence level")
    ax.set_ylabel("effort of the stability-VOI planner")
    ax.set_title("(c) Value of geometry", loc="left")
    ax.legend(**{**leg, "ncol": 1})
    ax.grid(axis="y", color=GRID, lw=0.5)
    ax.set_axisbelow(True)
    fig.tight_layout(w_pad=1.6)
    save(fig, "fig_e3_robustness")


if __name__ == "__main__":
    which = sys.argv[2].split(",") if len(sys.argv) > 2 else ["cases", "e1", "e4", "models", "anytime", "e3"]
    for name, fn in (("cases", fig_cases), ("e1", fig_e1), ("e4", fig_e4), ("pareto", fig_e2_pareto), ("models", fig_e2_models),
                     ("anytime", fig_e2_anytime), ("e3", fig_e3)):
        if name in which:
            fn()
            print("figure:", name, flush=True)
