"""Evidence-acquisition policies, simulated outcomes, baselines and the hindsight reference.

Actions
-------
CLARIFY(v)  reveal the true value of one interpretation variable v (property semantics, door configuration,
            railing function, space category); scope = type (shared) or element (local).
VALUE(t)    reveal the certified code quantity for the groups in scope t (door/railing type, flight, space).

Adaptive policies (all stop a check only when its conclusion is stable, except `conf`)
------------------------------------------------------------------------------------
sv       stability-based value of information: expected number of checks made stable per unit effort; when no single
         action can stabilise a check, the equivalence-class edge-cutting gain (EC2) is used as look-ahead surrogate
ec2      EC2 gain per unit effort only (decision-ambiguity reduction)
uncert   most ambiguous check first, then its cheapest action
fixed    checks in model order, cheapest action first
random   uniformly random relevant action
value    checks in model order, request the certified value (no clarification questions)
conf     sv acquisition, but a check is closed once its most probable decision reaches confidence tau
Reference and non-adaptive baselines: oracle (hindsight ILP), naive (designated source at face value),
complete (completeness-first, request every missing designated item, then face-value decisions).
"""
from __future__ import annotations

import itertools
import math
from collections import Counter, defaultdict
from dataclasses import dataclass

import numpy as np

from . import catalog as C
from .engine import EPS_VALUE, build_clusters, classify_segment, decision

FAMILY_WEIGHTS_CONSEQUENCE = {"door": 3.0, "stair": 3.0, "railing": 3.0, "space": 1.0}


# ============================================================================= truth
def sample_segs(segs, rng):
    lens = [max(h - l, 0.0) for l, h in segs]
    tot = sum(lens)
    if tot <= 0:
        l, _ = segs[int(rng.integers(len(segs)))]
        return float(l)
    r = float(rng.random()) * tot
    for (l, h), ln in zip(segs, lens):
        if r <= ln:
            return float(l + r)
        r -= ln
    return float(segs[-1][1])


def sample_truth(full_clusters: dict, rng):
    """Draw a hidden state from the full-information version space (declared design prior)."""
    tv, tq = {}, {}
    for cid in sorted(full_clusters):
        cm = full_clusters[cid]
        a = cm.kept_a[int(rng.integers(len(cm.kept_a)))]
        for v, x in zip(cm.shared, a):
            tv[v] = x
        for gm in cm.groups:
            hs = [h for h in cm.vs[gm.gid] if h.a == a]
            if not hs:
                continue
            h = hs[int(rng.integers(len(hs)))]
            for v, x in h.b.items():
                tv[v] = x
            tq[gm.gid] = sample_segs(h.segs, rng)
    return tv, tq


def true_decision(gm, tv, tq):
    assign = {v: tv.get(v) for v in gm.cat_vars}
    spec = gm.requirement(assign)
    q = tq[gm.gid]
    v = classify_segment(q, q, spec)[0][2]
    return decision(v), v


# ============================================================================= actions
@dataclass
class Action:
    kind: str
    cid: str
    target: str
    groups: tuple
    cost: float
    key: str
    ec2: float = 0.0
    stab: float = 0.0


def _value_outcomes(cm, gid):
    """Partition of a group's admissible q-support into outcome cells: list of (mV, mN)."""
    pieces = []
    for h in cm.vs[gid]:
        pieces.extend(h.pieces())
    if not pieces:
        return []
    pts = sorted({p[0] for p in pieces} | {p[1] for p in pieces})
    out = []
    pm = defaultdict(lambda: [0.0, 0.0])
    for x0, x1, v, m in pieces:
        if x1 - x0 <= 1e-9:
            pm[x0][0 if v == "FAIL" else 1] += m
    for x, (mv, mn) in pm.items():
        out.append((mv, mn))
    for b0, b1 in zip(pts[:-1], pts[1:]):
        if b1 - b0 <= 1e-9:
            continue
        mv = mn = 0.0
        for x0, x1, v, m in pieces:
            if x1 - x0 <= 1e-9:
                continue
            ov = min(b1, x1) - max(b0, x0)
            if ov > 0:
                w = m * ov / (x1 - x0)
                if v == "FAIL":
                    mv += w
                else:
                    mn += w
        if mv + mn > 0:
            out.append((mv, mn))
    return out


