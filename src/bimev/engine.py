"""Version-space reasoning over interpreted evidence and conclusion stability.

Formalisation (see manuscript Section 3)
---------------------------------------
For a cluster K (checks that share interpretation variables, e.g. all doors of one type) let
    a  = assignment of shared categorical variables (semantics of a property, configuration, function ...)
    b  = assignment of group-local categorical variables (e.g. space category)
    q  = the code-relevant quantity of a group (mm)
Every evidence source s offers interpretation-dependent options o with an interval I_s,o(a,b) and a fault
cost c(o) in {0,1}: the declared reading costs 0, an alternative unit costs 1, a gross error ('err',
no constraint) costs 1 (0 for suspected export defaults). Categorical sources cost 1 when contradicted.
The pointwise fault cost of a candidate value x is
    C_g(x | a,b) = sum_s min{ c(o) : x in I_s,o(a,b) or o = err } + sum_cat [a,b violates cat source].
The admissible set of a group under (a,b) is the set of minimum-cost values, and the cluster keeps the
shared assignments whose summed minimum cost is minimal (minimum-cardinality diagnosis).
A check is *stable* when every admissible hypothesis yields the same decision class
(violation 'V' vs no violation 'N', where 'N' covers pass and not-applicable).
"""
from __future__ import annotations

import itertools
import math
from dataclasses import dataclass

from . import catalog as C

EPS_VALUE = 0.1          # half-width of a revealed (certified) design value, mm
MAX_LOCAL_ASSIGN = 64


def _key(values):
    return "|".join(values)


# ----------------------------------------------------------------------------- requirements
def requirement_for(family: str, req_key: str, occupancy: str, rulebook: str, assign: dict, cat_vars: list):
    rb = C.RULEBOOKS.get(rulebook, {})
    spec_all = rb.get(req_key) or C.RULEBOOKS["US"][req_key]
    spec = spec_all[occupancy]
    if family == "door":
        cfg = assign.get(cat_vars[0])
        if cfg == "OTHER":
            return None
        if len(cat_vars) > 1 and assign.get(cat_vars[1]) == "NONPASSAGE":
            return None
        return spec
    if family == "railing":
        return spec[assign[cat_vars[0]]]
    if family == "space":
        return spec[assign[cat_vars[0]]]
    return spec  # stairs: fixed requirement


def classify_segment(lo: float, hi: float, spec):
    """Split [lo,hi] by a requirement into (lo, hi, verdict) pieces; verdict in PASS/FAIL/NA."""
    if spec is None:
        return [(lo, hi, "NA")]
    cuts = sorted({v for v in (spec.get("min"), spec.get("max")) if v is not None and lo < v < hi})
    pts = [lo] + cuts + [hi]
    out = []
    for x0, x1 in zip(pts[:-1], pts[1:]):
        xm = 0.5 * (x0 + x1) if x1 > x0 else x0
        ok = True
        if spec.get("min") is not None and xm < spec["min"]:
            ok = False
        if spec.get("max") is not None and xm > spec["max"]:
            ok = False
        out.append((x0, x1, "PASS" if ok else "FAIL"))
    return out


def decision(verdict: str) -> str:
    return "V" if verdict == "FAIL" else "N"


