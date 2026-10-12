"""Evidence extraction: IFC model -> JSON evidence ledger (clusters, groups, sources, variables).

Ledger structure (per project)
------------------------------
vars[name]     = {domain, scope ('cluster'|'group'), kind, cluster, group?, label}
clusters[cid]  = {family, label, groups: [gid]}
groups[gid]    = {family, cluster, elements, names, multiplicity, category_vars, requirement_key,
                  value_scope ('cluster'|'group'), sources: [...], naive: {...}, complete: {...}}
source (numeric)     = {sid, label, level, kind:'num', deps:[var], table:{key:{mode:[lo,hi]}},
                        suspect, raw, value_mm, note}
source (categorical) = {sid, label, level, kind:'cat', var, allowed:[...], raw}
Keys of `table` are '|'.join(values of deps) ('' when deps is empty). Modes: 'ok' and 'u:<unit>'.
All lengths in mm.
"""
from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from pathlib import Path

import ifcopenshell.util.element as ue
import numpy as np

from . import catalog as C
from .ifcutil import (length_scale_m, norm_text, open_model, parse_dim_pair, parse_single_mm,
                      parse_stair_type_limits, prop_lookup, shape_extent_mm, storey_of, typed_props)

PROP_TOL = 0.2     # representation tolerance for stored design dimensions (mm)
HEIGHT_TOL = 1.0   # railing heights (mm)
SPACE_TOL = 5.0    # ceiling heights (mm)
# geometry-derived interpretation bounds (mm); widened jointly with the door deductions in robustness runs
RAIL_GEOM_BELOW = 300.0   # top of a level railing may lie up to this much below the body extent
RAIL_GEOM_ABOVE = 100.0   # ... or up to this much above it (base above the walking surface)
STAIR_GEOM_SLACK = 360.0  # soffit/waist below the base plus tread thickness included in the flight extent
CEIL_GEOM_TOL = 30.0      # finished-floor / ceiling-soffit reference tolerance


def apply_widening(lam: float):
    """Widen every declared interpretation interval by `lam` x its width on each side (misspecification runs)."""
    global RAIL_GEOM_BELOW, RAIL_GEOM_ABOVE, STAIR_GEOM_SLACK, CEIL_GEOM_TOL
    if lam <= 0:
        return
    for k, (lo, hi) in list(C.DOOR_DELTA.items()):
        w = hi - lo
        C.DOOR_DELTA[k] = (lo - lam * w, hi + lam * w)
    lo, hi = C.DOUBLE_LEAF_SHARE
    C.DOUBLE_LEAF_SHARE = (max(0.3, lo - lam * (hi - lo)), min(1.0, hi + lam * (hi - lo)))
    RAIL_GEOM_BELOW *= 1 + lam
    RAIL_GEOM_ABOVE *= 1 + lam
    STAIR_GEOM_SLACK *= 1 + lam
    CEIL_GEOM_TOL *= 1 + lam


class Ledger:
    def __init__(self, project: str, schema: str, occupancy: str, scale_m: float):
        self.d = {"project": project, "schema": schema, "occupancy": occupancy, "length_scale_m": scale_m,
                  "metric": abs(scale_m - 1.0) < 1e-9 or abs(scale_m - 0.001) < 1e-12,
                  "vars": {}, "clusters": {}, "groups": {}}

    def var(self, name, domain, scope, kind, cluster, label, group=None):
        v = self.d["vars"].get(name)
        if v is None:
            self.d["vars"][name] = {"domain": list(domain), "scope": scope, "kind": kind, "cluster": cluster,
                                    "group": group, "label": label}
        return name

    def cluster(self, cid, family, label):
        if cid not in self.d["clusters"]:
            self.d["clusters"][cid] = {"family": family, "label": label, "groups": []}
        return cid

    def group(self, gid, payload):
        self.d["groups"][gid] = payload
        self.d["clusters"][payload["cluster"]]["groups"].append(gid)


# ----------------------------------------------------------------------------- numeric source helpers
def _unit_modes(raw_value: float, declared_scale_m: float, metric: bool):
    """Alternative-unit fault modes for a stored length value: {mode: value_mm}."""
    modes = {}
    for u, s in C.ALT_UNIT_SCALES_M.items():
        if abs(s - declared_scale_m) < 1e-12:
            continue
        modes[f"u:{u}"] = float(raw_value) * s * 1000.0
    return modes


def num_source(sid, label, level, deps, table, raw=None, value_mm=None, suspect=False, note="", weight=1.0):
    """Numeric evidence source. `weight` is the fault cost of overruling it (geometry: 2, see catalog)."""
    return {"sid": sid, "label": label, "level": level, "kind": "num", "deps": deps, "table": table,
            "suspect": bool(suspect), "raw": raw, "value_mm": value_mm, "note": note, "weight": float(weight)}


def cat_source(sid, label, level, var, allowed, raw=None, weight=1.0):
    return {"sid": sid, "label": label, "level": level, "kind": "cat", "var": var, "allowed": sorted(set(allowed)),
            "raw": raw, "weight": float(weight)}