class World:
    """One project at one evidence level with a hidden state; tracks spent effort and revealed facts."""

    def __init__(self, ledger, level, rulebook, tv, tq, costs=None, tau=None, weights=None, clusters=None,
                 drop_geometry=False):
        self.ledger = ledger
        self.clusters = clusters if clusters is not None else build_clusters(ledger, level, rulebook,
                                                                             drop_geometry=drop_geometry)
        self.tv, self.tq = tv, tq
        self.costs = dict(costs or C.COST)
        self.tau = tau
        self.weights = weights or {}
        self.spent = 0.0
        self.n = Counter()
        self.cost_by_family = Counter()
        self.valued = set()
        self.status = {}
        self.order = []
        for cid in ledger["clusters"]:
            if cid in self.clusters:
                for gm in self.clusters[cid].groups:
                    self.order.append((cid, gm))
        self.total = sum(gm.mult for _, gm in self.order)
        self.total_w = sum(gm.mult * self.w(gm) for _, gm in self.order)
        self._actions = {}
        for cid in self.clusters:
            self._refresh(cid)

    def w(self, gm):
        return self.weights.get(gm.family, 1.0)

    # ---------------------------------------------------------------- state
    def _refresh(self, cid):
        cm = self.clusters[cid]
        for gm in cm.groups:
            self.status[gm.gid] = cm.status(gm.gid)
        self._actions[cid] = None

    def open_group(self, gid):
        kind, mV, mN, _ = self.status[gid]
        if kind != "UNSTABLE":
            return False
        if self.tau is not None:
            tot = mV + mN
            if tot > 0 and max(mV, mN) / tot >= self.tau:
                return False
        return True

    def actions(self, cid):
        if self._actions.get(cid) is not None:
            return self._actions[cid]
        cm = self.clusters[cid]
        open_g = [gm for gm in cm.groups if self.open_group(gm.gid)]
        acts = []
        if open_g:
            cc, cv = self.costs["CLARIFY"], self.costs["VALUE"]
            for i, v in enumerate(cm.shared):
                if v in cm.revealed:
                    continue
                if len({a[i] for a in cm.kept_a}) < 2:
                    continue
                aff = tuple(gm.gid for gm in open_g if v in gm.vars)
                if aff:
                    acts.append(Action("CLARIFY", cid, v, aff, cc, f"C|{v}"))
            for gm in open_g:
                for v in cm.local[gm.gid]:
                    if v in cm.revealed:
                        continue
                    if len({h.b.get(v) for h in cm.vs[gm.gid]}) < 2:
                        continue
                    acts.append(Action("CLARIFY", cid, v, (gm.gid,), cc, f"C|{v}"))
            scope = open_g[0].g["value_scope"]
            if scope == "cluster":
                if any(gm.gid not in self.valued for gm in open_g):
                    acts.append(Action("VALUE", cid, cid, tuple(gm.gid for gm in open_g), cv, f"V|{cid}"))
            else:
                for gm in open_g:
                    if gm.gid not in self.valued:
                        acts.append(Action("VALUE", cid, gm.gid, (gm.gid,), cv, f"V|{gm.gid}"))
            for a in acts:
                self._score(cm, a)
        self._actions[cid] = acts
        return acts

    def _score(self, cm, act):
        """EC2 expected edge-weight reduction and expected number of newly stable checks (weighted)."""
        gmap = {gm.gid: gm for gm in cm.groups}
        ec2 = stab = 0.0
        if act.kind == "CLARIFY" and act.target in cm.shared:
            i = cm.shared.index(act.target)
            cnt = Counter(a[i] for a in cm.kept_a)
            n = len(cm.kept_a)
            for gid in act.groups:
                mV0, mN0 = self.status[gid][1], self.status[gid][2]
                exp_w = exp_s = 0.0
                for x, c in cnt.items():
                    hs = [h for h in cm.vs[gid] if h.a[i] == x]
                    mV, mN, _ = cm.class_masses(gid, hs)
                    p = c / n
                    exp_w += p * mV * mN
                    exp_s += p * (1.0 if (mV <= 1e-12 or mN <= 1e-12) else 0.0)
                m = gmap[gid].mult * self.w(gmap[gid])
                ec2 += m * (mV0 * mN0 - exp_w)
                stab += m * exp_s
        elif act.kind == "CLARIFY":
            gid = act.groups[0]
            mV0, mN0 = self.status[gid][1], self.status[gid][2]
            by = defaultdict(list)
            for h in cm.vs[gid]:
                by[h.b.get(act.target)].append(h)
            exp_w = exp_s = 0.0
            for x, hs in by.items():
                mV, mN, _ = cm.class_masses(gid, hs)
                p = mV + mN
                exp_w += p * mV * mN
                exp_s += p * (1.0 if (mV <= 1e-12 or mN <= 1e-12) else 0.0)
            m = gmap[gid].mult * self.w(gmap[gid])
            ec2 += m * (mV0 * mN0 - exp_w)
            stab += m * exp_s
        else:
            for gid in act.groups:
                mV0, mN0 = self.status[gid][1], self.status[gid][2]
                exp_w = exp_s = 0.0
                for mV, mN in _value_outcomes(cm, gid):
                    p = mV + mN
                    exp_w += p * mV * mN
                    exp_s += p * (1.0 if (mV <= 1e-12 or mN <= 1e-12) else 0.0)
                m = gmap[gid].mult * self.w(gmap[gid])
                ec2 += m * (mV0 * mN0 - exp_w)
                stab += m * exp_s
        act.ec2 = max(ec2, 0.0)
        act.stab = stab

    def apply(self, act):
        cm = self.clusters[act.cid]
        if act.kind == "CLARIFY":
            if act.target in self.tv:
                cm.revealed[act.target] = self.tv[act.target]
        else:
            gids = [gm.gid for gm in cm.groups] if act.target == act.cid else [act.target]
            for gid in gids:
                if gid in self.tq:
                    q = self.tq[gid]
                    cm.trusted[gid] = (q - EPS_VALUE, q + EPS_VALUE)
                    self.valued.add(gid)
        cm.solve()
        self.spent += act.cost
        self.n[act.kind] += 1
        self.cost_by_family[cm.groups[0].family] += act.cost
        self._refresh(act.cid)

    # ---------------------------------------------------------------- metrics
    def closed(self):
        """(closed element checks, consequence-weighted closed element checks)."""
        w = ww = 0.0
        for cid, gm in self.order:
            if not self.open_group(gm.gid):
                w += gm.mult
                ww += gm.mult * self.w(gm)
        return w, ww

    def summary(self):
        res = Counter()
        rows = []
        for cid, gm in self.order:
            kind, mV, mN, sub = self.status[gm.gid]
            truth = true_decision(gm, self.tv, self.tq)[0] if gm.gid in self.tq else None
            if kind == "STABLE_V":
                verdict, how = "V", "stable"
            elif kind == "STABLE_N":
                verdict, how = "N", "stable"
            elif self.tau is not None and not self.open_group(gm.gid):
                verdict, how = ("V" if mV > mN else "N"), "confident"
            else:
                verdict, how = None, "escalated"
            correct = (verdict == truth) if (verdict is not None and truth is not None) else None
            res[how] += gm.mult
            if correct is True:
                res["correct"] += gm.mult
            elif correct is False:
                res["wrong"] += gm.mult
                res[f"wrong_{gm.family}"] += gm.mult
            if verdict == "V" and truth == "N":
                res["false_violation"] += gm.mult
            if verdict == "N" and truth == "V":
                res["missed_violation"] += gm.mult
            rows.append((gm.gid, gm.family, gm.mult, how, verdict, truth))
        res["cost"] = self.spent
        res["n_clarify"] = self.n["CLARIFY"]
        res["n_value"] = self.n["VALUE"]
        res["checks"] = self.total
        for fam, v in self.cost_by_family.items():
            res[f"cost_{fam}"] = v
        for cid, gm in self.order:
            res[f"checks_{gm.family}"] += gm.mult
        return dict(res), rows