# ----------------------------------------------------------------------------- group model
class GroupModel:
    def __init__(self, gid: str, g: dict, ledger: dict, level_rank: int, rulebook: str, drop_geometry=False):
        self.gid = gid
        self.g = g
        self.family = g["family"]
        self.quantity = g["quantity"]
        self.mult = int(g["multiplicity"])
        self.occupancy = ledger["occupancy"]
        self.rulebook = rulebook
        self.cat_vars = list(g["category_vars"])
        lo, hi = C.DOMAIN[self.quantity]
        self.domain = (lo, hi)
        vis = [s for s in g["sources"] if C.LEVEL_RANK[s["level"]] <= level_rank]
        if drop_geometry:  # ablation: no geometry-derived evidence
            vis = [s for s in vis if not (s["sid"].startswith("geom") or s["sid"] == "ceil")]
        self.cat_sources = [s for s in vis if s["kind"] == "cat"]
        # merge numeric sources that carry identical information (same deps and interval table)
        merged = {}
        for s in vis:
            if s["kind"] != "num":
                continue
            sig = (tuple(s["deps"]), repr(sorted((k, sorted((m, tuple(round(x, 3) for x in iv))
                                                           for m, iv in v.items())) for k, v in s["table"].items())),
                   s["suspect"], s.get("weight", 1.0))
            if sig in merged:
                merged[sig]["labels"].append(s["label"])
            else:
                merged[sig] = {**s, "labels": [s["label"]]}
        self.num_sources = list(merged.values())
        vs = []
        for s in self.num_sources:
            vs.extend(s["deps"])
        vs.extend(s["var"] for s in self.cat_sources)
        vs.extend(self.cat_vars)
        seen = []
        for v in vs:
            if v not in seen:
                seen.append(v)
        self.vars = seen
        self._cache = {}

    # options per numeric source under an assignment: list of (lo, hi, cost); plus the cost of 'err'
    def _options(self, s, assign):
        key = _key([assign[d] for d in s["deps"]])
        row = s["table"].get(key)
        w = float(s.get("weight", 1.0))
        opts = []
        if row is not None:
            for mode, iv in row.items():
                opts.append((iv[0], iv[1], 0.0 if mode == "ok" else w))
        return opts, (0.0 if s["suspect"] else w)

    def mincost(self, assign: dict, trusted=None):
        """Minimum fault cost and admissible segments for q under a full assignment of self.vars."""
        ck = (tuple(assign[v] for v in self.vars), trusted)
        hit = self._cache.get(ck)
        if hit is not None:
            return hit
        base_cost = 0.0
        for s in self.cat_sources:
            if assign[s["var"]] not in s["allowed"]:
                base_cost += float(s.get("weight", 1.0))
        lo, hi = self.domain
        if trusted is not None:
            lo, hi = max(lo, trusted[0]), min(hi, trusted[1])
        if hi < lo:
            res = (math.inf, [])
            self._cache[ck] = res
            return res
        srcs = [self._options(s, assign) for s in self.num_sources]
        pts = {lo, hi}
        for opts, _ in srcs:
            for a, b, _c in opts:
                if lo < a < hi:
                    pts.add(a)
                if lo < b < hi:
                    pts.add(b)
        pts = sorted(pts)
        segs = []
        for x0, x1 in zip(pts[:-1], pts[1:]):
            xm = 0.5 * (x0 + x1)
            cost = base_cost
            for opts, err_cost in srcs:
                best = err_cost
                for a, b, c in opts:
                    if a <= xm <= b and c < best:
                        best = c
                        if best == 0.0:
                            break
                cost += best
            segs.append((x0, x1, cost))
        if not segs:  # degenerate domain (point)
            x = lo
            cost = base_cost
            for opts, err_cost in srcs:
                cost += min([c for a, b, c in opts if a <= x <= b] + [err_cost])
            segs = [(x, x, cost)]
        cstar = min(c for _, _, c in segs)
        keep = []
        for x0, x1, c in segs:
            if c == cstar:
                if keep and abs(keep[-1][1] - x0) < 1e-9:
                    keep[-1] = (keep[-1][0], x1)
                else:
                    keep.append((x0, x1))
        res = (cstar, keep)
        self._cache[ck] = res
        return res

    def requirement(self, assign):
        return requirement_for(self.family, self.g["requirement_key"], self.occupancy, self.rulebook, assign,
                               self.cat_vars)


# ----------------------------------------------------------------------------- version space
@dataclass
class Hyp:
    a: tuple          # shared assignment (values in cluster.shared order)
    b: dict           # local assignment {var: value}
    segs: list        # admissible q segments [(lo,hi)]
    w: float          # probability mass (normalised within group)
    spec: object      # requirement

    def pieces(self):
        """(lo, hi, verdict, mass) pieces of this hypothesis."""
        tot = sum(max(h - l, 0.0) for l, h in self.segs)
        out = []
        for l, h in self.segs:
            share = (h - l) / tot if tot > 0 else 1.0 / len(self.segs)
            for x0, x1, v in classify_segment(l, h, self.spec):
                frac = ((x1 - x0) / (h - l)) if h > l else 1.0
                out.append((x0, x1, v, self.w * share * frac))
        return out


