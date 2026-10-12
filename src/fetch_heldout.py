"""Download the pre-registered held-out candidates from IFC-Bench v2 (Hugging Face, sylvainHellin/ifc-bench).

Usage: python -E -P fetch_heldout.py <dest_root> <manifest.json>
Each project gets its own directory <dest_root>/projects/<project>/ with arc.ifc, license.txt and model_card.md.
Files are written unmodified; the architectural file is saved as arc.ifc and its original name is recorded.
"""
import hashlib
import json
import sys
import time
import urllib.request
from pathlib import Path

BASE = "https://huggingface.co/datasets/sylvainHellin/ifc-bench/resolve/main/projects"
# project -> architectural file (rule 1 of PREREGISTRATION.md section 4); None = no architectural model
ARC = {
    "ettenheim_gis": None,
    "fantasy_hotel_1": "arc.ifc",
    "fantasy_hotel_2": "arc.ifc",
    "fantasy_office_building_2": "arc.ifc",
    "fantasy_office_building_3": "arc.ifc",
    "fantasy_residential_building_1": "arc.ifc",
    "hitos": "arc.ifc",
    "molio": "arc.ifc",
    "samuel_macalister_sample_house": "arc.ifc",
    "sixty5": "arc.ifc",
    "west_riverside_hospital": "arc_ifc4.ifc",
}


def fetch(url: str, dest: Path):
    tmp = dest.with_suffix(dest.suffix + ".part")
    h = hashlib.sha256()
    n = 0
    req = urllib.request.Request(url, headers={"User-Agent": "R10-study/1.0"})
    with urllib.request.urlopen(req, timeout=120) as r, tmp.open("wb") as fh:
        while True:
            chunk = r.read(1 << 20)
            if not chunk:
                break
            fh.write(chunk)
            h.update(chunk)
            n += len(chunk)
    tmp.replace(dest)
    return n, h.hexdigest()


def main():
    root, manifest = Path(sys.argv[1]), Path(sys.argv[2])
    rows = []
    for proj, arc in ARC.items():
        d = root / "projects" / proj
        d.mkdir(parents=True, exist_ok=True)
        files = [("model_card.md", "model_card.md"), ("license.txt", "license.txt")]
        if arc:
            files.append((arc, "arc.ifc"))
        for remote, local in files:
            dest = d / local
            t0 = time.time()
            n, sha = fetch(f"{BASE}/{proj}/{remote}?download=true", dest)
            rows.append({"project": proj, "remote_file": remote, "local_file": str(dest.relative_to(root)),
                         "bytes": n, "sha256": sha, "url": f"{BASE}/{proj}/{remote}",
                         "retrieved_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})
            print(f"{proj}/{remote} -> {local}: {n:,} bytes in {time.time() - t0:.0f}s", flush=True)
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(json.dumps({"dataset": "sylvainHellin/ifc-bench (v2)", "files": rows}, indent=1),
                        encoding="utf-8")
    print("manifest:", manifest)


if __name__ == "__main__":
    main()