def _len_mm(pv, scale_m: float):
    """Length value in mm; unitless IfcReal/IfcInteger values are read in the declared model unit."""
    if pv.value_mm is not None:
        return pv.value_mm, False
    if isinstance(pv.raw, (int, float)) and not isinstance(pv.raw, bool) and pv.measure in ("IfcReal", "IfcInteger"):
        return float(pv.raw) * scale_m * 1000.0, True
    return None, False


def _interval(lo, hi):
    return [float(lo), float(hi)]


def _is_suspect(value_mm: float, metric: bool) -> bool:
    return metric and any(abs(value_mm - s) < 0.6 for s in C.SUSPECT_DEFAULTS_MM)


def _level_of(pv) -> str:
    return "std" if pv.standard else "full"


# ============================================================================= DOORS
CLEAR_ACTIVE_RE = re.compile(r"(active leaf clear opening width|durchgangsbreite gehfl)", re.I)
CLEAR_RE = re.compile(r"(durchgangslichte breite|durchgangsbreite|lichter durchgang breite|clear opening width|"
                      r"clear passage|width clear passage|lichte breite|clear width)", re.I)
LEAF_ACTIVE_RE = re.compile(r"(width of the active leaf)", re.I)
LEAF_RE = re.compile(r"(tuerblatt breite|türblatt breite|width classic 1 leaf|leaf width)", re.I)
OPENING_RE = re.compile(r"(rohbauoeffnung breite|rohbauöffnung breite|rohbaubreite|rough width|structural opening|"
                        r"maueroeffnungsmass breite|maueröffnungsmaß breite|architekturlichte breite|"
                        r"oeffnungsbreite|öffnungsbreite|baurichtmass|baurichtmaß)", re.I)
OUTER_RE = re.compile(r"^(rahmen breite)$", re.I)
EXCLUDE_RE = re.compile(r"(thickness|dicke|trim|rail width|stile|rahmenbreite|rahmen-breite|stockbreite|"
                        r"fensterbank|sturz|breite_|fensterrahmen|panel|griff|schwelle)", re.I)
AMBIG_NAMES = {"width", "breite"}


HEIGHT_WORD_RE = re.compile(r"(height|höhe|hoehe)", re.I)


def classify_door_width(set_name: str, name: str, value_mm: float):
    n = name.strip()
    nl = n.lower()
    if value_mm is None or value_mm < 400 or value_mm > 4000:
        return None
    if HEIGHT_WORD_RE.search(nl):
        return None
    if "architekturlichte" in nl:
        return "OPENING"  # ArchiCAD: architectural clear dimension of the wall opening
    if CLEAR_ACTIVE_RE.search(nl):
        return "CLEAR_ACTIVE"
    if LEAF_ACTIVE_RE.search(nl):
        return "LEAF_ACTIVE"
    if EXCLUDE_RE.search(nl):
        return None
    if CLEAR_RE.search(nl):
        return "CLEAR"
    if LEAF_RE.search(nl):
        return "LEAF"
    if OPENING_RE.search(nl):
        return "OPENING"
    if OUTER_RE.search(nl):
        return "OUTER"
    if set_name in ("Qto_DoorBaseQuantities", "BaseQuantities") and nl == "width":
        return "OPENING"  # IFC: total outer width of the door lining (= wall opening)
    if nl in AMBIG_NAMES:
        return "AMBIG"
    return None


def door_interval(v: float, cls: str, cfg: str):
    if cfg == "OTHER":
        # rule not applicable (revolving/overhead/elevator doors): width evidence places no constraint, so that
        # numeric conflicts cannot overturn categorical applicability evidence
        return _interval(0.0, 1e6)
    lo_d, hi_d = C.DOOR_DELTA["CLEAR" if cls in ("CLEAR", "CLEAR_ACTIVE") else
                              ("LEAF" if cls in ("LEAF", "LEAF_ACTIVE") else cls)]
    if cfg == "DOUBLE" and cls not in ("CLEAR_ACTIVE", "LEAF_ACTIVE"):
        f_lo, f_hi = C.DOUBLE_LEAF_SHARE
        return _interval(f_lo * (v - hi_d), f_hi * (v - lo_d))
    return _interval(v - hi_d, v - lo_d)


def door_table(v_modes: dict, sem_domain: list | None, fixed_cls: str | None, cfg_domain: list):
    """Interval table for a door width source. deps = [sem?, cfg]."""
    table = {}
    classes = sem_domain if sem_domain else [fixed_cls]
    for cls in classes:
        for cfg in cfg_domain:
            key = (f"{cls}|{cfg}" if sem_domain else cfg)
            table[key] = {m: door_interval(v, cls, cfg) for m, v in v_modes.items()}
    return table


