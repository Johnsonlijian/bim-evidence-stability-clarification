"""Declared knowledge used by the checker: rulebooks, interpretation catalogue, dictionaries, costs.

Everything in this module is a *declared, citable assumption*. Numerical requirements are taken from
public model codes (US: IBC 2021, IRC 2021, 2010 ADA Standards; DE variant for doors: DIN 18040-1).
Interpretation intervals are engineering allowances documented in the manuscript (Table 3) and
checked for coverage against models that carry several width semantics at once.
All lengths in millimetres.
"""
from __future__ import annotations

# ------------------------------------------------------------------ rulebooks
# requirement spec: {"min": x} / {"max": x} / {"min": a, "max": b}; None = not applicable
RULEBOOKS = {
    "US": {
        # IBC 2021 1010.1.1 (32 in = 813 mm clear opening width); 2010 ADA Standards 404.2.3 (815 mm)
        "door_clear_width": {"commercial": {"min": 813.0}, "residential": {"min": 813.0}},
        # IBC 2021 1011.5.2: riser 4-7 in (102-178 mm), tread >= 11 in (279 mm);
        # IRC 2021 R311.7.5.1/.2: riser <= 7-3/4 in (196 mm), tread >= 10 in (254 mm)
        "stair_riser": {"commercial": {"min": 102.0, "max": 178.0}, "residential": {"max": 196.0}},
        "stair_tread": {"commercial": {"min": 279.0}, "residential": {"min": 254.0}},
        # IBC 1015.3 guards >= 42 in (1067 mm); IRC R312.1.2 guards >= 36 in (914 mm);
        # IBC 1014.2 / IRC R311.7.8.1 handrails 34-38 in (864-965 mm)
        "railing_height": {
            "commercial": {"GUARD": {"min": 1067.0}, "HANDRAIL": {"min": 864.0, "max": 965.0}},
            "residential": {"GUARD": {"min": 914.0}, "HANDRAIL": {"min": 864.0, "max": 965.0}},
        },
        # IBC 1208.2: occupiable/habitable spaces and corridors >= 7 ft 6 in (2286 mm);
        # bathrooms, toilet rooms, kitchens, storage and laundry rooms >= 7 ft (2134 mm).
        # IRC R305.1: habitable space, hallways, bathrooms, toilet rooms, laundry >= 7 ft (2134 mm).
        "ceiling_height": {
            "commercial": {"OCCUPIABLE": {"min": 2286.0}, "SERVICE": {"min": 2134.0}, "NONOCC": None},
            "residential": {"OCCUPIABLE": {"min": 2134.0}, "SERVICE": {"min": 2134.0}, "NONOCC": None},
        },
    },
    # Sensitivity variant: DIN 18040-1 clear passage width >= 90 cm for doors
    "DE_DOOR": {
        "door_clear_width": {"commercial": {"min": 900.0}, "residential": {"min": 900.0}},
    },
}

OCCUPANCY = {
    "4351": "commercial", "ac20": "commercial", "city_house_munich": "residential",
    "dental_clinic": "commercial", "digital_hub": "commercial", "duplex": "residential",
    "fantasy_office_building_1": "commercial", "fzk_house": "residential", "wbdg_office": "commercial",
}

# ------------------------------------------------------------------ quantity domains (plausibility)
DOMAIN = {
    "door_clear_width": (300.0, 3000.0),
    "stair_riser": (50.0, 300.0),
    "stair_tread": (100.0, 450.0),
    "railing_height": (300.0, 2000.0),
    "ceiling_height": (1500.0, 15000.0),
}

# ------------------------------------------------------------------ door width semantics
# Deduction  delta = (value of the width source) - (code clear width), in mm, per semantic class.
#   CLEAR   explicit clear-passage width (tool definitions may or may not deduct the leaf at 90 deg)
#   LEAF    nominal leaf (panel) width: leaf thickness at 90 deg + stop + hinge offset
#   OPENING structural/rough/nominal opening width (IfcDoor.OverallWidth by schema definition)
#   OUTER   outer extent of the door body incl. lining, frame or casing (geometry bounding box)
DOOR_DELTA = {
    "CLEAR": (0.0, 60.0),
    "LEAF": (40.0, 100.0),
    "OPENING": (60.0, 220.0),
    "OUTER": (60.0, 320.0),
}
# Active-leaf share of the overall width for double-leaf doors (equal pairs 0.5, unequal pairs up to 0.75)
DOUBLE_LEAF_SHARE = (0.45, 0.75)

