"""Build JSON evidence ledgers for a declared set of IFC models (frozen extraction code in bimev/).

Usage:
  python -E -P run_extract.py --root <dir with projects/<name>/arc.ifc> --out <dir>
                              [--projects a,b,c] [--occupancy occupancy.json] [--widen 0.5]

--occupancy maps project -> 'residential' (IRC) or 'commercial' (IBC); the map is declared before extraction from
the model cards (PREREGISTRATION.md). Projects not in the map keep the catalogue default.
"""
import argparse
import json
import sys
import time
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from bimev import catalog as C  # noqa: E402
from bimev.extract import apply_widening, build_ledger  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--projects", default="")
    ap.add_argument("--occupancy", default="")
    ap.add_argument("--widen", type=float, default=0.0)
    a = ap.parse_args()
    if a.occupancy:
        C.OCCUPANCY.update(json.loads(Path(a.occupancy).read_text(encoding="utf-8")))
    if a.widen > 0:
        apply_widening(a.widen)
        print("interpretation intervals widened by", a.widen, "DOOR_DELTA", C.DOOR_DELTA, flush=True)
    keep = {p for p in a.projects.split(",") if p}
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    for pd in sorted((Path(a.root) / "projects").iterdir()):
        ifc = pd / "arc.ifc"
        if not ifc.exists() or (keep and pd.name not in keep):
            continue
        t0 = time.time()
        led = build_ledger(ifc, pd.name)
        (out / f"ledger_{pd.name}.json").write_text(json.dumps(led, indent=1, ensure_ascii=False, default=str),
                                                    encoding="utf-8")
        fam = defaultdict(int)
        for g in led["groups"].values():
            fam[g["family"]] += g["multiplicity"]
        print(pd.name, led["schema"], led["occupancy"], dict(fam), "groups", len(led["groups"]), "vars",
              len(led["vars"]), f"{time.time() - t0:.1f}s", flush=True)


if __name__ == "__main__":
    main()