def extract_doors(f, L: Ledger, scale_m: float):
    metric = L.d["metric"]
    proj = L.d["project"]
    occ = L.d["occupancy"]
    by_type = defaultdict(list)
    for d in f.by_type("IfcDoor"):
        t = ue.get_type(d)
        # one cluster per named door type: exporters split a family type into several type objects (e.g. one
        # IfcDoorStyle per swing direction), but a designer answers type-level questions once per named type
        key = ((t.Name or t.GlobalId) if t is not None else (d.Name or "").rsplit(":", 1)[0] or f"untyped{d.id()}")
        by_type[key].append((d, t))

    for ti, (tkey, members) in enumerate(sorted(by_type.items(), key=lambda kv: kv[0])):
        t = members[0][1]
        tname = (t.Name if t is not None else (members[0][0].Name or "")) or ""
        cid = L.cluster(f"{proj}|door|{ti}", "door", tname)
        # --- configuration evidence (shared per type)
        op = None
        if t is not None:
            op = getattr(t, "OperationType", None)
        if not op:
            op = getattr(members[0][0], "OperationType", None)
        cfg_from_op = C.door_config_from_operation(op)
        nt = norm_text(tname + " " + (members[0][0].Name or ""))
        cfg_from_name = None
        if any(tok in nt for tok in ("garage", "revolv", "drehtuer", "elevator", "aufzug", "lift")):
            cfg_from_name = ["OTHER"]
        elif any(tok in nt for tok in C.DOUBLE_TOKENS):
            cfg_from_name = ["DOUBLE"]
        elif "schiebe" in nt or "sliding" in nt:
            cfg_from_name = ["SLIDING"]
        elif any(tok in nt for tok in C.SINGLE_TOKENS):
            cfg_from_name = ["SWING", "SLIDING"]
        cfg_domain = list(C.DOOR_CONFIGS)
        if cfg_from_op is None and cfg_from_name is None:
            cfg_prior = ["SWING", "DOUBLE"]  # declared default: swing door, single or double leaf
            cfg_domain = cfg_prior
        cfg_var = L.var(f"{cid}|cfg", cfg_domain, "cluster", "cfg", cid, "door configuration (OperationType)")
        cat_srcs = []
        if cfg_from_op is not None:
            cat_srcs.append(cat_source("op", "IfcDoorType.OperationType", "min", cfg_var, cfg_from_op, raw=op,
                                       weight=C.WEIGHT_SCHEMA_TYPE))
        if cfg_from_name is not None:
            cat_srcs.append(cat_source("nm_cfg", "Name tokens (configuration)", "min", cfg_var, cfg_from_name,
                                       raw=tname))
        # --- applicability for low openings (access panels / pass-throughs)
        heights = [float(getattr(d, "OverallHeight", 0) or 0) * scale_m * 1000.0 for d, _ in members]
        nd = parse_dim_pair(tname) or parse_dim_pair(members[0][0].Name)
        nominal_h = max([h for h in heights if h > 0] + ([nd[1]] if nd else []) or [0.0])
        cat_vars = [cfg_var]
        if 0 < nominal_h < 1900:
            app_var = L.var(f"{cid}|app", ["PASSAGE", "NONPASSAGE"], "cluster", "app", cid,
                            "door is a passage door (applicability)")
            cat_vars.append(app_var)
        # --- semantic variables (shared per type)
        sem_ow = L.var(f"{cid}|sem|IfcDoor.OverallWidth", ["OPENING", "LEAF"], "cluster", "sem", cid,
                       "meaning of IfcDoor.OverallWidth")
        sem_nm = L.var(f"{cid}|sem|Name", ["LEAF", "OPENING"], "cluster", "sem", cid,
                       "meaning of nominal width in type name")

        # --- per-instance evidence, grouped by identical signature
        sigs = defaultdict(list)
        for d, _ in members:
            props = prop_lookup(typed_props(d, scale_m))
            srcs = []
            ow = getattr(d, "OverallWidth", None)
            if ow:
                v = float(ow) * scale_m * 1000.0
                modes = {"ok": v, **_unit_modes(float(ow), scale_m, metric)}
                srcs.append(num_source("ow", "IfcDoor.OverallWidth", "min", [sem_ow, cfg_var],
                                       door_table(modes, ["OPENING", "LEAF"], None, cfg_domain),
                                       raw=float(ow), value_mm=v))
            if nd:
                v = nd[0]
                srcs.append(num_source("nm", "Type name nominal width", "min", [sem_nm, cfg_var],
                                       door_table({"ok": v}, ["LEAF", "OPENING"], None, cfg_domain),
                                       raw=tname, value_mm=v))
            for lab, pv in sorted(props.items()):
                if pv.value_mm is None:
                    continue
                cls = classify_door_width(pv.set_name, pv.name, pv.value_mm)
                if cls is None:
                    continue
                v = pv.value_mm
                modes = {"ok": v, **_unit_modes(float(pv.raw), scale_m, metric)}
                lvl = _level_of(pv)
                sid = f"p:{lab}"
                if cls == "AMBIG":
                    svar = L.var(f"{cid}|sem|{lab}", ["LEAF", "OPENING"], "cluster", "sem", cid,
                                 f"meaning of {lab}")
                    srcs.append(num_source(sid, lab, lvl, [svar, cfg_var],
                                           door_table(modes, ["LEAF", "OPENING"], None, cfg_domain),
                                           raw=pv.raw, value_mm=v, suspect=_is_suspect(v, metric)))
                else:
                    srcs.append(num_source(sid, lab, lvl, [cfg_var], door_table(modes, None, cls, cfg_domain),
                                           raw=pv.raw, value_mm=v, suspect=_is_suspect(v, metric),
                                           note=cls))
            ext = shape_extent_mm(d, world=False)
            if ext is not None:
                gx = float(ext[1][0] - ext[0][0])
                if 300 < gx < 6000:
                    srcs.append(num_source("geom", "Body extent (local X)", "min", [cfg_var],
                                           door_table({"ok": gx}, None, "OUTER", cfg_domain), raw=gx, value_mm=gx,
                                           note="OUTER", weight=C.WEIGHT_GEOMETRY))
            sig = tuple(sorted((s["sid"], round(s["value_mm"] or 0, 0)) for s in srcs))
            sigs[sig].append((d, srcs))

        for gi, (sig, rows) in enumerate(sorted(sigs.items(), key=lambda kv: str(kv[0]))):
            d0, srcs = rows[0]
            gid = f"{cid}|g{gi}"
            ow_v = next((s["value_mm"] for s in srcs if s["sid"] == "ow"), None)
            clear_v = next((s["value_mm"] for s in srcs if s.get("note") in ("CLEAR", "CLEAR_ACTIVE")), None)
            L.group(gid, {
                "family": "door", "quantity": "door_clear_width", "cluster": cid,
                "elements": [r[0].id() for r in rows], "names": [r[0].Name for r in rows][:3],
                "multiplicity": len(rows), "category_vars": cat_vars, "requirement_key": "door_clear_width",
                "value_scope": "cluster", "sources": cat_srcs + srcs,
                "naive": {"value_mm": ow_v, "label": "IfcDoor.OverallWidth", "category": None},
                "complete": {"value_mm": clear_v, "label": "explicit clear width", "needs_category": False},
            })