# ============================================================================= adaptive policies
def _rank_sv(a):
    return (a.stab / a.cost, a.ec2 / a.cost, -a.cost, a.key)


def choose(world: World, policy: str, rng):
    cand = []
    for cid in world.clusters:
        cand.extend(world.actions(cid))
    if not cand:
        return None
    if policy in ("sv", "sv_cw", "conf"):
        return max(cand, key=_rank_sv)
    if policy == "ec2":
        return max(cand, key=lambda a: (a.ec2 / a.cost, -a.cost, a.key))
    if policy == "random":
        return cand[int(rng.integers(len(cand)))]
    if policy == "degree":
        # residual-degree ordering (value-blind): the request that touches the largest number of unsettled
        # element checks per unit effort; transplanted from source-recovery ordering for missing evidence
        mult = {gm.gid: gm.mult for _, gm in world.order}
        return max(cand, key=lambda a: (sum(mult[g] for g in a.groups) / a.cost, -a.cost, a.key))
    if policy in ("fixed", "uncert", "value"):
        opens = [gm for cid, gm in world.order if world.open_group(gm.gid)]
        if policy == "uncert":
            opens.sort(key=lambda gm: -gm.mult * min(world.status[gm.gid][1], world.status[gm.gid][2]))
        # take the first open check (in the policy's order) that still has an admissible request
        for target in opens:
            acts = [a for a in cand if target.gid in a.groups]
            if policy == "value":
                acts = [a for a in acts if a.kind == "VALUE"] or acts
            if acts:
                order = {v: i for i, v in enumerate(target.vars)}
                return min(acts, key=lambda a: (a.cost, order.get(a.target, 99), a.key))
        return None
    raise ValueError(policy)