# Door configuration from IfcDoorType/IfcDoorStyle/IfcDoor.OperationType
def door_config_from_operation(op: str | None) -> list[str] | None:
    if not op or op in ("NOTDEFINED", "USERDEFINED"):
        return None
    if op.startswith("SINGLE_SWING") or op in ("DOUBLE_SWING_LEFT", "DOUBLE_SWING_RIGHT"):
        return ["SWING"]
    if op.startswith("DOUBLE_DOOR") and "SLIDING" not in op and "FOLDING" not in op:
        return ["DOUBLE"]
    if "SLIDING" in op:
        return ["SLIDING"]
    return ["OTHER"]  # revolving, rolling-up, folding, swing-fixed ...


DOOR_CONFIGS = ["SWING", "DOUBLE", "SLIDING", "OTHER"]
DOUBLE_TOKENS = ("double", "dbl", "doppel", "2-flg", "zweifl", "pair")
SINGLE_TOKENS = ("single", "sgl", "1-flg", "einfl")

# ------------------------------------------------------------------ unit fault modes
# A length value may have been written in a unit other than the declared project unit
# (e.g. IFC2x3 IfcStairFlight.RiserHeight exported in feet inside metre models).
ALT_UNIT_SCALES_M = {"ft": 0.3048, "in": 0.0254, "mm": 0.001, "m": 1.0}

# Suspected export defaults: imperial round numbers found in metric models (observed recurring values)
SUSPECT_DEFAULTS_MM = (304.8, 1219.2)

# ------------------------------------------------------------------ fault-cost weights (minimum-weight diagnosis)
# Overruling a source costs its weight; ordinary property/attribute/name values weigh 1.
WEIGHT_GEOMETRY = 2.0      # IFC Pset definitions: geometric parameters take precedence over size properties
WEIGHT_SCHEMA_TYPE = 2.0   # schema-level type enumerations (OperationType, PredefinedType)
WEIGHT_INTENT = 0.0        # design intent (stair calculation rules, design limits in type names): recorded, non-binding

# ------------------------------------------------------------------ railing function dictionary
GUARD_TOKENS = ("guard", "bruestung", "balustrade", "umwehrung", "staebe", "baluster", "absturz")
HANDRAIL_TOKENS = ("handrail", "handlauf")

# ------------------------------------------------------------------ space category dictionary
SPACE_NONOCC = ("schacht", "shaft", "luftraum", "open to below", "aufzug", "elevator", "lift ", "chase",
                "plenum", "void", "treppe", "stair", "roof")
SPACE_SERVICE = ("wc", "toilet", "restroom", " rr", "rr ", "bath", "bad", "dusche", "shower", "kitchen", "kueche",
                 "teekueche", "storage", "lager", "abstell", "jan. cl", "janitor", "closet", "laundry", "wasch",
                 "soil", "trash", "muell", "s-3 storage")
SPACE_OCC = ("office", "buero", "meeting", "besprechung", "conference", "seminar", "labor", "lab ", " lab", "waiting",
             "reception", "lounge", "living", "wohnen", "bedroom", "schlaf", "kind", "dining", "essen", "lobby",
             "foyer", "vestibule", "vest/", "entry", "eingang", "corridor", "flur", "hallway", "diele", "workspace",
             "working space", "team rm", "exam", "cafeteria", "veranstaltung", "break rm", "interaction",
             "cubicle", "provider", "classroom", "studio", "nurse", "consult", "dental", "operat", "imaging",
             "recovery", "treatment", "station", "conf", "workroom", "work room", "copy", "file", "noc", "boc",
             "scif", "cmdr", "field surgeon", "sipr", "reenlst", "secure doc", "staff", "opt", "ph tech",
             "check", "records", "pharmacy", "sterili", "x-ray", "xray", "procedure", "specimen")
SPACE_EQUIP = ("mech", "elec", "technik", "tele/comm", "comm. room", "comm room", "server", "it ", "utility",
               "ankleide", "haustechnik", "hausanschluss", "heiz")

# ------------------------------------------------------------------ action costs (relative effort units)
COST = {
    "CLARIFY": 1.0,   # designer answers a closed question (semantics, unit, applicability, function)
    "VALUE": 3.0,     # designer supplies and certifies the code-relevant value (product data / dimension check)
}

# ------------------------------------------------------------------ evidence levels
LEVELS = ("min", "std", "full")
LEVEL_RANK = {"min": 0, "std": 1, "full": 2}