# ============================================================================= STAIR FLIGHTS
def _stair_num(pv_lookup, names):
    for n in names:
        pv = pv_lookup.get(n)
        if pv is not None and isinstance(pv.raw, (int, float)) and not isinstance(pv.raw, bool) and pv.raw > 1:
            return int(round(float(pv.raw))), pv
    return None, None


def extract_stairs(f, L: Ledger, scale_m: float):
    metric = L.d["metric"]
    proj = L.d["project"]
    for fl in f.by_type("IfcStairFlight"):
        props = prop_lookup(typed_props(fl, scale_m))
        parent = ue.get_aggregate(fl)
        pprops = prop_lookup(typed_props(parent, scale_m)) if parent is not None and parent.is_a("IfcStair") else {}
        name = fl.Name or ""
        tname = (ue.get_type(fl).Name if ue.get_type(fl) is not None else "") or ""
        limits = parse_stair_type_limits(name) or parse_stair_type_limits(tname) or (
            parse_stair_type_limits(parent.Name) if parent is not None else None)
        ext = shape_extent_mm(fl, world=True)
        dz = float(ext[1][2] - ext[0][2]) if ext is not None else None
        # riser count by evidence level
        n_attr = getattr(fl, "NumberOfRiser", None) if fl.is_a() == "IfcStairFlight" else None
        n_std, _ = _stair_num(props, ["Pset_StairFlightCommon.NumberOfRiser"])
        n_full, _ = _stair_num(props, [k for k in props if re.search(r"(actual number of risers|anzahl steigungen)",
                                                                      k, re.I)])
        for qty, attr_name, pset_names, vendor_re, lim_idx, lim_kind in (
                ("stair_riser", "RiserHeight", ["Pset_StairFlightCommon.RiserHeight"],
                 r"(actual riser height|tatsächliche steigung|tatsaechliche steigung)", 0, "ub"),
                ("stair_tread", "TreadLength", ["Pset_StairFlightCommon.TreadLength",
                                                "Pset_StairFlightCommon.TreadLengthAtOffset"],
                 r"(actual tread depth|tatsächliche auftrittsbreite|tatsaechliche auftrittsbreite)", 1, "lb")):
            cid = L.cluster(f"{proj}|{qty}|{fl.id()}", "stair", name)
            srcs = []
            av = getattr(fl, attr_name, None) if hasattr(fl, attr_name) else None
            if av:
                v = float(av) * scale_m * 1000.0
                modes = {"ok": v, **_unit_modes(float(av), scale_m, metric)}
                srcs.append(num_source("attr", f"IfcStairFlight.{attr_name}", "min", [],
                                       {"": {m: _interval(x - PROP_TOL, x + PROP_TOL) for m, x in modes.items()}},
                                       raw=float(av), value_mm=v, suspect=_is_suspect(v, metric)))
            for pn in pset_names:
                pv = props.get(pn)
                if pv is not None and pv.value_mm:
                    v = pv.value_mm
                    modes = {"ok": v, **_unit_modes(float(pv.raw), scale_m, metric)}
                    lvl = _level_of(pv)
                    srcs.append(num_source(f"p:{pn}:{pv.scope}", pn + (" (type)" if pv.scope == "type" else ""), lvl,
                                           [], {"": {m: _interval(x - PROP_TOL, x + PROP_TOL)
                                                     for m, x in modes.items()}},
                                           raw=pv.raw, value_mm=v, suspect=_is_suspect(v, metric)))
            # type-level values that differ from instance values (fantasy model) are kept as separate sources
            for pv in typed_props(fl, scale_m):
                if pv.scope == "type" and pv.label in pset_names and pv.value_mm:
                    inst = props.get(pv.label)
                    if inst is not None and inst.scope == "inst" and abs(inst.value_mm - pv.value_mm) > 1:
                        v = pv.value_mm
                        srcs.append(num_source(f"t:{pv.label}", pv.label + " (type)", _level_of(pv), [],
                                               {"": {"ok": _interval(v - PROP_TOL, v + PROP_TOL),
                                                     **{m: _interval(x - PROP_TOL, x + PROP_TOL) for m, x in
                                                        _unit_modes(float(pv.raw), scale_m, metric).items()}}},
                                               raw=pv.raw, value_mm=v, suspect=_is_suspect(v, metric)))
            for lab, pv in sorted(props.items()):
                if pv.value_mm and re.search(vendor_re, lab, re.I):
                    v = pv.value_mm
                    srcs.append(num_source(f"p:{lab}", lab, _level_of(pv), [],
                                           {"": {"ok": _interval(v - PROP_TOL, v + PROP_TOL)}},
                                           raw=pv.raw, value_mm=v, suspect=_is_suspect(v, metric)))
            # parent-stair Pset values
            ppn = "Pset_StairCommon." + attr_name
            pv = pprops.get(ppn)
            if pv is not None and pv.value_mm:
                v = pv.value_mm
                modes = {"ok": v, **_unit_modes(float(pv.raw), scale_m, metric)}
                srcs.append(num_source("stair", ppn + " (stair)", _level_of(pv), [],
                                       {"": {m: _interval(x - PROP_TOL, x + PROP_TOL) for m, x in modes.items()}},
                                       raw=pv.raw, value_mm=v, suspect=_is_suspect(v, metric)))
            # design limits encoded in names and stair calculation rules state design intent: authoring tools warn
            # but do not enforce them, so they are recorded but non-binding (weight 0: overruling them costs nothing)
            if limits is not None:
                lv = limits[lim_idx]
                iv = _interval(-1e9, lv + PROP_TOL) if lim_kind == "ub" else _interval(lv - PROP_TOL, 1e9)
                srcs.append(num_source("name_lim", f"Type-name design limit ({'max riser' if lim_kind == 'ub' else 'min tread'})",
                                       "min", [], {"": {"ok": iv}}, raw=name, value_mm=lv, note="INTENT",
                                       weight=C.WEIGHT_INTENT))
            # stair calculation rules (vendor) on parent stair
            for lab, pv in sorted(pprops.items()):
                if pv.value_mm and ((qty == "stair_riser" and re.search(r"(maximum riser height|maximale stufenh)", lab, re.I))
                                    or (qty == "stair_tread" and re.search(r"(minimum tread depth|mindestauftritt)", lab, re.I))):
                    lv = pv.value_mm
                    iv = _interval(-1e9, lv + PROP_TOL) if qty == "stair_riser" else _interval(lv - PROP_TOL, 1e9)
                    srcs.append(num_source(f"rule:{lab}", lab + " (stair rule)", "full", [], {"": {"ok": iv}},
                                           raw=pv.raw, value_mm=lv, note="INTENT", weight=C.WEIGHT_INTENT))
            # geometry: riser bounded by flight rise and riser count, r in [(dz-360)/N, dz/(N-2)]
            if qty == "stair_riser" and dz is not None:
                for lvl, n in (("min", int(n_attr) if n_attr else None), ("std", n_std), ("full", n_full)):
                    if n and n > 3:
                        srcs.append(num_source(f"geom:{lvl}", f"Body rise / riser count (N={n}, {lvl})", lvl, [],
                                               {"": {"ok": _interval(max(0.0, (dz - STAIR_GEOM_SLACK) / n),
                                                                 dz / (n - 2) * (1 + (STAIR_GEOM_SLACK / 360.0 - 1)))}},
                                               raw=dz, value_mm=None, note=f"N={n}", weight=C.WEIGHT_GEOMETRY))
                        break
            if not srcs:
                continue
            naive_v = None
            if av:
                naive_v = float(av) * scale_m * 1000.0
            elif props.get(pset_names[0]) is not None:
                naive_v = props[pset_names[0]].value_mm
            comp_v = props[pset_names[0]].value_mm if props.get(pset_names[0]) is not None else None
            L.group(f"{cid}|g0", {
                "family": "stair", "quantity": qty, "cluster": cid, "elements": [fl.id()], "names": [name],
                "multiplicity": 1, "category_vars": [], "requirement_key": qty, "value_scope": "group",
                "sources": srcs,
                "naive": {"value_mm": naive_v, "label": f"IfcStairFlight.{attr_name} or Pset", "category": None},
                "complete": {"value_mm": comp_v, "label": pset_names[0], "needs_category": False},
                "geom_dz_mm": dz,
            })


