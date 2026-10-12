"""Bounding-box sizes of IfcRailing elements per name stem (to see whether they are balusters or rail segments).

Usage: python -E -P railing_bbox.py <arc.ifc> [per_stem]
"""
import sys
from collections import defaultdict

import ifcopenshell
import ifcopenshell.geom
import numpy as np

f = ifcopenshell.open(sys.argv[1])
k = int(sys.argv[2]) if len(sys.argv) > 2 else 4
s = ifcopenshell.geom.settings()
s.set("use-world-coords", True)
by = defaultdict(list)
for r in f.by_type("IfcRailing"):
    by[(r.Name or "").split(":")[0]].append(r)
for stem, rs in sorted(by.items(), key=lambda kv: -len(kv[1])):
    sizes = []
    for r in rs[:k]:
        try:
            sh = ifcopenshell.geom.create_shape(s, r)
            v = np.array(sh.geometry.verts).reshape(-1, 3)
            sizes.append(tuple(np.round((v.max(0) - v.min(0)) * 1000).astype(int)))
        except Exception as e:  # noqa: BLE001
            sizes.append(("err", str(e)[:40]))
    print(f"{stem!r}: {len(rs)} elements; bbox (mm, x/y/z) of first {k}: {sizes}; "
          f"ObjectType={rs[0].ObjectType!r} PredefinedType={getattr(rs[0], 'PredefinedType', None)!r} "
          f"Description={rs[0].Description!r}")