def run_policy(ledger, level, rulebook, tv, tq, policy, rng, costs=None, tau=None, budget=math.inf,
               max_steps=100000, clusters=None, drop_geometry=False):
    weights = FAMILY_WEIGHTS_CONSEQUENCE if policy == "sv_cw" else None
    w = World(ledger, level, rulebook, tv, tq, costs=costs, tau=(tau if policy == "conf" else None),
              weights=weights, clusters=clusters, drop_geometry=drop_geometry)
    # anytime trajectories always report both plain and consequence-weighted closure
    cw = FAMILY_WEIGHTS_CONSEQUENCE

    def closure():
        n = nw = 0.0
        for cid, gm in w.order:
            if not w.open_group(gm.gid):
                n += gm.mult
                nw += gm.mult * cw.get(gm.family, 1.0)
        return n, nw

    tot_w = sum(gm.mult * cw.get(gm.family, 1.0) for _, gm in w.order)
    c0 = closure()
    traj = [(0.0, c0[0] / w.total, c0[1] / tot_w)]
    steps = 0
    while steps < max_steps:
        a = choose(w, policy, rng)
        if a is None or w.spent + a.cost > budget + 1e-9:
            break
        w.apply(a)
        c = closure()
        traj.append((w.spent, c[0] / w.total, c[1] / tot_w))
        steps += 1
    s, rows = w.summary()
    return s, traj, rows