# ============================================================================= RAILINGS
RAIL_H_RE = re.compile(r"(railing height|geländerhöhe|gelaenderhoehe|top rail\.height|\.height$|\.höhe$|"
                       r"höhe \(z größe\)|hoehe \(z groesse\))", re.I)


def _function_tokens(type_part: str):
    t = norm_text(type_part)
    g = any(tok in t for tok in C.GUARD_TOKENS)
    h = any(tok in t for tok in C.HANDRAIL_TOKENS)
    if g:
        return ["GUARD"]
    if h:
        return ["HANDRAIL"]
    return None


def extract_railings(f, L: Ledger, scale_m: float):
    metric = L.d["metric"]
    proj = L.d["project"]
    by_type = defaultdict(list)
    for r in f.by_type("IfcRailing"):
        t = ue.get_type(r)
        nm = r.Name or ""
        key = t.Name if (t is not None and t.Name) else re.sub(r":\d+$", "", nm)
        by_type[key].append(r)
    for ti, (tkey, members) in enumerate(sorted(by_type.items())):
        cid = L.cluster(f"{proj}|rail|{ti}", "railing", tkey)
        fn_var = L.var(f"{cid}|fn", ["GUARD", "HANDRAIL"], "cluster", "fn", cid, "railing function (guard/handrail)")
        type_part = tkey.split(":", 1)[1] if ":" in tkey else tkey
        cat_srcs = []
        ftok = _function_tokens(type_part)
        if ftok:
            cat_srcs.append(cat_source("nm_fn", "Type-name function tokens", "min", fn_var, ftok, raw=type_part))
        pre = getattr(members[0], "PredefinedType", None)
        if pre in ("HANDRAIL",):
            cat_srcs.append(cat_source("pre", "IfcRailing.PredefinedType", "min", fn_var, ["HANDRAIL"], raw=pre,
                                       weight=C.WEIGHT_SCHEMA_TYPE))
        elif pre in ("GUARDRAIL", "BALUSTRADE"):
            cat_srcs.append(cat_source("pre", "IfcRailing.PredefinedType", "min", fn_var, ["GUARD"], raw=pre,
                                       weight=C.WEIGHT_SCHEMA_TYPE))
        nominal = parse_single_mm(type_part)
        sigs = defaultdict(list)
        for r in members:
            props = prop_lookup(typed_props(r, scale_m))
            srcs = []
            if nominal and 300 < nominal < 2000:
                srcs.append(num_source("nm", "Type-name nominal height", "min", [],
                                       {"": {"ok": _interval(nominal - 10, nominal + 10)}}, raw=type_part,
                                       value_mm=nominal))
            for lab, pv in sorted(props.items()):
                if not RAIL_H_RE.search(lab):
                    continue
                if re.search(r"(landing|adjust|anpassung|zu geschoss|projekt-nullpunkt|höhenangabe|unterschied)", lab, re.I):
                    continue
                v, unitless = _len_mm(pv, scale_m)
                if v is None:
                    continue
                modes = {"ok": v, **_unit_modes(float(pv.raw), scale_m, metric)}
                srcs.append(num_source(f"p:{lab}", lab, _level_of(pv), [],
                                       {"": {m: _interval(x - HEIGHT_TOL, x + HEIGHT_TOL) for m, x in modes.items()}},
                                       raw=pv.raw, value_mm=v, suspect=_is_suspect(v, metric),
                                       note=("unitless IfcReal" if unitless else "")))
            ext = shape_extent_mm(r, world=True)
            dz = float(ext[1][2] - ext[0][2]) if ext is not None else None
            if dz is not None and 300 < dz < 1600:
                srcs.append(num_source("geom", "Body height extent (level railing)", "min", [],
                                       {"": {"ok": _interval(dz - RAIL_GEOM_BELOW, dz + RAIL_GEOM_ABOVE)}}, raw=dz, value_mm=dz, note="UB",
                                       weight=C.WEIGHT_GEOMETRY))
            sig = tuple(sorted((s["sid"], round(s["value_mm"] or 0, 0)) for s in srcs))
            sigs[sig].append((r, srcs, props))
        for gi, (sig, rows) in enumerate(sorted(sigs.items(), key=lambda kv: str(kv[0]))):
            r0, srcs, props = rows[0]
            pset_h = props.get("Pset_RailingCommon.Height")
            pset_h_mm = _len_mm(pset_h, scale_m)[0] if pset_h is not None else None
            naive_cat = "HANDRAIL" if pre == "HANDRAIL" else "GUARD"
            L.group(f"{cid}|g{gi}", {
                "family": "railing", "quantity": "railing_height", "cluster": cid,
                "elements": [x[0].id() for x in rows], "names": [x[0].Name for x in rows][:3],
                "multiplicity": len(rows), "category_vars": [fn_var], "requirement_key": "railing_height",
                "value_scope": "cluster", "sources": cat_srcs + srcs,
                "naive": {"value_mm": pset_h_mm, "label": "Pset_RailingCommon.Height",
                          "category": [naive_cat]},
                "complete": {"value_mm": pset_h_mm, "label": "Pset_RailingCommon.Height",
                             "needs_category": pre not in ("HANDRAIL", "GUARDRAIL", "BALUSTRADE"),
                             "category": (["HANDRAIL"] if pre == "HANDRAIL" else
                                          (["GUARD"] if pre in ("GUARDRAIL", "BALUSTRADE") else None))},
            })


