"""IFC access helpers: typed property values with unit handling, geometry extents and name parsing.

All lengths returned by this module are in millimetres (mm) unless stated otherwise.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache

import ifcopenshell
import ifcopenshell.geom
import ifcopenshell.util.element as ue
import ifcopenshell.util.unit as uu
import numpy as np

LENGTH_MEASURES = {"IfcLengthMeasure", "IfcPositiveLengthMeasure", "IfcNonNegativeLengthMeasure"}
AREA_MEASURES = {"IfcAreaMeasure"}
# Property/quantity sets defined by the IFC specification (ISO 16739) are treated as "standard";
# IFC2x3 exporters frequently write the base quantities into an element quantity named "BaseQuantities".
STANDARD_SET_RE = re.compile(r"^(Pset_|Qto_|BaseQuantities$)")


@dataclass
class PropValue:
    scope: str          # "inst" or "type"
    set_name: str
    name: str
    raw: object         # stored value
    measure: str        # IFC measure / quantity entity name
    value_mm: float | None  # converted length in mm when the value is a length, else None
    standard: bool      # belongs to an IFC-standard property/quantity set

    @property
    def label(self) -> str:
        return f"{self.set_name}.{self.name}"


def open_model(path: str) -> ifcopenshell.file:
    return ifcopenshell.open(path)


def length_scale_m(f: ifcopenshell.file) -> float:
    """Metres per model length unit (declared unit context)."""
    return float(uu.calculate_unit_scale(f))


def _iter_property_definitions(ent):
    """Yield (scope, definition) for property sets / element quantities on an instance and its type."""
    for rel in getattr(ent, "IsDefinedBy", None) or []:
        if rel.is_a("IfcRelDefinesByProperties"):
            d = rel.RelatingPropertyDefinition
            if d is not None:
                if isinstance(d, tuple):
                    for dd in d:
                        yield "inst", dd
                else:
                    yield "inst", d
    typ = ue.get_type(ent)
    if typ is not None:
        for d in getattr(typ, "HasPropertySets", None) or []:
            yield "type", d


def typed_props(ent, length_scale: float) -> list[PropValue]:
    """All single-value properties and quantities of an element (instance and type), unit-converted."""
    out: list[PropValue] = []
    for scope, d in _iter_property_definitions(ent):
        set_name = getattr(d, "Name", None) or ""
        standard = bool(STANDARD_SET_RE.match(set_name))
        if d.is_a("IfcPropertySet"):
            for p in d.HasProperties or []:
                if not p.is_a("IfcPropertySingleValue") or p.NominalValue is None:
                    continue
                nv = p.NominalValue
                measure = nv.is_a()
                raw = nv.wrappedValue
                value_mm = None
                if measure in LENGTH_MEASURES and isinstance(raw, (int, float)):
                    value_mm = float(raw) * length_scale * 1000.0
                out.append(PropValue(scope, set_name, p.Name, raw, measure, value_mm, standard))
        elif d.is_a("IfcElementQuantity"):
            for q in d.Quantities or []:
                if q.is_a("IfcQuantityLength"):
                    raw = q.LengthValue
                    out.append(PropValue(scope, set_name, q.Name, raw, "IfcQuantityLength",
                                         float(raw) * length_scale * 1000.0, standard))
                elif q.is_a("IfcQuantityArea"):
                    out.append(PropValue(scope, set_name, q.Name, q.AreaValue, "IfcQuantityArea", None, standard))
                elif q.is_a("IfcQuantityCount"):
                    out.append(PropValue(scope, set_name, q.Name, q.CountValue, "IfcQuantityCount", None, standard))
    return out


def prop_lookup(props: list[PropValue]) -> dict[str, PropValue]:
    """Map 'Set.Name' -> PropValue; instance values take precedence over type values."""
    d: dict[str, PropValue] = {}
    for p in props:
        if p.label not in d or (d[p.label].scope == "type" and p.scope == "inst"):
            d[p.label] = p
    return d


# ---------------------------------------------------------------- geometry
_SETTINGS = {}


def _settings(world: bool):
    key = bool(world)
    if key not in _SETTINGS:
        s = ifcopenshell.geom.settings()
        s.set("use-world-coords", key)
        _SETTINGS[key] = s
    return _SETTINGS[key]


def shape_extent_mm(ent, world: bool = False):
    """Axis-aligned extent of the element body in mm: (min xyz, max xyz) or None if no geometry.

    With world=False the extent is expressed in the element's local placement frame
    (for doors and windows the local X axis runs along the host wall).
    """
    try:
        sh = ifcopenshell.geom.create_shape(_settings(world), ent)
    except Exception:  # noqa: BLE001
        return None
    v = np.asarray(sh.geometry.verts, dtype=float).reshape(-1, 3)
    if v.size == 0 or not np.all(np.isfinite(v)):
        return None
    return v.min(axis=0) * 1000.0, v.max(axis=0) * 1000.0


def storey_of(ent):
    c = ue.get_container(ent)
    guard = 0
    while c is not None and not c.is_a("IfcBuildingStorey") and guard < 10:
        c = ue.get_aggregate(c)
        guard += 1
    return c if (c is not None and c.is_a("IfcBuildingStorey")) else None


# ---------------------------------------------------------------- names
_NUM = r"(\d+(?:[.,]\d+)?)"
_UNIT = r"\s*(mm|cm|m|\"|''|in)?"
DIM_PAIR_RE = re.compile(_NUM + _UNIT + r"\s*[xX×]\s*" + _NUM + _UNIT)
SINGLE_MM_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*(mm|cm)\b", re.I)


def _to_float(tok: str) -> float:
    return float(tok.replace(",", "."))


def _scale_by_suffix(val_tok: str, suffix: str | None, other_suffix: str | None, kind: str) -> list[float]:
    """Return candidate values in mm for a dimension token.

    Explicit suffixes are honoured; otherwise the unit is inferred from magnitude for the declared
    kind ('door_width' or 'door_height'). A suffix 'mm' on a token with three decimals and a single
    leading digit (e.g. '1.220') is read with a thousands separator (1220 mm).
    """
    v = _to_float(val_tok)
    suf = (suffix or other_suffix or "").lower()
    if suf in ('"', "''", "in"):
        return [v * 25.4]
    if suf == "mm":
        if "." in val_tok and len(val_tok.split(".")[1]) == 3 and v < 10:
            return [v * 1000.0]
        return [v]
    if suf == "cm":
        return [v * 10.0]
    if suf == "m":
        return [v * 1000.0]
    # magnitude inference
    if v >= 300:
        return [v]
    if v >= 30:
        return [v * 10.0]
    if 0.3 <= v < 4:
        return [v * 1000.0]
    return []


def parse_dim_pair(text: str | None):
    """Parse 'W x H' nominal dimensions from a type/instance name. Returns (w_mm, h_mm) or None."""
    if not text:
        return None
    m = DIM_PAIR_RE.search(text)
    if not m:
        return None
    w_tok, w_suf, h_tok, h_suf = m.group(1), m.group(2), m.group(3), m.group(4)
    w = _scale_by_suffix(w_tok, w_suf, h_suf, "door_width")
    h = _scale_by_suffix(h_tok, h_suf, w_suf, "door_height")
    if not w or not h:
        return None
    return w[0], h[0]


def parse_single_mm(text: str | None):
    """First explicit metric dimension in a name (e.g. '1100mm Guard Rail'), in mm."""
    if not text:
        return None
    m = SINGLE_MM_RE.search(text)
    if not m:
        return None
    v = _to_float(m.group(1))
    return v * (10.0 if m.group(2).lower() == "cm" else 1.0)


STAIR_LIMIT_RE = re.compile(
    r"(\d+(?:[.,]\d+)?)\s*(mm|\")\s*max\.?\s*riser.*?(\d+(?:[.,]\d+)?)\s*(mm|\")\s*tread", re.I)


def parse_stair_type_limits(text: str | None):
    """Parse design limits encoded in stair type names, e.g. '180mm Max Riser 280mm Tread'.

    Returns (max_riser_mm, min_tread_mm) or None.
    """
    if not text:
        return None
    m = STAIR_LIMIT_RE.search(text)
    if not m:
        return None
    r = _to_float(m.group(1)) * (25.4 if m.group(2) == '"' else 1.0)
    t = _to_float(m.group(3)) * (25.4 if m.group(4) == '"' else 1.0)
    return r, t


@lru_cache(maxsize=None)
def _norm(s: str) -> str:
    return s.lower().replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("ß", "ss")


def norm_text(s: str | None) -> str:
    return _norm(s or "")