# ============================================================================= non-adaptive baselines
NAIVE_LABELS = {
    "door_clear_width": ["IfcDoor.OverallWidth"],
    "stair_riser": ["IfcStairFlight.RiserHeight", "Pset_StairFlightCommon.RiserHeight"],
    "stair_tread": ["IfcStairFlight.TreadLength", "Pset_StairFlightCommon.TreadLength"],
    "railing_height": ["Pset_RailingCommon.Height"],
    "ceiling_height": ["FinishCeilingHeight", "ClearHeight", "Lichte Höhe", "Unbounded Height",
                       "Qto_SpaceBaseQuantities.Height", "BaseQuantities.Height", "Space body height"],
}
COMPLETE_LABELS = {
    "stair_riser": ["Pset_StairFlightCommon.RiserHeight"],
    "stair_tread": ["Pset_StairFlightCommon.TreadLength"],
    "railing_height": ["Pset_RailingCommon.Height"],
    "ceiling_height": ["Qto_SpaceBaseQuantities.FinishCeilingHeight", "BaseQuantities.FinishCeilingHeight",
                       "BaseQuantities.ClearHeight"],
}


def _visible_raw(gm, labels, exact=False):
    """Face value (declared unit) of the first visible numeric source matching a designated label."""
    for lab in labels:
        for s in gm.num_sources:
            for sl in s["labels"]:
                hit = (sl == lab) if exact else (lab.lower() in sl.lower())
                if hit and s.get("value_mm") is not None:
                    return float(s["value_mm"])
    return None


def _naive_category(gm, cm):
    """Category assumed by a non-reasoning checker."""
    if gm.family == "door":
        allowed = None
        for s in gm.cat_sources:
            if s["label"].startswith("IfcDoorType.OperationType"):
                allowed = s["allowed"]
        assign = {gm.cat_vars[0]: (allowed[0] if allowed else "SWING")}
        if len(gm.cat_vars) > 1:
            assign[gm.cat_vars[1]] = "PASSAGE"
        return assign
    if gm.family == "railing":
        pre = next((s for s in gm.cat_sources if s["label"] == "IfcRailing.PredefinedType"), None)
        return {gm.cat_vars[0]: (pre["allowed"][0] if pre else "GUARD")}
    if gm.family == "space":
        nm = next((s for s in gm.cat_sources if s["label"] == "Space name tokens"), None)
        return {gm.cat_vars[0]: (nm["allowed"][0] if nm else "OCCUPIABLE")}
    return {}


def run_naive(ledger, level, rulebook, tv, tq, clusters=None, drop_geometry=False):
    cl = clusters if clusters is not None else build_clusters(ledger, level, rulebook, drop_geometry=drop_geometry)
    res = Counter()
    for cid, cm in cl.items():
        for gm in cm.groups:
            truth = true_decision(gm, tv, tq)[0] if gm.gid in tq else None
            v = _visible_raw(gm, NAIVE_LABELS[gm.quantity], exact=(gm.family != "space"))
            if v is None:
                res["escalated"] += gm.mult
                continue
            spec = gm.requirement(_naive_category(gm, cm))
            verdict = decision(classify_segment(v, v, spec)[0][2])
            res["decided"] += gm.mult
            if verdict == truth:
                res["correct"] += gm.mult
            else:
                res["wrong"] += gm.mult
                res[f"wrong_{gm.family}"] += gm.mult
                res["false_violation" if verdict == "V" else "missed_violation"] += gm.mult
    res["cost"] = 0.0
    res["checks"] = sum(gm.mult for cm in cl.values() for gm in cm.groups)
    return dict(res)