# ============================================================================= SPACES (ceiling height)
CLEAR_H_RE = re.compile(r"(finishceilingheight|clearheight)", re.I)
GROSS_H_RE = re.compile(r"(^qto_spacebasequantities\.height$|^basequantities\.height$)", re.I)
# Room height parameters of authoring tools: Revit "Unbounded Height" (German UI: "Lichte Höhe") and ArchiCAD
# "Raumhöhe" give the room's computational upper limit, which may or may not coincide with the finished ceiling.
AMBIG_H_RE = re.compile(r"(unbounded height|lichte höhe|lichte hoehe|raumhöhe|raumhoehe)", re.I)


def _space_category(text: str):
    t = " " + norm_text(text) + " "
    if any(tok in t for tok in C.SPACE_NONOCC):
        return ["NONOCC"]
    if any(tok in t for tok in C.SPACE_SERVICE):
        return ["SERVICE"]
    if any(tok in t for tok in C.SPACE_EQUIP):
        return ["OCCUPIABLE", "NONOCC"]
    if any(tok in t for tok in C.SPACE_OCC):
        return ["OCCUPIABLE"]
    return None


def extract_spaces(f, L: Ledger, scale_m: float):
    metric = L.d["metric"]
    proj = L.d["project"]
    cid = L.cluster(f"{proj}|space", "space", "all spaces")
    sem_ub = L.var(f"{cid}|sem|RoomHeight", ["CLEAR", "GROSS"], "cluster", "sem", cid,
                   "meaning of the room height parameter (finished ceiling vs computational upper limit)")
    sem_body = L.var(f"{cid}|sem|Body", ["CLEAR", "GROSS"], "cluster", "sem", cid,
                     "meaning of space body height (finished ceiling vs upper limit)")
    # ceiling coverings (world extents)
    covs = []
    for c in f.by_type("IfcCovering"):
        if getattr(c, "PredefinedType", None) != "CEILING":
            continue
        ext = shape_extent_mm(c, world=True)
        if ext is not None:
            covs.append(ext)

    for sp in f.by_type("IfcSpace"):
        props = prop_lookup(typed_props(sp, scale_m))
        label_txt = " ".join(x for x in [sp.LongName or "", sp.Name or ""] if x)
        gid = f"{cid}|{sp.id()}"
        cat_var = L.var(f"{gid}|cat", ["OCCUPIABLE", "SERVICE", "NONOCC"], "group", "cat", cid,
                        "space category (applicability)", group=gid)
        srcs = []
        cat = _space_category(label_txt)
        if cat:
            srcs.append(cat_source("nm_cat", "Space name tokens", "min", cat_var, cat, raw=label_txt))
        for lab, pv in sorted(props.items()):
            if not re.search(r"(category description|raumkategorie|omniclass table 13 category)", lab, re.I):
                continue
            c2 = _space_category(str(pv.raw))
            if c2:
                srcs.append(cat_source(f"p:{lab}", lab, _level_of(pv), cat_var, c2, raw=pv.raw))
        for lab, pv in sorted(props.items()):
            if pv.value_mm is None:
                continue
            ll = lab.lower()
            if "höhe zu geschoss" in ll or "höhenangabe" in ll or "höhenkote" in ll or "für berechnung" in ll:
                continue
            v = pv.value_mm
            modes = {"ok": v, **_unit_modes(float(pv.raw), scale_m, metric)}
            if CLEAR_H_RE.search(lab.split(".", 1)[1] if "." in lab else lab):
                srcs.append(num_source(f"p:{lab}", lab, _level_of(pv), [],
                                       {"": {m: _interval(x - SPACE_TOL, x + SPACE_TOL) for m, x in modes.items()}},
                                       raw=pv.raw, value_mm=v, suspect=_is_suspect(v, metric), note="CLEAR"))
            elif GROSS_H_RE.search(lab):
                srcs.append(num_source(f"p:{lab}", lab, _level_of(pv), [],
                                       {"": {m: _interval(0.0, x + SPACE_TOL) for m, x in modes.items()}},
                                       raw=pv.raw, value_mm=v, suspect=_is_suspect(v, metric), note="GROSS"))
            elif AMBIG_H_RE.search(lab):
                srcs.append(num_source(f"p:{lab}", lab, _level_of(pv), [sem_ub],
                                       {"CLEAR": {m: _interval(x - SPACE_TOL, x + SPACE_TOL) for m, x in modes.items()},
                                        "GROSS": {m: _interval(0.0, x + SPACE_TOL) for m, x in modes.items()}},
                                       raw=pv.raw, value_mm=v, note="AMBIG"))
        ext = shape_extent_mm(sp, world=True)
        if ext is not None:
            (x0, y0, z0), (x1, y1, z1) = ext
            dz = float(z1 - z0)
            if 1500 < dz < 15000:
                srcs.append(num_source("geom", "Space body height", "min", [sem_body],
                                       {"CLEAR": {"ok": _interval(dz - 20, dz + 20)},
                                        "GROSS": {"ok": _interval(0.0, dz + 20)}}, raw=dz, value_mm=dz,
                                       weight=C.WEIGHT_GEOMETRY))
            # lowest ceiling covering above the space footprint
            area = max((x1 - x0) * (y1 - y0), 1.0)
            best = None
            for (cx0, cy0, cz0), (cx1, cy1, cz1) in covs:
                ox = max(0.0, min(x1, cx1) - max(x0, cx0))
                oy = max(0.0, min(y1, cy1) - max(y0, cy0))
                if ox * oy < 0.25 * area:
                    continue
                if not (z0 + 1500 < cz0 <= z1 + 200):
                    continue
                h = float(cz0 - z0)
                best = h if best is None else min(best, h)
            if best is not None:
                srcs.append(num_source("ceil", "Ceiling covering soffit above floor (geometry)", "min", [],
                                       {"": {"ok": _interval(best - CEIL_GEOM_TOL, best + CEIL_GEOM_TOL)}}, raw=best, value_mm=best,
                                       note="CLEAR", weight=C.WEIGHT_GEOMETRY))
        if not any(s["kind"] == "num" for s in srcs):
            pass  # no height evidence at all: retained (domain only)
        naive_v, naive_lab = None, None
        for pat in ("finishceilingheight", "clearheight", "lichte höhe", "unbounded height", "qto_spacebasequantities.height",
                    "basequantities.height"):
            for lab, pv in props.items():
                if pv.value_mm and pat in lab.lower():
                    naive_v, naive_lab = pv.value_mm, lab
                    break
            if naive_v is not None:
                break
        comp_v = None
        for lab, pv in props.items():
            if pv.value_mm and pv.standard and re.search(r"(finishceilingheight|clearheight)", lab, re.I):
                comp_v = pv.value_mm
        L.group(gid, {
            "family": "space", "quantity": "ceiling_height", "cluster": cid, "elements": [sp.id()],
            "names": [label_txt], "multiplicity": 1, "category_vars": [cat_var],
            "requirement_key": "ceiling_height", "value_scope": "group", "sources": srcs,
            "naive": {"value_mm": naive_v, "label": naive_lab, "category": cat if cat else ["OCCUPIABLE"]},
            "complete": {"value_mm": comp_v, "label": "Qto FinishCeilingHeight/ClearHeight", "needs_category": True,
                         "category": None},
        })