class ClusterModel:
    """All groups of a cluster with their shared variables, revealed facts and current version space."""

    def __init__(self, cid: str, ledger: dict, level_rank: int, rulebook: str, drop_geometry=False):
        self.cid = cid
        self.ledger = ledger
        self.groups = [GroupModel(gid, ledger["groups"][gid], ledger, level_rank, rulebook, drop_geometry)
                       for gid in ledger["clusters"][cid]["groups"]]
        self.vars_meta = ledger["vars"]
        allv = []
        for gm in self.groups:
            for v in gm.vars:
                if v not in allv:
                    allv.append(v)
        self.shared = [v for v in allv if self.vars_meta[v]["scope"] == "cluster"]
        self.local = {gm.gid: [v for v in gm.vars if self.vars_meta[v]["scope"] == "group"] for gm in self.groups}
        self.revealed: dict[str, str] = {}
        self.trusted: dict[str, tuple] = {}
        self.vs = None

    def domain(self, v):
        if v in self.revealed:
            return [self.revealed[v]]
        return list(self.vars_meta[v]["domain"])

    def solve(self):
        shared_dom = [self.domain(v) for v in self.shared]
        best_total = math.inf
        per_a = []
        for a in itertools.product(*shared_dom) if self.shared else [()]:
            aa = dict(zip(self.shared, a))
            total = 0.0
            gres = []
            for gm in self.groups:
                loc = self.local[gm.gid]
                loc_dom = [self.domain(v) for v in loc]
                best_g = math.inf
                hyps = []
                for b in itertools.product(*loc_dom) if loc else [()]:
                    bb = dict(zip(loc, b))
                    assign = {**aa, **bb}
                    cst, segs = gm.mincost(assign, self.trusted.get(gm.gid))
                    if cst < best_g:
                        best_g, hyps = cst, [(bb, segs, gm.requirement(assign))]
                    elif cst == best_g and cst < math.inf:
                        hyps.append((bb, segs, gm.requirement(assign)))
                total += best_g
                gres.append((best_g, hyps))
                if total > best_total:
                    break
            if total < best_total - 1e-9:
                best_total, per_a = total, [(a, gres)]
            elif abs(total - best_total) <= 1e-9:
                per_a.append((a, gres))
        self.min_cost = best_total
        n_a = len(per_a)
        vs = {gm.gid: [] for gm in self.groups}
        for a, gres in per_a:
            for gm, (cst, hyps) in zip(self.groups, gres):
                if not hyps:
                    continue
                w = 1.0 / n_a / len(hyps)
                for bb, segs, spec in hyps:
                    vs[gm.gid].append(Hyp(a, bb, segs, w, spec))
        # renormalise per group (groups always have >=1 hypothesis unless infeasible)
        for gid, hs in vs.items():
            tot = sum(h.w for h in hs)
            for h in hs:
                h.w = h.w / tot if tot > 0 else 0.0
        self.vs = vs
        self.n_a = n_a
        self.kept_a = [a for a, _ in per_a]
        return vs

    # ---------------------------------------------------------------- summaries
    def class_masses(self, gid, hyps=None):
        hs = self.vs[gid] if hyps is None else hyps
        mV = mN = 0.0
        sub = {"PASS": 0.0, "FAIL": 0.0, "NA": 0.0}
        for h in hs:
            for x0, x1, v, m in h.pieces():
                sub[v] += m
                if v == "FAIL":
                    mV += m
                else:
                    mN += m
        return mV, mN, sub

    def status(self, gid):
        mV, mN, sub = self.class_masses(gid)
        if mV <= 1e-12 and mN > 0:
            kind = "STABLE_N"
        elif mN <= 1e-12 and mV > 0:
            kind = "STABLE_V"
        else:
            kind = "UNSTABLE"
        return kind, mV, mN, sub

    def support(self, gid):
        lo = min((l for h in self.vs[gid] for l, _ in h.segs), default=None)
        hi = max((u for h in self.vs[gid] for _, u in h.segs), default=None)
        return lo, hi


def build_clusters(ledger: dict, level: str, rulebook: str = "US", families=None, drop_geometry=False):
    lr = C.LEVEL_RANK[level]
    out = {}
    for cid, c in ledger["clusters"].items():
        if families and c["family"] not in families:
            continue
        if not c["groups"]:
            continue
        cm = ClusterModel(cid, ledger, lr, rulebook, drop_geometry)
        cm.solve()
        out[cid] = cm
    return out