def run_complete(ledger, level, rulebook, tv, tq, costs=None, clusters=None, drop_geometry=False):
    """Completeness-first acquisition: every missing designated item is requested, then face-value decisions."""
    costs = dict(costs or C.COST)
    cl = clusters if clusters is not None else build_clusters(ledger, level, rulebook, drop_geometry=drop_geometry)
    res = Counter()
    spent = 0.0
    n_c = n_v = 0
    for cid, cm in cl.items():
        valued_cluster = False
        clarified = set()
        for gm in cm.groups:
            truth = true_decision(gm, tv, tq)[0] if gm.gid in tq else None
            if gm.family == "door":
                v = None
                for s in gm.num_sources:
                    if s.get("note") in ("CLEAR", "CLEAR_ACTIVE") and s.get("value_mm") is not None:
                        v = float(s["value_mm"])
                        break
            else:
                v = _visible_raw(gm, COMPLETE_LABELS[gm.quantity], exact=True)
            if v is None:
                if gm.g["value_scope"] == "cluster":
                    if not valued_cluster:
                        spent += costs["VALUE"]
                        res[f"cost_{gm.family}"] += costs["VALUE"]
                        n_v += 1
                        valued_cluster = True
                else:
                    spent += costs["VALUE"]
                    res[f"cost_{gm.family}"] += costs["VALUE"]
                    n_v += 1
                v = tq.get(gm.gid)
            assign = _naive_category(gm, cm)
            if gm.family == "railing":
                pre = next((s for s in gm.cat_sources if s["label"] == "IfcRailing.PredefinedType"), None)
                if pre is None:
                    var = gm.cat_vars[0]
                    if var not in clarified:
                        spent += costs["CLARIFY"]
                        res[f"cost_{gm.family}"] += costs["CLARIFY"]
                        n_c += 1
                        clarified.add(var)
                    assign = {var: tv.get(var)}
            elif gm.family == "space":
                nm = next((s for s in gm.cat_sources if s["label"] == "Space name tokens"), None)
                if nm is None or len(nm["allowed"]) != 1:
                    spent += costs["CLARIFY"]
                    res[f"cost_{gm.family}"] += costs["CLARIFY"]
                    n_c += 1
                    assign = {gm.cat_vars[0]: tv.get(gm.cat_vars[0])}
            elif gm.family == "door":
                if len(gm.cat_vars) > 1:
                    assign[gm.cat_vars[1]] = tv.get(gm.cat_vars[1], "PASSAGE")
            if v is None:
                res["escalated"] += gm.mult
                continue
            spec = gm.requirement(assign)
            verdict = decision(classify_segment(v, v, spec)[0][2])
            res["decided"] += gm.mult
            if verdict == truth:
                res["correct"] += gm.mult
            else:
                res["wrong"] += gm.mult
                res[f"wrong_{gm.family}"] += gm.mult
                res["false_violation" if verdict == "V" else "missed_violation"] += gm.mult
    res["cost"] = spent
    res["n_clarify"] = n_c
    res["n_value"] = n_v
    res["checks"] = sum(gm.mult for cm in cl.values() for gm in cm.groups)
    return dict(res)


# ============================================================================= hindsight reference (ILP)
def _min_hyps(cm, gm, aa, loc_dom, trusted):
    loc = cm.local[gm.gid]
    best, hyps = math.inf, []
    for b in itertools.product(*loc_dom) if loc else [()]:
        assign = {**aa, **dict(zip(loc, b))}
        cst, segs = gm.mincost(assign, trusted)
        if cst < best:
            best, hyps = cst, [(assign, segs)]
        elif cst == best and cst < math.inf:
            hyps.append((assign, segs))
    return best, hyps


def _local_stable(cm, gm, tv, tq, reveal_vars, value):
    """Is check gm stable after revealing `reveal_vars` (and its certified value if `value`)?

    Revealed shared variables filter the retained shared assignments. A revealed local variable or value changes
    the group's own fault cost under each shared assignment; as in the full update, only the shared assignments
    whose cluster total stays minimal are kept (their totals differ by the group's cost increase only).
    """
    kept = [a for a in cm.kept_a
            if all(a[cm.shared.index(v)] == tv.get(v) for v in reveal_vars if v in cm.shared)]
    if not kept:
        return False
    trusted_old = cm.trusted.get(gm.gid)
    trusted = (tq[gm.gid] - EPS_VALUE, tq[gm.gid] + EPS_VALUE) if value else trusted_old
    loc = cm.local[gm.gid]
    loc_dom_old = [cm.domain(v) for v in loc]
    loc_dom = [[tv[v]] if (v in reveal_vars and v in tv) else cm.domain(v) for v in loc]
    per_a = []
    for a in kept:
        aa = dict(zip(cm.shared, a))
        old, _ = _min_hyps(cm, gm, aa, loc_dom_old, trusted_old)
        new, hyps = _min_hyps(cm, gm, aa, loc_dom, trusted)
        if new < math.inf:
            per_a.append((new - old, hyps))
    if not per_a:
        return False
    dmin = min(d for d, _ in per_a)
    classes = set()
    for d, hyps in per_a:
        if d > dmin + 1e-9:
            continue
        for assign, segs in hyps:
            spec = gm.requirement(assign)
            for l, h in segs:
                for _, _, v in classify_segment(l, h, spec):
                    classes.add(decision(v))
        if len(classes) > 1:
            return False
    return len(classes) == 1