# ============================================================================= driver
def build_ledger(ifc_path: Path, project: str) -> dict:
    f = open_model(str(ifc_path))
    scale = length_scale_m(f)
    L = Ledger(project, f.schema, C.OCCUPANCY.get(project, "commercial"), scale)
    extract_doors(f, L, scale)
    extract_stairs(f, L, scale)
    extract_railings(f, L, scale)
    extract_spaces(f, L, scale)
    return L.d


def main(argv):
    root = Path(argv[1])
    out = Path(argv[2])
    if len(argv) > 3:
        apply_widening(float(argv[3]))
        print("interpretation intervals widened by", argv[3], "DOOR_DELTA", C.DOOR_DELTA)
    out.mkdir(parents=True, exist_ok=True)
    for pd in sorted((root / "projects").iterdir()):
        ifc = pd / "arc.ifc"
        if not ifc.exists():
            continue
        led = build_ledger(ifc, pd.name)
        (out / f"ledger_{pd.name}.json").write_text(json.dumps(led, indent=1, ensure_ascii=False, default=str),
                                                    encoding="utf-8")
        fam = defaultdict(int)
        for g in led["groups"].values():
            fam[g["family"]] += g["multiplicity"]
        print(pd.name, dict(fam), "groups", len(led["groups"]), "vars", len(led["vars"]), flush=True)


if __name__ == "__main__":
    main(sys.argv)