def run_oracle(ledger, level, rulebook, tv, tq, costs=None, max_set=4, clusters=None, drop_geometry=False):
    """Minimum-cost set of actions that stabilises every stabilisable check, given known outcomes."""
    from scipy.optimize import LinearConstraint, milp

    costs = dict(costs or C.COST)
    cl = clusters if clusters is not None else build_clusters(ledger, level, rulebook, drop_geometry=drop_geometry)
    tests = {}
    test_family = {}
    covers = []
    escal = 0
    total_checks = 0
    for cid, cm in cl.items():
        for gm in cm.groups:
            total_checks += gm.mult
            if cm.status(gm.gid)[0] != "UNSTABLE":
                continue
            rel = []
            for i, v in enumerate(cm.shared):
                if v in gm.vars and len({a[i] for a in cm.kept_a}) > 1:
                    rel.append(("C", v))
            for v in cm.local[gm.gid]:
                if len({h.b.get(v) for h in cm.vs[gm.gid]}) > 1:
                    rel.append(("C", v))
            rel.append(("V", cid if gm.g["value_scope"] == "cluster" else gm.gid))
            minimal = []
            for k in range(1, min(len(rel), max_set) + 1):
                for S in itertools.combinations(rel, k):
                    if any(set(m) <= set(S) for m in minimal):
                        continue
                    rv = [x[1] for x in S if x[0] == "C"]
                    val = any(x[0] == "V" for x in S)
                    if _local_stable(cm, gm, tv, tq, rv, val):
                        minimal.append(S)
            if not minimal:
                escal += gm.mult
                continue
            for S in minimal:
                for t in S:
                    tests[t] = costs["CLARIFY"] if t[0] == "C" else costs["VALUE"]
                    test_family[t] = gm.family
            covers.append((gm.mult, minimal))
    if not covers:
        return {"cost": 0.0, "escalated": escal, "checks": total_checks, "n_clarify": 0, "n_value": 0, "status": 0}
    tkeys = sorted(tests, key=str)
    tidx = {t: i for i, t in enumerate(tkeys)}
    ny = sum(len(m) for _, m in covers)
    nv = len(tkeys) + ny
    c = np.zeros(nv)
    for t, i in tidx.items():
        c[i] = tests[t]
    rows, lb, ub = [], [], []
    yi = len(tkeys)
    for mult, minimal in covers:
        r = np.zeros(nv)
        for S in minimal:
            r[yi] = 1.0
            for t in S:
                rr = np.zeros(nv)
                rr[yi] = 1.0
                rr[tidx[t]] = -1.0
                rows.append(rr)
                lb.append(-np.inf)
                ub.append(0.0)
            yi += 1
        rows.append(r)
        lb.append(1.0)
        ub.append(np.inf)
    A = np.vstack(rows)
    sol = milp(c, constraints=LinearConstraint(A, lb, ub), integrality=np.ones(nv), bounds=(0, 1))
    x = np.round(sol.x[:len(tkeys)]).astype(int) if sol.x is not None else np.ones(len(tkeys), dtype=int)
    chosen = [t for t, i in tidx.items() if x[i] == 1]
    res = {"cost": float(sum(tests[t] for t in chosen)), "escalated": escal, "checks": total_checks,
           "n_clarify": sum(1 for t in chosen if t[0] == "C"), "n_value": sum(1 for t in chosen if t[0] == "V"),
           "status": int(sol.status)}
    for t in chosen:
        k = f"cost_{test_family[t]}"
        res[k] = res.get(k, 0.0) + tests[t]
    return res
